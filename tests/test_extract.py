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


def test_parse_drops_malformed():
    good = {"label": "x", "attributes": {}, "timestamp_s": 1, "bbox": [0.1, 0.1, 0.5, 0.5]}
    bad = {"label": "y", "attributes": {}, "timestamp_s": 1, "bbox": [0.9, 0.1, 0.5, 0.5]}
    assert ex.parse_items(json.dumps([good, bad])) == [good]
    with pytest.raises(ex.ExtractError):
        ex.parse_items("not json")


@needs_ffmpeg
def test_saved_response_to_items_with_crops(tmp_path, monkeypatch):
    video = tmp_path / "v.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=10:duration=10",
                    "-pix_fmt", "yuv420p", "-y", str(video)], check=True)
    monkeypatch.setattr(config, "ROOT", tmp_path)  # write crops under tmp, not the repo
    saved = json.loads(SAVED.read_text())
    items = ex.items_from_response(saved["raw_text"], video, "r_test")
    assert len(items) == len(saved["items"]) == 10
    item_schema = {"$ref": "#/$defs/item", "$defs": SCHEMA["$defs"]}
    for it in items:
        Draft202012Validator(item_schema).validate(it)
        assert (tmp_path / it["crop_path"]).stat().st_size > 0
        assert it["crop_path"] == f"frames/r_test/{it['item_id']}.jpg"
        assert it["t_start"] == it["t_end"] and it["description"] and it["query"]
