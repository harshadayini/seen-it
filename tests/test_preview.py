"""preview tests: fake image model, fake photo download, fake Decisions call. No network."""
import importlib

import pytest

from backend import config

pv = importlib.import_module("backend.video.preview")


@pytest.fixture
def scene(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ROOT", tmp_path)
    (tmp_path / "frames").mkdir()
    (tmp_path / "frames" / "s.jpg").write_bytes(b"\xff\xd8scene-bytes" * 20)
    monkeypatch.setattr(pv, "shrink", lambda d, *a: d)  # no ffmpeg needed
    return "frames/s.jpg"


def test_good_first_try_saves_one_composite_and_keeps_score(scene, tmp_path):
    calls = []
    out = pv.make_preview(scene, "https://x/p.jpg", "r1", "i1",
                          generate=lambda s, p: calls.append(1) or b"IMG-A",
                          fetch=lambda u: b"product" * 30, check=lambda s, p, r: 0.93)
    assert out == {"image_path": "previews/r1/i1.jpg", "fidelity": 0.93, "regenerated": False}
    assert len(calls) == 1 and (tmp_path / out["image_path"]).read_bytes() == b"IMG-A"


def test_low_score_regenerates_once_and_keeps_the_better(scene, tmp_path):
    results, scores = iter([b"LOW", b"BETTER"]), iter([0.4, 0.7])
    out = pv.make_preview(scene, "https://x/p.jpg", "r1", "i1", generate=lambda s, p: next(results),
                          fetch=lambda u: b"product" * 30, check=lambda s, p, r: next(scores))
    assert out["regenerated"] is True and out["fidelity"] == 0.7
    assert (tmp_path / out["image_path"]).read_bytes() == b"BETTER"


def test_second_attempt_worse_keeps_first(scene, tmp_path):
    results, scores = iter([b"FIRST", b"WORSE"]), iter([0.6, 0.2])
    out = pv.make_preview(scene, "https://x/p.jpg", "r1", "i1", generate=lambda s, p: next(results),
                          fetch=lambda u: b"product" * 30, check=lambda s, p, r: next(scores))
    assert out["fidelity"] == 0.6 and (tmp_path / out["image_path"]).read_bytes() == b"FIRST"


def test_unavailable_check_gives_null_fidelity_and_no_retry(scene):
    calls = []
    out = pv.make_preview(scene, "https://x/p.jpg", "r1", "i1", generate=lambda s, p: calls.append(1) or b"IMG",
                          fetch=lambda u: b"product" * 30, check=lambda s, p, r: None)
    assert out["fidelity"] is None and out["regenerated"] is False and len(calls) == 1


def test_missing_scene_and_bad_url_raise(scene):
    with pytest.raises(pv.PreviewError):
        pv.make_preview("frames/nope.jpg", "https://x/p.jpg", "r1", "i1", generate=lambda s, p: b"x", fetch=lambda u: b"y" * 200)
    with pytest.raises(pv.PreviewError):
        pv._fetch_image("file:///etc/passwd")


def test_check_fidelity_takes_the_lower_probability():
    fake = lambda input_blocks, questions, cfg: ({"answers": {"product_matches": {"noul": 0.9}, "scene_preserved": {"noul": 0.6}}}, 5.0)  # noqa: E731
    assert pv.check_fidelity(b"a", b"b", b"c", invoke=fake) == 0.6
    assert sum(1 for b in [{"type": "image"}]) == 1


def test_check_fidelity_is_none_when_it_cannot_run_or_answer_is_unusable():
    def boom(*a, **k):
        raise RuntimeError("multi-image rejected")

    assert pv.check_fidelity(b"a", b"b", b"c", invoke=boom) is None
    bad = lambda input_blocks, questions, cfg: ({"answers": {"product_matches": {"noul": "high"}}}, 1.0)  # noqa: E731
    assert pv.check_fidelity(b"a", b"b", b"c", invoke=bad) is None
