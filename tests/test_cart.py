"""Tests for backend/shopify/cart.py using a mock HTTP transport (no network)."""
import httpx
import pytest

from backend.shopify import cart as cart_mod
from backend.shopify.cart import CartError, create_cart, mcp_url, update_cart


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def _ok(cart_id="gid://shopify/Cart/c1", url="https://shop.example.com/cart/c/c1"):
    return {"jsonrpc": "2.0", "id": 1, "result": {"structuredContent": {"cart": {"id": cart_id, "continue_url": url}}}}


def test_mcp_url_strips_scheme():
    assert mcp_url("https://a.myshopify.com/x") == "https://a.myshopify.com/api/ucp/mcp"


def test_create_cart_request_and_response():
    seen = {}

    def handler(req: httpx.Request):
        seen["url"] = str(req.url)
        seen["body"] = req.read().decode()
        return httpx.Response(200, json=_ok())

    out = create_cart("a.myshopify.com", "gid://shopify/ProductVariant/1", 2, client=_client(handler))
    assert out == {"cart_id": "gid://shopify/Cart/c1", "continue_url": "https://shop.example.com/cart/c/c1"}
    assert seen["url"] == "https://a.myshopify.com/api/ucp/mcp"
    assert '"create_cart"' in seen["body"] and '"ucp-agent"' in seen["body"] and '"quantity":2' in seen["body"].replace(" ", "")


def test_update_cart():
    out = update_cart("a.myshopify.com", "gid://shopify/Cart/c1", [], client=_client(lambda r: httpx.Response(200, json=_ok())))
    assert out["cart_id"] == "gid://shopify/Cart/c1"


def test_rate_limit_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr(cart_mod.time, "sleep", lambda s: None)
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(429, headers={"Retry-After": "1"}) if calls["n"] < 3 else httpx.Response(200, json=_ok())

    assert create_cart("a.myshopify.com", "v", client=_client(handler))["cart_id"]
    assert calls["n"] == 3


def test_rate_limit_gives_up(monkeypatch):
    monkeypatch.setattr(cart_mod.time, "sleep", lambda s: None)
    with pytest.raises(CartError) as e:
        create_cart("a.myshopify.com", "v", client=_client(lambda r: httpx.Response(429)))
    assert e.value.code == "rate_limited"


def test_rpc_error_raises():
    err = {"jsonrpc": "2.0", "id": 1, "error": {"code": -32000, "message": "Unauthorized"}}
    with pytest.raises(CartError) as e:
        create_cart("a.myshopify.com", "v", client=_client(lambda r: httpx.Response(200, json=err)))
    assert e.value.code == "rpc_error"


def test_unrecoverable_message_raises():
    payload = _ok()
    payload["result"]["structuredContent"]["cart"]["messages"] = [
        {"type": "error", "code": "out_of_stock", "content": "Sold out", "severity": "unrecoverable"}
    ]
    with pytest.raises(CartError) as e:
        create_cart("a.myshopify.com", "v", client=_client(lambda r: httpx.Response(200, json=payload)))
    assert e.value.code == "out_of_stock"


def test_live_shape_cart_directly_in_structured_content():
    # Shape observed from a real merchant: no "cart" wrapper.
    payload = {"jsonrpc": "2.0", "id": 1, "result": {"structuredContent": {
        "id": "gid://shopify/Cart/live1", "continue_url": "https://s.myshopify.com/cart/c/live1", "messages": []}}}
    out = create_cart("a.myshopify.com", "v", client=_client(lambda r: httpx.Response(200, json=payload)))
    assert out == {"cart_id": "gid://shopify/Cart/live1", "continue_url": "https://s.myshopify.com/cart/c/live1"}


def test_bad_quantity():
    with pytest.raises(CartError):
        create_cart("a.myshopify.com", "v", 0)
