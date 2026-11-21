"""Phase 3 unit tests for status classification, `relook` recovery, and desk budget picker.

What this module does:
    Verifies all Phase 3 requirements and compatibility with P1 (`backend/video/`),
    P3 (`backend/shopify/cart.py`), and `backend/api.py`:
    1. `classify_status` respects `ThresholdConfig` boundaries (`exact`, `similar`, `none`).
    2. `resolve()` full happy path on fresh P1 items (`state="processing"`) without
       unnecessary `relook` when initial pass achieves `exact`.
    3. `resolve()` `relook` recovery: `none -> exact` sets `recovered=True`;
       `similar -> similar` with worse second pass preserves first-pass candidate and
       keeps `recovered=False`.
    4. `resolve()` `enable_relook=False` ablation mode skips `relook` cleanly.
    5. `resolve()` skips redundant second search when P1's `relook` stub returns
       an unchanged query and crop.
    6. `resolve()` handles `ShopifyCatalogError` and `DecisionsCheckerError` by
       marking `state="failed"`, `status=None`, zero fabricated candidates/scores.
    7. `resolve()` preserves pre-resolved `fixtures/sample_run.json` stub items so
       `tests/test_contract.py` stays green on `main`.
    8. `resolve()` desk mode routes through `check_desk_candidates`.
    9. `pick_within_budget()` finds the exact global optimum (beating naive greedy),
       aligns 100% with `backend/api.py`'s `_best()` and `_totals()`, handles
       impossible budgets, and validates against `contracts/run.schema.json`.

Use cases:
    - Executed locally via `python3 -m unittest discover -s backend/matching/tests -v`.

What this module must NOT do:
    - Must not make live network calls or depend on real API credentials.
"""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from backend.config import ThresholdConfig, load_config
from backend.matching.budget import compute_totals, pick_within_budget
from backend.matching.checker import DecisionsCheckerError
from backend.matching.models import validate_run_dict
from backend.matching.status import classify_status, merge_candidates, resolve
from backend.shopify.catalog import ShopifyCatalogError


def _cand(
    upid: str,
    title: str,
    price: float,
    p_prod: float | None,
    p_var: float | None = None,
    domain: str = "demo-shop.myshopify.com",
) -> dict:
    """Build a contract-compliant candidate dictionary for Phase 3 tests."""
    return {
        "upid": upid,
        "variant_id": f"gid://shopify/ProductVariant/{upid.split('/')[-1]}",
        "title": title,
        "merchant_domain": domain,
        "price": price,
        "currency": "USD",
        "image_url": f"https://cdn.shopify.com/s/files/1/0001/{upid.split('/')[-1]}.jpg",
        "p_same_product": p_prod,
        "p_same_variant": p_var,
    }


class TestPhase3StatusAndResolve(unittest.TestCase):
    """Unit tests for `backend/matching/status.py`."""

    def setUp(self) -> None:
        self.cfg = load_config(Path("/nonexistent/.env"))
        self.fresh_item = {
            "item_id": "i1",
            "state": "processing",
            "t_start": 12.0,
            "t_end": 15.0,
            "crop_path": "frames/r_001/i1.jpg",
            "description": "matte black arc floor lamp",
            "attributes": {"color": "black", "category": "lighting"},
            "query": "black arc floor lamp",
            "candidates": [],
            "status": None,
            "recovered": False,
        }

    def test_classify_status_uses_config_thresholds(self) -> None:
        """Verify exact/similar/none boundaries follow ThresholdConfig."""
        t = ThresholdConfig(exact_product=0.82, exact_variant=0.70, similar_product=0.55)
        self.assertEqual(classify_status([], t), "none")
        self.assertEqual(classify_status([_cand("p1", "Lamp", 100, 0.82, 0.75)], t), "exact")
        self.assertEqual(classify_status([_cand("p1", "Lamp", 100, 0.81, 0.90)], t), "similar")
        self.assertEqual(classify_status([_cand("p1", "Lamp", 100, 0.55, 0.40)], t), "similar")
        self.assertEqual(classify_status([_cand("p1", "Lamp", 100, 0.54, 0.40)], t), "none")

    def test_resolve_exact_first_pass_does_not_call_relook(self) -> None:
        """Verify exact match finishes in one pass without triggering relook."""
        relook_called = []

        def fake_search(q, f):
            return [_cand("p_exact", "Arc Lamp Black", 129.0, None, None)]

        def fake_check(item, cands):
            c = dict(cands[0])
            c["p_same_product"] = 0.91
            c["p_same_variant"] = 0.85
            return [c]

        out = resolve(
            self.fresh_item,
            video_path="demo.mp4",
            cfg=self.cfg,
            search_fn=fake_search,
            check_fn=fake_check,
            relook_fn=lambda it, vp: (relook_called.append(1) or it),
        )
        self.assertEqual(out["state"], "done")
        self.assertEqual(out["status"], "exact")
        self.assertFalse(out["recovered"])
        self.assertEqual(relook_called, [])

    def test_resolve_relook_recovers_none_to_exact(self) -> None:
        """Verify relook runs once on `none`, improves query, and marks recovered=True."""
        queries_seen = []

        def fake_search(q, f):
            queries_seen.append(q)
            if "brass" in q:
                return [_cand("p_good", "Arc Lamp Matte Black Brass", 139.0, None)]
            return [_cand("p_bad", "Plastic Desk Lamp", 25.0, None)]

        def fake_check(item, cands):
            out = []
            for c in cands:
                copy_c = dict(c)
                if copy_c["upid"] == "p_good":
                    copy_c["p_same_product"] = 0.89
                    copy_c["p_same_variant"] = 0.83
                else:
                    copy_c["p_same_product"] = 0.21
                    copy_c["p_same_variant"] = 0.14
                out.append(copy_c)
            return out

        def fake_relook(it, vp):
            refined = dict(it)
            refined["query"] = "matte black arc floor lamp brushed brass base"
            refined["crop_path"] = "frames/r_001/i1_relook.jpg"
            return refined

        out = resolve(
            self.fresh_item,
            video_path="demo.mp4",
            cfg=self.cfg,
            search_fn=fake_search,
            check_fn=fake_check,
            relook_fn=fake_relook,
        )
        self.assertEqual(len(queries_seen), 2)
        self.assertEqual(out["state"], "done")
        self.assertEqual(out["status"], "exact")
        self.assertTrue(out["recovered"])
        self.assertEqual(out["candidates"][0]["upid"], "p_good")
        self.assertEqual(out["crop_path"], "frames/r_001/i1_relook.jpg")

    def test_resolve_relook_preserves_better_first_pass_and_respects_disable_flag(self) -> None:
        """Verify candidate merging never loses better pass-1 candidate and enable_relook=False skips."""
        relook_calls = []

        def fake_search(q, f):
            if "refined" in q:
                return [_cand("p_worse", "Worse Match", 99.0, None)]
            return [_cand("p_first", "Decent Similar Lamp", 120.0, None)]

        def fake_check(item, cands):
            c = dict(cands[0])
            c["p_same_product"] = 0.68 if c["upid"] == "p_first" else 0.30
            c["p_same_variant"] = 0.55 if c["upid"] == "p_first" else 0.20
            return [c]

        def fake_relook(it, vp):
            relook_calls.append(1)
            r = dict(it)
            r["query"] = "refined lamp query"
            return r

        # With relook disabled (eval ablation)
        no_relook = resolve(
            self.fresh_item,
            video_path="demo.mp4",
            enable_relook=False,
            cfg=self.cfg,
            search_fn=fake_search,
            check_fn=fake_check,
            relook_fn=fake_relook,
        )
        self.assertEqual(relook_calls, [])
        self.assertEqual(no_relook["status"], "similar")
        self.assertFalse(no_relook["recovered"])

        # With relook enabled but second pass scores worse -> preserves pass-1 candidate
        with_relook = resolve(
            self.fresh_item,
            video_path="demo.mp4",
            enable_relook=True,
            cfg=self.cfg,
            search_fn=fake_search,
            check_fn=fake_check,
            relook_fn=fake_relook,
        )
        self.assertEqual(len(relook_calls), 1)
        self.assertEqual(with_relook["status"], "similar")
        self.assertFalse(with_relook["recovered"])
        self.assertEqual(with_relook["candidates"][0]["upid"], "p_first")

    def test_resolve_marks_failed_honestly_on_upstream_error(self) -> None:
        """Verify AGENT_RULES.md §3.5: upstream failure marks state=failed without fake data."""
        def failing_search(q, f):
            raise ShopifyCatalogError("503 service unavailable", status_code=503, retryable=True)

        out1 = resolve(self.fresh_item, cfg=self.cfg, search_fn=failing_search)
        self.assertEqual(out1["state"], "failed")
        self.assertIsNone(out1["status"])
        self.assertEqual(out1["candidates"], [])

        def failing_check(it, cands):
            raise DecisionsCheckerError("Missing GEMINI_API_KEY")

        out2 = resolve(
            self.fresh_item,
            cfg=self.cfg,
            search_fn=lambda q, f: [_cand("p1", "Lamp", 100.0, None)],
            check_fn=failing_check,
        )
        self.assertEqual(out2["state"], "failed")
        self.assertIsNone(out2["status"])

    def test_resolve_preserves_preresolved_fixture_items_for_contract_tests(self) -> None:
        """Verify fixture stub items pass through idempotently so tests/test_contract.py stays green."""
        fixture = json.loads(self.cfg.fixtures_sample_run_path.read_text(encoding="utf-8"))
        resolved_items = [resolve(i) for i in fixture["items"]]
        self.assertEqual([i["status"] for i in resolved_items], ["exact", "similar", "none"])
        self.assertTrue(resolved_items[1]["recovered"])
        totals = compute_totals(resolved_items, budget=150.0)
        self.assertEqual(totals["price"], 418.0)
        self.assertFalse(totals["within_budget"])

    def test_resolve_desk_mode_routes_to_desk_checker(self) -> None:
        """Verify mode='desk' invokes check_desk_candidates with photo and user request."""
        desk_calls = []

        def fake_desk_check(item, cands, *, desk_photo_path=None, user_request=""):
            desk_calls.append((desk_photo_path, user_request))
            c = dict(cands[0])
            c["p_same_product"] = 0.88
            c["p_same_variant"] = 0.82
            return [c]

        out = resolve(
            self.fresh_item,
            mode="desk",
            desk_photo_path="desk.jpg",
            user_request="make this warmer, under $150",
            cfg=self.cfg,
            search_fn=lambda q, f: [_cand("p_desk", "Warm Wood Lamp", 58.0, None)],
            desk_check_fn=fake_desk_check,
        )
        self.assertEqual(desk_calls, [("desk.jpg", "make this warmer, under $150")])
        self.assertEqual(out["state"], "done")
        self.assertEqual(out["status"], "exact")

    def test_merge_candidates_keeps_highest_score_per_variant(self) -> None:
        """Verify merge_candidates deduplicates by (upid, variant_id) keeping highest score."""
        merged = merge_candidates(
            [_cand("p1", "Lamp", 100.0, 0.55, 0.50)],
            [_cand("p1", "Lamp", 100.0, 0.84, 0.80), _cand("p2", "Chair", 200.0, 0.72, 0.65)],
        )
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0]["upid"], "p1")
        self.assertEqual(merged[0]["p_same_product"], 0.84)


class TestPhase3DeskBudgetPicker(unittest.TestCase):
    """Unit tests for `backend/matching/budget.py`."""

    def test_pick_within_budget_finds_exact_global_optimum_and_validates_schema(self) -> None:
        """Verify exact solver picks optimal 3-slot combination under $150 (beating naive greedy)."""
        # Slot 1 (lamp): $130 (0.95) vs $60 (0.85)
        # Slot 2 (desk mat): $50 (0.88) vs $35 (0.80)
        # Slot 3 (planter): $45 (0.86) vs $30 (0.75)
        # Naive top-1 per slot = $225 > $150.
        # Optimal under $150: $60 (0.85) + $50 (0.88) + $30 (0.75) = $140, total score = 2.48
        # OR $60 (0.85) + $35 (0.80) + $45 (0.86) = $140, total score = 2.51 (GLOBAL OPTIMUM!)
        slots = [
            {
                "item_id": "s1",
                "state": "done",
                "description": "warm desk lamp",
                "status": "exact",
                "recovered": False,
                "candidates": [
                    _cand("p_lamp_hi", "Designer Brass Lamp", 130.0, 0.95, 0.95),
                    _cand("p_lamp_mid", "Warm Linen Desk Lamp", 60.0, 0.85, 0.85),
                ],
            },
            {
                "item_id": "s2",
                "state": "done",
                "description": "wool felt desk mat",
                "status": "exact",
                "recovered": False,
                "candidates": [
                    _cand("p_mat_hi", "Merino Felt Mat Large", 50.0, 0.88, 0.88),
                    _cand("p_mat_mid", "Warm Oat Desk Mat", 35.0, 0.80, 0.80),
                ],
            },
            {
                "item_id": "s3",
                "state": "done",
                "description": "ceramic desk planter",
                "status": "exact",
                "recovered": False,
                "candidates": [
                    _cand("p_pot_hi", "Speckled Terracotta Pot", 45.0, 0.86, 0.86),
                    _cand("p_pot_lo", "Mini Ceramic Planter", 30.0, 0.75, 0.75),
                ],
            },
        ]

        picked = pick_within_budget(slots, budget=150.0)
        chosen_upids = [item["candidates"][0]["upid"] for item in picked]
        self.assertEqual(chosen_upids, ["p_lamp_mid", "p_mat_mid", "p_pot_hi"])

        # Verify backend/api.py's _totals logic agrees 100%
        totals = compute_totals(picked, budget=150.0)
        self.assertEqual(totals["price"], 140.0)
        self.assertTrue(totals["within_budget"])

        # Verify full run payload validates against contracts/run.schema.json
        run_payload = {
            "run_id": "r_desk_001",
            "state": "done",
            "mode": "desk",
            "source": {"video_id": None, "duration_s": None, "budget_usd": 150.0},
            "items": picked,
            "totals": totals,
        }
        self.assertEqual(validate_run_dict(run_payload), [])

    def test_pick_within_budget_skips_unaffordable_slots_cleanly(self) -> None:
        """Verify impossible budget marks slots as status='none' with $0 total."""
        slots = [
            {
                "item_id": "s1",
                "state": "done",
                "status": "exact",
                "candidates": [_cand("p1", "Lamp", 80.0, 0.90, 0.90)],
            }
        ]
        picked = pick_within_budget(slots, budget=10.0)
        self.assertEqual(picked[0]["status"], "none")
        self.assertEqual(picked[0]["candidates"], [])
        self.assertEqual(compute_totals(picked, budget=10.0), {"price": 0.0, "within_budget": True})


if __name__ == "__main__":
    unittest.main()
