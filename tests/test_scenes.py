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
