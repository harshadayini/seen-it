"""Evaluation metrics, 3-row calibration table, threshold sweep, and failure gallery (P2).

What this module does:
    Computes all quantitative metrics required by `CLAUDE.md` section 10 for
    Seen It's "Proof it works" judging criterion:
    - Item recall (items found vs ground-truth `labels.json`).
    - Exact-product match accuracy (top-1 UPID match and top-3 UPID recall).
    - Color / variant accuracy (`variant_id` exact match or color match fallback).
    - Unmatched / invented-item review table for hand auditing.
    - 3-row confidence calibration table (`[0.50, 0.70)`, `[0.70, 0.85)`,
      `[0.85, 1.00]`) + Expected Calibration Error (ECE).
    - `relook` before-vs-after recovery delta.
    - Build-set threshold sweep (`sweep_thresholds`, strictly blocked on `heldout`).
    - Categorized 3-example Failure Gallery (`motion_blur`, `look_alike`,
      `not_in_catalog`).
    - Unified comparison table merging P1's single-frame baseline, P3's manual
      Google Lens CSV/JSON results, Seen It (no relook), and Seen It (+ relook).

Use cases:
    - Imported by `eval/run_eval.py` to score build and held-out evaluation runs.
    - Imported by unit tests (`backend/matching/tests/test_phase5_eval.py`).

What this module must NOT do:
    - Must NEVER tune thresholds on `heldout` videos (`sweep_thresholds` raises
      `ValueError` if any label entry has `split != "build"`).
    - Must NEVER fabricate metrics or hide failed items.
    - Must NEVER persist merchant image bytes.
"""

from __future__ import annotations

import csv
from pathlib import Path
import re
from typing import Any

from backend.config import ThresholdConfig
from backend.matching.logging_utils import get_logger, log_function_call


LOGGER = get_logger(__name__)

# 3-row calibration bins per CLAUDE.md §10 ("does 0.8 confidence mean about 80% correct?")
CALIBRATION_BINS: tuple[tuple[str, float, float, bool], ...] = (
    ("0.50-0.70", 0.50, 0.70, False),
    ("0.70-0.85", 0.70, 0.85, False),
    ("0.85-1.00", 0.85, 1.00, True),
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_COLOR_WORDS = frozenset(
    {
        "black",
        "white",
        "ivory",
        "cream",
        "beige",
        "oat",
        "tan",
        "brown",
        "walnut",
        "oak",
        "brass",
        "gold",
        "silver",
        "chrome",
        "nickel",
        "gray",
        "grey",
        "charcoal",
        "blue",
        "navy",
        "green",
        "olive",
        "sage",
        "red",
        "rust",
        "terracotta",
        "pink",
        "blush",
        "yellow",
        "orange",
        "purple",
    }
)


def _tokenize(text: str | None) -> set[str]:
    """Extract lowercase alphanumeric word tokens from text for fuzzy alignment.

    Args:
        text: Input label, description, or title string.

    Returns:
        Set of lowercase word tokens (`len >= 2`).

    Side effects:
        None.
    """
    if not text:
        return set()
    return {tok for tok in _TOKEN_RE.findall(text.lower()) if len(tok) >= 2}


def _extract_colors(text: str | None) -> set[str]:
    """Extract known color words from a product name, title, or attribute value.

    Args:
        text: Arbitrary product text.

    Returns:
        Set of matched color tokens.

    Side effects:
        None.
    """
    return _tokenize(text) & _COLOR_WORDS


def _normalize_id(val: str | None) -> str | None:
    """Normalize a Shopify GID or URL string for exact equality checks.

    Args:
        val: Raw UPID or variant ID string (or `None`).

    Returns:
        Stripped string, or `None` when empty.

    Side effects:
        None.
    """
    if not isinstance(val, str):
        return None
    cleaned = val.strip()
    return cleaned if cleaned else None


def _item_midpoint_t(item: dict[str, Any]) -> float | None:
    """Compute midpoint timestamp of a predicted item if `t_start`/`t_end` exist.

    Args:
        item: Predicted item dictionary.

    Returns:
        Midpoint timestamp in seconds, or `None` if unavailable.

    Side effects:
        None.
    """
    t_start = item.get("t_start")
    t_end = item.get("t_end")
    if isinstance(t_start, (int, float)) and isinstance(t_end, (int, float)):
        return (float(t_start) + float(t_end)) / 2.0
    if isinstance(t_start, (int, float)):
        return float(t_start)
    if isinstance(t_end, (int, float)):
        return float(t_end)
    return None


def _alignment_score(pred_item: dict[str, Any], gt_prod: dict[str, Any]) -> float:
    """Score how likely a predicted item corresponds to a ground-truth product.

    Strongly favors exact UPID overlap in top candidates, then combines
    name/description token Jaccard similarity and timestamp proximity.

    Args:
        pred_item: Predicted item dictionary from Seen It.
        gt_prod: Ground-truth product entry from `labels.json`.

    Returns:
        Alignment score `>= 0.0` (0.0 means no plausible match).

    Side effects:
        None.
    """
    gt_upid = _normalize_id(gt_prod.get("upid"))
    cands = pred_item.get("candidates") or []
    cand_upids = [_normalize_id(c.get("upid")) for c in cands if isinstance(c, dict)]

    # Exact UPID hit in top-1 or top-3 is a decisive alignment signal.
    if gt_upid and gt_upid in cand_upids:
        return 10.0 if cand_upids[0] == gt_upid else 6.0

    gt_tokens = _tokenize(gt_prod.get("name"))
    pred_text = " ".join(
        filter(
            None,
            [
                str(pred_item.get("description") or ""),
                str(pred_item.get("query") or ""),
                str((cands[0].get("title") if cands and isinstance(cands[0], dict) else "") or ""),
            ],
        )
    )
    pred_tokens = _tokenize(pred_text)

    lexical = 0.0
    if gt_tokens and pred_tokens:
        overlap = len(gt_tokens & pred_tokens)
        union = len(gt_tokens | pred_tokens)
        recall_overlap = overlap / len(gt_tokens)
        jaccard = overlap / union
        lexical = 0.6 * recall_overlap + 0.4 * jaccard

    time_bonus = 0.0
    approx_t = gt_prod.get("approx_t")
    mid_t = _item_midpoint_t(pred_item)
    if isinstance(approx_t, (int, float)) and mid_t is not None:
        dt = abs(mid_t - float(approx_t))
        if dt <= 10.0:
            time_bonus = 0.35 * (1.0 - dt / 10.0)

    total = lexical + time_bonus
    # Require minimum lexical or close-timestamp+lexical signal to avoid bogus pairing.
    if lexical < 0.15 and time_bonus < 0.25:
        return 0.0
    return total


def align_predictions_to_ground_truth(
    pred_items: list[dict[str, Any]],
    gt_products: list[dict[str, Any]],
) -> tuple[list[tuple[dict[str, Any], dict[str, Any]]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Greedily align predicted items to ground-truth products 1-to-1.

    Args:
        pred_items: Predicted item dicts for a single video.
        gt_products: Ground-truth product entries from `labels.json`.

    Returns:
        Tuple of `(matched_pairs, unmatched_gt_products, unmatched_pred_items)`.

    Side effects:
        None.
    """
    scored_edges: list[tuple[float, int, int]] = []
    for p_idx, pred in enumerate(pred_items):
        for g_idx, gt in enumerate(gt_products):
            score = _alignment_score(pred, gt)
            if score > 0.0:
                scored_edges.append((score, p_idx, g_idx))

    scored_edges.sort(key=lambda row: row[0], reverse=True)
    used_preds: set[int] = set()
    used_gts: set[int] = set()
    matched: list[tuple[dict[str, Any], dict[str, Any]]] = []

    for _score, p_idx, g_idx in scored_edges:
        if p_idx in used_preds or g_idx in used_gts:
            continue
        used_preds.add(p_idx)
        used_gts.add(g_idx)
        matched.append((pred_items[p_idx], gt_products[g_idx]))

    unmatched_gt = [gt_products[i] for i in range(len(gt_products)) if i not in used_gts]
    unmatched_pred = [pred_items[i] for i in range(len(pred_items)) if i not in used_preds]
    return matched, unmatched_gt, unmatched_pred


def _is_exact_product_hit(pred_item: dict[str, Any], gt_prod: dict[str, Any], top_k: int = 1) -> bool:
    """Check whether any of the top-`top_k` predicted candidates matches `gt_prod["upid"]`.

    Args:
        pred_item: Predicted item dictionary.
        gt_prod: Ground-truth product entry.
        top_k: Candidate rank cutoff (1 for top-1 exact match, 3 for top-3 recall).

    Returns:
        True if `gt_prod["upid"]` matches within `candidates[:top_k]`.

    Side effects:
        None.
    """
    gt_upid = _normalize_id(gt_prod.get("upid"))
    if not gt_upid:
        return False
    cands = (pred_item.get("candidates") or [])[:top_k]
    return any(_normalize_id(c.get("upid")) == gt_upid for c in cands if isinstance(c, dict))


def _is_variant_or_color_hit(pred_item: dict[str, Any], gt_prod: dict[str, Any]) -> bool | None:
    """Check top-1 color/variant match against ground truth.

    Uses exact `variant_id` equality when `gt_prod["variant_id"]` is present;
    otherwise compares extracted color tokens from `gt_prod["color"]` or
    `gt_prod["name"]` against top-1 candidate title and item attributes.

    Args:
        pred_item: Predicted item dictionary.
        gt_prod: Ground-truth product entry.

    Returns:
        True/False if variant or color is evaluable, or `None` when ground truth
        has neither `variant_id` nor any color cue.

    Side effects:
        None.
    """
    cands = pred_item.get("candidates") or []
    top = cands[0] if cands and isinstance(cands[0], dict) else None
    gt_vid = _normalize_id(gt_prod.get("variant_id"))
    if gt_vid:
        if top is None:
            return False
        return _normalize_id(top.get("variant_id")) == gt_vid

    gt_colors = _extract_colors(gt_prod.get("color")) or _extract_colors(gt_prod.get("name"))
    if not gt_colors:
        return None
    if top is None:
        return False
    pred_colors = _extract_colors(top.get("title")) | _extract_colors(
        str((pred_item.get("attributes") or {}).get("color") or "")
    )
    return bool(gt_colors & pred_colors)


def compute_calibration_table(
    observations: list[tuple[float, bool]],
) -> dict[str, Any]:
    """Compute the 3-row calibration table and Expected Calibration Error (ECE).

    Bins: `[0.50, 0.70)`, `[0.70, 0.85)`, `[0.85, 1.00]`.

    Args:
        observations: List of `(predicted_p_same_product, is_exact_product_match)`.

    Returns:
        Dictionary containing `"rows"` (list of 3 bin summaries) and `"ece"`.

    Side effects:
        None.
    """
    rows: list[dict[str, Any]] = []
    total_binned = 0
    weighted_gap = 0.0

    for label, lo, hi, inclusive_hi in CALIBRATION_BINS:
        in_bin = [
            (p, correct)
            for p, correct in observations
            if (lo <= p <= hi if inclusive_hi else lo <= p < hi)
        ]
        n = len(in_bin)
        if n == 0:
            rows.append(
                {
                    "bin": label,
                    "range": [lo, hi],
                    "count": 0,
                    "mean_confidence": None,
                    "empirical_accuracy": None,
                    "calibration_gap": None,
                }
            )
            continue

        mean_conf = sum(p for p, _ in in_bin) / n
        emp_acc = sum(1.0 for _, c in in_bin if c) / n
        gap = abs(mean_conf - emp_acc)
        total_binned += n
        weighted_gap += gap * n
        rows.append(
            {
                "bin": label,
                "range": [lo, hi],
                "count": n,
                "mean_confidence": round(mean_conf, 4),
                "empirical_accuracy": round(emp_acc, 4),
                "calibration_gap": round(gap, 4),
            }
        )

    ece = round(weighted_gap / total_binned, 4) if total_binned > 0 else None
    return {"rows": rows, "ece": ece, "binned_count": total_binned}


def classify_failure_cause(
    pred_item: dict[str, Any] | None,
    gt_prod: dict[str, Any],
) -> tuple[str, str]:
    """Categorize a missed ground-truth item into one of the 3 Failure Gallery causes.

    Categories per `CLAUDE.md` section 10:
    - `"not_in_catalog"`: GT product has no resolved catalog UPID, or search returned 0 hits.
    - `"look_alike"`: Candidate returned with moderate/high score (`>= 0.40`) but wrong UPID.
    - `"motion_blur"`: Missed extraction, very brief appearance (`< 1.5s`), blur cue,
      or low visual confidence despite catalog availability.

    Args:
        pred_item: Aligned predicted item dict (or `None` if extraction missed it).
        gt_prod: Ground-truth product entry.

    Returns:
        Tuple of `(category, explanation)`.

    Side effects:
        None.
    """
    if not _normalize_id(gt_prod.get("upid")):
        return (
            "not_in_catalog",
            f"'{gt_prod.get('name', 'Item')}' does not resolve to an eligible Shopify Catalog UPID.",
        )

    if pred_item is None:
        return (
            "motion_blur",
            f"Extractor missed '{gt_prod.get('name', 'Item')}' around t={gt_prod.get('approx_t')}s (fast cut or occlusion).",
        )

    cands = pred_item.get("candidates") or []
    if not cands:
        return (
            "not_in_catalog",
            f"Shopify catalog search returned 0 candidates for '{pred_item.get('query') or gt_prod.get('name')}'.",
        )

    top = cands[0]
    p_prod = float(top.get("p_same_product") or 0.0)
    desc_lower = str(pred_item.get("description") or "").lower()
    t_start = pred_item.get("t_start")
    t_end = pred_item.get("t_end")
    short_window = (
        isinstance(t_start, (int, float))
        and isinstance(t_end, (int, float))
        and (float(t_end) - float(t_start)) < 1.5
    )

    if "blur" in desc_lower or "hidden" in desc_lower or "occluded" in desc_lower or short_window:
        return (
            "motion_blur",
            f"Brief/obscured frame ({t_start}s-{t_end}s) reduced visual match confidence (top p={p_prod:.2f}).",
        )

    if p_prod >= 0.40:
        return (
            "look_alike",
            f"Look-alike '{top.get('title')}' scored p={p_prod:.2f} instead of ground-truth '{gt_prod.get('name')}'.",
        )

    return (
        "motion_blur",
        f"Low visual similarity (p={p_prod:.2f}) between extracted crop and catalog candidates.",
    )


def evaluate_video_runs(
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compute full evaluation metrics across a list of `(label, run)` video records.

    Each element in `records` must contain:
    - `"label"`: deserialized `labels.json` dict (`video_id`, `split`, `products`).
    - `"run"`: contract-compliant run dict (`items[]`).
    - `"latency_ms"` (optional): end-to-end matching latency in ms.

    Args:
        records: List of per-video evaluation record dicts.

    Returns:
        Structured summary dictionary containing recall, exact-product accuracy,
        top-3 recall, color/variant accuracy, recovery counts, calibration table,
        invented-item review table, failure gallery (up to 3 diverse examples),
        and per-video breakdowns.

    Side effects:
        Logs summary metrics at INFO level.
    """
    log_function_call(LOGGER, "eval.metrics.evaluate_video_runs", {"video_count": len(records)})

    total_gt = 0
    total_found = 0
    catalog_gt = 0
    exact_top1 = 0
    exact_top3 = 0
    variant_evaluable = 0
    variant_hits = 0
    recovered_count = 0
    failed_items = 0
    total_pred_items = 0

    calibration_obs: list[tuple[float, bool]] = []
    invented_review: list[dict[str, Any]] = []
    all_failures: list[dict[str, Any]] = []
    per_video: list[dict[str, Any]] = []
    latencies: list[float] = []

    for rec in records:
        label = rec["label"]
        run = rec["run"]
        video_id = str(label.get("video_id") or run.get("source", {}).get("video_id") or "unknown")
        gt_products = list(label.get("products") or [])
        pred_items = list(run.get("items") or [])

        if isinstance(rec.get("latency_ms"), (int, float)):
            latencies.append(float(rec["latency_ms"]))

        total_gt += len(gt_products)
        total_pred_items += len(pred_items)
        failed_items += sum(1 for item in pred_items if item.get("state") == "failed")
        recovered_count += sum(1 for item in pred_items if item.get("recovered") is True)

        matched_pairs, unmatched_gt, unmatched_pred = align_predictions_to_ground_truth(
            pred_items, gt_products
        )
        total_found += len(matched_pairs)

        v_exact = 0
        v_catalog = 0

        for pred_item, gt_prod in matched_pairs:
            has_gt_upid = bool(_normalize_id(gt_prod.get("upid")))
            top1_ok = _is_exact_product_hit(pred_item, gt_prod, top_k=1)
            top3_ok = _is_exact_product_hit(pred_item, gt_prod, top_k=3)

            if has_gt_upid:
                catalog_gt += 1
                v_catalog += 1
                if top1_ok:
                    exact_top1 += 1
                    v_exact += 1
                if top3_ok:
                    exact_top3 += 1

                cands = pred_item.get("candidates") or []
                if cands and isinstance(cands[0].get("p_same_product"), (int, float)):
                    calibration_obs.append((float(cands[0]["p_same_product"]), top1_ok))

            var_ok = _is_variant_or_color_hit(pred_item, gt_prod)
            if var_ok is not None:
                variant_evaluable += 1
                if var_ok:
                    variant_hits += 1

            if not top1_ok:
                cause, explanation = classify_failure_cause(pred_item, gt_prod)
                all_failures.append(
                    {
                        "video_id": video_id,
                        "item_id": pred_item.get("item_id"),
                        "gt_name": gt_prod.get("name"),
                        "gt_upid": gt_prod.get("upid"),
                        "predicted_status": pred_item.get("status"),
                        "top_candidate_title": (
                            pred_item["candidates"][0].get("title")
                            if pred_item.get("candidates")
                            else None
                        ),
                        "top_p_same_product": (
                            pred_item["candidates"][0].get("p_same_product")
                            if pred_item.get("candidates")
                            else None
                        ),
                        "crop_path": pred_item.get("crop_path"),
                        "cause": cause,
                        "explanation": explanation,
                    }
                )

        for gt_prod in unmatched_gt:
            if _normalize_id(gt_prod.get("upid")):
                catalog_gt += 1
                v_catalog += 1
            cause, explanation = classify_failure_cause(None, gt_prod)
            all_failures.append(
                {
                    "video_id": video_id,
                    "item_id": None,
                    "gt_name": gt_prod.get("name"),
                    "gt_upid": gt_prod.get("upid"),
                    "predicted_status": None,
                    "top_candidate_title": None,
                    "top_p_same_product": None,
                    "crop_path": None,
                    "cause": cause,
                    "explanation": explanation,
                }
            )

        for pred_item in unmatched_pred:
            cands = pred_item.get("candidates") or []
            invented_review.append(
                {
                    "video_id": video_id,
                    "item_id": pred_item.get("item_id"),
                    "description": pred_item.get("description"),
                    "crop_path": pred_item.get("crop_path"),
                    "status": pred_item.get("status"),
                    "top_candidate_title": cands[0].get("title") if cands else None,
                    "top_p_same_product": cands[0].get("p_same_product") if cands else None,
                    "is_invented": None,  # Hand-judged boolean (CLAUDE.md §10)
                }
            )

        per_video.append(
            {
                "video_id": video_id,
                "split": label.get("split"),
                "gt_count": len(gt_products),
                "found_count": len(matched_pairs),
                "exact_top1_count": v_exact,
                "catalog_gt_count": v_catalog,
                "unmatched_predictions": len(unmatched_pred),
            }
        )

    # Select up to 3 diverse Failure Gallery examples (1 per cause where available).
    gallery: list[dict[str, Any]] = []
    seen_causes: set[str] = set()
    for failure in all_failures:
        if failure["cause"] not in seen_causes:
            gallery.append(failure)
            seen_causes.add(failure["cause"])
        if len(gallery) >= 3:
            break
    if len(gallery) < 3:
        for failure in all_failures:
            if failure not in gallery:
                gallery.append(failure)
            if len(gallery) >= 3:
                break

    def _rate(num: int, den: int) -> float:
        return round(num / den, 4) if den > 0 else 0.0

    summary = {
        "video_count": len(records),
        "total_gt_products": total_gt,
        "catalog_resolved_gt_products": catalog_gt,
        "total_predicted_items": total_pred_items,
        "failed_items": failed_items,
        "items_found_count": total_found,
        "items_found_recall": _rate(total_found, total_gt),
        "exact_product_top1_count": exact_top1,
        "exact_product_accuracy": _rate(exact_top1, catalog_gt),
        "exact_product_top3_count": exact_top3,
        "exact_product_top3_recall": _rate(exact_top3, catalog_gt),
        "variant_evaluable_count": variant_evaluable,
        "variant_correct_count": variant_hits,
        "variant_accuracy": _rate(variant_hits, variant_evaluable),
        "recovered_items_count": recovered_count,
        "unmatched_predictions_count": len(invented_review),
        "avg_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else None,
        "calibration": compute_calibration_table(calibration_obs),
        "invented_review": invented_review,
        "failure_gallery": gallery,
        "per_video": per_video,
    }
    return summary


def compute_relook_delta(
    without_relook: dict[str, Any],
    with_relook: dict[str, Any],
) -> dict[str, Any]:
    """Compute before-vs-after `relook` recovery lift metrics.

    Args:
        without_relook: Output of `evaluate_video_runs()` with `enable_relook=False`.
        with_relook: Output of `evaluate_video_runs()` with `enable_relook=True`.

    Returns:
        Dictionary summarizing exact-match delta, variant delta, and recovered count.

    Side effects:
        None.
    """
    return {
        "exact_accuracy_before": without_relook["exact_product_accuracy"],
        "exact_accuracy_after": with_relook["exact_product_accuracy"],
        "exact_accuracy_delta": round(
            with_relook["exact_product_accuracy"] - without_relook["exact_product_accuracy"], 4
        ),
        "variant_accuracy_before": without_relook["variant_accuracy"],
        "variant_accuracy_after": with_relook["variant_accuracy"],
        "variant_accuracy_delta": round(
            with_relook["variant_accuracy"] - without_relook["variant_accuracy"], 4
        ),
        "recovered_items_count": with_relook["recovered_items_count"],
    }


def sweep_thresholds(
    build_records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Sweep `(exact_product, similar_product)` thresholds strictly on the `build` split.

    Enforces `CLAUDE.md` section 10 & 15c: refuses to run if any record belongs
    to `heldout` so we never tune on held-out videos.

    Args:
        build_records: List of `{"label": ..., "run": ...}` dicts from `split == "build"`.

    Returns:
        Dictionary with `"best_thresholds"`, `"best_f1"`, `"env_freeze_snippet"`,
        and top-5 grid candidates.

    Raises:
        ValueError: If `build_records` is empty or contains any non-`"build"` video.

    Side effects:
        Logs best build-set thresholds at INFO level.
    """
    if not build_records:
        raise ValueError("sweep_thresholds requires at least one build-split video record.")

    for rec in build_records:
        split = str(rec.get("label", {}).get("split") or "").strip().lower()
        if split != "build":
            raise ValueError(
                f"Refusing to sweep thresholds on split='{split}'. "
                "CLAUDE.md forbids tuning thresholds on heldout videos."
            )

    # Collect (top1_p_same_product, is_true_exact_upid) pairs across aligned items.
    pairs: list[tuple[float, bool]] = []
    for rec in build_records:
        matched, _unmatched_gt, _unmatched_pred = align_predictions_to_ground_truth(
            rec["run"].get("items") or [],
            rec["label"].get("products") or [],
        )
        for pred_item, gt_prod in matched:
            if not _normalize_id(gt_prod.get("upid")):
                continue
            cands = pred_item.get("candidates") or []
            if not cands or not isinstance(cands[0].get("p_same_product"), (int, float)):
                continue
            pairs.append(
                (float(cands[0]["p_same_product"]), _is_exact_product_hit(pred_item, gt_prod, top_k=1))
            )

    exact_grid = [round(0.60 + 0.05 * i, 2) for i in range(7)]  # 0.60 .. 0.90
    similar_grid = [round(0.35 + 0.05 * i, 2) for i in range(8)]  # 0.35 .. 0.70

    grid_results: list[dict[str, Any]] = []
    for ex_t in exact_grid:
        for sim_t in similar_grid:
            if sim_t >= ex_t:
                continue
            ThresholdConfig(exact_product=ex_t, exact_variant=0.70, similar_product=sim_t).validate()

            tp = sum(1 for p, y in pairs if p >= ex_t and y)
            fp = sum(1 for p, y in pairs if p >= ex_t and not y)
            fn = sum(1 for p, y in pairs if p < ex_t and y)
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
            # Prefer similar threshold near 0.50 as a gentle tie-breaker when exact F1 ties.
            sim_reg = -abs(sim_t - 0.50) * 0.001
            grid_results.append(
                {
                    "exact_product": ex_t,
                    "similar_product": sim_t,
                    "precision": round(precision, 4),
                    "recall": round(recall, 4),
                    "f1": round(f1, 4),
                    "_rank": (round(f1, 6), round(precision, 6), sim_reg),
                }
            )

    grid_results.sort(key=lambda r: r["_rank"], reverse=True)
    best = grid_results[0]
    cleaned_top = [{k: v for k, v in row.items() if k != "_rank"} for row in grid_results[:5]]

    snippet = (
        f"SEEN_IT_EXACT_PRODUCT_THRESHOLD={best['exact_product']}\n"
        f"SEEN_IT_SIMILAR_PRODUCT_THRESHOLD={best['similar_product']}\n"
        "SEEN_IT_THRESHOLDS_FROZEN=true"
    )
    LOGGER.info(
        f"Build-set threshold sweep complete: exact={best['exact_product']}, "
        f"similar={best['similar_product']}, f1={best['f1']}"
    )
    return {
        "evaluated_pairs": len(pairs),
        "best_thresholds": {
            "exact_product": best["exact_product"],
            "similar_product": best["similar_product"],
        },
        "best_f1": best["f1"],
        "best_precision": best["precision"],
        "best_recall": best["recall"],
        "top_candidates": cleaned_top,
        "env_freeze_snippet": snippet,
    }


def load_google_lens_csv(csv_path: Path) -> dict[str, Any] | None:
    """Parse P3's manual Google Lens comparison CSV (CLAUDE.md section 10).

    Expected columns (case-insensitive, booleans accept `1/0/true/false/yes/no`):
    `video_id, item_name, found_any_retailer, found_on_shopify, color_match`

    Args:
        csv_path: Path to manual Google Lens scoring CSV.

    Returns:
        Summary metrics dict for Google Lens, or `None` if file does not exist.

    Side effects:
        Reads `csv_path` if present.
    """
    if not csv_path.is_file():
        return None

    def _to_bool(val: str | None) -> bool:
        return str(val or "").strip().lower() in ("1", "true", "yes", "y")

    rows: list[dict[str, str]] = []
    with csv_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append({str(k).strip().lower(): str(v or "").strip() for k, v in row.items()})

    if not rows:
        return None

    n = len(rows)
    any_ret = sum(1 for r in rows if _to_bool(r.get("found_any_retailer")))
    on_shop = sum(1 for r in rows if _to_bool(r.get("found_on_shopify")))
    color_ok = sum(1 for r in rows if _to_bool(r.get("color_match")))

    return {
        "sample_size": n,
        "found_any_retailer_accuracy": round(any_ret / n, 4),
        "exact_product_accuracy": round(on_shop / n, 4),  # Shopify exact-product rate
        "variant_accuracy": round(color_ok / n, 4),
    }
