"""Thin glue: endpoints call each person's functions. Keep it small."""
import itertools
import logging
import time

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend import config

from backend.matching import resolve
from backend.shopify import create_cart
from backend.video import desk_items, extract
from backend.video import preview as make_preview



def _configure_logging() -> None:
    """Make INFO lines from every seen_it.* logger show in the uvicorn terminal.

    Uvicorn only configures its own loggers, so without this our INFO lines are dropped.
    Idempotent: reuses the handler matching/logging_utils may already have attached.
    """
    root = logging.getLogger("seen_it")
    root.setLevel(logging.INFO)
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        root.addHandler(handler)
    root.propagate = False


_configure_logging()
log = logging.getLogger("seen_it.api")
app = FastAPI(title="Seen It")
# The web app (Next.js dev server) runs on another port and loads crops from /frames.
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
                   allow_methods=["*"], allow_headers=["*"])
config.FRAMES_DIR.mkdir(exist_ok=True)
app.mount("/frames", StaticFiles(directory=config.FRAMES_DIR), name="frames")

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


def _process(run_id: str, req: RunRequest) -> None:
    """Fill the run in the background so GET /run/<id> shows items as they finish.

    Extracts items (state "processing"), publishes them, then resolves each one (search +
    check + status) and marks it "done" or "failed". Sets the run "done", or "failed" with an
    "error" message if extraction itself fails. Never raises: a failure is recorded on the run.
    """
    run = RUNS[run_id]
    try:
        if req.mode == "desk":
            found = desk_items(req.photo or "", req.request)
        else:
            t0 = time.monotonic()
            found = extract(req.video or "", run_id)
            log.info("stage=extract run=%s seconds=%.1f items=%d", run_id, time.monotonic() - t0, len(found))
        items = [{**i, "state": "processing"} for i in found]
        run["items"] = list(items)
        for n, item in enumerate(found):
            t1 = time.monotonic()
            try:
                items[n] = {**resolve(item, video_path=req.video), "state": "done"}
            except Exception as e:  # noqa: BLE001  one bad item must not sink the run
                log.warning("resolve failed for %s: %s", item.get("item_id"), type(e).__name__)
                items[n] = {**item, "state": "failed"}
            log.info("stage=resolve run=%s item=%s seconds=%.1f status=%s state=%s", run_id,
                     item.get("item_id"), time.monotonic() - t1, items[n].get("status"), items[n].get("state"))
            run["items"] = list(items)
            run["totals"] = _totals(items, req.budget)
        run["state"] = "done"
    except Exception as e:  # noqa: BLE001
        log.error("run %s failed: %s", run_id, type(e).__name__)
        run["state"] = "failed"
        run["error"] = f"{type(e).__name__}: {str(e)[:300]}"


@app.post("/run")
def post_run(req: RunRequest, background: BackgroundTasks) -> dict:
    """Start a run and return at once with state "processing"; poll GET /run/<id> for the items."""
    run_id = f"r_{next(_counter):03d}"
    run = {
        "run_id": run_id,
        "state": "processing",
        "mode": req.mode,
        "source": {"video_id": req.video, "duration_s": None, "budget_usd": req.budget},
        "items": [],
        "totals": {"price": 0, "within_budget": True},
    }
    RUNS[run_id] = run
    background.add_task(_process, run_id, req)
    return dict(run)


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
