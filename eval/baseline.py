"""P1: the single-shot baseline we compare Seen It against.

Does: takes ONE frame from the middle of the video, makes ONE Gemini call asking what products are in it, searches the
Shopify catalog once per product with just that label, and keeps the top result. No boxes, no second pass, no query
rewriting, no Decisions check, no second look: the "just ask a model and take the first hit" approach.
Must not: call the Decisions API or relook, print the API key, or invent results (a failed call raises).
Usage: .venv/bin/python -m eval.baseline <video url or path> [out.json]
"""
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from backend import config
from backend.matching.catalog import search
from backend.video.extract import ensure_local

PROMPT = ('List every PURCHASABLE product visible in this single image (furniture, decor, lighting, electronics, '
          'accessories; not walls, floors or people), at most 10. Return ONLY a JSON array of short product names, '
          'for example ["black desk lamp", "wireless mouse"].')


def middle_frame(video: Path, out: Path) -> float:
    """Save the middle frame of the video as a jpg. Returns the timestamp used (seconds)."""
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
                       capture_output=True, text=True)
    t = float(r.stdout.strip() or 2.0) / 2
    subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1", "-q:v", "2", "-y",
                    str(out)], check=True)
    return t


def ask_labels(frame: Path) -> list[str]:
    """One Argon call on the middle frame. Returns the product names it listed (capped at 10)."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=config.GEMINI_API_KEY)
    resp = client.models.generate_content(
        model=config.GEMINI_ARGON_MODEL,
        contents=[types.Part.from_bytes(data=frame.read_bytes(), mime_type="image/jpeg"), PROMPT],
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    data = json.loads(re.sub(r"^```(?:json)?|```$", "", (resp.text or "").strip(), flags=re.M).strip())
    return [str(x) for x in data if isinstance(x, str)][:10]


def run_baseline(video: str) -> dict:
    """Run the baseline on one video. Returns {"seconds", "frame_t", "items": [{label, top: candidate or None}]}."""
    t0 = time.monotonic()
    local = ensure_local(video)
    with tempfile.TemporaryDirectory() as tmp:
        frame = Path(tmp) / "mid.jpg"
        t = middle_frame(local, frame)
        labels = ask_labels(frame)
    items = []
    for label in labels:
        hits = search(label, {})
        items.append({"label": label, "top": hits[0] if hits else None})
    return {"seconds": round(time.monotonic() - t0, 1), "frame_t": round(t, 2), "items": items}


if __name__ == "__main__":
    result = run_baseline(sys.argv[1])
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(json.dumps(result, indent=2))
    print(json.dumps({"seconds": result["seconds"], "items": len(result["items"])}))
