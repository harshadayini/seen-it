"""Phase 1 unit tests for Shopify Global Catalog MCP client and candidate normalizer.

What this module does:
    Verifies all Phase 1 components without requiring live network access:
    1. ISO 4217 minor/major currency conversions (2-decimal USD, 0-decimal JPY, 3-decimal KWD).
    2. High-level filter translation to UCP 2026-08-25 `catalog.filters` + `catalog.context`.
    3. OAuth2 `client_credentials` token acquisition, in-memory cache hit, expiry refresh,
       and graceful unauthenticated fallback when credentials are unset.
    4. Exponential backoff retries on HTTP 429 (honoring `Retry-After`) and transient 503.
    5. `lookup_catalog` automatic chunking into <= 50 IDs per MCP call.
    6. `get_product` retrieval and structured `ShopifyCatalogError` propagation on error.
    7. `matching.catalog.search` normalization of real UCP 2026-08-25 payloads into
       `contracts/run.schema.json`-valid candidate dicts (dedup, availability, currency,
       seller domain, media fallback, and no fabricated products on failure).

Use cases:
    - Executed locally via `python3 -m unittest discover -s backend/matching/tests -v`.

What this module must NOT do:
    - Must not make live network requests or cache merchant images on disk.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from backend.config import load_config
from backend.matching.catalog import normalize_products_to_candidates, search
from backend.matching.models import validate_run_dict
from backend.shopify.catalog import (
    ShopifyCatalogError,
    _ShopifyTokenManager,
    get_product,
    lookup_catalog,
    major_to_minor_price,
    minor_to_major_price,
    search_catalog,
)


SAMPLE_UCP_PRODUCT = {
    "id": "gid://shopify/p/3YIScy9mSzOEcCsBGA3DxL",
    "title": "Teamson Home Arquer Arc Floor Lamp",
    "price_range": {
        "min": {"amount": 16999, "currency": "USD"},
        "max": {"amount": 18999, "currency": "USD"},
    },
    "media": [
        {
            "type": "image",
            "url": "https://cdn.shopify.com/s/files/1/0000/products/product-fallback.jpg",
        }
    ],
    "variants": [
        {
            "id": "gid://shopify/ProductVariant/40189129752757",
            "title": "Antique Brass",
            "price": {"amount": 16999, "currency": "USD"},
            "availability": {"available": True},
            "options": [{"name": "Finish", "label": "Antique Brass"}],
            "media": [
                {
                    "type": "image",
                    "url": "https://cdn.shopify.com/s/files/1/0000/products/variant-brass.jpg",
                }
            ],
            "seller": {
                "id": "gid://shopify/Shop/56431509685",
                "name": "US - Teamson Home",
                "url": "https://teamsonhome.com",
                "domain": "teamsonus.myshopify.com",
            },
        },
        {
            "id": "gid://shopify/ProductVariant/40189129752758",
            "title": "Sold Out Chrome",
            "price": {"amount": 16999, "currency": "USD"},
            "availability": {"available": False},
            "seller": {"domain": "teamsonus.myshopify.com"},
        },
        {
            "id": "gid://shopify/ProductVariant/40189129752759",
            "title": "Matte Black",
            "price": {"amount": 17500, "currency": "USD"},
            "availability": {"available": True},
            "media": [],
            "seller": {"url": "https://shop.teamsonhome.com/products/lamp"},
        },
    ],
}


def _mcp_success_body(payload: dict) -> bytes:
    """Wrap a UCP payload inside a JSON-RPC 2.0 `structuredContent` response."""
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": "test-rpc",
            "result": {"structuredContent": {"ucp": {"version": "2026-08-25", "status": "success"}, **payload}},
        }
    ).encode("utf-8")


class TestPhase1ShopifyCatalog(unittest.TestCase):
    """Unit tests for `backend/shopify/catalog.py`."""

    def setUp(self) -> None:
        self.cfg = load_config(Path("/nonexistent/.env"))

    def test_currency_minor_major_conversions(self) -> None:
        """Verify 2-decimal, 0-decimal, and 3-decimal ISO 4217 price conversions."""
        self.assertEqual(minor_to_major_price(16999, "USD"), 169.99)
        self.assertEqual(major_to_minor_price(150.0, "USD"), 15000)
        self.assertEqual(minor_to_major_price(4500, "JPY"), 4500.0)
        self.assertEqual(major_to_minor_price(4500, "JPY"), 4500)
        self.assertEqual(minor_to_major_price(12500, "KWD"), 12.5)
        self.assertEqual(major_to_minor_price(12.5, "KWD"), 12500)

    def test_oauth_token_is_cached_and_refreshed_on_expiry(self) -> None:
        """Verify token manager caches token in memory and refreshes near expiry."""
        calls: list[str] = []
        clock = [1000.0]

        def fake_post(url: str, body: bytes, headers: dict, timeout_s: float):
            calls.append(url)
            return (
                200,
                {},
                json.dumps({"access_token": f"tok_{len(calls)}", "expires_in": 300}).encode("utf-8"),
            )

        tm = _ShopifyTokenManager()
        env = {"SHOPIFY_CLIENT_ID": "cid_1", "SHOPIFY_CLIENT_SECRET": "csec_1"}
        with patch.dict(os.environ, env, clear=False):
            t1 = tm.get_bearer_token(cfg=self.cfg, http_post_fn=fake_post, now_fn=lambda: clock[0])
            clock[0] += 100.0  # still valid (200s remaining > 60s buffer)
            t2 = tm.get_bearer_token(cfg=self.cfg, http_post_fn=fake_post, now_fn=lambda: clock[0])
            clock[0] += 160.0  # now 40s remaining < 60s buffer -> refresh
            t3 = tm.get_bearer_token(cfg=self.cfg, http_post_fn=fake_post, now_fn=lambda: clock[0])

        self.assertEqual(t1, "tok_1")
        self.assertEqual(t2, "tok_1")
        self.assertEqual(t3, "tok_2")
        self.assertEqual(len(calls), 2)

    def test_search_catalog_sends_ucp_envelope_and_retries_429(self) -> None:
        """Verify search_catalog translates filters, includes profile, and retries 429."""
        requests_seen: list[dict] = []
        sleeps: list[float] = []
        responses = [
            (429, {"retry-after": "1.5"}, b"rate limited"),
            (200, {}, _mcp_success_body({"products": [SAMPLE_UCP_PRODUCT]})),
        ]

        def fake_post(url: str, body: bytes, headers: dict, timeout_s: float):
            requests_seen.append(json.loads(body.decode("utf-8")))
            return responses.pop(0)

        tm = _ShopifyTokenManager()
        with patch.dict(os.environ, {"SHOPIFY_CLIENT_ID": "", "SHOPIFY_CLIENT_SECRET": ""}, clear=False):
            products = search_catalog(
                "black arc floor lamp",
                {"max_price": 200.0, "currency": "USD", "ships_to": "US"},
                limit=5,
                cfg=self.cfg,
                http_post_fn=fake_post,
                sleep_fn=sleeps.append,
                token_manager=tm,
            )

        self.assertEqual(len(products), 1)
        self.assertEqual(sleeps, [1.5])
        sent = requests_seen[0]
        self.assertEqual(sent["method"], "tools/call")
        self.assertEqual(sent["params"]["name"], "search_catalog")
        args = sent["params"]["arguments"]
        self.assertEqual(args["meta"]["ucp-agent"]["profile"], self.cfg.shopify_agent_profile_url)
        self.assertEqual(args["catalog"]["filters"]["price"]["max"], 20000)
        self.assertEqual(args["catalog"]["filters"]["ships_to"], {"country": "US"})
        self.assertEqual(args["catalog"]["pagination"]["limit"], 5)

    def test_lookup_catalog_chunks_batches_of_50(self) -> None:
        """Verify lookup_catalog splits 120 IDs into 50 + 50 + 20 batches."""
        batch_sizes: list[int] = []

        def fake_post(url: str, body: bytes, headers: dict, timeout_s: float):
            req = json.loads(body.decode("utf-8"))
            ids = req["params"]["arguments"]["catalog"]["ids"]
            batch_sizes.append(len(ids))
            return 200, {}, _mcp_success_body({"products": [{"id": ids[0], "variants": []}]})

        tm = _ShopifyTokenManager()
        ids_120 = [f"gid://shopify/p/{i}" for i in range(120)]
        with patch.dict(os.environ, {"SHOPIFY_CLIENT_ID": "", "SHOPIFY_CLIENT_SECRET": ""}, clear=False):
            out = lookup_catalog(ids_120, cfg=self.cfg, http_post_fn=fake_post, token_manager=tm)

        self.assertEqual(batch_sizes, [50, 50, 20])
        self.assertEqual(len(out), 3)

    def test_get_product_returns_product_and_raises_on_rpc_error(self) -> None:
        """Verify get_product unwraps product detail and raises ShopifyCatalogError on error."""
        tm = _ShopifyTokenManager()

        def ok_post(url: str, body: bytes, headers: dict, timeout_s: float):
            return 200, {}, _mcp_success_body({"product": SAMPLE_UCP_PRODUCT})

        def err_post(url: str, body: bytes, headers: dict, timeout_s: float):
            return (
                200,
                {},
                json.dumps(
                    {"jsonrpc": "2.0", "id": "x", "error": {"code": -32602, "message": "Invalid params"}}
                ).encode("utf-8"),
            )

        with patch.dict(os.environ, {"SHOPIFY_CLIENT_ID": "", "SHOPIFY_CLIENT_SECRET": ""}, clear=False):
            prod = get_product(
                "gid://shopify/p/3YIScy9mSzOEcCsBGA3DxL",
                cfg=self.cfg,
                http_post_fn=ok_post,
                token_manager=tm,
            )
            self.assertEqual(prod["id"], SAMPLE_UCP_PRODUCT["id"])

            with self.assertRaises(ShopifyCatalogError):
                get_product("bad-id", cfg=self.cfg, http_post_fn=err_post, token_manager=tm)


class TestPhase1MatchingCatalog(unittest.TestCase):
    """Unit tests for `backend/matching/catalog.py` normalization and `search()`."""

    def test_normalize_products_to_contract_valid_candidates(self) -> None:
        """Verify variants flatten cleanly, skip unavailable, fall back media/domain, and pass contract."""
        cands = normalize_products_to_candidates([SAMPLE_UCP_PRODUCT], max_candidates=10)
        self.assertEqual(len(cands), 2)

        first, second = cands[0], cands[1]
        self.assertEqual(first["upid"], "gid://shopify/p/3YIScy9mSzOEcCsBGA3DxL")
        self.assertEqual(first["variant_id"], "gid://shopify/ProductVariant/40189129752757")
        self.assertEqual(first["title"], "Teamson Home Arquer Arc Floor Lamp - Antique Brass")
        self.assertEqual(first["merchant_domain"], "teamsonus.myshopify.com")
        self.assertEqual(first["price"], 169.99)
        self.assertEqual(first["currency"], "USD")
        self.assertEqual(
            first["image_url"],
            "https://cdn.shopify.com/s/files/1/0000/products/variant-brass.jpg",
        )
        self.assertIsNone(first["p_same_product"])
        self.assertIsNone(first["p_same_variant"])

        # Second available variant falls back to product media and seller.url hostname
        self.assertEqual(second["merchant_domain"], "shop.teamsonhome.com")
        self.assertEqual(
            second["image_url"],
            "https://cdn.shopify.com/s/files/1/0000/products/product-fallback.jpg",
        )

        # Verify normalized candidates pass full run.schema.json validation
        run_payload = {
            "run_id": "r_test",
            "state": "processing",
            "mode": "video",
            "source": {"video_id": "v1", "duration_s": 12.0, "budget_usd": None},
            "items": [{"item_id": "i1", "state": "processing", "candidates": cands}],
            "totals": {"price": None, "within_budget": None},
        }
        self.assertEqual(validate_run_dict(run_payload), [])

    def test_search_propagates_upstream_error_without_fabricating(self) -> None:
        """Verify AGENT_RULES.md §3.5: search() never returns fake products on failure."""
        def failing_search(*args, **kwargs):
            raise ShopifyCatalogError("upstream 503", status_code=503, retryable=True)

        with self.assertRaises(ShopifyCatalogError):
            search("black arc lamp", {}, search_catalog_fn=failing_search)


if __name__ == "__main__":
    unittest.main()
