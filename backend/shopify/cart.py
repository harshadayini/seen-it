"""Merchant Cart MCP client (P3): create_cart / update_cart / continue_url per merchant.

What it does
    Talks JSON-RPC (`tools/call`) to a merchant's Universal Commerce Protocol Cart MCP at
    https://{shop-domain}/api/ucp/mcp and returns the cart id plus the `continue_url` that
    hands the buyer to the merchant's own checkout.

Use cases and boundaries
    - One cart per merchant (cross-merchant carts are not available to us).
    - Cart tools accept anonymous calls, so no bearer token or secret is used here.
      Anonymous traffic has the lowest rate-limit tier, hence the backoff below.
    - Never places an order and never calls Checkout MCP. We stop at `continue_url`.
    - Only the Cart MCP is used. No Admin or Storefront GraphQL, no /global/v2/ REST.

Invariants
    - No fake carts: any failure raises CartError with a clean, structured message.
    - Nothing from the response is cached or written to disk.
    - 429 and transient 5xx responses are retried with exponential backoff and jitter,
      honoring Retry-After when present.
"""
from __future__ import annotations

import json
import logging
import random
import time

import httpx

from backend import config

log = logging.getLogger("seen_it.shopify.cart")

MAX_ATTEMPTS = 4
BASE_BACKOFF_S = 0.5
MAX_BACKOFF_S = 8.0
TIMEOUT_S = 20.0


class CartError(RuntimeError):
    """Raised when a cart call fails. `code` is a short machine-readable reason."""

    def __init__(self, code: str, message: str, merchant_domain: str | None = None):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.merchant_domain = merchant_domain


def mcp_url(merchant_domain: str) -> str:
    """Return the Cart MCP endpoint for a merchant.

    Args:
        merchant_domain: shop domain such as "store.myshopify.com" (scheme and path are stripped).
    Returns:
        https://{shop-domain}/api/ucp/mcp
    """
    domain = merchant_domain.strip().removeprefix("https://").removeprefix("http://").split("/")[0]
    if not domain:
        raise CartError("bad_merchant", "empty merchant domain")
    return f"https://{domain}/api/ucp/mcp"


def _backoff(attempt: int, retry_after: str | None) -> float:
    """Seconds to wait before the next attempt (Retry-After wins, else exponential + jitter)."""
    if retry_after:
        try:
            return min(float(retry_after), 60.0)
        except ValueError:
            pass
    return min(MAX_BACKOFF_S, BASE_BACKOFF_S * (2**attempt)) * (0.5 + random.random())


def _call_tool(merchant_domain: str, name: str, arguments: dict, client: httpx.Client | None = None) -> dict:
    """Call one Cart MCP tool and return its `structuredContent.cart` dict.

    Args:
        merchant_domain: target merchant.
        name: tool name ("create_cart" or "update_cart").
        arguments: tool arguments; the agent profile `meta` is added here.
        client: optional httpx client (tests inject a mock transport).
    Returns:
        The cart object from the response.
    Raises:
        CartError on transport failure, JSON-RPC error, or an unrecoverable business message.
    Side effects:
        One HTTP POST per attempt; logs name and domain only (no request bodies).
    """
    url = mcp_url(merchant_domain)
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": name,
            "arguments": {"meta": {"ucp-agent": {"profile": config.SHOPIFY_AGENT_PROFILE_URL}}, **arguments},
        },
    }
    owns_client = client is None
    client = client or httpx.Client(timeout=TIMEOUT_S)
    try:
        for attempt in range(MAX_ATTEMPTS):
            log.info("cart_mcp_call tool=%s merchant=%s attempt=%d", name, merchant_domain, attempt + 1)
            try:
                resp = client.post(url, json=body, headers={"Content-Type": "application/json"})
            except httpx.HTTPError as exc:
                if attempt + 1 < MAX_ATTEMPTS:
                    time.sleep(_backoff(attempt, None))
                    continue
                raise CartError("network", f"could not reach {merchant_domain}: {exc.__class__.__name__}", merchant_domain)
            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt + 1 < MAX_ATTEMPTS:
                    time.sleep(_backoff(attempt, resp.headers.get("Retry-After")))
                    continue
                raise CartError("rate_limited" if resp.status_code == 429 else "upstream", f"HTTP {resp.status_code}", merchant_domain)
            if resp.status_code >= 400:
                raise CartError("http_error", f"HTTP {resp.status_code}", merchant_domain)
            return _parse_cart(resp.json(), merchant_domain)
    finally:
        if owns_client:
            client.close()
    raise CartError("unknown", "no response", merchant_domain)  # pragma: no cover


def _parse_cart(payload: dict, merchant_domain: str) -> dict:
    """Extract the cart from a JSON-RPC response or raise CartError.

    Args:
        payload: decoded JSON-RPC response.
        merchant_domain: used only for error context.
    Returns:
        The cart dict (`result.structuredContent.cart`).
    """
    if "error" in payload:
        err = payload["error"] or {}
        raise CartError("rpc_error", str(err.get("message", "unknown error")), merchant_domain)
    result = payload.get("result") or {}
    sc = result.get("structuredContent") or {}
    # Live merchants return the cart object directly in structuredContent; the docs show it
    # nested under "cart". Accept both, then fall back to the JSON text in content[0].
    cart = sc.get("cart") or (sc if sc.get("id") else None)
    if not cart:
        try:
            text = json.loads((result.get("content") or [{}])[0].get("text") or "{}")
            cart = text.get("cart") or (text if text.get("id") else None)
        except (ValueError, AttributeError, IndexError):
            cart = None
    if not cart:
        raise CartError("no_cart", "response contained no cart", merchant_domain)
    for msg in cart.get("messages") or []:
        if msg.get("type") == "error" and msg.get("severity") in (None, "unrecoverable"):
            raise CartError(str(msg.get("code", "cart_error")), str(msg.get("content", "")), merchant_domain)
    return cart


def _summarize(cart: dict) -> dict:
    """Reduce a cart to the fields our API returns: id, continue_url, and any warnings."""
    warnings = [m.get("content", "") for m in cart.get("messages") or [] if m.get("type") == "warning"]
    out = {"cart_id": cart.get("id"), "continue_url": cart.get("continue_url")}
    if warnings:
        out["warnings"] = warnings
    return out


def create_cart(merchant_domain: str, variant_id: str, qty: int = 1, client: httpx.Client | None = None) -> dict:
    """Create a cart at one merchant with a single variant.

    Args:
        merchant_domain: shop domain (e.g. "lumen-and-oak.myshopify.com").
        variant_id: Shopify variant GID ("gid://shopify/ProductVariant/...").
        qty: quantity, at least 1.
        client: optional httpx client for tests.
    Returns:
        {"cart_id": str, "continue_url": str} (plus "warnings" if the merchant adjusted anything).
    Raises:
        CartError on any failure. Never returns a fabricated cart.
    """
    if qty < 1:
        raise CartError("bad_quantity", "qty must be at least 1", merchant_domain)
    cart = _call_tool(
        merchant_domain,
        "create_cart",
        {"cart": {"line_items": [{"quantity": qty, "item": {"id": variant_id}}]}},
        client,
    )
    return _summarize(cart)


def update_cart(
    merchant_domain: str, cart_id: str, line_items: list[dict], client: httpx.Client | None = None
) -> dict:
    """Replace a cart's line items (add, change quantity, or remove).

    Args:
        merchant_domain: shop domain the cart belongs to.
        cart_id: id returned by create_cart.
        line_items: [{"quantity": int, "item": {"id": variant_gid}}, ...]
        client: optional httpx client for tests.
    Returns:
        {"cart_id": str, "continue_url": str}.
    Raises:
        CartError on failure.
    """
    cart = _call_tool(merchant_domain, "update_cart", {"id": cart_id, "cart": {"line_items": line_items}}, client)
    return _summarize(cart)


def get_continue_url(cart: dict) -> str | None:
    """Return the checkout handoff URL from a create_cart/update_cart result, or None."""
    return cart.get("continue_url")
