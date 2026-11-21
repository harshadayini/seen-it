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


def test_post_run_and_get_run():
    r = client.post("/run", json={"video": "demo.mp4", "mode": "video"})
    assert r.status_code == 200
    validate(r.json())
    got = client.get(f"/run/{r.json()['run_id']}")
    assert got.status_code == 200
    validate(got.json())
    assert got.json() == r.json()


def test_post_run_desk_mode_with_budget():
    r = client.post("/run", json={"photo": "desk.jpg", "mode": "desk", "budget": 150, "request": "warmer"})
    validate(r.json())
    assert r.json()["mode"] == "desk"
    assert r.json()["totals"]["within_budget"] is False  # stub items total 418 > 150


def test_get_run_unknown():
    assert client.get("/run/nope").status_code == 404


def test_post_preview():
    run = client.post("/run", json={"video": "demo.mp4"}).json()
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
    run = client.post("/run", json={"video": "demo.mp4"}).json()
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
    run = client.post("/run", json={"video": "demo.mp4"}).json()
    assert client.post("/cart", json={"run_id": run["run_id"], "item_ids": ["i3"]}).status_code == 422
