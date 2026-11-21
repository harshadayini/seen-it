#!/usr/bin/env python3
"""Save a finished run from the local API to fixtures/saved_runs/<run_id>.json (a recorded fallback).

Usage: .venv/bin/python scripts/save_run.py <run_id> [--base-url http://localhost:8000]
Replay later with POST /run/replay {"run_id": "<run_id>"}.

Must not: store merchant images or catalog text (AGENT_RULES 2.2). Candidates keep only UPIDs, variant
IDs, merchant domains and scores; title, price, currency and image_url are blanked. Never saves a
run that is still processing.
"""
import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

SAVED_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "saved_runs"
KEEP = ("upid", "variant_id", "merchant_domain", "p_same_product", "p_same_variant")
# The contract requires a string title, so it is blanked rather than removed.
BLANKED = {"title": "", "price": None, "currency": None, "image_url": None}


def strip_candidate(cand: dict) -> dict:
    """Return the candidate with only IDs, merchant domain and scores kept; catalog text/images blanked."""
    return {**BLANKED, **{k: cand.get(k) for k in KEEP}}


def strip_run(run: dict) -> dict:
    """Return a copy of the run safe to commit: candidates reduced to IDs and scores."""
    out = json.loads(json.dumps(run))
    for item in out.get("items", []):
        item["candidates"] = [strip_candidate(c) for c in item.get("candidates") or []]
        item["preview"] = None  # generated images are not saved
        item["cart"] = {"cart_id": None, "continue_url": None}
    out["totals"] = {"price": 0, "within_budget": True}  # prices are not stored, so totals cannot be rebuilt
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("run_id")
    ap.add_argument("--base-url", default="http://localhost:8000")
    args = ap.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", args.run_id):
        print("invalid run_id", file=sys.stderr)
        return 2
    try:
        with urllib.request.urlopen(f"{args.base_url}/run/{args.run_id}", timeout=10) as r:
            run = json.load(r)
    except (urllib.error.URLError, OSError) as e:
        print(f"cannot GET run {args.run_id} from {args.base_url}: {e}", file=sys.stderr)
        return 1
    if run.get("state") not in ("done", "failed"):
        print(f"run {args.run_id} is still {run.get('state')}; wait until it is finished", file=sys.stderr)
        return 1
    SAVED_DIR.mkdir(parents=True, exist_ok=True)
    path = SAVED_DIR / f"{args.run_id}.json"
    path.write_text(json.dumps(strip_run(run), indent=2) + "\n")
    print(f"saved {path} ({len(run.get('items', []))} items, state={run['state']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
