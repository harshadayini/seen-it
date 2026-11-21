"""Stress conditions and ffmpeg helpers (P3).

What it does
    Defines the ways we deliberately damage a clip (shake, noise, low light, blur), plus small
    ffmpeg wrappers to apply them and to grab a still frame for the UI.

Boundaries and invariants
    - Pure media processing. No Gemini or Shopify calls happen here.
    - Every filter chain is a fixed string from CONDITIONS below; nothing from user input is ever
      passed to ffmpeg except file paths we generate ourselves.
    - No clean-up or repair is applied: the models see the damaged clip exactly as it is.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

TARGET_WIDTH = 720
CLIP_SECONDS = 20

CONDITIONS: dict[str, dict[str, str]] = {
    "shaky": {
        "name": "Shaky camera",
        "blurb": "Handheld shake with motion blur, like filming while walking.",
        "degrade": (
            "crop=w=iw*0.82:h=ih*0.82:x='(iw-ow)/2*(1+sin(45*t))':y='(ih-oh)/2*(1+cos(53*t))',"
            f"scale={TARGET_WIDTH}:-2,tmix=frames=3"
        ),
        "degrade_x": (
            "crop=w=iw*0.62:h=ih*0.62:x='(iw-ow)/2*(1+sin(95*t))':y='(ih-oh)/2*(1+cos(110*t))',"
            f"scale={TARGET_WIDTH}:-2,tmix=frames=7"
        ),
    },
    "noisy": {
        "name": "Heavy noise",
        "blurb": "Grainy, compressed footage, like a cheap sensor in a dim room.",
        "degrade": "noise=alls=70:allf=t+u",
        "degrade_x": "noise=alls=100:allf=t+u,boxblur=2",
    },
    "dark": {
        "name": "Low light",
        "blurb": "Underexposed with sensor grain, like a late-night room tour.",
        "degrade": "eq=brightness=-0.32:contrast=0.7:gamma=0.8,noise=alls=22:allf=t",
        "degrade_x": "eq=brightness=-0.55:contrast=0.55:gamma=0.6,noise=alls=45:allf=t",
    },
    "blurry": {
        "name": "Soft, low resolution",
        "blurb": "Tiny, blurry upload that was stretched back up.",
        "degrade": f"scale=160:-2,scale={TARGET_WIDTH}:-2:flags=bilinear,boxblur=2",
        "degrade_x": f"scale=48:-2,scale={TARGET_WIDTH}:-2:flags=bilinear,boxblur=4",
    },
}


def ffmpeg_path() -> str | None:
    """Return the ffmpeg executable on PATH, or None if it is not installed."""
    return shutil.which("ffmpeg")


def _run(args: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    """Run ffmpeg quietly. Raises RuntimeError with the tail of stderr on failure."""
    exe = ffmpeg_path()
    if not exe:
        raise RuntimeError("ffmpeg is not installed or not on PATH")
    proc = subprocess.run([exe, "-y", "-v", "error", *args], capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or "ffmpeg failed").strip()[-300:])
    return proc


def prepare(src: Path, out: Path) -> Path:
    """Trim a source video to CLIP_SECONDS, scale it to TARGET_WIDTH and drop audio (the clean baseline).

    Args:
        src: input video file. out: where to write the prepared clip.
    Returns: out. Side effects: writes a file.
    """
    _run(["-i", str(src), "-t", str(CLIP_SECONDS), "-vf", f"scale={TARGET_WIDTH}:-2", "-an",
          "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p", str(out)])
    return out


def apply(src: Path, out: Path, vf: str) -> Path:
    """Apply one fixed filter chain to a clip and write the result.

    Args: src: input clip; out: output path; vf: a chain from CONDITIONS. Returns: out.
    """
    _run(["-i", str(src), "-vf", vf, "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
          "-pix_fmt", "yuv420p", str(out)])
    return out


def duration_s(path: Path) -> float | None:
    """Clip length in seconds, read from ffmpeg's banner (no ffprobe needed), or None."""
    exe = ffmpeg_path()
    if not exe:
        return None
    proc = subprocess.run([exe, "-i", str(path)], capture_output=True, text=True, timeout=60)
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", proc.stderr or "")
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]) if m else None


def thumb(src: Path, out: Path, at: float) -> Path:
    """Save one still frame at `at` seconds as a JPEG for the web UI."""
    _run(["-ss", f"{at:.2f}", "-i", str(src), "-frames:v", "1", "-q:v", "3", str(out)], timeout=60)
    return out
