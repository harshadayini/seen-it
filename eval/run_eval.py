"""Evaluation runner CLI for Seen It build-set calibration and held-out runs (P2).

What this module does:
    Implements `eval/run_eval.py` per `CLAUDE.md` sections 6, 10, and 15c:
    - Loads `data/eval/<video_id>/labels.json` filtered by `--split build|heldout`.
    - Enforces split discipline: `--sweep` is strictly allowed on `--split build`
      only (refuses to tune thresholds on `heldout`).
    - Runs P1's `extract()` + P2's `resolve()` per video, supporting
      `--compare-relook` to measure exact before-vs-after `relook` recovery lift.
    - Merges optional P1 single-frame baseline JSON (`eval/results/baseline_results.json`)
      and optional P3 manual Google Lens CSV (`eval/results/google_lens.csv`) into
      one unified `eval/results/results.json` and slide-ready SVG charts.
    - Provides `--dry-run` (using `fixtures/sample_run.json`) so the entire
      evaluation & charting pipeline can be verified locally in 1 second.
    - Provides `--resolve-labels <labels.json>` helper to populate ground-truth
      `upid` and `variant_id` fields via live Shopify `lookup_catalog()`.

Use cases:
    - Build-set calibration sweep:
      `python3 -m eval.run_eval --split build --sweep`
    - Held-out final run with `relook` before/after comparison:
      `python3 -m eval.run_eval --split heldout --compare-relook`
    - Dry-run smoke verification (zero external API keys required):
      `python3 -m eval.run_eval --dry-run`
    - Resolve Shopify UPIDs/variant IDs in a ground-truth `labels.json`:
      `python3 -m eval.run_eval --resolve-labels data/eval/v01/labels.json`

What this module must NOT do:
    - Must NEVER tune thresholds on `heldout` videos.
    - Must NEVER save or re-host merchant product images into `eval/results/`.
    - Must NEVER fabricate evaluation metrics when pipeline calls fail.
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import time
from typing import Any, Callable

from backend.config import CONFIG, AppConfig
from backend.matching.logging_utils import get_logger, log_function_call
from backend.matching.status import resolve as default_resolve
from backend.shopify.catalog import lookup_catalog
from backend.video.extract import extract as default_extract
from eval.charts import generate_eval_charts
from eval.metrics import (
    compute_relook_delta,
    evaluate_video_runs,
    load_google_lens_csv,
    sweep_thresholds,
)


LOGGER = get_logger(__name__)


def load_eval_labels(eval_data_dir: Path, split: str) -> list[dict[str, Any]]:
    """Load all `data/eval/<video_id>/labels.json` files matching `split`.

    Args:
        eval_data_dir: Root directory containing per-video subdirectories.
        split: `"build"` or `"heldout"`.

    Returns:
        Sorted list of parsed `labels.json` dictionaries for the requested split.

    Raises:
        ValueError: If `split` is not `"build"` or `"heldout"`.

    Side effects:
        Reads JSON files under `eval_data_dir`.
    """
    if split not in ("build", "heldout"):
        raise ValueError(f"Invalid split '{split}'. Expected 'build' or 'heldout'.")

    if not eval_data_dir.is_dir():
        return []

    labels: list[dict[str, Any]] = []
    for label_path in sorted(eval_data_dir.glob("*/labels.json")):
        data = json.loads(label_path.read_text(encoding="utf-8"))
        if str(data.get("split", "")).strip().lower() == split:
            data["_label_dir"] = str(label_path.parent)
            labels.append(data)
    return labels


def _resolve_video_path(label: dict[str, Any]) -> str:
    """Resolve the local video file path (or source URL) for a ground-truth label.

    Args:
        label: Parsed `labels.json` dictionary.

    Returns:
        Best available video path or source URL string.

    Side effects:
        Checks filesystem existence for local video files inside `_label_dir`.
    """
    explicit = label.get("video_path")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()

    label_dir = label.get("_label_dir")
    if isinstance(label_dir, str):
        for ext in ("mp4", "mov", "webm", "mkv"):
            candidate = Path(label_dir) / f"video.{ext}"
            if candidate.is_file():
                return str(candidate)

    return str(label.get("source_url") or label.get("video_id") or "")


def run_pipeline_on_labels(
    labels: list[dict[str, Any]],
    *,
    enable_relook: bool = True,
    force_resolve: bool = True,
    cfg: AppConfig = CONFIG,
    extract_fn: Callable[[str], list[dict[str, Any]]] | None = None,
    resolve_fn: Callable[..., dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Run extraction + matching resolution across a list of labeled videos.

    Args:
        labels: List of parsed `labels.json` dictionaries.
        enable_relook: Whether to enable single-pass `relook` recovery.
        force_resolve: Passed through to `resolve(..., force=...)`.
        cfg: Active `AppConfig`.
        extract_fn: Injectable P1 extraction function (defaults to `backend.video.extract.extract`).
        resolve_fn: Injectable P2 resolution function (defaults to `backend.matching.status.resolve`).

    Returns:
        List of `{"label": ..., "run": ..., "latency_ms": float}` evaluation records.

    Side effects:
        Executes video extraction and Shopify/Decisions resolution for each video.
    """
    do_extract = extract_fn or default_extract
    do_resolve = resolve_fn or default_resolve

    records: list[dict[str, Any]] = []
    for label in labels:
        video_id = str(label.get("video_id") or "unknown")
        video_path = _resolve_video_path(label)
        t0 = time.monotonic()

        extracted_items = do_extract(video_path)
        resolved_items = [
            do_resolve(
                item,
                video_path=video_path,
                enable_relook=enable_relook,
                force=force_resolve,
                cfg=cfg,
            )
            for item in extracted_items
        ]
        latency_ms = round((time.monotonic() - t0) * 1000.0, 2)

        run_dict = {
            "run_id": f"eval_{video_id}_{'relook' if enable_relook else 'norelook'}",
            "state": "done",
            "mode": "video",
            "source": {"video_id": video_id, "duration_s": None, "budget_usd": None},
            "items": resolved_items,
            "totals": {"price": None, "within_budget": None},
        }
        records.append({"label": label, "run": run_dict, "latency_ms": latency_ms})

    return records


def resolve_ground_truth_labels_file(
    label_path: Path,
    *,
    lookup_fn: Callable[[list[str]], list[dict[str, Any]]] = lookup_catalog,
) -> dict[str, Any]:
    """Populate `upid` and `variant_id` in a `labels.json` via live Shopify `lookup_catalog`.

    Args:
        label_path: Filesystem path to `data/eval/<video_id>/labels.json`.
        lookup_fn: Injectable lookup function (defaults to `backend.shopify.catalog.lookup_catalog`).

    Returns:
        Updated `labels.json` dictionary (also written back to `label_path`).

    Side effects:
        Calls Shopify Global Catalog MCP `lookup_catalog` and updates `label_path` in place.
    """
    log_function_call(LOGGER, "eval.run_eval.resolve_ground_truth_labels_file", {"label_path": str(label_path)})
    data = json.loads(label_path.read_text(encoding="utf-8"))
    products = data.get("products") or []
    urls = [
        p["product_url"].strip()
        for p in products
        if isinstance(p, dict) and isinstance(p.get("product_url"), str) and p["product_url"].strip()
    ]
    if not urls:
        return data

    resolved = lookup_fn(urls)
    by_url: dict[str, tuple[str | None, str | None]] = {}
    for prod in resolved:
        upid = prod.get("id")
        for var in prod.get("variants") or []:
            v_url = str(var.get("url") or "").split("?", 1)[0].rstrip("/").lower()
            if v_url:
                by_url[v_url] = (upid, var.get("id"))

    for prod in products:
        raw_url = str(prod.get("product_url") or "").split("?", 1)[0].rstrip("/").lower()
        if raw_url in by_url:
            prod["upid"], prod["variant_id"] = by_url[raw_url]

    label_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return data


def build_dry_run_records(cfg: AppConfig = CONFIG) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build deterministic fixture-backed `(without_relook, with_relook)` records for `--dry-run`.

    Clearly labeled as a fixture dry-run so teammates can verify `results.json`
    and SVG chart generation before live videos are collected.

    Args:
        cfg: Active `AppConfig` pointing to `fixtures/sample_run.json`.

    Returns:
        Tuple of `(records_without_relook, records_with_relook)`.

    Side effects:
        Reads `fixtures/sample_run.json`.
    """
    sample_run = json.loads(cfg.fixtures_sample_run_path.read_text(encoding="utf-8"))
    label = {
        "video_id": sample_run["source"]["video_id"],
        "split": "build",
        "source_url": "fixture://sample_run",
        "products": [
            {
                "name": "matte black arc floor lamp brass base",
                "product_url": "https://lumen-and-oak.myshopify.com/products/arc-floor-lamp",
                "upid": "gid://shopify/p/7Fq2kLm9XaR4",
                "variant_id": "gid://shopify/ProductVariant/44120398110",
                "color": "black",
                "approx_t": 13.5,
            },
            {
                "name": "cream boucle accent chair curved back walnut legs",
                "product_url": "https://softline-furniture.myshopify.com/products/curved-boucle-armchair",
                "upid": "gid://shopify/p/9Hd5sWe2YkL1",
                "variant_id": "gid://shopify/ProductVariant/45230917782",
                "color": "ivory",
                "approx_t": 43.0,
            },
            {
                "name": "small hand-thrown speckled ceramic vase",
                "product_url": "https://example.com/vintage-unlisted-vase",
                "upid": None,
                "variant_id": None,
                "color": "off-white",
                "approx_t": 63.5,
            },
        ],
    }

    # Simulate before-relook run where item i2 had not yet recovered to the exact UPID
    before_run = copy.deepcopy(sample_run)
    before_run["items"][1]["recovered"] = False
    before_run["items"][1]["status"] = "none"
    before_run["items"][1]["candidates"] = [
        {
            "upid": "gid://shopify/p/wrong-chair-pre-relook",
            "variant_id": "gid://shopify/ProductVariant/000000",
            "title": "Beige Linen Dining Chair",
            "merchant_domain": "other-shop.myshopify.com",
            "price": 199.0,
            "currency": "USD",
            "image_url": "https://example.com/catalog/dining-chair.jpg",
            "p_same_product": 0.34,
            "p_same_variant": 0.25,
        }
    ]

    with_relook_records = [{"label": label, "run": sample_run, "latency_ms": 420.0}]
    without_relook_records = [{"label": label, "run": before_run, "latency_ms": 310.0}]
    return without_relook_records, with_relook_records


def run_evaluation(
    *,
    split: str = "build",
    do_sweep: bool = False,
    compare_relook: bool = False,
    dry_run: bool = False,
    allow_unfrozen: bool = False,
    output_dir: Path | None = None,
    baseline_json_path: Path | None = None,
    google_lens_csv_path: Path | None = None,
    cfg: AppConfig = CONFIG,
    extract_fn: Callable[[str], list[dict[str, Any]]] | None = None,
    resolve_fn: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Execute an end-to-end evaluation run, writing `results.json` and SVG charts.

    Args:
        split: `"build"` or `"heldout"`.
        do_sweep: If True, runs build-set threshold grid sweep (blocked on `heldout`).
        compare_relook: If True, evaluates both `enable_relook=False` and `True`.
        dry_run: If True, uses `fixtures/sample_run.json` (labeled `dry_run: true`).
        allow_unfrozen: Allows held-out evaluation even if `CONFIG.thresholds.frozen` is False.
        output_dir: Destination directory for `results.json` and `.svg` charts
            (defaults to `cfg.eval_results_dir`).
        baseline_json_path: Optional path to P1's `baseline_results.json`.
        google_lens_csv_path: Optional path to P3's manual `google_lens.csv`.
        cfg: Active `AppConfig`.
        extract_fn: Injectable extraction function for tests.
        resolve_fn: Injectable resolution function for tests.

    Returns:
        Complete `results.json` payload dictionary.

    Raises:
        ValueError: If `--sweep` is requested on `heldout`, or `heldout` is run
            with unfrozen thresholds without `allow_unfrozen=True`.

    Side effects:
        Writes `results.json` and `.svg` charts into `output_dir`.
    """
    log_function_call(
        LOGGER,
        "eval.run_eval.run_evaluation",
        {
            "split": split,
            "do_sweep": do_sweep,
            "compare_relook": compare_relook,
            "dry_run": dry_run,
        },
    )

    if do_sweep and split != "build":
        raise ValueError("Refusing --sweep on non-build split. Never tune thresholds on heldout.")
    if split == "heldout" and not dry_run and not cfg.thresholds.frozen and not allow_unfrozen:
        raise ValueError(
            "Thresholds are not frozen yet (SEEN_IT_THRESHOLDS_FROZEN=false). "
            "Freeze thresholds from the build split before evaluating heldout, "
            "or pass --allow-unfrozen explicitly."
        )

    out_dir = output_dir or cfg.eval_results_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    without_summary: dict[str, Any] | None = None
    relook_delta: dict[str, Any] | None = None

    if dry_run:
        records_without, records_with = build_dry_run_records(cfg)
        with_summary = evaluate_video_runs(records_with)
        without_summary = evaluate_video_runs(records_without)
        relook_delta = compute_relook_delta(without_summary, with_summary)
        sweep_result = sweep_thresholds(records_with) if do_sweep else None
    else:
        labels = load_eval_labels(cfg.eval_data_dir, split)
        records_with = run_pipeline_on_labels(
            labels,
            enable_relook=True,
            cfg=cfg,
            extract_fn=extract_fn,
            resolve_fn=resolve_fn,
        )
        with_summary = evaluate_video_runs(records_with)
        if compare_relook:
            records_without = run_pipeline_on_labels(
                labels,
                enable_relook=False,
                cfg=cfg,
                extract_fn=extract_fn,
                resolve_fn=resolve_fn,
            )
            without_summary = evaluate_video_runs(records_without)
            relook_delta = compute_relook_delta(without_summary, with_summary)
        sweep_result = sweep_thresholds(records_with) if do_sweep else None

    # Optional P1 baseline JSON and P3 manual Google Lens CSV
    b_path = baseline_json_path or (out_dir / "baseline_results.json")
    baseline_summary = (
        json.loads(b_path.read_text(encoding="utf-8")) if b_path.is_file() else None
    )
    lens_path = google_lens_csv_path or (out_dir / "google_lens.csv")
    lens_summary = load_google_lens_csv(lens_path)

    comparison: list[dict[str, Any]] = []
    if isinstance(baseline_summary, dict):
        comparison.append(
            {
                "label": "Single-Frame Baseline",
                "exact": baseline_summary.get("exact_product_accuracy", 0.0),
                "variant": baseline_summary.get("variant_accuracy", 0.0),
            }
        )
    if isinstance(lens_summary, dict):
        comparison.append(
            {
                "label": "Google Lens (Shopify)",
                "exact": lens_summary.get("exact_product_accuracy", 0.0),
                "variant": lens_summary.get("variant_accuracy", 0.0),
            }
        )
    if without_summary is not None:
        comparison.append(
            {
                "label": "Seen It (No relook)",
                "exact": without_summary["exact_product_accuracy"],
                "variant": without_summary["variant_accuracy"],
            }
        )
    comparison.append(
        {
            "label": "Seen It (+ relook)",
            "exact": with_summary["exact_product_accuracy"],
            "variant": with_summary["variant_accuracy"],
        }
    )

    payload: dict[str, Any] = {
        "split": "dry_run_fixture" if dry_run else split,
        "dry_run": dry_run,
        "thresholds_used": {
            "exact_product": cfg.thresholds.exact_product,
            "exact_variant": cfg.thresholds.exact_variant,
            "similar_product": cfg.thresholds.similar_product,
            "frozen": cfg.thresholds.frozen,
        },
        "seen_it_with_relook": with_summary,
        "seen_it_without_relook": without_summary,
        "relook_delta": relook_delta,
        "baseline": baseline_summary,
        "google_lens": lens_summary,
        "threshold_sweep": sweep_result,
        "comparison": comparison,
    }

    results_file = out_dir / "results.json"
    results_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    charts = generate_eval_charts(payload, out_dir)
    payload["generated_charts"] = charts
    results_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    LOGGER.info(
        f"Evaluation complete ({payload['split']}): exact={with_summary['exact_product_accuracy']}, "
        f"variant={with_summary['variant_accuracy']}, charts={len(charts)}"
    )
    return payload


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for `python3 -m eval.run_eval`.

    Args:
        argv: Optional CLI argument list (defaults to `sys.argv[1:]`).

    Returns:
        Exit code (`0` on success).

    Side effects:
        Runs evaluation or label resolution and prints concise summary to stdout.
    """
    parser = argparse.ArgumentParser(description="Seen It evaluation & threshold calibration harness (P2)")
    parser.add_argument("--split", choices=("build", "heldout"), default="build")
    parser.add_argument("--sweep", action="store_true", help="Sweep thresholds on build split only")
    parser.add_argument("--compare-relook", action="store_true", help="Run with and without relook")
    parser.add_argument("--dry-run", action="store_true", help="Verify pipeline using fixtures/sample_run.json")
    parser.add_argument("--allow-unfrozen", action="store_true", help="Allow heldout run before freezing thresholds")
    parser.add_argument("--output-dir", type=Path, default=None, help="Output directory (default eval/results)")
    parser.add_argument("--resolve-labels", type=Path, default=None, help="Fill upid/variant_id in a labels.json via Shopify lookup")
    args = parser.parse_args(argv)

    if args.resolve_labels is not None:
        updated = resolve_ground_truth_labels_file(args.resolve_labels)
        print(f"Resolved labels in {args.resolve_labels} ({len(updated.get('products', []))} products)")
        return 0

    result = run_evaluation(
        split=args.split,
        do_sweep=args.sweep,
        compare_relook=args.compare_relook,
        dry_run=args.dry_run,
        allow_unfrozen=args.allow_unfrozen,
        output_dir=args.output_dir,
    )
    summary = result["seen_it_with_relook"]
    print(
        f"EVAL ({result['split']}): recall={summary['items_found_recall']} | "
        f"exact={summary['exact_product_accuracy']} | variant={summary['variant_accuracy']} | "
        f"recovered={summary['recovered_items_count']}"
    )
    if result.get("threshold_sweep"):
        print("\nRecommended frozen thresholds (.env):")
        print(result["threshold_sweep"]["env_freeze_snippet"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
