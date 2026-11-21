"""Catalog search and candidate normalization for Seen It matching (P2).

What this module does:
    Implements the agreed P2 `search(query: str, filters: dict) -> list[dict]`
    function from `CLAUDE.md` section 6. Queries Shopify's Global Catalog MCP
    via `backend.shopify.catalog.search_catalog`, flattens UPID-grouped product
    variants into contract-compliant candidate dictionaries matching
    `contracts/run.schema.json` (`$defs.candidate`), converts ISO 4217 minor
    currency units into major floats, extracts merchant domains and image URLs,
    deduplicates variants, and enforces the candidate limit from `backend/config.py`.

Use cases:
    - Called by `backend/matching/status.py` (`resolve()`) during initial
      matching and after P1's `relook()` produces a refined query.
    - Called by `eval/run_eval.py` during build-set calibration and held-out runs.

What this module must NOT do:
    - Must NEVER cache Shopify catalog responses on disk or in a database.
    - Must NEVER download or re-host merchant product images (only passes
      through the merchant's own CDN `image_url`).
    - Must NEVER fabricate fake products when Shopify fails or returns 0 hits.
    - Must NEVER score `p_same_product` / `p_same_variant` (that belongs solely
      to `backend/matching/checker.py`).
"""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from backend.config import CONFIG, AppConfig
from backend.matching.logging_utils import get_logger, log_function_call
from backend.matching.models import Candidate
from backend.shopify.catalog import (
    minor_to_major_price,
    search_catalog,
)


LOGGER = get_logger(__name__)


def _extract_image_url(
    variant: dict[str, Any],
    product: dict[str, Any],
) -> str | None:
    """Extract the best merchant image URL from variant media, falling back to product media.

    Args:
        variant: Raw UCP variant dictionary.
        product: Parent raw UCP product dictionary.

    Returns:
        Direct merchant/Shopify CDN image URL string, or `None` if unavailable.

    Side effects:
        None.
    """
    for container in (variant, product):
        media_list = container.get("media")
        if not isinstance(media_list, list):
            continue
        for entry in media_list:
            if not isinstance(entry, dict):
                continue
            media_type = str(entry.get("type", "image")).lower()
            if media_type != "image":
                continue
            direct_url = entry.get("url")
            if isinstance(direct_url, str) and direct_url.startswith(("http://", "https://")):
                return direct_url
            preview = entry.get("preview")
            if isinstance(preview, dict):
                preview_url = preview.get("url")
                if isinstance(preview_url, str) and preview_url.startswith(("http://", "https://")):
                    return preview_url
    return None


def _extract_merchant_domain(variant: dict[str, Any]) -> str | None:
    """Extract the Shopify merchant domain from a UCP variant's `seller` metadata.

    Prefers `seller.domain` (typically `*.myshopify.com` or primary store domain
    needed by P3's `/.well-known/ucp` cart discovery), falling back to the
    hostname of `seller.url` or `variant.url`.

    Args:
        variant: Raw UCP variant dictionary.

    Returns:
        Normalized lowercase merchant domain string, or `None` if unavailable.

    Side effects:
        None.
    """
    seller = variant.get("seller")
    if isinstance(seller, dict):
        domain = seller.get("domain")
        if isinstance(domain, str) and domain.strip():
            cleaned = domain.strip().lower()
            if "://" in cleaned:
                parsed = urlparse(cleaned)
                if parsed.hostname:
                    return parsed.hostname.lower()
            return cleaned.rstrip("/")

        seller_url = seller.get("url")
        if isinstance(seller_url, str) and seller_url.strip():
            parsed = urlparse(seller_url.strip())
            if parsed.hostname:
                return parsed.hostname.lower()

    variant_url = variant.get("url")
    if isinstance(variant_url, str) and variant_url.strip():
        parsed = urlparse(variant_url.strip())
        if parsed.hostname:
            return parsed.hostname.lower()

    return None


def _extract_product_url(variant: dict[str, Any]) -> str | None:
    """Return the merchant's product-page URL for a variant, without Shopify tracking params.

    Args:
        variant: Raw UCP variant dictionary (its `url` is the storefront page, with `?variant=`).
    Returns:
        An https URL, or None if the variant has no usable URL. Drops `_gsid` and `utm_*`.
    """
    raw = variant.get("url")
    if not isinstance(raw, str) or not raw.strip():
        return None
    parsed = urlparse(raw.strip())
    if parsed.scheme != "https" or not parsed.hostname:
        return None
    keep = [(k, v) for k, v in parse_qsl(parsed.query) if k == "variant"]
    return urlunparse(parsed._replace(query=urlencode(keep), fragment=""))


def _extract_price(
    variant: dict[str, Any],
    product: dict[str, Any],
) -> tuple[float | None, str | None]:
    """Extract major-unit float price and ISO 4217 currency code from variant or product.

    Args:
        variant: Raw UCP variant dictionary.
        product: Parent raw UCP product dictionary.

    Returns:
        Tuple of `(major_price_float_or_none, currency_code_or_none)`.

    Side effects:
        None.
    """
    price_obj = variant.get("price")
    if not isinstance(price_obj, dict):
        price_range = product.get("price_range")
        if isinstance(price_range, dict) and isinstance(price_range.get("min"), dict):
            price_obj = price_range["min"]

    if not isinstance(price_obj, dict):
        return None, None

    currency = price_obj.get("currency")
    currency_str = str(currency).upper() if currency else None
    amount_minor = price_obj.get("amount")
    if amount_minor is None:
        return None, currency_str

    return minor_to_major_price(amount_minor, currency_str), currency_str


def _build_candidate_title(product: dict[str, Any], variant: dict[str, Any]) -> str:
    """Build a descriptive, non-empty title combining product and variant option info.

    Args:
        product: Parent raw UCP product dictionary.
        variant: Raw UCP variant dictionary.

    Returns:
        Clean human-readable candidate title string.

    Side effects:
        None.
    """
    product_title = str(product.get("title") or "").strip()
    variant_title = str(variant.get("title") or "").strip()

    if variant_title and variant_title.lower() != "default title":
        if product_title and product_title.lower() not in variant_title.lower():
            return f"{product_title} - {variant_title}"
        return variant_title

    options = variant.get("options")
    if isinstance(options, list) and options:
        opt_labels = [
            str(o.get("label")).strip()
            for o in options
            if isinstance(o, dict) and o.get("label")
        ]
        if opt_labels and product_title:
            joined = " / ".join(opt_labels)
            if joined.lower() not in product_title.lower():
                return f"{product_title} ({joined})"

    return product_title or variant_title or "Untitled Shopify Product"


def normalize_products_to_candidates(
    products: list[dict[str, Any]],
    *,
    max_candidates: int | None = None,
    only_available: bool = True,
    max_variants_per_product: int = 2,
) -> list[dict[str, Any]]:
    """Flatten UPID-grouped Shopify UCP products into contract-compliant candidate dicts.

    Limits variants taken per UPID (default 2) so a single product with 20 sizes
    does not crowd out diverse product matches before Decisions verification.

    Args:
        products: Raw `products[]` list returned by Shopify Global Catalog MCP.
        max_candidates: Optional cap on total returned candidates.
        only_available: If True, skips variants where `availability.available is False`.
        max_variants_per_product: Maximum variants emitted per UPID cluster.

    Returns:
        List of deduplicated candidate dicts strictly conforming to `$defs.candidate`
        in `contracts/run.schema.json`.

    Side effects:
        None.
    """
    candidates: list[dict[str, Any]] = []
    seen_keys: set[tuple[str | None, str | None]] = set()
    cap = max_candidates if max_candidates is not None else CONFIG.decisions_max_candidates

    for product in products:
        if not isinstance(product, dict):
            continue
        upid = product.get("id")
        variants = product.get("variants")
        if not isinstance(variants, list) or not variants:
            continue

        taken_for_product = 0
        for variant in variants:
            if not isinstance(variant, dict):
                continue
            if taken_for_product >= max_variants_per_product:
                break

            availability = variant.get("availability")
            if (
                only_available
                and isinstance(availability, dict)
                and availability.get("available") is False
            ):
                continue

            variant_id = variant.get("id")
            dedupe_key = (str(upid) if upid else None, str(variant_id) if variant_id else None)
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)

            price, currency = _extract_price(variant, product)
            title = _build_candidate_title(product, variant)
            merchant_domain = _extract_merchant_domain(variant)
            image_url = _extract_image_url(variant, product)
            product_url = _extract_product_url(variant)

            candidate = Candidate(
                title=title,
                upid=str(upid) if upid else None,
                variant_id=str(variant_id) if variant_id else None,
                merchant_domain=merchant_domain,
                price=price,
                currency=currency,
                image_url=image_url,
                product_url=product_url,
                p_same_product=None,
                p_same_variant=None,
            )
            candidates.append(candidate.to_dict())
            taken_for_product += 1

            if len(candidates) >= cap:
                return candidates

    return candidates


def search(
    query: str,
    filters: dict[str, Any] | None = None,
    *,
    cfg: AppConfig = CONFIG,
    search_catalog_fn: Any = search_catalog,
) -> list[dict[str, Any]]:
    """Search Shopify Global Catalog and return normalized candidate dicts for an item.

    Matches the agreed P2 signature in `CLAUDE.md` section 6:
    `search(query: str, filters: dict) -> list[Candidate]`.

    Args:
        query: Search query string describing the target product.
        filters: Optional filter dictionary (`max_price`, `min_price`, `currency`,
            `ships_to`, `available`, `categories`, `limit`, `max_variants_per_product`).
        cfg: Active `AppConfig`.
        search_catalog_fn: Injectable catalog search function (defaults to live
            `backend.shopify.catalog.search_catalog`).

    Returns:
        List of contract-compliant candidate dicts (`p_same_product` and
        `p_same_variant` initialized to `None` pending Decisions API verification).

    Raises:
        ValueError: If `query` is empty or whitespace.
        ShopifyCatalogError: Propagated directly if upstream Shopify search fails
            (never hidden with fabricated products).

    Side effects:
        Calls Shopify Global Catalog MCP over HTTPS and logs sanitized call
        metadata at INFO level.
    """
    cleaned_query = (query or "").strip()
    if not cleaned_query:
        raise ValueError("matching.catalog.search requires a non-empty 'query' string.")

    caller_filters = dict(filters or {})
    max_candidates = int(caller_filters.pop("limit", cfg.decisions_max_candidates))
    max_variants_per_product = int(caller_filters.pop("max_variants_per_product", 2))
    only_available = bool(caller_filters.get("available", True))

    log_function_call(
        LOGGER,
        "matching.catalog.search",
        {
            "query": cleaned_query,
            "filters": caller_filters,
            "max_candidates": max_candidates,
        },
    )

    raw_products = search_catalog_fn(
        cleaned_query,
        caller_filters,
        limit=max_candidates,
        cfg=cfg,
    )
    candidates = normalize_products_to_candidates(
        raw_products,
        max_candidates=max_candidates,
        only_available=only_available,
        max_variants_per_product=max_variants_per_product,
    )
    LOGGER.info(
        f"matching.catalog.search normalized {len(raw_products)} products into {len(candidates)} candidates"
    )
    return candidates
