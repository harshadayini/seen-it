"""P1 probe: send ONE video to Gemini 4 Argon and answer three questions.

Does: (1) tries a YouTube URL directly, falling back to yt-dlp + Files API upload;
(2) asks for the CLAUDE.md 15b extraction JSON and checks its shape; (3) times the call
and reports rate-limit errors. Prints a summary of the answers.
Must not: print the API key, build extract(), edit other directories, or send sampling
params (temperature/topP/topK/candidateCount/thinkingBudget) to a Gemini 4 model.

Saves every run to data/probe/<timestamp>.json (gitignored): input, model, timing, usage,
raw text, parsed items and shape problems. Pass --out PATH to choose the file.

Usage: python scripts/argon_probe.py <youtube-url | local-video-path> [--no-direct] [--out PATH]
"""
import argparse
import json
import re
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend import config  # noqa: E402  (model IDs and key come only from config/.env)

from google import genai  # noqa: E402
from google.genai import errors, types  # noqa: E402

PROMPT = """You are watching a video. List every PURCHASABLE product visible in it
(furniture, decor, lighting, clothing, accessories). Do NOT list walls, floors, people,
or generic background. At most 10 items. Return ONLY a JSON array; each entry:
{"label": str,
 "attributes": {"color": str, "material": str, "category": str, "style": str},
 "timestamp_s": number,   // the single best moment in the video to see this product
 "bbox": [ymin, xmin, ymax, xmax]}  // normalized 0-1 box around the product in the frame at timestamp_s
"""
ATTR_KEYS = {"color", "material", "category", "style"}


def scrub(text: str) -> str:
    """Remove the API key from any text before printing. Returns the cleaned text."""
    key = config.GEMINI_API_KEY
    return text.replace(key, "[REDACTED]") if key else text


def describe_error(e: Exception) -> str:
    """One-line, key-free description of an exception (class, HTTP code if any, message)."""
    code = getattr(e, "code", None)
    return scrub(f"{type(e).__name__}{f' [{code}]' if code else ''}: {str(e)[:400]}")


def generate(client, video_part) -> tuple[object, float]:
    """Call Argon once with the video and PROMPT. Returns (response, seconds). Raises on failure."""
    t0 = time.monotonic()
    resp = client.models.generate_content(
        model=config.GEMINI_ARGON_MODEL,
        contents=[types.Content(role="user", parts=[video_part, types.Part(text=PROMPT)])],
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    return resp, time.monotonic() - t0


def upload(client, path: Path):
    """Upload a local file through the Files API and wait until ACTIVE. Returns the file part."""
    t0 = time.monotonic()
    f = client.files.upload(file=str(path))
    while getattr(f.state, "name", str(f.state)) == "PROCESSING":
        time.sleep(2)
        f = client.files.get(name=f.name)
    state = getattr(f.state, "name", str(f.state))
    print(f"   upload finished in {time.monotonic() - t0:.1f}s, file state: {state}")
    if state != "ACTIVE":
        raise RuntimeError(f"uploaded file not ACTIVE: {state}")
    return types.Part(file_data=types.FileData(file_uri=f.uri, mime_type=f.mime_type))


def download(url: str, outdir: Path) -> Path:
    """Download a video with yt-dlp (capped at 720p mp4) into outdir. Returns the file path."""
    import yt_dlp

    opts = {"outtmpl": str(outdir / "probe.%(ext)s"), "format": "mp4[height<=720]/best[height<=720]/best",
            "quiet": True, "no_warnings": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        print(f"   downloaded: duration={info.get('duration')}s title-length={len(info.get('title') or '')}")
        return Path(ydl.prepare_filename(info))


def check_shape(text: str) -> tuple[bool, list[str]]:
    """Parse the model output and check it against the 15b spec. Returns (ok, problems)."""
    problems: list[str] = []
    try:
        items = json.loads(re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip())
    except json.JSONDecodeError as e:
        return False, [f"not valid JSON: {e}"]
    if not isinstance(items, list):
        return False, ["top level is not a JSON array"]
    if len(items) > 10:
        problems.append(f"{len(items)} items (cap is ~10)")
    for n, it in enumerate(items):
        miss = {"label", "attributes", "timestamp_s", "bbox"} - set(it)
        if miss:
            problems.append(f"item {n}: missing {sorted(miss)}")
            continue
        if not ATTR_KEYS <= set(it["attributes"] or {}):
            problems.append(f"item {n}: attributes missing {sorted(ATTR_KEYS - set(it['attributes'] or {}))}")
        b = it["bbox"]
        if not (isinstance(b, list) and len(b) == 4 and all(isinstance(v, (int, float)) and 0 <= v <= 1 for v in b)
                and b[0] < b[2] and b[1] < b[3]):
            problems.append(f"item {n}: bbox not 4 normalized numbers [ymin,xmin,ymax,xmax]: {b}")
        if not isinstance(it["timestamp_s"], (int, float)):
            problems.append(f"item {n}: timestamp_s not a number")
    return not problems, problems


def main() -> int:
    """Run the probe. Returns process exit code (0 if a response came back, 1 otherwise)."""
    ap = argparse.ArgumentParser()
    ap.add_argument("video", help="YouTube URL or local video path")
    ap.add_argument("--no-direct", action="store_true", help="skip the direct-URL attempt")
    ap.add_argument("--out", help="where to save the result JSON (default data/probe/<timestamp>.json)")
    args = ap.parse_args()

    if not config.GEMINI_API_KEY:
        print("FAIL: GEMINI_API_KEY is not set (put it in .env)")
        return 1
    print(f"model: {config.GEMINI_ARGON_MODEL}  key: set ({len(config.GEMINI_API_KEY)} chars, not shown)")
    client = genai.Client(api_key=config.GEMINI_API_KEY)

    is_url = args.video.startswith(("http://", "https://"))
    answers: dict[str, str] = {}
    resp = secs = None
    rate_limited = False

    if is_url and not args.no_direct:
        print("\n[1] Trying the YouTube URL directly...")
        try:
            resp, secs = generate(client, types.Part(file_data=types.FileData(file_uri=args.video)))
            answers["q1"] = "YES: Argon accepted the YouTube URL directly."
        except Exception as e:  # noqa: BLE001 (probe: report every failure)
            print("   direct URL failed:", describe_error(e))
            rate_limited |= getattr(e, "code", None) == 429
            answers["q1"] = f"NO (direct URL failed: {describe_error(e)}). Falling back to yt-dlp + Files API."

    if resp is None:
        print("\n[1] Fallback: obtain file and upload through the Files API...")
        with tempfile.TemporaryDirectory() as tmp:
            try:
                path = download(args.video, Path(tmp)) if is_url else Path(args.video)
                part = upload(client, path)
                resp, secs = generate(client, part)
                answers.setdefault("q1", "n/a: input was a local file, uploaded via Files API.")
                answers["q1_upload"] = "Files API upload path works."
            except Exception as e:  # noqa: BLE001
                print("   FAILED:", describe_error(e))
                rate_limited |= getattr(e, "code", None) == 429
                answers["q3"] = f"call failed; rate limited (HTTP 429): {rate_limited}"

    print("\n=== RAW RESPONSE ===")
    ok = None
    if resp is not None:
        text = resp.text or ""
        print(scrub(text[:6000]) + ("\n...[truncated]" if len(text) > 6000 else ""))
        ok, problems = check_shape(text)
        um = resp.usage_metadata
        usage = f"prompt_tokens={getattr(um, 'prompt_token_count', None)} output_tokens={getattr(um, 'candidates_token_count', None)}"
        answers["q2"] = ("YES: valid JSON matching the 15b spec." if ok
                         else "PARTIAL/NO: " + "; ".join(problems[:6]))
        answers["q3"] = f"generate_content took {secs:.1f}s ({usage}); rate limited: {rate_limited}"
    if resp is not None:
        try:
            parsed = json.loads(re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip())
        except json.JSONDecodeError:
            parsed = None
        out = Path(args.out) if args.out else (
            Path(__file__).resolve().parent.parent / "data" / "probe" / f"{time.strftime('%Y%m%d-%H%M%S')}.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "input": args.video, "model": config.GEMINI_ARGON_MODEL, "seconds": round(secs, 1), "usage": usage,
            "shape_ok": ok, "shape_problems": problems, "items": parsed, "raw_text": text}, indent=2))
        print(f"\nsaved: {out}")
    print("\n=== ANSWERS ===")
    print("1. YouTube direct?   ", answers.get("q1", "not determined"))
    print("2. JSON spec?        ", answers.get("q2", "not determined (no response)"))
    print("3. Latency / limits? ", answers.get("q3", "not determined"))
    return 0 if resp is not None else 1


if __name__ == "__main__":
    sys.exit(main())
