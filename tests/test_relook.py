"""relook() tests: a generated video and a fake Argon answer, no network."""
import importlib
import json
import shutil
import subprocess

import pytest

from backend import config

rl = importlib.import_module("backend.video.relook")
needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")

GOOD = {"visible": True, "frame": 2, "bbox": [200, 300, 800, 700], "description": "slim black vertical stand",
        "attributes": {"color": "black", "material": "aluminum"}, "query": "  vertical laptop   stand black aluminum "}


def test_frame_times_window_step_and_clamp():
    assert rl.frame_times(5.0) == [3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0]
    assert rl.frame_times(0.5)[0] == 0.0 and len(rl.frame_times(0.5)) <= rl.MAX_RELOOK_FRAMES
    assert all(t >= 0 for t in rl.frame_times(0.0))


def test_parse_accepts_good_and_normalizes():
    p = rl.parse_relook(json.dumps(GOOD), 5)
    assert p["frame"] == 2 and p["query"] == "vertical laptop stand black aluminum"
    assert p["bbox"] == pytest.approx([0.2, 0.3, 0.8, 0.7])


@pytest.mark.parametrize("bad", [
    {**GOOD, "visible": False}, {**GOOD, "frame": 9}, {**GOOD, "frame": -1}, {**GOOD, "bbox": [800, 300, 200, 700]},
    {**GOOD, "bbox": [0, 0, 1200, 500]}, {**GOOD, "query": ""}, {**GOOD, "query": "x" * 101}, "not a dict",
])
def test_parse_rejects_bad(bad):
    assert rl.parse_relook(json.dumps(bad), 5) is None
    assert rl.parse_relook("not json", 5) is None


def _setup(tmp_path, monkeypatch):
    video = tmp_path / "v.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=10:duration=10",
                    "-pix_fmt", "yuv420p", "-y", str(video)], check=True)
    monkeypatch.setattr(config, "ROOT", tmp_path)
    item = {"item_id": "i3", "t_start": 5.0, "t_end": 5.0, "crop_path": "frames/r1/i3.jpg",
            "description": "laptop stand", "attributes": {"color": "black"}, "query": "laptop stand black",
            "status": "none", "recovered": False, "candidates": []}
    return video, item


@needs_ffmpeg
def test_relook_returns_sharper_copy_with_new_crop(tmp_path, monkeypatch):
    video, item = _setup(tmp_path, monkeypatch)
    seen = {}

    def fake_ask(frames, times, it):
        seen["n"], seen["times"] = len(frames), times
        return json.dumps(GOOD)

    out = rl.relook(item, str(video), ask=fake_ask)
    assert seen["n"] == 9 and seen["times"][0] == 3.0
    assert out["crop_path"] == "frames/r1/i3_relook.jpg" and (tmp_path / out["crop_path"]).stat().st_size > 0
    assert out["query"] == "vertical laptop stand black aluminum" and out["t_start"] == 4.0  # frame index 2 of the times
    assert out["attributes"] == {"color": "black", "material": "aluminum"}
    assert out["status"] == "none" and out["recovered"] is False  # P2 decides these
    assert item["crop_path"] == "frames/r1/i3.jpg"  # input not mutated


@needs_ffmpeg
def test_relook_unchanged_when_not_visible_or_failing(tmp_path, monkeypatch):
    video, item = _setup(tmp_path, monkeypatch)
    assert rl.relook(item, str(video), ask=lambda f, t, i: json.dumps({**GOOD, "visible": False})) == item
    assert rl.relook(item, str(video), ask=lambda f, t, i: "garbage") == item

    def boom(*a):
        raise RuntimeError("api down")

    assert rl.relook(item, str(video), ask=boom) == item
    assert rl.relook({**item, "t_start": None}, str(video), ask=boom)["crop_path"] == "frames/r1/i3.jpg"
