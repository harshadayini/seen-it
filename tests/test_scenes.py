"""Scene upload tests: a generated photo and video, real ffmpeg, no network."""
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from backend import config, scenes
from backend.api import app

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
client = TestClient(app)


@pytest.fixture(autouse=True)
def tmp_root(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ROOT", tmp_path)


def _make(tmp_path, args, name):
    out = tmp_path / name
    subprocess.run(["ffmpeg", "-v", "error", *args, "-y", str(out)], check=True)
    return out.read_bytes()


@needs_ffmpeg
def test_photo_upload_gives_one_frame(tmp_path):
    png = _make(tmp_path, ["-f", "lavfi", "-i", "testsrc=size=1600x900:rate=1:duration=1", "-frames:v", "1"], "p.png")
    out = scenes.save_scene(png)
    assert out["kind"] == "image" and len(out["frames"]) == 1 and out["default"] == 0
    assert (tmp_path / out["frames"][0]).stat().st_size > 100


@needs_ffmpeg
def test_video_upload_gives_four_frames_middle_default(tmp_path):
    mp4 = _make(tmp_path, ["-f", "lavfi", "-i", "testsrc=size=640x360:rate=10:duration=8", "-pix_fmt", "yuv420p"], "v.mp4")
    out = scenes.save_scene(mp4)
    assert out["kind"] == "video" and len(out["frames"]) == 4 and out["default"] == 2
    assert all((tmp_path / f).stat().st_size > 100 for f in out["frames"])


def test_bad_uploads_are_rejected(tmp_path):
    with pytest.raises(scenes.SceneError):
        scenes.save_scene(b"")
    with pytest.raises(scenes.SceneError):
        scenes.save_scene(b"this is not an image or a video" * 20)
    assert not list((tmp_path / "previews" / "scenes").glob("*/*")) if (tmp_path / "previews" / "scenes").exists() else True
    with pytest.raises(scenes.SceneError):
        scenes.scene_frame("../../etc/passwd")
    with pytest.raises(scenes.SceneError):
        scenes.scene_frame("abcdefabcdef", 0)


@needs_ffmpeg
def test_scene_endpoint_and_frame_lookup(tmp_path):
    png = _make(tmp_path, ["-f", "lavfi", "-i", "testsrc=size=800x600:rate=1:duration=1", "-frames:v", "1"], "p.png")
    r = client.post("/scene", content=png, headers={"content-type": "image/png"})
    assert r.status_code == 200, r.text
    sid = r.json()["scene_id"]
    assert scenes.scene_frame(sid, 0).endswith("f0.jpg")
    assert client.post("/scene", content=b"nope" * 50).status_code == 422


@needs_ffmpeg
def test_video_upload_endpoint_accepts_a_video_and_returns_a_usable_path(tmp_path):
    mp4 = _make(tmp_path, ["-f", "lavfi", "-i", "testsrc=size=320x240:rate=10:duration=3", "-pix_fmt", "yuv420p"], "v.mp4")
    r = client.post("/upload", content=mp4, headers={"content-type": "video/mp4"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["video"].endswith(".mp4") and body["duration_s"] >= 2.5 and body["bytes"] == len(mp4)
    assert (tmp_path / "data" / "uploads").exists() and len(list((tmp_path / "data" / "uploads").glob("*"))) == 1  # raw temp removed


def test_video_upload_endpoint_rejects_junk_empty_and_oversize(tmp_path, monkeypatch):
    assert client.post("/upload", content=b"not a video" * 100).status_code == 422
    assert client.post("/upload", content=b"").status_code == 422
    monkeypatch.setattr(scenes, "MAX_VIDEO_BYTES", 1000)
    assert client.post("/upload", content=b"x" * 5000).status_code == 413
    left = list((tmp_path / "data" / "uploads").glob("*")) if (tmp_path / "data" / "uploads").exists() else []
    assert left == []  # no half-saved files


@pytest.mark.skipif(shutil.which("sips") is None, reason="macOS sips not available")
def test_iphone_heic_photo_is_converted_with_sips(tmp_path):
    png = tmp_path / "p.png"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=1200x900:rate=1:duration=1", "-frames:v", "1", "-y", str(png)], check=True)
    heic = tmp_path / "p.heic"
    made = subprocess.run(["sips", "-s", "format", "heic", str(png), "--out", str(heic)], capture_output=True)
    if made.returncode != 0 or not heic.exists():
        pytest.skip("this sips cannot write HEIC")
    out = scenes.save_scene(heic.read_bytes())
    assert out["kind"] == "image" and len(out["frames"]) == 1
    assert (tmp_path / out["frames"][0]).stat().st_size > 100
