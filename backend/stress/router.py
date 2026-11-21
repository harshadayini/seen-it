"""Stress-test endpoints (P3).

POST /stress             {video, conditions?} -> {stress_id}; runs in the background.
GET  /stress/conditions  the conditions we test and the clean-up used for each.
GET  /stress/{id}        progress and, when done, the scored results.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.stress import degrade, runner

router = APIRouter(prefix="/stress", tags=["stress"])


class StressRequest(BaseModel):
    video: str
    conditions: list[str] | None = None
    severity: str = "standard"  # or "extreme"


@router.get("/conditions")
def conditions() -> list[dict]:
    """The damage conditions we test, for the UI's explainer."""
    return [{"id": k, "name": v["name"], "blurb": v["blurb"]} for k, v in degrade.CONDITIONS.items()]


@router.post("")
def start_stress(req: StressRequest) -> dict:
    """Start a stress run on a link or local file path and return its id."""
    source = req.video.strip().strip("\"'")
    if not source:
        raise HTTPException(422, "Give a video link or file path.")
    return {"stress_id": runner.start(source, req.conditions, req.severity)}


@router.get("/{stress_id}")
def get_stress(stress_id: str) -> dict:
    """Current state of a stress run."""
    with runner._LOCK:
        run = runner.STRESS.get(stress_id)
        if run is None:
            raise HTTPException(404, f"unknown stress run {stress_id}")
        return dict(run)
