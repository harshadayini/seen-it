"""extract() tests: a saved Argon response, a generated video, no network."""
import importlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from backend import config

ex = importlib.import_module("backend.video.extract")  # the package re-exports the function under the same name
SAVED = Path(__file__).resolve().parent.parent / "fixtures" / "argon_probe" / "shorts_gcd8-axeb2o.json"
SCHEMA = json.loads(config.SCHEMA_PATH.read_text())

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def test_build_query_uses_label_color_material():
    q = ex.build_query("LED desk lamp bar", {"color": "black", "material": "metal and plastic"})
    assert q == "black led desk lamp bar metal plastic"


def test_pad_bbox_grows_and_clamps():
    assert ex.pad_bbox([0.4, 0.4, 0.6, 0.6], 0.10) == pytest.approx([0.38, 0.38, 0.62, 0.62])
    assert ex.pad_bbox([0.0, 0.9, 0.5, 1.0], 0.10) == pytest.approx([0.0, 0.89, 0.55, 1.0])


def test_stub_mode_returns_fixture_items():
    assert config.USE_STUBS
    assert [i["item_id"] for i in ex.extract("whatever.mp4")] == ["i1", "i2", "i3"]


def test_parse_drops_malformed_and_ignores_video_boxes():
    good = {"label": "x", "attributes": {}, "timestamp_s": 1, "bbox": [0.9, 0.1, 0.5, 0.5]}  # bbox ignored
    bad = {"label": "y", "attributes": {}, "timestamp_s": "soon"}
    assert ex.parse_items(json.dumps([good, bad])) == [good]
    with pytest.raises(ex.ExtractError):
        ex.parse_items("not json")


def test_parse_boxes_scales_and_drops_invalid():
    text = json.dumps([{"id": "i1", "bbox": [100, 200, 500, 900]},
                       {"id": "i2", "bbox": [500, 200, 100, 900]},   # min above max
                       {"id": "i3", "bbox": [0, 0, 1200, 500]},      # out of range
                       {"id": "i4"}])
    assert ex.parse_boxes(text) == {"i1": pytest.approx([0.1, 0.2, 0.5, 0.9])}
    with pytest.raises(ex.ExtractError):
        ex.parse_boxes("nope")


def _video(tmp_path):
    video = tmp_path / "v.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=10:duration=10",
                    "-pix_fmt", "yuv420p", "-y", str(video)], check=True)
    return video


def _size(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout.strip()
    return tuple(int(v) for v in out.split(","))


@needs_ffmpeg
def test_saved_response_two_pass_crops_and_full_frame_fallback(tmp_path, monkeypatch):
    video = _video(tmp_path)
    monkeypatch.setattr(config, "ROOT", tmp_path)  # write crops under tmp, not the repo
    saved = json.loads(SAVED.read_text())
    calls = []

    def fake_locate(frame, group):
        calls.append([i for i, _ in group])
        return {group[0][0]: [0.25, 0.25, 0.75, 0.75]}  # only the first item of each frame gets a box

    items = ex.items_from_response(saved["raw_text"], video, "r_test", locate=fake_locate)
    assert len(items) == len(saved["items"]) == 10
    assert sum(len(c) for c in calls) == 10 and len(calls) <= 3  # items grouped by shared timestamp
    item_schema = {"$ref": "#/$defs/item", "$defs": SCHEMA["$defs"]}
    boxed = [c[0] for c in calls]
    for it in items:
        Draft202012Validator(item_schema).validate(it)
        crop = tmp_path / it["crop_path"]
        assert crop.stat().st_size > 0 and it["crop_path"] == f"frames/r_test/{it['item_id']}.jpg"
        assert it["t_start"] == it["t_end"] and it["description"] and it["query"]
        w, h = _size(crop)
        # boxed items are cropped (about 60% of the frame after padding); the rest keep the full 640x360 frame
        assert (w, h) != (640, 360) if it["item_id"] in boxed else (w, h) == (640, 360)
    assert not list((tmp_path / "frames" / "r_test").glob("_frame_*"))  # temp frames cleaned up


@needs_ffmpeg
def test_failed_box_call_keeps_items(tmp_path, monkeypatch):
    video = _video(tmp_path)
    monkeypatch.setattr(config, "ROOT", tmp_path)
    saved = json.loads(SAVED.read_text())
    items = ex.items_from_response(saved["raw_text"], video, "r_fail", locate=lambda f, g: {})
    assert len(items) == 10 and all((tmp_path / i["crop_path"]).stat().st_size > 0 for i in items)
