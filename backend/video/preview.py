"""P1: "See it here". Place a matched Shopify product into the user's own scene, then check the result.

Does: shrinks the scene photo and the product's listing photo (about 4x faster generation), asks the Gemini
image model to add the product to the scene (everything else unchanged), saves the composite under
previews/<run_id>/<item_id>.jpg, then asks the Decisions API two questions about the result: does the added
product look like the reference, and is the rest of the scene preserved. If the score is below
config.PREVIEW_MIN_FIDELITY it regenerates ONCE and keeps the better of the two.
Must not: save, cache or re-host the merchant's photo (it lives in memory for this call only; only the generated
composite is written), report a fidelity it did not measure (an unavailable check returns fidelity None), print
the API key, or send sampling params (AGENT_RULES). A failure raises PreviewError with a clean message.
"""
import base64
import logging
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable

from backend import config

log = logging.getLogger("seen_it.preview")

MAX_SCENE_WIDTH = 512        # smaller inputs cut generation from ~58 s to ~14 s in testing
MAX_IMAGE_BYTES = 8_000_000  # cap for any downloaded or uploaded image
PROMPT = (
    "IMAGE 1 is the user's scene. IMAGE 2 is only a product reference photo: use it ONLY to learn what the "
    "product looks like (shape, color, finish). IGNORE IMAGE 2's background and room completely. "
    "Output IMAGE 1 with that product added into it at a believable place and scale, with matching perspective, "
    "lighting and shadows. Everything else in IMAGE 1 (the room, objects, people) must stay exactly as it is. "
    "The output must look like IMAGE 1, not IMAGE 2."
)


class PreviewError(RuntimeError):
    """The preview could not be made (bad image, upstream failure). The message never contains the key."""


def shrink(data: bytes, max_w: int = MAX_SCENE_WIDTH) -> bytes:
    """Return the image as a JPEG no wider than max_w pixels (aspect kept), using ffmpeg through pipes.

    Args: data: any image bytes; max_w: pixel cap. Returns: JPEG bytes; the original bytes if ffmpeg fails.
    """
    cmd = ["ffmpeg", "-v", "error", "-i", "pipe:0", "-vf", f"scale='min({max_w},iw)':-2", "-frames:v", "1",
           "-f", "image2", "-c:v", "mjpeg", "pipe:1"]
    try:
        r = subprocess.run(cmd, input=data, capture_output=True, timeout=30)
        return r.stdout if r.returncode == 0 and r.stdout else data
    except (OSError, subprocess.SubprocessError):
        return data


def _fetch_image(url: str) -> bytes:
    """Download a product photo into memory (never to disk). Raises PreviewError for a bad URL, size or type."""
    if not url.startswith(("http://", "https://")):
        raise PreviewError("the matched product has no usable image URL")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310  scheme checked above
            data = r.read(MAX_IMAGE_BYTES + 1)
    except Exception as e:  # noqa: BLE001
        raise PreviewError(f"could not download the product photo ({type(e).__name__})") from e
    if len(data) > MAX_IMAGE_BYTES or len(data) < 100:
        raise PreviewError("the product photo is empty or too large")
    return data


def _generate(scene: bytes, product: bytes) -> bytes:
    """One call to the Gemini image model. Returns the composite's image bytes; raises PreviewError."""
    from google import genai
    from google.genai import types

    if not config.GEMINI_API_KEY or not config.GEMINI_IMAGE_MODEL:
        raise PreviewError("GEMINI_API_KEY or GEMINI_IMAGE_MODEL is not set")
    t0 = time.monotonic()
    try:
        client = genai.Client(api_key=config.GEMINI_API_KEY)
        resp = client.models.generate_content(
            model=config.GEMINI_IMAGE_MODEL,
            contents=[types.Part.from_bytes(data=scene, mime_type="image/jpeg"),
                      types.Part.from_bytes(data=product, mime_type="image/jpeg"), PROMPT],
            config=types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"]),
        )
    except Exception as e:  # noqa: BLE001
        msg = str(e).replace(config.GEMINI_API_KEY, "[REDACTED]")[:200]
        raise PreviewError(f"image model call failed: {type(e).__name__}: {msg}") from e
    log.info("preview generate model=%s seconds=%.1f", config.GEMINI_IMAGE_MODEL, time.monotonic() - t0)
    for cand in resp.candidates or []:
        for part in (cand.content.parts if cand.content else []):
            inline = getattr(part, "inline_data", None)
            if inline and inline.data:
                return inline.data
    raise PreviewError("the image model returned no image")


def _block(data: bytes) -> dict[str, Any]:
    """A Decisions API image input block (low resolution keeps the check fast)."""
    return {"type": "image", "data": base64.b64encode(data).decode("ascii"), "mime_type": "image/jpeg",
            "resolution": "low"}


def check_fidelity(scene: bytes, product: bytes, result: bytes, invoke: Callable | None = None) -> float | None:
    """Score a composite with the Decisions API. Returns min(product looks right, scene preserved) in 0-1, or None.

    Args: scene/product/result: JPEG bytes (original scene, reference photo, generated composite); invoke: the
    Decisions call, defaults to the matching package's helper (tests pass a fake). Returns None, and logs why,
    when the check cannot run (for example the API rejects several images). Never invents a score.
    """
    try:
        if invoke is None:
            from backend.matching.checker import _invoke_decisions_api as invoke  # shared Decisions call
        blocks = [{"type": "text", "text": "ORIGINAL SCENE:\n"}, _block(scene),
                  {"type": "text", "text": "\nREFERENCE PRODUCT PHOTO:\n"}, _block(product),
                  {"type": "text", "text": "\nGENERATED SCENE (original with the product added):\n"}, _block(result)]
        questions = {
            "product_matches": {"type": "noul",
                                "instructions": "Does the product that was added in the GENERATED SCENE look like the "
                                                "REFERENCE PRODUCT PHOTO (same shape, color and finish)?",
                                "criteria": {"true_description": "Same product shape, color and finish.",
                                             "false_description": "A different-looking product, or none was added."}},
            "scene_preserved": {"type": "noul",
                                "instructions": "Apart from the added product, is the GENERATED SCENE the same room and "
                                                "objects as the ORIGINAL SCENE?",
                                "criteria": {"true_description": "Same room, objects and layout.",
                                             "false_description": "The scene was changed or replaced."}},
        }
        answers = invoke(input_blocks=blocks, questions=questions, cfg=config.CONFIG)[0].get("answers", {})
        probs = []
        for key in questions:
            raw = (answers.get(key) or {}).get("noul")
            if not isinstance(raw, (int, float)) or isinstance(raw, bool):
                return None
            probs.append(max(0.0, min(1.0, float(raw))))
        return round(min(probs), 4)
    except Exception as e:  # noqa: BLE001
        log.warning("fidelity check unavailable (%s)", f"{type(e).__name__}: {str(e)[:160]}")
        return None


def make_preview(scene_path: str, product_image_url: str, run_id: str, item_id: str,
                 generate: Callable | None = None, fetch: Callable | None = None,
                 check: Callable | None = None) -> dict:
    """Make and check a preview of a product in a scene.

    Args: scene_path: the user's scene image (path relative to the repo root, or absolute); product_image_url: the
    matched Shopify listing photo; run_id/item_id: name previews/<run_id>/<item_id>.jpg; generate, fetch, check:
    injectable for tests. Returns {"image_path", "fidelity" (0-1 or None when unchecked), "regenerated"}.
    Side effects: up to two image-model calls and two Decisions calls; writes one jpg. Raises PreviewError.
    """
    generate, fetch, check = generate or _generate, fetch or _fetch_image, check or check_fidelity
    scene_file = Path(scene_path) if Path(scene_path).is_absolute() else config.ROOT / scene_path
    if not scene_file.is_file():
        raise PreviewError("the scene image is missing")
    scene = shrink(scene_file.read_bytes())
    product = shrink(fetch(product_image_url))  # in memory only
    best_bytes, best_score, regenerated = b"", None, False
    for attempt in (1, 2):
        out = generate(scene, product)
        score = check(scene, product, out)
        if not best_bytes or (score or 0) > (best_score or 0):
            best_bytes, best_score = out, score
        if score is None or score >= config.PREVIEW_MIN_FIDELITY or attempt == 2:
            break
        regenerated = True  # below the bar on the first try: generate once more and keep the better
        log.info("preview %s fidelity %.2f below %.2f; regenerating", item_id, score, config.PREVIEW_MIN_FIDELITY)
    rel = f"previews/{run_id}/{item_id}.jpg"
    path = config.ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(best_bytes)
    log.info("preview %s saved fidelity=%s regenerated=%s", item_id, best_score, regenerated)
    return {"image_path": rel, "fidelity": best_score, "regenerated": regenerated}


def preview(frame_path: str, product_image_url: str) -> str:
    """CLAUDE.md signature: make a preview and return its image path (use make_preview for the fidelity too)."""
    return make_preview(frame_path, product_image_url, "adhoc", Path(frame_path).stem)["image_path"]
