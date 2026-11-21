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
