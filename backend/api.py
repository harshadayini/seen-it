"""Thin glue: endpoints call each person's functions. Keep it small."""
import copy
import itertools
import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend import config

from backend.matching import resolve
from backend.matching.status import STATUS_RANK
from backend.shopify import create_cart
from backend.shopify.cart import CartError, update_cart
from backend.video import desk_items, extract
from backend.video.relook import relook
from backend.video.preview import PreviewError, make_preview



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
config.PREVIEWS_DIR.mkdir(exist_ok=True)
app.mount("/frames", StaticFiles(directory=config.FRAMES_DIR), name="frames")
app.mount("/previews", StaticFiles(directory=config.PREVIEWS_DIR), name="previews")

RUNS: dict[str, dict] = {}
_STARTED: dict[str, tuple] = {}  # run_id -> (request key, start time), for duplicate-request detection
_counter = itertools.count(1)
# Items resolved at once. Kept small: Gemini calls are capped near 5 (AGENT_RULES 3.4) and the
# Shopify catalog rate-limits (its client retries 429s with backoff).
RESOLVE_WORKERS = 4
RELOOK_WORKERS = 3
RUN_TIME_BUDGET_S = float(os.getenv("RUN_TIME_BUDGET_S", "45"))  # no new second looks after this many seconds
DEDUPE_WINDOW_S = 180  # a repeated POST /run for the same input returns the run already in progress
SAVED_RUNS_DIR = config.ROOT / "fixtures" / "saved_runs"
_SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class RunRequest(BaseModel):
    video: str | None = None
    photo: str | None = None
    mode: str = "video"
    budget: float | None = None
    request: str = ""


class ReplayRequest(BaseModel):
    run_id: str


class PreviewRequest(BaseModel):
    run_id: str
    item_id: str
    scene_image: str | None = None  # optional data URL (camera capture or upload); default is the item's video frame
    retry_if_low: bool = False      # regenerate once if the fidelity is below the bar (doubles the time); eval uses it


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
    t_start = time.monotonic()
    try:
        if req.mode == "desk":
            found = desk_items(req.photo or "", req.request)
        else:
            t0 = time.monotonic()
            found = extract(req.video or "", run_id)
            log.info("stage=extract run=%s seconds=%.1f items=%d", run_id, time.monotonic() - t0, len(found))
        items = [{**i, "state": "processing"} for i in found]
        run["items"] = list(items)
        run["totals"] = _totals(items, req.budget)

        def first_pass(n: int, item: dict) -> tuple[int, dict, float]:
            """Search + check one item WITHOUT the second look, so its card can show right away."""
            t1 = time.monotonic()
            try:
                out = resolve(item, video_path=req.video, enable_relook=False)  # keeps its own state
            except Exception as e:  # noqa: BLE001  one bad item must not sink the run
                log.warning("resolve failed for %s: %s", item.get("item_id"), type(e).__name__)
                out = {**item, "state": "failed"}
            return n, out, time.monotonic() - t1

        def publish(n: int, out: dict) -> None:
            """Replace one slot and refresh the run. Only the main thread calls this."""
            items[n] = out
            run["items"] = list(items)
            run["totals"] = _totals(items, req.budget)

        t_resolve = time.monotonic()
        with ThreadPoolExecutor(max_workers=RESOLVE_WORKERS) as pool:
            for fut in as_completed([pool.submit(first_pass, n, i) for n, i in enumerate(found)]):
                n, out, secs = fut.result()
                publish(n, out)
                log.info("stage=first_pass run=%s item=%s seconds=%.1f status=%s state=%s", run_id,
                         found[n].get("item_id"), secs, out.get("status"), out.get("state"))
        log.info("stage=first_pass_all run=%s seconds=%.1f workers=%d", run_id, time.monotonic() - t_resolve,
                 RESOLVE_WORKERS)

        # Second look (relook) for weak items, inside the time budget. The first-pass result is already
        # visible; a second look only replaces it when the status improves, so it can never make things worse.
        if req.mode == "video" and req.video:
            def second_look(n: int, first: dict) -> tuple[int, dict | None]:
                """Re-look one weak item; return the improved item, or None to keep the first pass."""
                if time.monotonic() - t_start > RUN_TIME_BUDGET_S:
                    log.info("stage=second_look run=%s item=%s skipped: time budget used", run_id, first.get("item_id"))
                    return n, None
                try:
                    looked = relook(first, req.video)
                    if looked.get("crop_path") == first.get("crop_path") and looked.get("query") == first.get("query"):
                        return n, None
                    better = resolve(looked, video_path=req.video, enable_relook=False, force=True)
                except Exception as e:  # noqa: BLE001
                    log.warning("second look failed for %s: %s", first.get("item_id"), type(e).__name__)
                    return n, None
                if STATUS_RANK[better.get("status")] > STATUS_RANK[first.get("status")]:
                    return n, {**better, "recovered": True, "state": "done"}
                return n, None

            weak = [(n, it) for n, it in enumerate(items) if it.get("status") in ("similar", "none")]
            t_second = time.monotonic()
            with ThreadPoolExecutor(max_workers=RELOOK_WORKERS) as pool:
                for fut in as_completed([pool.submit(second_look, n, it) for n, it in weak]):
                    n, better = fut.result()
                    if better is not None:
                        publish(n, better)
                        log.info("stage=second_look run=%s item=%s recovered %s", run_id, found[n].get("item_id"),
                                 better.get("status"))
            log.info("stage=second_look_all run=%s items=%d seconds=%.1f", run_id, len(weak), time.monotonic() - t_second)
        run["state"] = "done"
    except Exception as e:  # noqa: BLE001
        log.error("run %s failed: %s", run_id, type(e).__name__)
        run["state"] = "failed"
        run["error"] = f"{type(e).__name__}: {str(e)[:300]}"


@app.post("/run")
def post_run(req: RunRequest, background: BackgroundTasks) -> dict:
    """Start a run and return at once with state "processing"; poll GET /run/<id> for the items."""
    key = (req.mode, req.video or req.photo, req.budget, req.request)
    for old_id, started in list(_STARTED.items()):
        old = RUNS.get(old_id)
        if old and old["state"] == "processing" and started[0] == key and time.monotonic() - started[1] < DEDUPE_WINDOW_S:
            log.info("duplicate POST /run for %s: returning %s", key[1], old_id)
            return dict(old)
    run_id = f"r_{next(_counter):03d}"
    _STARTED[run_id] = (key, time.monotonic())
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


@app.post("/run/replay")
def post_run_replay(req: ReplayRequest) -> dict:
    """Load a saved finished run from fixtures/saved_runs/<run_id>.json as a new finished run.

    A fallback for when a live run fails. The copy gets a fresh run_id so it never overwrites a live
    run; it is already "done", so GET /run/<id> and /preview and /cart work on it as usual.
    """
    if not _SAFE_RUN_ID.match(req.run_id):
        raise HTTPException(422, "invalid run_id")
    path = SAVED_RUNS_DIR / f"{req.run_id}.json"
    if not path.is_file():
        raise HTTPException(404, f"no saved run {req.run_id}")
    saved = json.loads(path.read_text())
    if saved.get("state") not in ("done", "failed"):
        raise HTTPException(422, f"saved run {req.run_id} is not finished")
    run = copy.deepcopy(saved)
    run["run_id"] = f"r_{next(_counter):03d}"
    RUNS[run["run_id"]] = run
    log.info("replay saved=%s as=%s items=%d", req.run_id, run["run_id"], len(run.get("items", [])))
    return run


@app.get("/run/{run_id}")
def get_run(run_id: str) -> dict:
    return _get_run(run_id)


def _save_scene(data_url: str, run_id: str, item_id: str) -> str:
    """Decode a data URL image (a camera capture) into previews/<run>/<item>_scene.jpg. Returns the repo-relative path."""
    import base64
    import re

    m = re.match(r"^data:image/(?:jpeg|jpg|png|webp);base64,(.+)$", data_url, re.S)
    if not m:
        raise HTTPException(422, "scene_image must be a base64 data URL (jpeg, png or webp)")
    try:
        raw = base64.b64decode(m.group(1), validate=False)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(422, "scene_image is not valid base64") from e
    if not (100 < len(raw) <= 8_000_000):
        raise HTTPException(422, "scene_image is empty or larger than 8 MB")
    rel = f"previews/{run_id}/{item_id}_scene.jpg"
    (config.ROOT / rel).parent.mkdir(parents=True, exist_ok=True)
    (config.ROOT / rel).write_bytes(raw)
    return rel


@app.post("/preview")
def post_preview(req: PreviewRequest) -> dict:
    """Place the item's matched product into a scene (the camera capture if sent, else its video frame) and check it.

    Takes about 17 s (image model, then the Decisions check); about double with retry_if_low. Returns the preview with its measured fidelity, or null
    fidelity when the check could not run. A failure returns 502 with a clear message and never a fake image.
    """
    item = _get_item(_get_run(req.run_id), req.item_id)
    best = _best(item)
    if best is None or not best.get("image_url"):
        raise HTTPException(422, f"item {req.item_id} has no matched product image to place")
    scene = _save_scene(req.scene_image, req.run_id, req.item_id) if req.scene_image else item.get("frame_path")
    if not scene:
        raise HTTPException(422, f"item {req.item_id} has no scene image; send scene_image")
    try:
        item["preview"] = make_preview(scene, best["image_url"], req.run_id, req.item_id, retry_if_low=req.retry_if_low)
    except PreviewError as e:
        raise HTTPException(502, str(e)) from e
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
        try:
            cart = create_cart(domain, pairs[0][1]["variant_id"], 1)
            if len(pairs) > 1:  # every extra item from the same store goes into the same cart
                cart = update_cart(domain, cart["cart_id"], [{"quantity": 1, "item": {"id": b["variant_id"]}} for _, b in pairs])
        except CartError as exc:  # clean structured error, never a fake cart
            raise HTTPException(502, {"error": exc.code, "message": exc.message, "merchant_domain": domain})
        for item, _ in pairs:
            item["cart"] = dict(cart)
        carts.append({"merchant_domain": domain, "item_ids": [i["item_id"] for i, _ in pairs], **cart})
    return {"run_id": req.run_id, "carts": carts}
