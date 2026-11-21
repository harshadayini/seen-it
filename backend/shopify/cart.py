"""P3 stub. TODO: UCP create_cart per merchant."""


def create_cart(merchant_domain: str, variant_id: str, qty: int = 1) -> dict:
    return {
        "cart_id": f"gid://shopify/Cart/stub-{merchant_domain}",
        "continue_url": f"https://{merchant_domain}/cart/c/stub?checkout",
    }
