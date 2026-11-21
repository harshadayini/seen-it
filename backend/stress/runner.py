"""Stress-test runner (P3): damage a clip and see what the model still finds.

What it does
    For one source video it builds a clean baseline clip, then for each chosen condition makes a
    damaged copy, runs the real `extract()` (Gemini 4 Argon) on every version, and scores each
    against the clean baseline: how many of the baseline's items did it still find (recall) and
    which did it miss.

Boundaries and invariants
    - Uses the real pipeline: no fake results. If `extract` fails for a version, that version
      records the error and the rest continue. With stubs enabled the run fails with a clear
      message, because stub output would make the numbers meaningless.
    - The score is "recall against the clean clip", not against human labels. The UI says so.
    - Runs in a background thread and writes progress into a shared dict that the API polls.
    - Frames for the UI are written under frames/stress/<id>/ (gitignored).
"""
from __future__ import annotations

import re
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from backend import config
from backend.stress import degrade
from backend.video import extract
from backend.video.extract import ExtractError, _download

STRESS: dict[str, dict] = {}
_LOCK = threading.Lock()
BREAKING_RECALL = 0.5  # below this, the condition counts as a breaking point
MAX_WORKERS = 3  # parallel Argon calls (AGENT_RULES caps this at about 5)

_STOP = {"a", "an", "the", "and", "with", "of", "for", "on", "in", "to", "small", "large", "black", "white"}


def _tokens(text: str) -> set[str]:
    """Lower-case content words of a label, without colours and filler."""
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if w not in _STOP and len(w) > 2}


def same_item(a: dict, b: dict) -> bool:
    """True if two extracted items plausibly name the same object (shared content words)."""
    ta, tb = _tokens(a.get("label", "")), _tokens(b.get("label", ""))
    if not ta or not tb:
        return False
    overlap = len(ta & tb) / min(len(ta), len(tb))
    same_cat = a.get("category") and a.get("category") == b.get("category")
    return overlap >= 0.5 or (same_cat and overlap > 0)


def score(baseline: list[dict], variant: list[dict]) -> dict:
    """Compare a version's items with the clean baseline.

    Args: baseline / variant: lists of {"label", "category"}.
    Returns: {"found": [...], "missed": [...], "extra": [...], "recall": float 0..1}.
    """
    found, missed = [], []
    for b in baseline:
        (found if any(same_item(b, v) for v in variant) else missed).append(b["label"])
    extra = [v["label"] for v in variant if not any(same_item(b, v) for b in baseline)]
    return {"found": found, "missed": missed, "extra": extra, "recall": round(len(found) / len(baseline), 3) if baseline else 0.0}


def _summarise(items: list[dict]) -> list[dict]:
    """Reduce extract() items to the fields the stress view needs."""
    return [{"label": i.get("description") or "item", "category": (i.get("attributes") or {}).get("category"), "t": i.get("t_start")} for i in items]


def best_frame_time(items: list[dict], duration: float | None) -> float:
    """Pick the moment to show in the UI: the second where the most items are visible together.

    Args: items: summarised baseline items (each may carry a time `t` in seconds); duration: clip length.
    Returns: a time in seconds inside the clip. Falls back to the middle of the clip when no item has a time,
    so the picture is never a random or blurry frame chosen by a fixed offset.
    """
    end = max((duration or 10.0) - 0.5, 0.0)
    times = [float(i["t"]) for i in items if isinstance(i.get("t"), (int, float)) and 0 <= float(i["t"]) <= end]
    if not times:
        return min((duration or 10.0) / 2, end)
    # For each candidate time, count how many items are visible within one second of it.
    return max(times, key=lambda t: (sum(abs(t - o) <= 1.0 for o in times), -abs(t - (duration or 10.0) / 2)))


def _set(stress_id: str, **fields) -> None:
    with _LOCK:
        STRESS[stress_id].update(fields)


def _step(stress_id: str, key: str, state: str, note: str | None = None) -> None:
    with _LOCK:
        for s in STRESS[stress_id]["steps"]:
            if s["key"] == key:
                s["state"] = state
                if note is not None:
                    s["note"] = note


def start(source: str, condition_ids: list[str] | None, severity: str = "standard") -> str:
    """Create a stress run and start it in a background thread.

    Args: source: video link or local file path; condition_ids: subset of degrade.CONDITIONS (default all).
    severity: "standard" or "extreme" (much harsher damage, to find where it really breaks).
    Returns: the stress id to poll.
    """
    ids = [c for c in (condition_ids or list(degrade.CONDITIONS)) if c in degrade.CONDITIONS] or list(degrade.CONDITIONS)
    severity = "extreme" if severity == "extreme" else "standard"
    stress_id = f"s_{uuid.uuid4().hex[:8]}"
    steps = [{"key": "baseline", "label": "Clean clip", "state": "waiting"}]
    for c in ids:
        steps.append({"key": f"{c}:degraded", "label": f"{degrade.CONDITIONS[c]['name']}: damaged", "state": "waiting"})
    with _LOCK:
        STRESS[stress_id] = {"stress_id": stress_id, "state": "processing", "severity": severity, "source": source, "steps": steps, "baseline": None, "conditions": [], "summary": None, "error": None, "started": time.time()}
    threading.Thread(target=_run, args=(stress_id, source, ids, severity), daemon=True).start()
    return stress_id


def _extract_timed(path: Path, run_id: str) -> dict:
    """Run extract() on one clip. Returns {"items", "latency_s", "error"} (never raises)."""
    t0 = time.monotonic()
    try:
        items = extract(str(path), run_id=run_id)
        return {"items": _summarise(items), "latency_s": round(time.monotonic() - t0, 1), "error": None}
    except (ExtractError, Exception) as exc:  # noqa: BLE001 - record and continue
        return {"items": [], "latency_s": round(time.monotonic() - t0, 1), "error": str(exc)[:240]}


def _run(stress_id: str, source: str, ids: list[str], severity: str) -> None:
    """Background worker: build clips, run every version, score, and write the result."""
    try:
        if config.USE_STUBS:
            raise RuntimeError("Stubs are switched on (SEEN_IT_STUBS), so stress results would be fake. Turn stubs off and retry.")
        if not degrade.ffmpeg_path():
            raise RuntimeError("ffmpeg is not installed or not on PATH.")
        out_dir = config.FRAMES_DIR / "stress" / stress_id
        out_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            if source.startswith(("http://", "https://")):
                local = _download(source, tmp)
            else:
                local = Path(source)
                if not local.is_file():
                    raise RuntimeError("That file path isn't a file on this computer. Drop the file or paste its full path.")
            clean = degrade.prepare(local, tmp / "clean.mp4")
            clip_len = degrade.duration_s(clean)

            versions: dict[str, Path] = {"baseline": clean}
            for c in ids:
                spec = degrade.CONDITIONS[c]
                vf = spec["degrade_x"] if severity == "extreme" else spec["degrade"]
                versions[f"{c}:degraded"] = degrade.apply(clean, tmp / f"{c}-degraded.mp4", vf)

            results: dict[str, dict] = {}

            def work(key: str) -> None:
                _step(stress_id, key, "running")
                res = _extract_timed(versions[key], f"stress-{stress_id}-{key.replace(':', '-')}")
                results[key] = res
                _step(stress_id, key, "failed" if res["error"] else "done", res["error"])

            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
                list(pool.map(work, versions.keys()))

            base = results["baseline"]
            if base["error"] or not base["items"]:
                raise RuntimeError(base["error"] or "The model found nothing in the clean clip, so there is nothing to compare against.")
            # Show the frame where the model saw the most items at once, the same moment in every version.
            at = best_frame_time(base["items"], clip_len)
            degrade.thumb(versions["baseline"], out_dir / "baseline.jpg", at)
            for c in ids:
                degrade.thumb(versions[f"{c}:degraded"], out_dir / f"{c}-degraded.jpg", at)

        _set(stress_id, baseline={"items": base["items"], "latency_s": base["latency_s"], "frame": f"frames/stress/{stress_id}/baseline.jpg"})

        conds, breaking = [], None
        for c in ids:
            spec = degrade.CONDITIONS[c]
            dres = results[f"{c}:degraded"]
            dscore = score(base["items"], dres["items"])
            conds.append({
                "id": c, "name": spec["name"], "blurb": spec["blurb"],
                "damage": spec["degrade_x"] if severity == "extreme" else spec["degrade"],
                "degraded": {**dscore, "latency_s": dres["latency_s"], "error": dres["error"], "frame": f"frames/stress/{stress_id}/{c}-degraded.jpg"},
            })
            if breaking is None and dscore["recall"] < BREAKING_RECALL:
                breaking = spec["name"]
        weakest = min(conds, key=lambda x: x["degraded"]["recall"])
        avg_d = sum(c["degraded"]["recall"] for c in conds) / len(conds)
        _set(stress_id, conditions=conds, summary={"baseline_items": len(base["items"]), "avg_degraded": round(avg_d, 3), "breaking_point": breaking, "weakest": {"name": weakest["name"], "recall": weakest["degraded"]["recall"]}, "threshold": BREAKING_RECALL}, state="done")
    except Exception as exc:  # noqa: BLE001
        _set(stress_id, state="failed", error=str(exc)[:300])
