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


def test_post_preview():
    run = finished(client.post("/run", json={"video": "demo.mp4"}).json())
    r = client.post("/preview", json={"run_id": run["run_id"], "item_id": "i1"})
    assert r.status_code == 200
    validate(r.json()["preview"], "preview")
    validate(client.get(f"/run/{run['run_id']}").json())


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
