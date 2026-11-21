"""P1: the second look. Re-examine a weak item in denser frames around its timestamp.

Does: when P2's resolve() finds an item only "similar" or "none", grab several frames within
+/-RELOOK_WINDOW_S seconds of the item's timestamp, send them to Gemini 4 Argon, and ask it to pick
the clearest frame, box the product tightly, and write a sharper description and catalog query.
Returns a copy of the item with a NEW crop (frames/<run>/<item_id>_relook.jpg), description,
attributes and query; resolve() then searches and checks again once and decides `recovered`.
Must not: search Shopify or score candidates (P2), set `recovered` or `status` itself, invent a
better answer when Argon cannot see the product (it returns the item unchanged), or print the key.
A failure never raises: the original item comes back unchanged and the failure is logged.
"""
import json
import logging
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from backend import config
from backend.video.extract import (ExtractError, _crop_frame, _grab_frame, _scrub, _valid_bbox,
                                   build_query, ensure_local)

Item = dict[str, Any]
log = logging.getLogger("seen_it.relook")

RELOOK_WINDOW_S = 2.0   # CLAUDE.md section 4: +/-2 seconds
RELOOK_STEP_S = 0.5     # denser than the first pass (which used one frame per item)
MAX_RELOOK_FRAMES = 9

PROMPT = """These are {n} frames from one video, in order, taken at {times} seconds.
I am looking for this product: {description} (attributes: {attributes}).
A first search for it did not find a confident match in the shopping catalog.
Pick the ONE frame where the product is clearest and largest, then describe exactly what you can
now see. Do not guess a brand or model name unless it is clearly readable on the product. Return ONLY a JSON object:
{{"visible": bool,                      // false if the product is not clearly visible in any frame
 "frame": int,                          // 0-based index of the frame you chose
 "bbox": [ymin, xmin, ymax, xmax],      // tight box on that frame, integers normalized 0-1000
 "description": str,                    // one specific sentence: shape, finish, notable details
 "attributes": {{"color": str, "material": str, "category": str, "style": str}},
 "query": str}}                         // 3-7 word catalog search query, product type first
"""


def frame_times(ts: float, window: float = RELOOK_WINDOW_S, step: float = RELOOK_STEP_S) -> list[float]:
    """Timestamps (seconds) to sample around ts: ts-window to ts+window every step, never below 0.

    Args: ts: item timestamp; window/step: seconds. Returns: sorted unique times, at most MAX_RELOOK_FRAMES,
    keeping the ones nearest ts when trimming.
    """
    n = int(round(window / step))
    times = sorted({round(max(0.0, ts + k * step), 3) for k in range(-n, n + 1)})
    if len(times) > MAX_RELOOK_FRAMES:
        times = sorted(sorted(times, key=lambda t: abs(t - ts))[:MAX_RELOOK_FRAMES])
    return times


def parse_relook(text: str, n_frames: int) -> dict | None:
    """Parse and validate Argon's relook answer.

    Args: text: the model's JSON object; n_frames: how many frames were sent.
    Returns: {"frame", "bbox" (0-1), "description", "attributes", "query"} or None if the product was
    not visible, the JSON is malformed, or the frame index or box is invalid.
    """
    try:
        d = json.loads(re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip())
    except json.JSONDecodeError:
        return None
    if not isinstance(d, dict) or d.get("visible") is not True:
        return None
    frame, bbox = d.get("frame"), d.get("bbox")
    if not (isinstance(frame, int) and 0 <= frame < n_frames):
        return None
    if not (isinstance(bbox, list) and len(bbox) == 4 and all(isinstance(v, (int, float)) for v in bbox)):
        return None
    box = [v / 1000 for v in bbox]
    q = d.get("query")
    if not _valid_bbox(box) or not (isinstance(q, str) and 1 <= len(q.strip()) <= 100):
        return None
    attrs = d.get("attributes") if isinstance(d.get("attributes"), dict) else {}
    desc = d.get("description") if isinstance(d.get("description"), str) and d["description"].strip() else None
    return {"frame": frame, "bbox": box, "description": desc, "attributes": attrs, "query": " ".join(q.split())}


def _ask_argon(frames: list[Path], times: list[float], item: Item) -> str:
    """Send the frames and the item description to Argon. Returns the response text.

    Side effects: one Argon call, logged at INFO. No sampling params (AGENT_RULES). Raises on API failure.
    """
    from google import genai
    from google.genai import types

    prompt = PROMPT.format(n=len(frames), times=", ".join(f"{t:g}" for t in times),
                           description=item.get("description") or item.get("query") or "the product",
                           attributes=json.dumps(item.get("attributes") or {}))
    parts = [types.Part.from_bytes(data=f.read_bytes(), mime_type="image/jpeg") for f in frames]
    parts.append(types.Part(text=prompt))
    client = genai.Client(api_key=config.GEMINI_API_KEY)
    t0 = time.monotonic()
    resp = client.models.generate_content(
        model=config.GEMINI_ARGON_MODEL,
        contents=[types.Content(role="user", parts=parts)],
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    log.info("relook argon call item=%s frames=%d seconds=%.1f", item.get("item_id"), len(frames), time.monotonic() - t0)
    return resp.text or ""


def relook(item: Item, video_path: str, ask=None) -> Item:
    """Take a second, denser look at a weak item and return a sharper copy of it.

    Args: item: contract item with t_start, crop_path, description, attributes and query;
    video_path: local file or URL of the source video (a URL reuses extract()'s cached download);
    ask: function(frames, times, item) -> response text, defaults to the Argon call (tests pass a fake).
    Returns: a copy with a new crop_path, description, attributes, query and t_start/t_end set to the
    chosen frame's time. If the product is not visible, Argon fails, or a frame cannot be read, returns
    `item` unchanged. Never sets status or recovered. Side effects: one Argon call, writes
    frames/<run>/<item_id>_relook.jpg, temp frames are removed.
    """
    ask = ask or _ask_argon
    item_id = item.get("item_id", "unknown")
    ts = item.get("t_start")
    crop_rel = item.get("crop_path")
    if not isinstance(ts, (int, float)) or not crop_rel:
        log.warning("relook skipped for %s: no timestamp or crop", item_id)
        return item
    try:
        video = ensure_local(video_path)
        times = frame_times(float(ts))
        with tempfile.TemporaryDirectory() as tmp:
            frames, kept = [], []
            for n, t in enumerate(times):
                f = Path(tmp) / f"f{n}.jpg"
                if _grab_frame(video, t, f):
                    frames.append(f)
                    kept.append(t)
            if not frames:
                log.warning("relook skipped for %s: no frames could be read near %.1fs", item_id, ts)
                return item
            parsed = parse_relook(ask(frames, kept, item), len(frames))
            if parsed is None:
                log.info("relook %s: product not clearly visible or answer unusable; item unchanged", item_id)
                return item
            new_rel = str(Path(crop_rel).with_name(f"{item_id}_relook.jpg"))
            out = config.ROOT / new_rel
            if not _crop_frame(frames[parsed["frame"]], parsed["bbox"], out):
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(frames[parsed["frame"]], out)  # no usable crop: keep the clearer full frame
            chosen = kept[parsed["frame"]]
    except (ExtractError, OSError) as e:
        log.warning("relook failed for %s (%s); item unchanged", item_id, _scrub(f"{type(e).__name__}: {str(e)[:200]}"))
        return item
    except Exception as e:  # noqa: BLE001  a failed second look must never sink the run
        log.warning("relook failed for %s (%s); item unchanged", item_id, _scrub(f"{type(e).__name__}: {str(e)[:200]}"))
        return item

    new = dict(item)
    new.update({
        "crop_path": new_rel,
        "t_start": chosen, "t_end": chosen,
        "description": parsed["description"] or item.get("description"),
        "attributes": {**(item.get("attributes") or {}), **parsed["attributes"]},
        "query": parsed["query"] or build_query(item.get("description") or "", item.get("attributes") or {}),
    })
    log.info("relook %s: query %r -> %r, frame at %.1fs", item_id, item.get("query"), new["query"], chosen)
    return new
