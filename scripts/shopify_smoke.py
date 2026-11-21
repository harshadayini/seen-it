"""Shopify smoke test (P3): one search, one lookup, one cart creation, against live services.

Usage:
    python scripts/shopify_smoke.py                       # search, then cart on the first hit
    python scripts/shopify_smoke.py --merchant SHOP.myshopify.com --variant gid://shopify/ProductVariant/123

What it checks
    1. search + lookup via P2's backend.shopify.catalog, if that module exists yet (skipped otherwise).
    2. create_cart on a merchant, printing cart id and continue_url.
Invariants: never places an order; never prints secrets (the cart call uses none).
Exit code is 0 only if the cart step succeeded.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.shopify.cart import CartError, create_cart  # noqa: E402


def try_catalog() -> tuple[str, str] | None:
    """Run one catalog search and lookup if P2's module is available.

    Returns:
        (merchant_domain, variant_id) of the first hit, or None if unavailable/empty.
    """
    try:
        from backend.shopify import catalog
    except ImportError as exc:
        print(f"SKIP  catalog search (could not import backend.shopify.catalog: {exc})")
        return None
    try:
        products = catalog.search_catalog("black arc floor lamp", {"ships_to": "US", "currency": "USD"}, limit=5)
    except Exception as exc:  # report, do not hide
        print(f"FAIL  search_catalog: {exc.__class__.__name__}: {exc}")
        return None
    # search_catalog returns raw UCP products: variants[] each with id and seller.domain.
    for product in products:
        for variant in product.get("variants") or []:
            domain = (variant.get("seller") or {}).get("domain")
            if domain and variant.get("id"):
                print(f"PASS  search_catalog -> {variant.get('title') or product.get('title')} @ {domain}")
                return domain, variant["id"]
    print("FAIL  search_catalog returned no variant with a seller domain")
    return None


def main() -> int:
    """Parse args, run the steps, and return a process exit code."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--merchant")
    ap.add_argument("--variant")
    args = ap.parse_args()

    merchant, variant = args.merchant, args.variant
    if not (merchant and variant):
        found = try_catalog()
        if found:
            merchant, variant = found
    if not (merchant and variant):
        print("FAIL  need --merchant and --variant (or a working catalog search)")
        return 1
    try:
        cart = create_cart(merchant, variant, 1)
    except CartError as exc:
        print(f"FAIL  create_cart at {merchant}: {exc}")
        return 1
    print(f"PASS  create_cart at {merchant}")
    print(f"      cart_id      = {cart.get('cart_id')}")
    print(f"      continue_url = {cart.get('continue_url')}")
    print("      (open the continue_url to see checkout; do not complete an order)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
