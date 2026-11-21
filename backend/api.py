"""Thin glue: endpoints call each person's functions. Keep it small."""
import itertools

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from backend.matching import resolve
from backend.shopify import create_cart
from backend.video import desk_items, extract
from backend.video import preview as make_preview

app = FastAPI(title="Seen It")

RUNS: dict[str, dict] = {}
_counter = itertools.count(1)


class RunRequest(BaseModel):
    video: str | None = None
    photo: str | None = None
    mode: str = "video"
    budget: float | None = None
    request: str = ""


class PreviewRequest(BaseModel):
    run_id: str
    item_id: str


class CartRequest(BaseModel):
    run_id: str
    item_ids: list[str]


def _get_run(run_id: str) -> dict:
    if run_id not in RUNS:
        raise HTTPException(404, f"unknown run {run_id}")
    return RUNS[run_id]


def _get_item(run: dict, item_id: str) -> dict:
    for item in run["items"]:
        if item["item_id"] == item_id:
            return item
    raise HTTPException(404, f"unknown item {item_id}")


def _best(item: dict) -> dict | None:
    cands = [c for c in item.get("candidates") or [] if c.get("price") is not None]
    if item.get("status") not in ("exact", "similar") or not cands:
        return None
    return max(cands, key=lambda c: c.get("p_same_product") or 0)


def _totals(items: list[dict], budget: float | None) -> dict:
    total = sum(c["price"] for i in items if (c := _best(i)))
    return {"price": total, "within_budget": True if budget is None else total <= budget}


@app.post("/run")
def post_run(req: RunRequest) -> dict:
    if req.mode == "desk":
        items = desk_items(req.photo or "", req.request)
    else:
        items = extract(req.video or "")
    items = [resolve(i) for i in items]
    run_id = f"r_{next(_counter):03d}"
    run = {
        "run_id": run_id,
        "state": "done",
        "mode": req.mode,
        "source": {"video_id": req.video, "duration_s": None, "budget_usd": req.budget},
        "items": items,
        "totals": _totals(items, req.budget),
    }
    RUNS[run_id] = run
    return run


@app.get("/run/{run_id}")
def get_run(run_id: str) -> dict:
    return _get_run(run_id)


@app.post("/preview")
def post_preview(req: PreviewRequest) -> dict:
    item = _get_item(_get_run(req.run_id), req.item_id)
    best = _best(item)
    path = make_preview(item.get("crop_path") or "", (best or {}).get("image_url") or "")
    item["preview"] = {"image_path": path, "fidelity": 0.88, "regenerated": False}
    return {"run_id": req.run_id, "item_id": req.item_id, "preview": item["preview"]}


@app.post("/cart")
def post_cart(req: CartRequest) -> dict:
    run = _get_run(req.run_id)
    by_merchant: dict[str, list[tuple[dict, dict]]] = {}
    for item_id in req.item_ids:
        item = _get_item(run, item_id)
        best = _best(item)
        if best is None:
            raise HTTPException(422, f"item {item_id} has no purchasable match")
        by_merchant.setdefault(best["merchant_domain"], []).append((item, best))
    carts = []
    for domain, pairs in by_merchant.items():
        cart = create_cart(domain, pairs[0][1]["variant_id"], 1)
        for item, _ in pairs:
            item["cart"] = dict(cart)
        carts.append({"merchant_domain": domain, "item_ids": [i["item_id"] for i, _ in pairs], **cart})
    return {"run_id": req.run_id, "carts": carts}
