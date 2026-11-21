"""Phase 5 unit tests for evaluation metrics, calibration, threshold sweep, and SVG charts.

What this module does:
    Verifies all Phase 5 evaluation requirements (`CLAUDE.md` §10 & §15c):
    1. Alignment, item recall, exact-product top-1/top-3 accuracy, variant/color
       accuracy, and invented-item review table generation.
    2. 3-row calibration table (`0.50-0.70`, `0.70-0.85`, `0.85-1.00`) and ECE.
    3. Build-set threshold sweep succeeds on `build` and strictly refuses `heldout`.
    4. `relook` before-vs-after delta computation.
    5. Failure gallery categorization (`motion_blur`, `look_alike`, `not_in_catalog`).
    6. Manual Google Lens CSV parsing (`found_any_retailer`, `found_on_shopify`, `color_match`).
    7. End-to-end `run_evaluation(dry_run=True)` writing valid `results.json`
       and all 3 slide-ready SVG charts into a temporary directory.

Use cases:
    - Executed locally via `python3 -m unittest discover -s backend/matching/tests -v`.

What this module must NOT do:
    - Must not make live network requests or pollute `eval/results/` during unit tests.
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from backend.config import load_config
from eval.metrics import (
    compute_calibration_table,
    compute_relook_delta,
    evaluate_video_runs,
    load_google_lens_csv,
    sweep_thresholds,
)
from eval.run_eval import build_dry_run_records, run_evaluation


class TestPhase5EvalMetrics(unittest.TestCase):
    """Unit tests for `eval/metrics.py`."""

    def setUp(self) -> None:
        self.cfg = load_config(Path("/nonexistent/.env"))

    def test_calibration_table_bins_and_ece(self) -> None:
        """Verify 3-row calibration bins and ECE calculation."""
        obs = [
            (0.55, False),
            (0.65, True),    # bin 0.50-0.70 -> mean=0.60, acc=0.50, gap=0.10
            (0.75, True),
            (0.80, True),    # bin 0.70-0.85 -> mean=0.775, acc=1.00, gap=0.225
            (0.90, True),
            (0.94, True),    # bin 0.85-1.00 -> mean=0.92, acc=1.00, gap=0.08
        ]
        cal = compute_calibration_table(obs)
        self.assertEqual(len(cal["rows"]), 3)
        self.assertEqual(cal["rows"][0]["bin"], "0.50-0.70")
        self.assertEqual(cal["rows"][0]["count"], 2)
        self.assertAlmostEqual(cal["rows"][0]["mean_confidence"], 0.60, places=4)
        self.assertAlmostEqual(cal["rows"][0]["empirical_accuracy"], 0.50, places=4)
        self.assertEqual(cal["rows"][2]["bin"], "0.85-1.00")
        self.assertAlmostEqual(cal["rows"][2]["empirical_accuracy"], 1.0, places=4)
        self.assertIsNotNone(cal["ece"])

    def test_evaluate_video_runs_and_relook_delta_on_dry_run_fixture(self) -> None:
        """Verify recall, exact match, variant accuracy, failure gallery, and relook lift."""
        before_records, after_records = build_dry_run_records(self.cfg)
        before_sum = evaluate_video_runs(before_records)
        after_sum = evaluate_video_runs(after_records)
        delta = compute_relook_delta(before_sum, after_sum)

        # Fixture has 3 GT items (2 with Shopify UPIDs, 1 unlisted ceramic vase)
        self.assertEqual(after_sum["items_found_recall"], 1.0)
        self.assertEqual(after_sum["exact_product_accuracy"], 1.0)
        self.assertEqual(before_sum["exact_product_accuracy"], 0.5)
        self.assertEqual(delta["exact_accuracy_delta"], 0.5)
        self.assertEqual(delta["recovered_items_count"], 1)
        # Unlisted ceramic vase surfaces cleanly in failure gallery as not_in_catalog
        causes = {f["cause"] for f in after_sum["failure_gallery"]}
        self.assertIn("not_in_catalog", causes)

    def test_sweep_thresholds_works_on_build_and_blocks_heldout(self) -> None:
        """Verify build-only threshold sweep enforces CLAUDE.md split integrity."""
        _before, after_records = build_dry_run_records(self.cfg)
        sweep = sweep_thresholds(after_records)
        self.assertIn("exact_product", sweep["best_thresholds"])
        self.assertIn("SEEN_IT_THRESHOLDS_FROZEN=true", sweep["env_freeze_snippet"])

        # Attempting to sweep on heldout MUST raise ValueError
        heldout_records = json.loads(json.dumps(after_records))
        heldout_records[0]["label"]["split"] = "heldout"
        with self.assertRaises(ValueError):
            sweep_thresholds(heldout_records)

    def test_google_lens_csv_loader(self) -> None:
        """Verify manual Google Lens CSV parses any-retailer, Shopify, and color rates."""
        with tempfile.TemporaryDirectory() as tmp:
            csv_file = Path(tmp) / "google_lens.csv"
            csv_file.write_text(
                "video_id,item_name,found_any_retailer,found_on_shopify,color_match\n"
                "v01,Arc Lamp,yes,yes,yes\n"
                "v01,Chair,yes,no,yes\n"
                "v02,Mug,no,no,no\n"
                "v02,Rug,yes,yes,no\n",
                encoding="utf-8",
            )
            lens = load_google_lens_csv(csv_file)
            assert lens is not None
            self.assertEqual(lens["sample_size"], 4)
            self.assertEqual(lens["found_any_retailer_accuracy"], 0.75)
            self.assertEqual(lens["exact_product_accuracy"], 0.50)
            self.assertEqual(lens["variant_accuracy"], 0.50)


class TestPhase5RunEvalEndToEnd(unittest.TestCase):
    """End-to-end tests for `eval/run_eval.py` and `eval/charts.py`."""

    def setUp(self) -> None:
        self.cfg = load_config(Path("/nonexistent/.env"))

    def test_dry_run_writes_results_json_and_all_three_svg_charts(self) -> None:
        """Verify dry-run generates results.json + comparison, calibration, and relook SVGs."""
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            # Include optional baseline JSON and Google Lens CSV to test full 4-bar chart
            (out_dir / "baseline_results.json").write_text(
                json.dumps({"exact_product_accuracy": 0.35, "variant_accuracy": 0.25}),
                encoding="utf-8",
            )
            (out_dir / "google_lens.csv").write_text(
                "video_id,item_name,found_any_retailer,found_on_shopify,color_match\n"
                "v01,Lamp,true,true,true\n"
                "v01,Chair,true,false,false\n",
                encoding="utf-8",
            )

            payload = run_evaluation(
                split="build",
                do_sweep=True,
                compare_relook=True,
                dry_run=True,
                output_dir=out_dir,
                cfg=self.cfg,
            )

            self.assertTrue((out_dir / "results.json").is_file())
            self.assertTrue((out_dir / "comparison_chart.svg").is_file())
            self.assertTrue((out_dir / "calibration_chart.svg").is_file())
            self.assertTrue((out_dir / "relook_recovery_chart.svg").is_file())
            self.assertEqual(len(payload["comparison"]), 4)
            self.assertIn("<svg", (out_dir / "comparison_chart.svg").read_text(encoding="utf-8"))

    def test_heldout_refuses_unfrozen_thresholds_unless_explicitly_overridden(self) -> None:
        """Verify held-out run blocks accidental evaluation before freezing build thresholds."""
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                run_evaluation(
                    split="heldout",
                    do_sweep=False,
                    dry_run=False,
                    output_dir=Path(tmp),
                    cfg=self.cfg,
                )


if __name__ == "__main__":
    unittest.main()
