"""Upload endpoint (P3): lets the web app send a local video or photo to the backend.

What it does
    POST /upload accepts one file (multipart), saves it under data/uploads/ with a random name,
    and returns its absolute path so the web app can start a run with it (POST /run {video: path}).

Boundaries and invariants
    - Only video and image extensions are accepted; the original file name is never used on disk.
    - Size is capped (MAX_BYTES) and a partial file is deleted if the cap is exceeded.
    - data/ is gitignored, so uploads are never committed. Nothing here calls Gemini or Shopify.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from backend import config

router = APIRouter()

ALLOWED = {".mp4", ".mov", ".webm", ".mkv", ".m4v", ".avi", ".jpg", ".jpeg", ".png", ".webp"}
MAX_BYTES = 400 * 1024 * 1024
UPLOAD_DIR = config.ROOT / "data" / "uploads"


@router.post("/upload")
async def upload(file: UploadFile = File(...)) -> dict:
    """Save an uploaded video or photo and return where it is.

    Args:
        file: the multipart file field.
    Returns:
        {"path": absolute path on this machine, "name": original name, "bytes": size}.
    Raises:
        HTTPException 415 for an unsupported type, 413 if over MAX_BYTES.
    Side effects:
        Writes one file under data/uploads/.
    """
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED:
        raise HTTPException(415, f"Unsupported file type '{suffix or 'unknown'}'. Use a video or photo.")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dest = UPLOAD_DIR / f"{uuid.uuid4().hex}{suffix}"
    size = 0
    try:
        with dest.open("wb") as out:
            while chunk := await file.read(1 << 20):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise HTTPException(413, "That file is too large (limit 400 MB).")
                out.write(chunk)
    except HTTPException:
        dest.unlink(missing_ok=True)
        raise
    return {"path": str(dest), "name": file.filename, "bytes": size}
