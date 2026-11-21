"""Loads fixtures/sample_run.json. Used only by stubs until real implementations land."""
import copy
import json

from backend.config import FIXTURE_PATH


def load_run() -> dict:
    return copy.deepcopy(json.loads(FIXTURE_PATH.read_text()))


def load_items() -> list[dict]:
    return load_run()["items"]
