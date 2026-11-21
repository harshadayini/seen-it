import json

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from backend.api import app
from backend.config import FIXTURE_PATH, SCHEMA_PATH

SCHEMA = json.loads(SCHEMA_PATH.read_text())
client = TestClient(app)


def validate(instance, ref=None):
    schema = SCHEMA if ref is None else {"$ref": f"#/$defs/{ref}", "$defs": SCHEMA["$defs"]}
    Draft202012Validator(schema).validate(instance)


def test_schema_is_valid():
    Draft202012Validator.check_schema(SCHEMA)


def test_fixture_validates():
    validate(json.loads(FIXTURE_PATH.read_text()))


def test_fixture_covers_all_statuses_and_recovery():
    items = json.loads(FIXTURE_PATH.read_text())["items"]
    assert {i["status"] for i in items} == {"exact", "similar", "none"}
    assert any(i["recovered"] for i in items)


def finished(body: dict) -> dict:
    """GET the run after POST /run (TestClient waits for the background work, so it is done)."""
    got = client.get(f"/run/{body['run_id']}")
    assert got.status_code == 200
    return got.json()


def test_post_run_returns_processing_then_done():
    r = client.post("/run", json={"video": "demo.mp4", "mode": "video"})
    assert r.status_code == 200
    assert r.json()["state"] == "processing" and r.json()["items"] == []
    validate(r.json())
    done = finished(r.json())
    validate(done)
    assert done["state"] == "done" and [i["state"] for i in done["items"]] == ["done"] * 3


def test_failed_extract_marks_run_failed(monkeypatch):
    import backend.api as api

    def boom(*a, **k):
        raise RuntimeError("argon down")

    monkeypatch.setattr(api, "extract", boom)
    run = finished(client.post("/run", json={"video": "x.mp4"}).json())
    validate(run)
    assert run["state"] == "failed" and "argon down" in run["error"]


def test_post_run_desk_mode_with_budget():
    r = finished(client.post("/run", json={"photo": "desk.jpg", "mode": "desk", "budget": 150, "request": "warmer"}).json())
    validate(r)
    assert r["mode"] == "desk"
    assert r["totals"]["within_budget"] is False  # stub items total 418 > 150


def test_get_run_unknown():
    assert client.get("/run/nope").status_code == 404


def _tiny_jpeg_data_url():
    import base64
    return "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8" + b"x" * 400).decode()


def test_post_preview_uses_camera_scene_and_returns_measured_fidelity(monkeypatch):
    import backend.api as api

    seen = {}

    def fake_make(scene, url, run_id, item_id, **kw):
        seen.update(scene=scene, url=url)
        return {"image_path": f"previews/{run_id}/{item_id}.jpg", "fidelity": 0.91, "regenerated": False}

    monkeypatch.setattr(api, "make_preview", fake_make)
    run = finished(client.post("/run", json={"video": "demo.mp4"}).json())
    r = client.post("/preview", json={"run_id": run["run_id"], "item_id": "i1", "scene_image": _tiny_jpeg_data_url()})
    assert r.status_code == 200, r.text
    validate(r.json()["preview"], "preview")
    assert r.json()["preview"]["fidelity"] == 0.91 and seen["scene"].endswith("_scene.jpg")
    validate(client.get(f"/run/{run['run_id']}").json())


def test_post_preview_rejects_missing_scene_unmatched_item_and_bad_image():
    run = finished(client.post("/run", json={"video": "demo.mp4"}).json())
    rid = run["run_id"]
    assert client.post("/preview", json={"run_id": rid, "item_id": "i1"}).status_code == 422   # no scene to use
    assert client.post("/preview", json={"run_id": rid, "item_id": "i3", "scene_image": _tiny_jpeg_data_url()}).status_code == 422  # no match
    assert client.post("/preview", json={"run_id": rid, "item_id": "i1", "scene_image": "not a data url"}).status_code == 422
    assert client.post("/preview", json={"run_id": "nope", "item_id": "i1"}).status_code == 404


def test_post_preview_upstream_failure_is_502_not_a_fake_image(monkeypatch):
    import backend.api as api
    from backend.video.preview import PreviewError

    def boom(*a, **k):
        raise PreviewError("image model call failed")

    monkeypatch.setattr(api, "make_preview", boom)
    run = finished(client.post("/run", json={"video": "demo.mp4"}).json())
    before = run["items"][0].get("preview")
    r = client.post("/preview", json={"run_id": run["run_id"], "item_id": "i1", "scene_image": _tiny_jpeg_data_url()})
    assert r.status_code == 502 and "image model" in r.json()["detail"]
    assert finished(run)["items"][0].get("preview") == before  # a failed call never writes a preview


def test_post_cart(monkeypatch):
    # The real create_cart calls live merchants; tests use a local fake so they never hit the network.
    monkeypatch.setattr(
        "backend.api.create_cart",
        lambda domain, variant, qty=1: {"cart_id": f"gid://shopify/Cart/t-{domain}", "continue_url": f"https://{domain}/cart/c/t"},
    )
    run = finished(client.post("/run", json={"video": "demo.mp4"}).json())
    r = client.post("/cart", json={"run_id": run["run_id"], "item_ids": ["i1", "i2"]})
    assert r.status_code == 200
    body = r.json()
    assert len(body["carts"]) == 2  # one cart per merchant
    for c in body["carts"]:
        assert c["continue_url"].startswith("https://")
        validate({k: c[k] for k in ("cart_id", "continue_url")}, "cart")
    after = client.get(f"/run/{run['run_id']}").json()
    validate(after)
    assert after["items"][0]["cart"]["continue_url"]


def test_cart_rejects_unmatched_item():
    run = finished(client.post("/run", json={"video": "demo.mp4"}).json())
    assert client.post("/cart", json={"run_id": run["run_id"], "item_ids": ["i3"]}).status_code == 422


# --- parallel resolve ---

def test_resolve_runs_in_parallel_keeps_order_and_isolates_failures(monkeypatch):
    import threading
    import time

    import backend.api as api

    lock = threading.Lock()
    state = {"now": 0, "peak": 0, "snapshot_when_i1_started": None}
    delays = {"i1": 0.4, "i2": 0.05, "i3": 0.15}  # finish order is i2, i3, i1: the reverse of item order

    def fake_resolve(item, **kwargs):
        with lock:
            state["now"] += 1
            state["peak"] = max(state["peak"], state["now"])
        try:
            time.sleep(delays[item["item_id"]])
            if item["item_id"] == "i2":
                raise RuntimeError("shopify down")
            if item["item_id"] == "i1":
                # By now i2 has failed and i3 is done: the run already shows them while i1 is still processing.
                run = api.RUNS[list(api.RUNS)[-1]]
                state["snapshot_when_i1_started"] = {i["item_id"]: i["state"] for i in run["items"]}
            return {**item, "state": "done", "status": "none"}
        finally:
            with lock:
                state["now"] -= 1

    monkeypatch.setattr(api, "resolve", fake_resolve)
    run = finished(client.post("/run", json={"video": "demo.mp4"}).json())
    validate(run)
    assert run["state"] == "done"  # a failing item never fails the run
    assert [i["item_id"] for i in run["items"]] == ["i1", "i2", "i3"]
    assert [i["state"] for i in run["items"]] == ["done", "failed", "done"]
    assert state["peak"] == 3  # all three ran at once (limit is 4)
    assert state["snapshot_when_i1_started"] == {"i1": "processing", "i2": "failed", "i3": "done"}


def test_resolve_workers_are_capped(monkeypatch):
    import threading
    import time

    import backend.api as api

    lock = threading.Lock()
    state = {"now": 0, "peak": 0}

    def fake_resolve(item, **kwargs):
        with lock:
            state["now"] += 1
            state["peak"] = max(state["peak"], state["now"])
        time.sleep(0.05)
        with lock:
            state["now"] -= 1
        return {**item, "state": "done", "status": "none"}

    monkeypatch.setattr(api, "resolve", fake_resolve)
    monkeypatch.setattr(api, "RESOLVE_WORKERS", 2)
    run = finished(client.post("/run", json={"video": "demo.mp4"}).json())
    assert run["state"] == "done" and state["peak"] == 2


# --- replay of saved runs ---

@pytest.fixture
def saved_dir(tmp_path, monkeypatch):
    import backend.api as api

    monkeypatch.setattr(api, "SAVED_RUNS_DIR", tmp_path)
    return tmp_path


def test_replay_copies_saved_run_as_finished_run(saved_dir):
    saved = json.loads(FIXTURE_PATH.read_text())
    saved["run_id"] = "r_saved"
    (saved_dir / "r_saved.json").write_text(json.dumps(saved))
    r = client.post("/run/replay", json={"run_id": "r_saved"})
    assert r.status_code == 200
    body = r.json()
    validate(body)
    assert body["state"] == "done" and body["run_id"] != "r_saved"  # fresh id, never overwrites a live run
    assert client.get(f"/run/{body['run_id']}").json() == body
    assert body["items"] == saved["items"]


def test_replay_unknown_and_unsafe_ids(saved_dir):
    assert client.post("/run/replay", json={"run_id": "missing"}).status_code == 404
    assert client.post("/run/replay", json={"run_id": "../sample_run"}).status_code == 422


def test_replay_rejects_unfinished_run(saved_dir):
    saved = json.loads(FIXTURE_PATH.read_text())
    saved["state"] = "processing"
    (saved_dir / "r_busy.json").write_text(json.dumps(saved))
    assert client.post("/run/replay", json={"run_id": "r_busy"}).status_code == 422


def test_save_run_strips_catalog_text_and_images(monkeypatch):
    import importlib.util

    from backend.config import ROOT

    spec = importlib.util.spec_from_file_location("save_run", ROOT / "scripts" / "save_run.py")
    save_run = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(save_run)
    run = json.loads(FIXTURE_PATH.read_text())
    cand = run["items"][0]["candidates"][0]
    cleaned = save_run.strip_run(run)
    validate(cleaned)  # still a valid run, so it can be replayed
    c = cleaned["items"][0]["candidates"][0]
    assert c["upid"] == cand["upid"] and c["variant_id"] == cand["variant_id"]
    assert c["p_same_product"] == cand["p_same_product"] and c["merchant_domain"] == cand["merchant_domain"]
    assert c["title"] == "" and c["price"] is None and c["image_url"] is None
    assert all(i["preview"] is None for i in cleaned["items"])
