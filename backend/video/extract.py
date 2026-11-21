"""P1: find purchasable items in a video with Gemini 4 Argon, then crop each one.

Does: send the video to Argon (CLAUDE.md 15b spec), parse the JSON, cut the frame at each
item's timestamp with ffmpeg, crop it to the normalized bbox, save frames/<run_id>/<item_id>.jpg
and return Items shaped like fixtures/sample_run.json.
Must not: match products or call Shopify/Decisions (that is P2), invent items when the call
fails (raise ExtractError instead), print or return the API key, or send sampling params
(temperature/topP/topK/candidateCount/thinkingBudget) to a Gemini 4 model.
"""
import json
import logging
import re
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from backend import config
from backend.fixture import load_items

Item = dict[str, Any]  # shape: fixtures/sample_run.json items
log = logging.getLogger("seen_it.extract")

MAX_ITEMS = 10
PROMPT = """You are watching a video. List every PURCHASABLE product visible in it
(furniture, decor, lighting, clothing, accessories). Do NOT list walls, floors, people,
or generic background. At most 10 items. Return ONLY a JSON array; each entry:
{"label": str,
 "attributes": {"color": str, "material": str, "category": str, "style": str},
 "timestamp_s": number,   // the single best moment in the video to see this product
 "bbox": [ymin, xmin, ymax, xmax]}  // normalized 0-1 box around the product in the frame at timestamp_s
"""


class ExtractError(RuntimeError):
    """Extraction failed (upstream call, download or ffmpeg). The message never contains the key."""


def _scrub(text: str) -> str:
    """Remove the API key from text before it is logged or raised. Returns the cleaned text."""
    key = config.GEMINI_API_KEY
    return text.replace(key, "[REDACTED]") if key else text


def build_query(label: str, attributes: dict) -> str:
    """Build a catalog search query from label + color + material, without repeating words.

    Args: label: product label; attributes: dict that may hold "color" and "material".
    Returns: the query string, e.g. "black arc floor lamp metal".
    """
    words: list[str] = []
    for part in (attributes.get("color"), label, attributes.get("material")):
        for w in re.findall(r"[\w'-]+", (part or "").lower()):
            if w not in words and w not in ("and", "with", "on"):
                words.append(w)
    return " ".join(words)


def _valid_bbox(b) -> bool:
    """True if b is [ymin, xmin, ymax, xmax], four numbers in 0-1 with min below max."""
    return (isinstance(b, list) and len(b) == 4 and all(isinstance(v, (int, float)) and 0 <= v <= 1 for v in b)
            and b[0] < b[2] and b[1] < b[3])


def parse_items(text: str) -> list[dict]:
    """Parse Argon's response text into valid raw entries, dropping malformed ones.

    Args: text: the model's JSON (code fences tolerated). Returns: at most MAX_ITEMS entries
    that have a label, attributes, numeric timestamp_s and a valid bbox. Raises ExtractError
    if the text is not a JSON array.
    """
    try:
        data = json.loads(re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip())
    except json.JSONDecodeError as e:
        raise ExtractError(f"Argon response is not valid JSON: {e}") from e
    if not isinstance(data, list):
        raise ExtractError("Argon response is not a JSON array")
    good = []
    for n, e in enumerate(data):
        if (isinstance(e, dict) and e.get("label") and isinstance(e.get("attributes"), dict)
                and isinstance(e.get("timestamp_s"), (int, float)) and _valid_bbox(e.get("bbox"))):
            good.append(e)
        else:
            log.warning("dropping malformed Argon entry %d", n)
    return good[:MAX_ITEMS]


def pad_bbox(bbox: list[float], pad: float) -> list[float]:
    """Grow [ymin, xmin, ymax, xmax] outward by pad x the box's own height/width, clamped to 0-1.

    Args: bbox: normalized box; pad: fraction per side (0.10 = 10%). Returns: the padded box.
    """
    ymin, xmin, ymax, xmax = bbox
    dy, dx = (ymax - ymin) * pad, (xmax - xmin) * pad
    return [max(0.0, ymin - dy), max(0.0, xmin - dx), min(1.0, ymax + dy), min(1.0, xmax + dx)]


def _crop(video: Path, ts: float, bbox: list[float], out: Path) -> bool:
    """Cut one frame at ts seconds and crop it to bbox (padded by config.CROP_PADDING) with ffmpeg. Returns True if out was written.

    Side effects: creates out's folder and writes the jpg.
    """
    ymin, xmin, ymax, xmax = pad_bbox(bbox, config.CROP_PADDING)
    vf = f"crop=iw*{xmax - xmin:.4f}:ih*{ymax - ymin:.4f}:iw*{xmin:.4f}:ih*{ymin:.4f}"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{ts:.3f}", "-i", str(video), "-frames:v", "1",
           "-vf", vf, "-q:v", "2", "-y", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not out.exists():
        log.warning("ffmpeg could not crop frame at %.2fs: %s", ts, r.stderr.strip()[:200])
        return False
    return True


def items_from_response(text: str, video: Path, run_id: str) -> list[Item]:
    """Turn Argon's response text plus the local video into Items with crops on disk.

    Args: text: Argon JSON; video: local video file for ffmpeg; run_id: names the frames folder.
    Returns: Items (status None until P2's resolve). Entries whose crop fails are skipped.
    Side effects: writes frames/<run_id>/<item_id>.jpg.
    """
    items: list[Item] = []
    for e in parse_items(text):
        item_id = f"i{len(items) + 1}"
        crop_rel = f"frames/{run_id}/{item_id}.jpg"
        if not _crop(video, float(e["timestamp_s"]), e["bbox"], config.ROOT / crop_rel):
            continue
        ts = float(e["timestamp_s"])
        items.append({
            "item_id": item_id, "state": "done",
            "t_start": ts, "t_end": ts,  # Argon gives one best moment, not a span
            "crop_path": crop_rel,
            "description": e["label"],
            "attributes": e["attributes"],
            "query": build_query(e["label"], e["attributes"]),
            "candidates": [], "status": None, "recovered": False,
            "preview": None, "cart": {"cart_id": None, "continue_url": None},
        })
    return items


def _download(url: str, outdir: Path) -> Path:
    """Download a video with yt-dlp (max 720p) into outdir. Returns the file path."""
    import yt_dlp

    opts = {"outtmpl": str(outdir / "video.%(ext)s"), "format": "mp4[height<=720]/best[height<=720]/best",
            "quiet": True, "no_warnings": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        return Path(ydl.prepare_filename(ydl.extract_info(url, download=True)))


def _call_argon(source: str, local: Path | None) -> str:
    """Ask Argon for the item JSON. Returns the response text; raises ExtractError on failure.

    Tries a YouTube/http URL directly; if that fails (or the source is a local file) uploads
    `local` through the Files API. Side effects: one or two Gemini calls, logged at INFO.
    """
    from google import genai
    from google.genai import types

    if not config.GEMINI_API_KEY:
        raise ExtractError("GEMINI_API_KEY is not set")
    client = genai.Client(api_key=config.GEMINI_API_KEY)

    def ask(part) -> str:
        t0 = time.monotonic()
        resp = client.models.generate_content(
            model=config.GEMINI_ARGON_MODEL,
            contents=[types.Content(role="user", parts=[part, types.Part(text=PROMPT)])],
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        log.info("argon call model=%s seconds=%.1f response_chars=%d",
                 config.GEMINI_ARGON_MODEL, time.monotonic() - t0, len(resp.text or ""))
        return resp.text or ""

    try:
        if source.startswith(("http://", "https://")):
            try:
                return ask(types.Part(file_data=types.FileData(file_uri=source)))
            except Exception as e:  # noqa: BLE001
                log.warning("direct URL failed (%s); falling back to Files API", _scrub(str(e))[:200])
        if local is None:
            raise ExtractError("no local file to upload")
        f = client.files.upload(file=str(local))
        while getattr(f.state, "name", str(f.state)) == "PROCESSING":
            time.sleep(2)
            f = client.files.get(name=f.name)
        return ask(types.Part(file_data=types.FileData(file_uri=f.uri, mime_type=f.mime_type)))
    except ExtractError:
        raise
    except Exception as e:  # noqa: BLE001
        raise ExtractError(_scrub(f"{type(e).__name__}: {str(e)[:300]}")) from e


def extract_stub(video_path: str) -> list[Item]:
    """Fixture items, used when SEEN_IT_STUBS=1 so tests never touch the network."""
    return load_items()


def extract(video_path: str, run_id: str | None = None) -> list[Item]:
    """List the purchasable items in a video, each with a saved crop.

    Args: video_path: YouTube/http URL or local file; run_id: names frames/<run_id>/
    (optional so the CLAUDE.md signature still works; defaults to a timestamp).
    Returns: Items with t_start, t_end, crop_path, description, attributes, query filled.
    Side effects: calls Argon, downloads URLs to a temp dir, writes crops under frames/.
    Raises: ExtractError on upstream, download or ffmpeg failure.
    """
    if config.USE_STUBS:
        return extract_stub(video_path)
    run_id = run_id or time.strftime("adhoc-%Y%m%d-%H%M%S")
    is_url = video_path.startswith(("http://", "https://"))
    with tempfile.TemporaryDirectory() as tmp:
        try:
            if is_url:
                with ThreadPoolExecutor(max_workers=1) as pool:  # download while Argon works
                    dl = pool.submit(_download, video_path, Path(tmp))
                    try:
                        text = _call_argon(video_path, None)
                    except ExtractError as e:
                        if "no local file" not in str(e):
                            raise
                        text = _call_argon(video_path, dl.result())
                    local = dl.result()
            else:
                local = Path(video_path)
                text = _call_argon(video_path, local)
        except ExtractError:
            raise
        except Exception as e:  # noqa: BLE001
            raise ExtractError(_scrub(f"{type(e).__name__}: {str(e)[:300]}")) from e
        items = items_from_response(text, local, run_id)
    log.info("extract run=%s items=%d", run_id, len(items))
    return items
