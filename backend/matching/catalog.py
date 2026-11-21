"""P2 stub. TODO: Shopify Catalog search wrapper."""
from backend.fixture import load_items


def search(query: str, filters: dict) -> list[dict]:
    return load_items()[0]["candidates"]
