"""P1: the user's own scene for "See it here": a photo, a camera capture or a short video.

Does: stores an uploaded photo or video under previews/scenes/<scene_id>/, re-encodes it to JPEG frames no wider
than MAX_SCENE_PX (a photo gives one frame, a video gives SCENE_VIDEO_FRAMES evenly spaced frames to choose from),
and returns relative paths the preview step can use.
Must not: keep anything outside previews/scenes (gitignored, local), trust the upload's file name or type (the bytes
are decoded by ffmpeg and rejected if they are not an image or video), accept files over MAX_UPLOAD_BYTES, or
print the user's media in logs. Failures raise SceneError with a plain message.
"""
import logging
import re
import secrets
import shutil
import subprocess
import tempfile
from pathlib import Path

from backend import config

log = logging.getLogger("seen_it.scenes")

MAX_UPLOAD_BYTES = 60_000_000
MAX_SCENE_PX = 1024
SCENE_VIDEO_FRAMES = 4
SCENE_ID_RE = re.compile(r"^[a-f0-9]{12}$")


class SceneError(ValueError):
    """The upload is not usable (too big, not an image or video, unreadable)."""


def scenes_dir() -> Path:
    """Folder that holds every uploaded scene (previews/scenes, gitignored)."""
    return config.ROOT / "previews" / "scenes"


def _run(cmd: list[str], data: bytes | None = None, timeout: int = 60) -> subprocess.CompletedProcess:
    """Run ffmpeg/ffprobe, returning the finished process. Raises SceneError if the tool is missing or times out."""
    try:
        return subprocess.run(cmd, input=data, capture_output=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as e:
        raise SceneError(f"could not process the upload ({type(e).__name__})") from e


def _duration(path: Path) -> float | None:
    """Video length in seconds with ffprobe, or None for a still image or an unreadable file."""
    r = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)], timeout=20)
    try:
        d = float(r.stdout.decode().strip())
        return d if d > 0.2 else None
    except ValueError:
        return None


def _save_frame(src: Path, t: float | None, out: Path) -> bool:
    """Write one JPEG (at time t for a video, or the image itself when t is None), scaled to MAX_SCENE_PX wide."""
    cmd = ["ffmpeg", "-v", "error"]
    if t is not None:
        cmd += ["-ss", f"{t:.3f}"]
    cmd += ["-i", str(src), "-frames:v", "1", "-vf", f"scale='min({MAX_SCENE_PX},iw)':-2", "-q:v", "3", "-y", str(out)]
    r = _run(cmd)
    return r.returncode == 0 and out.exists() and out.stat().st_size > 100


def _convert_with_sips(src: Path, out: Path) -> bool:
    """Convert an image ffmpeg cannot read (an iPhone HEIC/HEIF photo) to a JPEG with macOS `sips`.

    Returns True if out was written. Returns False when sips is missing (not macOS) or the file is not an image.
    The output is scaled to at most MAX_SCENE_PX on its longest side.
    """
    if shutil.which("sips") is None:
        return False
    heic = src.with_suffix(".heic")  # sips picks the reader from the content, the name is only a hint
    shutil.copyfile(src, heic)
    r = _run(["sips", "-s", "format", "jpeg", "-Z", str(MAX_SCENE_PX), str(heic), "--out", str(out)], timeout=60)
    return r.returncode == 0 and out.exists() and out.stat().st_size > 100


def save_scene(data: bytes) -> dict:
    """Store an uploaded photo or video and extract its scene frame(s).

    Args: data: the raw uploaded bytes. Returns {"scene_id", "kind": "image"|"video", "frames": [relative paths],
    "default": index of the frame to use unless the user picks another}. Video frames are spread across the clip and
    the middle one is the default. Raises SceneError for an empty, oversized or undecodable upload.
    Side effects: writes previews/scenes/<scene_id>/f0.jpg ... and removes the temporary original.
    """
    if not data:
        raise SceneError("the upload is empty")
    if len(data) > MAX_UPLOAD_BYTES:
        raise SceneError(f"the upload is larger than {MAX_UPLOAD_BYTES // 1_000_000} MB")
    scene_id = secrets.token_hex(6)
    folder = scenes_dir() / scene_id
    folder.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "upload.bin"
            raw.write_bytes(data)
            dur = _duration(raw)
            if dur is None:
                times: list[float | None] = [None]
                kind = "image"
            else:
                times = [dur * f for f in (0.15, 0.4, 0.65, 0.85)][:SCENE_VIDEO_FRAMES]
                kind = "video"
            frames: list[str] = []
            for n, t in enumerate(times):
                out = folder / f"f{n}.jpg"
                if _save_frame(raw, t, out):
                    frames.append(f"previews/scenes/{scene_id}/f{n}.jpg")
            if not frames:  # ffmpeg could not decode it: try an iPhone HEIC/HEIF photo with macOS sips
                out = folder / "f0.jpg"
                if _convert_with_sips(raw, out):
                    frames, kind = [f"previews/scenes/{scene_id}/f0.jpg"], "image"
                    log.info("scene %s converted with sips (HEIC)", scene_id)
            if not frames:
                raise SceneError("that file is not a photo or video we can read")
    except SceneError:
        _discard(folder)
        raise
    log.info("scene %s saved kind=%s frames=%d", scene_id, kind, len(frames))
    return {"scene_id": scene_id, "kind": kind, "frames": frames, "default": len(frames) // 2 if kind == "video" else 0}


def _discard(folder: Path) -> None:
    """Delete a half-made scene folder."""
    for f in folder.glob("*"):
        f.unlink(missing_ok=True)
    folder.rmdir()


def scene_frame(scene_id: str, index: int = 0) -> str:
    """Relative path of one stored scene frame. Raises SceneError for a bad id or missing frame.

    Args: scene_id: from save_scene (12 hex characters, checked so it cannot escape the folder); index: frame number.
    """
    if not SCENE_ID_RE.match(scene_id or ""):
        raise SceneError("invalid scene_id")
    rel = f"previews/scenes/{scene_id}/f{int(index)}.jpg"
    if not (config.ROOT / rel).is_file():
        raise SceneError("unknown scene or frame")
    return rel


MAX_VIDEO_BYTES = 300_000_000


def uploads_dir() -> Path:
    """Folder for videos uploaded for analysis (data/uploads, gitignored, local only)."""
    return config.ROOT / "data" / "uploads"


def finish_video_upload(path: Path) -> dict:
    """Check a streamed upload is a real video and give it a proper extension.

    Args: path: the file the API streamed to disk. Returns {"video": absolute path, "bytes", "duration_s"}.
    Raises SceneError (and deletes the file) if ffprobe cannot read a video stream or the clip is under a second.
    The extension (mp4 or webm) is chosen from what the container really is, so Gemini gets the right MIME type.
    """
    r = _run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
              "stream=codec_type:format=format_name,duration", "-of", "default=nw=1", str(path)], timeout=30)
    info = r.stdout.decode(errors="replace")
    fmt = next((ln.split("=", 1)[1] for ln in info.splitlines() if ln.startswith("format_name=")), "")
    dur = next((ln.split("=", 1)[1] for ln in info.splitlines() if ln.startswith("duration=")), "")
    try:
        seconds = float(dur)
    except ValueError:
        seconds = 0.0
    if r.returncode != 0 or "codec_type=video" not in info or seconds < 1.0:
        path.unlink(missing_ok=True)
        raise SceneError("that file is not a video we can read (or it is shorter than a second)")
    final = path.with_suffix(".webm" if "webm" in fmt or "matroska" in fmt else ".mp4")
    path.rename(final)
    log.info("video upload saved bytes=%d duration=%.1f", final.stat().st_size, seconds)
    return {"video": str(final), "bytes": final.stat().st_size, "duration_s": round(seconds, 1)}
