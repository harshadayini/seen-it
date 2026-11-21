"""Shopify Global Catalog MCP client (Agentic Commerce / UCP stack only).

What this module does:
    Provides a typed, retry-hardened Python wrapper around Shopify's Global
    Catalog MCP endpoint (`https://catalog.shopify.com/api/ucp/mcp`) supporting:
    - OAuth2 `client_credentials` bearer token exchange and in-memory caching
      (`POST https://api.shopify.com/auth/access_token`) with proactive refresh.
    - JSON-RPC 2.0 `tools/call` transport with mandatory `meta.ucp-agent.profile`.
    - Exponential backoff with full jitter on HTTP 429 (honoring `Retry-After`)
      and transient 5xx / network errors.
    - The three UCP Catalog tools: `search_catalog`, `lookup_catalog` (chunked
      in batches of <= 50 IDs), and `get_product`.
    - ISO 4217 minor-unit <-> major-unit currency conversion helpers.

Use cases:
    - Called by `backend/matching/catalog.py` to discover live Shopify products
      across eligible merchants from extracted item queries and filters.
    - Called by `eval/` tooling to look up ground-truth product UPIDs/variants.
    - Supports both authenticated mode (higher rate limits when
      `SHOPIFY_CLIENT_ID` and `SHOPIFY_CLIENT_SECRET` are set) and
      unauthenticated profile-only mode at base rate limits.

What this module must NOT do:
    - Must NEVER cache catalog responses on disk or in any database.
    - Must NEVER download, persist, or re-host merchant product images.
    - Must NEVER call Shopify Admin GraphQL, Storefront GraphQL, or the retired
      `/global/v2/` REST endpoints.
    - Must NEVER touch merchant cart creation (`backend/shopify/cart.py` is P3's).
    - Must NEVER log or expose `SHOPIFY_CLIENT_SECRET` or OAuth bearer tokens.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import random
import threading
import time
from typing import Any
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request
import uuid

from backend.config import CONFIG, AppConfig, get_secret
from backend.matching.logging_utils import get_logger, log_function_call, sanitize_for_log


LOGGER = get_logger(__name__)

# ISO 4217 currency minor-unit exponents (default is 2 for USD, EUR, GBP, CAD, etc.)
_ZERO_DECIMAL_CURRENCIES = frozenset(
    {"BIF", "CLP", "DJF", "GNF", "JPY", "KMF", "KRW", "MGA", "PYG", "RWF", "UGX", "VND", "VUV", "XAF", "XOF", "XPF"}
)
_THREE_DECIMAL_CURRENCIES = frozenset({"BHD", "IQD", "JOD", "KWD", "LYD", "OMR", "TND"})


class ShopifyCatalogError(RuntimeError):
    """Structured error raised when Shopify OAuth or Global Catalog MCP calls fail."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        rpc_code: int | None = None,
        retryable: bool = False,
    ) -> None:
        """Initialize a structured Shopify catalog exception.

        Args:
            message: Human-readable error message (secrets must already be redacted).
            status_code: HTTP status code if the failure originated at HTTP layer.
            rpc_code: JSON-RPC error code if returned by the MCP server.
            retryable: Whether the error is transient (e.g. 429 or 5xx).

        Side effects:
            None.
        """
        super().__init__(message)
        self.status_code = status_code
        self.rpc_code = rpc_code
        self.retryable = retryable


def currency_exponent(currency: str | None) -> int:
    """Return the ISO 4217 minor-unit decimal exponent for a currency code.

    Args:
        currency: Three-letter ISO 4217 currency code (e.g. `"USD"`, `"JPY"`).

    Returns:
        Integer exponent (`0`, `2`, or `3`). Defaults to `2` when unknown/None.

    Side effects:
        None.
    """
    code = (currency or "USD").strip().upper()
    if code in _ZERO_DECIMAL_CURRENCIES:
        return 0
    if code in _THREE_DECIMAL_CURRENCIES:
        return 3
    return 2


def minor_to_major_price(amount_minor: int | float | None, currency: str | None = "USD") -> float | None:
    """Convert an ISO 4217 minor-unit integer price (e.g. 16999 cents) to major units (169.99).

    Args:
        amount_minor: Integer price in minor currency units from Shopify UCP.
        currency: ISO 4217 currency code controlling decimal shift.

    Returns:
        Price as a float in major currency units, or `None` if `amount_minor` is `None`.

    Side effects:
        None.
    """
    if amount_minor is None:
        return None
    exp = currency_exponent(currency)
    if exp == 0:
        return float(int(round(amount_minor)))
    return round(float(amount_minor) / (10**exp), exp)


def major_to_minor_price(amount_major: int | float, currency: str | None = "USD") -> int:
    """Convert a major-unit price (e.g. 150.0 USD) to integer minor units (15000).

    Args:
        amount_major: Price in major currency units (e.g. dollars).
        currency: ISO 4217 currency code controlling decimal shift.

    Returns:
        Integer price in minor currency units suitable for UCP `filters.price`.

    Side effects:
        None.
    """
    exp = currency_exponent(currency)
    return int(round(float(amount_major) * (10**exp)))


@dataclass
class _CachedToken:
    """In-memory OAuth bearer token entry (never persisted to disk)."""

    access_token: str
    expires_at: float


class _ShopifyTokenManager:
    """Thread-safe in-memory OAuth2 `client_credentials` token cache."""

    def __init__(self) -> None:
        """Initialize an empty token cache guarded by a threading lock.

        Side effects:
            None.
        """
        self._lock = threading.Lock()
        self._cached: _CachedToken | None = None

    def clear(self) -> None:
        """Clear any cached OAuth token from memory (used in tests or after 401).

        Returns:
            None.

        Side effects:
            Resets in-memory `_cached` token to `None`.
        """
        with self._lock:
            self._cached = None

    def get_bearer_token(
        self,
        *,
        cfg: AppConfig = CONFIG,
        http_post_fn: Any = None,
        now_fn: Any = time.monotonic,
    ) -> str | None:
        """Return a valid cached bearer token, refreshing via OAuth2 if near expiry.

        When `SHOPIFY_CLIENT_ID` or `SHOPIFY_CLIENT_SECRET` is not set in the
        environment, returns `None` so Global Catalog MCP can fall back to
        profile-only unauthenticated requests at base rate limits (per CLAUDE.md §8).

        Args:
            cfg: Active `AppConfig` holding auth URL, timeout, and expiry buffer.
            http_post_fn: Optional injectable HTTP POST callable for unit testing.
            now_fn: Monotonic clock callable for deterministic expiry testing.

        Returns:
            Bearer access token string, or `None` when credentials are unconfigured.

        Raises:
            ShopifyCatalogError: If credentials are configured but token exchange fails.

        Side effects:
            Performs an HTTPS POST to Shopify's OAuth token endpoint on cache miss
            and updates the in-memory token cache.
        """
        client_id = get_secret("SHOPIFY_CLIENT_ID", required=False)
        client_secret = get_secret("SHOPIFY_CLIENT_SECRET", required=False)
        if not client_id or not client_secret:
            return None

        with self._lock:
            now = now_fn()
            if self._cached is not None and now < (
                self._cached.expires_at - cfg.token_expiry_buffer_s
            ):
                return self._cached.access_token

            log_function_call(
                LOGGER,
                "shopify._ShopifyTokenManager.refresh_token",
                {"auth_url": cfg.shopify_auth_token_url, "grant_type": "client_credentials"},
            )
            payload = urllib_parse.urlencode(
                {
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                }
            ).encode("utf-8")
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            }

            post = http_post_fn or _raw_http_post
            status, _resp_headers, body_bytes = _request_with_retry(
                post_fn=post,
                url=cfg.shopify_auth_token_url,
                body=payload,
                headers=headers,
                cfg=cfg,
                operation="shopify_oauth_token",
            )
            if status >= 400:
                raise ShopifyCatalogError(
                    f"Shopify OAuth token exchange failed with HTTP {status}.",
                    status_code=status,
                    retryable=status in (429, 500, 502, 503, 504),
                )

            try:
                token_data = json.loads(body_bytes.decode("utf-8"))
            except Exception as exc:
                raise ShopifyCatalogError(
                    f"Shopify OAuth response was not valid JSON: {exc}"
                ) from exc

            access_token = token_data.get("access_token")
            expires_in = float(token_data.get("expires_in", 3600))
            if not isinstance(access_token, str) or not access_token:
                raise ShopifyCatalogError("Shopify OAuth response missing 'access_token'.")

            self._cached = _CachedToken(
                access_token=access_token,
                expires_at=now_fn() + max(expires_in, 60.0),
            )
            return access_token


_TOKEN_MANAGER = _ShopifyTokenManager()


def _raw_http_post(
    url: str,
    body: bytes,
    headers: dict[str, str],
    timeout_s: float,
) -> tuple[int, dict[str, str], bytes]:
    """Execute a raw HTTPS POST request using Python stdlib `urllib.request`.

    Args:
        url: Destination HTTPS endpoint URL.
        body: Raw request body bytes.
        headers: HTTP request headers dictionary.
        timeout_s: Socket timeout in seconds.

    Returns:
        Tuple of `(status_code, response_headers_lowercased, response_body_bytes)`.

    Raises:
        ShopifyCatalogError: On network/DNS/socket errors (marked retryable).

    Side effects:
        Performs an outbound HTTPS POST request.
    """
    req = urllib_request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib_request.urlopen(req, timeout=timeout_s) as resp:
            resp_headers = {k.lower(): v for k, v in resp.headers.items()}
            return int(resp.status), resp_headers, resp.read()
    except urllib_error.HTTPError as exc:
        resp_headers = {k.lower(): v for k, v in exc.headers.items()} if exc.headers else {}
        err_body = exc.read() if exc.fp is not None else b""
        return int(exc.code), resp_headers, err_body
    except (urllib_error.URLError, TimeoutError, OSError) as exc:
        raise ShopifyCatalogError(
            f"Network error contacting Shopify endpoint: {exc}",
            retryable=True,
        ) from exc


def _parse_retry_after(headers: dict[str, str]) -> float | None:
    """Parse numeric `Retry-After` header seconds if present.

    Args:
        headers: Lowercased HTTP response headers mapping.

    Returns:
        Suggested wait duration in seconds, or `None` if absent/non-numeric.

    Side effects:
        None.
    """
    raw = headers.get("retry-after")
    if not raw:
        return None
    try:
        return max(0.0, float(raw.strip()))
    except ValueError:
        return None


def _request_with_retry(
    *,
    post_fn: Any,
    url: str,
    body: bytes,
    headers: dict[str, str],
    cfg: AppConfig,
    operation: str,
    sleep_fn: Any = time.sleep,
    jitter_fn: Any = random.uniform,
) -> tuple[int, dict[str, str], bytes]:
    """Send an HTTP POST with exponential backoff + full jitter on 429 and 5xx errors.

    Args:
        post_fn: Callable `(url, body, headers, timeout_s) -> (status, headers, bytes)`.
        url: Destination endpoint URL.
        body: Encoded request body bytes.
        headers: Request headers (never logged raw).
        cfg: Active `AppConfig` providing retry attempts, base/max delay, and timeout.
        operation: Short label for INFO retry logs.
        sleep_fn: Injectable sleep function for deterministic tests.
        jitter_fn: Injectable jitter generator `(0.0, cap) -> float`.

    Returns:
        Tuple of `(status_code, response_headers, response_body_bytes)`.

    Raises:
        ShopifyCatalogError: When retries are exhausted on network failure.

    Side effects:
        Performs up to `cfg.retry_max_attempts` HTTP requests and sleeps between retries.
    """
    max_attempts = max(1, cfg.retry_max_attempts)
    last_exc: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            status, resp_headers, resp_body = post_fn(url, body, headers, cfg.http_timeout_s)
        except ShopifyCatalogError as exc:
            last_exc = exc
            if not exc.retryable or attempt == max_attempts:
                raise
            delay = min(cfg.retry_max_delay_s, cfg.retry_base_delay_s * (2 ** (attempt - 1)))
            wait_s = jitter_fn(0.0, delay)
            LOGGER.info(
                json.dumps(
                    {
                        "event": "shopify_retry",
                        "operation": operation,
                        "attempt": attempt,
                        "reason": "network_error",
                        "sleep_s": round(wait_s, 3),
                    }
                )
            )
            sleep_fn(wait_s)
            continue

        if status not in (429, 500, 502, 503, 504) or attempt == max_attempts:
            return status, resp_headers, resp_body

        retry_after = _parse_retry_after(resp_headers)
        exp_cap = min(cfg.retry_max_delay_s, cfg.retry_base_delay_s * (2 ** (attempt - 1)))
        wait_s = min(cfg.retry_max_delay_s, retry_after) if retry_after is not None else jitter_fn(0.0, exp_cap)
        LOGGER.info(
            json.dumps(
                {
                    "event": "shopify_retry",
                    "operation": operation,
                    "attempt": attempt,
                    "http_status": status,
                    "sleep_s": round(wait_s, 3),
                }
            )
        )
        sleep_fn(wait_s)

    assert last_exc is not None
    raise last_exc


def _extract_mcp_payload(rpc_response: dict[str, Any]) -> dict[str, Any]:
    """Extract the structured UCP response object from a JSON-RPC 2.0 MCP envelope.

    Handles `result.structuredContent` (UCP 2026-08-25 default),
    `result.content[0].text` (JSON-encoded text content), or direct `result`.

    Args:
        rpc_response: Parsed JSON-RPC response dictionary from Shopify Catalog MCP.

    Returns:
        Unwrapped UCP payload dictionary (containing `products` or `product` and `ucp`).

    Raises:
        ShopifyCatalogError: If the JSON-RPC envelope or UCP status indicates an error.

    Side effects:
        None.
    """
    if "error" in rpc_response and rpc_response["error"] is not None:
        err = rpc_response["error"]
        msg = err.get("message", "Unknown JSON-RPC error")
        detail = err.get("data")
        full_msg = f"{msg}: {detail}" if detail else msg
        raise ShopifyCatalogError(
            f"Shopify Catalog MCP JSON-RPC error: {full_msg}",
            rpc_code=err.get("code"),
            retryable=False,
        )

    result = rpc_response.get("result")
    if not isinstance(result, dict):
        raise ShopifyCatalogError("Shopify Catalog MCP response missing 'result' object.")

    if result.get("isError"):
        raise ShopifyCatalogError(
            f"Shopify Catalog MCP tool returned error: {sanitize_for_log(result)}"
        )

    payload: dict[str, Any]
    if isinstance(result.get("structuredContent"), dict):
        payload = result["structuredContent"]
    elif isinstance(result.get("content"), list) and result["content"]:
        first_block = result["content"][0]
        if isinstance(first_block, dict) and isinstance(first_block.get("text"), str):
            try:
                payload = json.loads(first_block["text"])
            except json.JSONDecodeError as exc:
                raise ShopifyCatalogError(
                    f"Unable to decode MCP text content as JSON: {exc}"
                ) from exc
        else:
            payload = result
    else:
        payload = result

    ucp_meta = payload.get("ucp")
    if isinstance(ucp_meta, dict) and ucp_meta.get("status") == "error":
        messages = payload.get("messages") or payload.get("errors") or []
        raise ShopifyCatalogError(
            f"Shopify Catalog UCP error status: {sanitize_for_log(messages)}"
        )

    return payload


def _call_catalog_mcp(
    tool_name: str,
    catalog_args: dict[str, Any],
    *,
    cfg: AppConfig = CONFIG,
    http_post_fn: Any = None,
    sleep_fn: Any = time.sleep,
    jitter_fn: Any = random.uniform,
    token_manager: _ShopifyTokenManager = _TOKEN_MANAGER,
) -> dict[str, Any]:
    """Invoke a Global Catalog MCP tool over JSON-RPC 2.0 with UCP profile metadata.

    Args:
        tool_name: One of `"search_catalog"`, `"lookup_catalog"`, or `"get_product"`.
        catalog_args: Tool-specific payload placed under `arguments.catalog`.
        cfg: Active `AppConfig`.
        http_post_fn: Optional injectable HTTP POST callable for unit testing.
        sleep_fn: Optional injectable sleep function for retry tests.
        jitter_fn: Optional injectable jitter generator for retry tests.
        token_manager: OAuth token cache manager instance.

    Returns:
        Unwrapped UCP response payload dictionary (never cached on disk).

    Raises:
        ShopifyCatalogError: On HTTP error, JSON parse error, JSON-RPC error,
            or UCP status error.

    Side effects:
        Sends an HTTPS POST request to `cfg.shopify_catalog_mcp_url` and emits
        structured INFO logs with request summary and latency.
    """
    t0 = time.monotonic()
    post = http_post_fn or _raw_http_post
    token = token_manager.get_bearer_token(cfg=cfg, http_post_fn=post)

    rpc_body = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": {
                "meta": {
                    "ucp-agent": {
                        "profile": cfg.shopify_agent_profile_url,
                    }
                },
                "catalog": catalog_args,
            },
        },
    }
    encoded_body = json.dumps(rpc_body).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    status, _resp_headers, resp_bytes = _request_with_retry(
        post_fn=post,
        url=cfg.shopify_catalog_mcp_url,
        body=encoded_body,
        headers=headers,
        cfg=cfg,
        operation=tool_name,
        sleep_fn=sleep_fn,
        jitter_fn=jitter_fn,
    )

    # If a cached bearer token was rejected with 401, clear cache and retry once.
    if status == 401 and token:
        token_manager.clear()
        fresh_token = token_manager.get_bearer_token(cfg=cfg, http_post_fn=post)
        if fresh_token:
            headers["Authorization"] = f"Bearer {fresh_token}"
            status, _resp_headers, resp_bytes = _request_with_retry(
                post_fn=post,
                url=cfg.shopify_catalog_mcp_url,
                body=encoded_body,
                headers=headers,
                cfg=cfg,
                operation=f"{tool_name}_reauth",
                sleep_fn=sleep_fn,
                jitter_fn=jitter_fn,
            )

    latency_ms = round((time.monotonic() - t0) * 1000.0, 2)
    if status >= 400:
        snippet = resp_bytes.decode("utf-8", errors="replace")[:300]
        raise ShopifyCatalogError(
            f"Shopify Catalog MCP '{tool_name}' failed with HTTP {status}: {sanitize_for_log(snippet)}",
            status_code=status,
            retryable=status in (429, 500, 502, 503, 504),
        )

    try:
        rpc_response = json.loads(resp_bytes.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ShopifyCatalogError(
            f"Shopify Catalog MCP '{tool_name}' returned invalid JSON: {exc}"
        ) from exc

    payload = _extract_mcp_payload(rpc_response)
    result_count = (
        len(payload.get("products", []))
        if "products" in payload
        else (1 if payload.get("product") else 0)
    )
    LOGGER.info(
        json.dumps(
            {
                "event": "shopify_catalog_mcp",
                "tool": tool_name,
                "authenticated": bool(token),
                "latency_ms": latency_ms,
                "result_count": result_count,
            }
        )
    )
    return payload


def _build_context(filters: dict[str, Any] | None, context: dict[str, Any] | None, cfg: AppConfig) -> dict[str, Any]:
    """Build the UCP `catalog.context` object from explicit context, filters, and defaults.

    Args:
        filters: Optional caller-supplied filter dictionary (may contain `currency`, `ships_to`).
        context: Optional explicit UCP context dictionary.
        cfg: Active `AppConfig` supplying default currency and country.

    Returns:
        UCP `context` dictionary with `currency` and `address_country` populated.

    Side effects:
        None.
    """
    ctx: dict[str, Any] = dict(context or {})
    f = filters or {}
    currency = ctx.get("currency") or f.get("currency") or cfg.shopify_default_currency
    ctx["currency"] = str(currency).upper()

    if "address_country" not in ctx:
        ships_to = f.get("ships_to")
        if isinstance(ships_to, str) and len(ships_to.strip()) == 2:
            ctx["address_country"] = ships_to.strip().upper()
        elif isinstance(ships_to, dict) and ships_to.get("country"):
            ctx["address_country"] = str(ships_to["country"]).strip().upper()
        else:
            ctx["address_country"] = cfg.shopify_default_country
    return ctx


def _build_ucp_filters(filters: dict[str, Any] | None, currency: str) -> dict[str, Any]:
    """Translate high-level search filter keys into UCP `catalog.filters` schema.

    Supported caller keys:
    - `max_price` / `min_price` (major currency units, e.g. `150.0` -> `15000` USD cents)
    - `price` (already formatted UCP dict `{"min": ..., "max": ...}`)
    - `ships_to` (`"US"` string or `{"country": "US", ...}` dict)
    - `available` (bool; defaults to True when omitted by caller)
    - `categories`, `condition`, `shops`, `attributes`, `price_tier`, `rating`, `media`

    Args:
        filters: Optional high-level filter dictionary.
        currency: ISO 4217 currency code used to convert major prices to minor units.

    Returns:
        UCP-compliant `filters` dictionary (empty dict if no filters apply).

    Side effects:
        None.
    """
    if not filters:
        return {"available": True}

    ucp_filters: dict[str, Any] = {}
    ucp_filters["available"] = bool(filters.get("available", True))

    # Price range handling: prefer explicit major-unit max_price/min_price if provided.
    price_filter: dict[str, int] = {}
    if isinstance(filters.get("price"), dict):
        if filters["price"].get("min") is not None:
            price_filter["min"] = int(filters["price"]["min"])
        if filters["price"].get("max") is not None:
            price_filter["max"] = int(filters["price"]["max"])
    if filters.get("min_price") is not None:
        price_filter["min"] = major_to_minor_price(filters["min_price"], currency)
    if filters.get("max_price") is not None:
        price_filter["max"] = major_to_minor_price(filters["max_price"], currency)
    if price_filter:
        ucp_filters["price"] = price_filter

    ships_to = filters.get("ships_to")
    if isinstance(ships_to, str) and ships_to.strip():
        ucp_filters["ships_to"] = {"country": ships_to.strip().upper()}
    elif isinstance(ships_to, dict) and ships_to.get("country"):
        cleaned = dict(ships_to)
        cleaned["country"] = str(cleaned["country"]).strip().upper()
        ucp_filters["ships_to"] = cleaned

    for passthrough_key in (
        "categories",
        "condition",
        "shops",
        "attributes",
        "price_tier",
        "rating",
        "media",
    ):
        if filters.get(passthrough_key) is not None:
            ucp_filters[passthrough_key] = filters[passthrough_key]

    return ucp_filters


def search_catalog(
    query: str,
    filters: dict[str, Any] | None = None,
    *,
    limit: int | None = None,
    context: dict[str, Any] | None = None,
    cfg: AppConfig = CONFIG,
    http_post_fn: Any = None,
    sleep_fn: Any = time.sleep,
    jitter_fn: Any = random.uniform,
    token_manager: _ShopifyTokenManager = _TOKEN_MANAGER,
) -> list[dict[str, Any]]:
    """Search Shopify's Global Catalog MCP by text query and structured filters.

    Text queries are the default per `CLAUDE.md` section 8 (image search is not
    sent by default due to upstream reliability issues).

    Args:
        query: Free-text product search query string.
        filters: Optional filter dict (`max_price`, `min_price`, `currency`,
            `ships_to`, `available`, `categories`, `condition`, `shops`, etc.).
        limit: Optional maximum number of UPID products to request (defaults to
            `cfg.shopify_search_default_limit`).
        context: Optional explicit UCP `context` dict (`currency`, `address_country`).
        cfg: Active `AppConfig`.
        http_post_fn: Optional injectable HTTP POST callable for tests.
        sleep_fn: Optional injectable sleep function for retry tests.
        jitter_fn: Optional injectable jitter function for retry tests.
        token_manager: OAuth token cache manager instance.

    Returns:
        List of raw UCP product dicts grouped by UPID (`products[]`). Never cached.

    Raises:
        ValueError: If `query` is empty/whitespace.
        ShopifyCatalogError: If the upstream Shopify MCP call fails.

    Side effects:
        Executes a live HTTPS POST to Shopify Global Catalog MCP and logs at INFO.
    """
    cleaned_query = (query or "").strip()
    if not cleaned_query:
        raise ValueError("search_catalog requires a non-empty 'query' string.")

    effective_limit = max(1, int(limit if limit is not None else cfg.shopify_search_default_limit))
    ucp_context = _build_context(filters, context, cfg)
    ucp_filters = _build_ucp_filters(filters, ucp_context["currency"])

    log_function_call(
        LOGGER,
        "shopify.catalog.search_catalog",
        {
            "query": cleaned_query,
            "filters": ucp_filters,
            "context": ucp_context,
            "limit": effective_limit,
        },
    )

    catalog_args: dict[str, Any] = {
        "query": cleaned_query,
        "context": ucp_context,
        "filters": ucp_filters,
        "pagination": {"limit": effective_limit},
    }
    if cfg.shopify_use_compact_view:
        catalog_args["view"] = "compact"

    payload = _call_catalog_mcp(
        "search_catalog",
        catalog_args,
        cfg=cfg,
        http_post_fn=http_post_fn,
        sleep_fn=sleep_fn,
        jitter_fn=jitter_fn,
        token_manager=token_manager,
    )
    products = payload.get("products")
    return list(products) if isinstance(products, list) else []


def lookup_catalog(
    ids: list[str],
    *,
    context: dict[str, Any] | None = None,
    cfg: AppConfig = CONFIG,
    http_post_fn: Any = None,
    sleep_fn: Any = time.sleep,
    jitter_fn: Any = random.uniform,
    token_manager: _ShopifyTokenManager = _TOKEN_MANAGER,
) -> list[dict[str, Any]]:
    """Look up Shopify products or variants by ID/URL, auto-chunked to <= 50 per call.

    Args:
        ids: List of UPIDs (`gid://shopify/p/...`), variant GIDs, or product URLs.
        context: Optional explicit UCP `context` dict (`currency`, `address_country`).
        cfg: Active `AppConfig` (supplies `shopify_lookup_batch_size`, max 50).
        http_post_fn: Optional injectable HTTP POST callable for tests.
        sleep_fn: Optional injectable sleep function for retry tests.
        jitter_fn: Optional injectable jitter function for retry tests.
        token_manager: OAuth token cache manager instance.

    Returns:
        Combined list of fresh UCP product dicts across all batches. Never cached.

    Raises:
        ShopifyCatalogError: If any upstream batch lookup fails.

    Side effects:
        Executes one or more HTTPS POST calls to Shopify Global Catalog MCP.
    """
    cleaned_ids = [item.strip() for item in ids if isinstance(item, str) and item.strip()]
    if not cleaned_ids:
        return []

    batch_size = min(50, max(1, cfg.shopify_lookup_batch_size))
    ucp_context = _build_context(None, context, cfg)
    log_function_call(
        LOGGER,
        "shopify.catalog.lookup_catalog",
        {"id_count": len(cleaned_ids), "batch_size": batch_size, "context": ucp_context},
    )

    all_products: list[dict[str, Any]] = []
    for start in range(0, len(cleaned_ids), batch_size):
        batch = cleaned_ids[start : start + batch_size]
        catalog_args: dict[str, Any] = {
            "ids": batch,
            "context": ucp_context,
        }
        if cfg.shopify_use_compact_view:
            catalog_args["view"] = "compact"
        payload = _call_catalog_mcp(
            "lookup_catalog",
            catalog_args,
            cfg=cfg,
            http_post_fn=http_post_fn,
            sleep_fn=sleep_fn,
            jitter_fn=jitter_fn,
            token_manager=token_manager,
        )
        products = payload.get("products")
        if isinstance(products, list):
            all_products.extend(products)

    return all_products


def get_product(
    upid: str,
    *,
    selected: list[dict[str, str]] | None = None,
    preferences: list[str] | None = None,
    context: dict[str, Any] | None = None,
    cfg: AppConfig = CONFIG,
    http_post_fn: Any = None,
    sleep_fn: Any = time.sleep,
    jitter_fn: Any = random.uniform,
    token_manager: _ShopifyTokenManager = _TOKEN_MANAGER,
) -> dict[str, Any]:
    """Retrieve full product details, variants, and option combinations for one UPID.

    Args:
        upid: Universal Product ID (e.g. `"gid://shopify/p/..."`) or variant ID.
        selected: Optional list of option selections `[{"name": "Color", "label": "Black"}]`.
        preferences: Optional buyer preference hints.
        context: Optional explicit UCP `context` dict.
        cfg: Active `AppConfig`.
        http_post_fn: Optional injectable HTTP POST callable for tests.
        sleep_fn: Optional injectable sleep function for retry tests.
        jitter_fn: Optional injectable jitter function for retry tests.
        token_manager: OAuth token cache manager instance.

    Returns:
        Fresh UCP product detail dictionary (`payload["product"]`). Never cached.

    Raises:
        ValueError: If `upid` is blank.
        ShopifyCatalogError: If the upstream MCP call fails or returns no product.

    Side effects:
        Executes a live HTTPS POST to Shopify Global Catalog MCP and logs at INFO.
    """
    cleaned_id = (upid or "").strip()
    if not cleaned_id:
        raise ValueError("get_product requires a non-empty 'upid' string.")

    ucp_context = _build_context(None, context, cfg)
    log_function_call(
        LOGGER,
        "shopify.catalog.get_product",
        {"upid": cleaned_id, "selected": selected, "context": ucp_context},
    )

    catalog_args: dict[str, Any] = {
        "id": cleaned_id,
        "context": ucp_context,
    }
    if selected:
        catalog_args["selected"] = selected
    if preferences:
        catalog_args["preferences"] = preferences
    if cfg.shopify_use_compact_view:
        catalog_args["view"] = "compact"

    payload = _call_catalog_mcp(
        "get_product",
        catalog_args,
        cfg=cfg,
        http_post_fn=http_post_fn,
        sleep_fn=sleep_fn,
        jitter_fn=jitter_fn,
        token_manager=token_manager,
    )
    product = payload.get("product")
    if not isinstance(product, dict):
        raise ShopifyCatalogError(
            f"Shopify Catalog MCP get_product returned no 'product' object for '{cleaned_id}'."
        )
    return product
