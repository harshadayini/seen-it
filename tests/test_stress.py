"""Tests for the stress-test scoring and condition definitions (no network, no ffmpeg needed)."""
from fastapi.testclient import TestClient

from backend.api import app
from backend.stress import degrade, runner

client = TestClient(app)


def test_same_item_matches_shared_words_and_ignores_colour():
    assert runner.same_item({"label": "black desk lamp"}, {"label": "desk lamp"})
    assert not runner.same_item({"label": "desk lamp"}, {"label": "computer monitor"})


def test_score_counts_found_missed_and_extra():
    base = [{"label": "desk lamp"}, {"label": "monitor stand"}, {"label": "smart speaker"}]
    var = [{"label": "lamp for desk"}, {"label": "plant"}]
    s = runner.score(base, var)
    assert s["found"] == ["desk lamp"] and set(s["missed"]) == {"monitor stand", "smart speaker"}
    assert s["extra"] == ["plant"] and s["recall"] == round(1 / 3, 3)


def test_every_condition_has_standard_and_extreme_damage():
    assert set(degrade.CONDITIONS) >= {"shaky", "noisy", "dark", "blurry"}
    for spec in degrade.CONDITIONS.values():
        assert spec["degrade"] and spec["degrade_x"] and spec["name"]
        assert "recover" not in spec  # no clean-up is ever applied


def test_conditions_endpoint_and_unknown_run():
    r = client.get("/stress/conditions")
    assert r.status_code == 200 and len(r.json()) >= 4
    assert client.get("/stress/s_nope").status_code == 404
    assert client.post("/stress", json={"video": "  "}).status_code == 422


def test_best_frame_time_picks_the_moment_with_most_items_visible():
    items = [{"t": 2.0}, {"t": 9.0}, {"t": 9.4}, {"t": 9.8}, {"t": 15.0}]
    assert 9.0 <= runner.best_frame_time(items, 20.0) <= 9.8
    assert runner.best_frame_time([], 20.0) == 10.0
    assert runner.best_frame_time([{"t": 99.0}], 20.0) == 10.0  # outside the clip: fall back to the middle
