"""Status classification and `relook` recovery orchestration for Seen It (P2).

What this module does:
    Implements config-driven status classification (`exact | similar | none`),
    candidate deduplication/merging across passes, and the agreed P2
    `resolve(item: dict) -> dict` orchestrator from `CLAUDE.md` sections 4 & 6.

    Orchestration flow for an unresolved item (`state == "processing"` or
    unscored candidates):
    1. Search Shopify Global Catalog via `backend.matching.catalog.search()`.
    2. Verify candidates via `backend.matching.checker.check()` (or
       `check_desk_candidates()` when `mode == "desk"`).
    3. Assign status (`exact`, `similar`, or `none`) using thresholds from
       `backend/config.py` (`CONFIG.thresholds`, never hardcoded in logic).
    4. If `enable_relook` is True, `mode == "video"`, `status in ("similar", "none")`,
       and `video_path` is available, invoke P1's `backend.video.relook.relook()`
       once to obtain a sharper crop/description/query, re-search and re-check,
       merge candidates keeping highest scores, and set `recovered = True` iff
       the item's status strictly improved (`none -> similar/exact` or
       `similar -> exact`).
    5. Transition `state` to `"done"` on success, or `"failed"` with zero
       fabricated products/probabilities if any upstream call fails.

Use cases:
    - Called by `backend/api.py` (`POST /run`) for every item emitted by P1's
      `extract()` or `desk_items()`.
    - Called by `eval/run_eval.py` with `enable_relook=False` vs
      `enable_relook=True` to measure recovery lift on build and held-out splits.
    - Preserves pre-resolved stub items from `fixtures/sample_run.json` when
      `force=False` so `tests/test_contract.py` stays green while P1 stubs land.

What this module must NOT do:
    - Must NEVER hardcode confidence thresholds inside branching logic (always
      read from `ThresholdConfig` / `CONFIG.thresholds`).
    - Must NEVER fabricate candidates, probabilities, or statuses when Shopify
      or Gemini Decisions fails.
    - Must NEVER edit P1's `backend/video/relook.py` or P3's cart/UI modules.
"""

from __future__ import annotations

import copy
import json
from typing import Any, Callable, Literal

from backend.config import CONFIG, AppConfig, ThresholdConfig
from backend.matching.catalog import search as default_search
from backend.matching.checker import (
    DecisionsCheckerError,
    check as default_check,
    check_desk_candidates as default_desk_check,
)
from backend.matching.logging_utils import get_logger, log_function_call, sanitize_for_log
from backend.shopify.catalog import ShopifyCatalogError
from backend.video.relook import relook as default_relook


LOGGER = get_logger(__name__)

StatusValue = Literal["exact", "similar", "none"]
STATUS_RANK: dict[str | None, int] = {
    None: -1,
    "none": 0,
    "similar": 1,
    "exact": 2,
}


def classify_status(
    candidates: list[dict[str, Any]],
    thresholds: ThresholdConfig | None = None,
) -> StatusValue:
    """Assign `exact`, `similar`, or `none` from scored candidates using config thresholds.

    Evaluates the highest-scoring candidate's `p_same_product` (and optionally
    `p_same_variant` when both are present) against `thresholds`. Never uses
    hardcoded cutoffs; all threshold values come from `backend/config.py`.

    Args:
        candidates: List of scored candidate dictionaries (`p_same_product`,
            `p_same_variant`).
        thresholds: Optional `ThresholdConfig` override (defaults to
            `CONFIG.thresholds`).

    Returns:
        One of `"exact"`, `"similar"`, or `"none"`.

    Side effects:
        None.
    """
    cfg_thresholds = thresholds or CONFIG.thresholds
    if not candidates:
        return "none"

    scored = [
        c
        for c in candidates
        if isinstance(c, dict) and isinstance(c.get("p_same_product"), (int, float))
    ]
    if not scored:
        return "none"

    best = max(
        scored,
        key=lambda c: (
            float(c["p_same_product"]),
            float(c["p_same_variant"]) if isinstance(c.get("p_same_variant"), (int, float)) else -1.0,
        ),
    )
    p_prod = float(best["p_same_product"])

    if p_prod >= cfg_thresholds.exact_product:
        return "exact"
    if p_prod >= cfg_thresholds.similar_product:
        return "similar"
    return "none"


def _candidate_key(cand: dict[str, Any]) -> tuple[str | None, str | None, str]:
    """Compute a stable deduplication key for a candidate across search passes.

    Args:
        cand: Candidate dictionary.

    Returns:
        Tuple `(upid, variant_id, normalized_title)` used for deduplication.

    Side effects:
        None.
    """
    upid = str(cand["upid"]) if cand.get("upid") else None
    variant_id = str(cand["variant_id"]) if cand.get("variant_id") else None
    title = str(cand.get("title") or "").strip().lower()
    if upid or variant_id:
        return (upid, variant_id, "")
    return (None, None, title)


def _candidate_sort_key(cand: dict[str, Any]) -> tuple[float, float]:
    """Return a descending-friendly sort tuple `(p_same_product, p_same_variant)`.

    Args:
        cand: Candidate dictionary.

    Returns:
        Two-float tuple treating `None` scores as `-1.0`.

    Side effects:
        None.
    """
    p_prod = cand.get("p_same_product")
    p_var = cand.get("p_same_variant")
    return (
        float(p_prod) if isinstance(p_prod, (int, float)) else -1.0,
        float(p_var) if isinstance(p_var, (int, float)) else -1.0,
    )


def merge_candidates(
    first_pass: list[dict[str, Any]],
    second_pass: list[dict[str, Any]],
    *,
    max_candidates: int | None = None,
) -> list[dict[str, Any]]:
    """Merge first-pass and `relook` candidates without losing higher-scoring matches.

    Deduplicates candidates by `(upid, variant_id)` keeping whichever copy
    achieved the higher `(p_same_product, p_same_variant)` score, then sorts
    descending and caps at `max_candidates`.

    Args:
        first_pass: Scored candidates from initial search + check.
        second_pass: Scored candidates from the `relook` pass.
        max_candidates: Optional cap (defaults to `CONFIG.decisions_max_candidates`).

    Returns:
        Merged, deduplicated, best-first list of candidate dictionaries.

    Side effects:
        None.
    """
    cap = max_candidates if max_candidates is not None else CONFIG.decisions_max_candidates
    by_key: dict[tuple[str | None, str | None, str], dict[str, Any]] = {}

    for cand in (*first_pass, *second_pass):
        if not isinstance(cand, dict):
            continue
        key = _candidate_key(cand)
        existing = by_key.get(key)
        if existing is None or _candidate_sort_key(cand) > _candidate_sort_key(existing):
            by_key[key] = copy.deepcopy(cand)

    merged = sorted(by_key.values(), key=_candidate_sort_key, reverse=True)
    return merged[:cap]


def _is_already_resolved_stub(item: dict[str, Any]) -> bool:
    """Detect whether an item is already fully resolved (e.g. from P1's fixture stub).

    An item is treated as pre-resolved only when `state == "done"`, `status` is
    already one of `exact | similar | none`, AND at least one candidate already
    carries a numeric `p_same_product` score. Real items emitted by P1's
    `extract()` arrive with `state == "processing"` and `candidates == []`.

    Args:
        item: Input item dictionary.

    Returns:
        True if the item is already resolved and should be preserved unless `force=True`.

    Side effects:
        None.
    """
    if item.get("state") != "done":
        return False
    if item.get("status") not in ("exact", "similar", "none"):
        return False
    candidates = item.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        return False
    return any(isinstance(c, dict) and isinstance(c.get("p_same_product"), (int, float)) for c in candidates)


def _ensure_contract_defaults(item: dict[str, Any]) -> dict[str, Any]:
    """Ensure optional schema keys exist on a copied item dict without altering values.

    Args:
        item: Working item dictionary copy.

    Returns:
        The normalized dictionary containing all standard `$defs.item` keys.

    Side effects:
        Mutates the working copy `item` in place.
    """
    item.setdefault("state", "processing")
    item.setdefault("t_start", None)
    item.setdefault("t_end", None)
    item.setdefault("crop_path", None)
    item.setdefault("description", None)
    item.setdefault("attributes", None)
    item.setdefault("query", None)
    item.setdefault("candidates", [])
    item.setdefault("status", None)
    item.setdefault("recovered", False)
    item.setdefault("preview", None)
    item.setdefault("cart", {"cart_id": None, "continue_url": None})
    return item


def _build_query_for_item(item: dict[str, Any]) -> str:
    """Determine the search query string for an item (`query` -> `description` fallback).

    Args:
        item: Item dictionary emitted by P1 (`extract` or `desk_items`).

    Returns:
        Non-empty trimmed query string, or `""` if neither `query` nor `description` exists.

    Side effects:
        None.
    """
    for field_name in ("query", "description"):
        val = item.get(field_name)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _build_filters_for_item(
    item: dict[str, Any],
    base_filters: dict[str, Any] | None,
) -> dict[str, Any]:
    """Assemble Shopify search filters for an item from caller filters and item attributes.

    Args:
        item: Target item dictionary.
        base_filters: Optional caller-level filters (e.g. `max_price`, `currency`, `ships_to`).

    Returns:
        Filter dictionary suitable for `backend.matching.catalog.search()`.

    Side effects:
        None.
    """
    out = dict(base_filters or {})
    out.setdefault("available", True)
    return out


def resolve(
    item: dict[str, Any],
    *,
    video_path: str | None = None,
    filters: dict[str, Any] | None = None,
    mode: str = "video",
    desk_photo_path: str | None = None,
    user_request: str = "",
    enable_relook: bool = True,
    force: bool = False,
    cfg: AppConfig = CONFIG,
    search_fn: Callable[..., list[dict[str, Any]]] | None = None,
    check_fn: Callable[..., list[dict[str, Any]]] | None = None,
    desk_check_fn: Callable[..., list[dict[str, Any]]] | None = None,
    relook_fn: Callable[[dict[str, Any], str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Resolve one extracted item end-to-end: search -> Decisions check -> status (+ relook).

    Preserves the agreed 1-argument signature `resolve(item: dict) -> dict`
    called by `backend/api.py`, while accepting optional keyword parameters for
    video `relook`, desk mode, evaluation ablations (`enable_relook=False`), and
    dependency injection in unit tests.

    Args:
        item: Item dictionary produced by P1 (`extract` or `desk_items`).
        video_path: Source video path enabling P1's `relook(item, video_path)` on
            `similar` or `none` items.
        filters: Optional Shopify catalog filter dict (`max_price`, `currency`, `ships_to`).
        mode: `"video"` (default) or `"desk"`.
        desk_photo_path: Optional desk photo path used when `mode == "desk"`.
        user_request: User styling prompt used when `mode == "desk"`.
        enable_relook: When True (default), attempts one `relook` recovery pass
            for `similar`/`none` items in video mode. Set False for before/after eval.
        force: If True, re-resolves even if `item` is already marked `state == "done"`
            with scored candidates.
        cfg: Active `AppConfig` supplying thresholds and limits.
        search_fn: Injectable catalog search function (defaults to `matching.catalog.search`).
        check_fn: Injectable video checker (defaults to `matching.checker.check`).
        desk_check_fn: Injectable desk checker (defaults to `matching.checker.check_desk_candidates`).
        relook_fn: Injectable P1 relook function (defaults to `backend.video.relook.relook`).

    Returns:
        New contract-compliant item dictionary (`contracts/run.schema.json`) with
        `candidates`, `status`, `recovered`, and `state` (`"done"` or `"failed"`).

    Side effects:
        Calls Shopify Global Catalog MCP, Gemini Decisions API, and optionally
        P1's `relook()`, emitting structured INFO logs. Never mutates input `item`.
    """
    working = _ensure_contract_defaults(copy.deepcopy(item))
    item_id = working.get("item_id", "unknown")

    log_function_call(
        LOGGER,
        "matching.status.resolve",
        {
            "item_id": item_id,
            "mode": mode,
            "enable_relook": enable_relook,
            "has_video_path": bool(video_path),
            "force": force,
            "initial_state": working.get("state"),
        },
    )

    if not force and _is_already_resolved_stub(working):
        LOGGER.info(
            json.dumps(
                {
                    "event": "resolve_passthrough_preresolved",
                    "item_id": item_id,
                    "status": working.get("status"),
                }
            )
        )
        return working

    do_search = search_fn or default_search
    do_check = check_fn or default_check
    do_desk_check = desk_check_fn or default_desk_check
    do_relook = relook_fn or default_relook

    query = _build_query_for_item(working)
    if not query:
        working["state"] = "failed"
        working["status"] = None
        working["recovered"] = False
        LOGGER.info(
            json.dumps(
                {
                    "event": "resolve_failed",
                    "item_id": item_id,
                    "reason": "missing_query_and_description",
                }
            )
        )
        return working

    working["query"] = query
    search_filters = _build_filters_for_item(working, filters)

    def _run_search_and_score(target_item: dict[str, Any], target_query: str) -> list[dict[str, Any]]:
        raw_candidates = do_search(target_query, search_filters)
        if not raw_candidates:
            return []
        if mode == "desk":
            return do_desk_check(
                target_item,
                raw_candidates,
                desk_photo_path=desk_photo_path,
                user_request=user_request,
            )
        return do_check(target_item, raw_candidates)

    try:
        first_candidates = _run_search_and_score(working, query)
        initial_status = classify_status(first_candidates, cfg.thresholds)
        working["candidates"] = first_candidates
        working["status"] = initial_status
        working["recovered"] = False

        # Single-pass `relook` recovery loop (CLAUDE.md §4)
        should_relook = (
            enable_relook
            and mode == "video"
            and initial_status in ("similar", "none")
            and bool(video_path)
        )
        if should_relook:
            assert video_path is not None
            LOGGER.info(
                json.dumps(
                    {
                        "event": "relook_triggered",
                        "item_id": item_id,
                        "initial_status": initial_status,
                    }
                )
            )
            refined = do_relook(copy.deepcopy(working), video_path)
            if isinstance(refined, dict):
                new_query = _build_query_for_item(refined) or query
                new_crop = refined.get("crop_path")
                query_changed = new_query.lower() != query.lower()
                crop_changed = bool(new_crop) and new_crop != working.get("crop_path")

                if query_changed or crop_changed:
                    working["query"] = new_query
                    if refined.get("description"):
                        working["description"] = refined["description"]
                    if refined.get("attributes"):
                        working["attributes"] = refined["attributes"]
                    if new_crop:
                        working["crop_path"] = new_crop

                    second_candidates = _run_search_and_score(working, new_query)
                    merged = merge_candidates(
                        first_candidates,
                        second_candidates,
                        max_candidates=cfg.decisions_max_candidates,
                    )
                    new_status = classify_status(merged, cfg.thresholds)
                    working["candidates"] = merged
                    working["status"] = new_status
                    working["recovered"] = STATUS_RANK[new_status] > STATUS_RANK[initial_status]
                    LOGGER.info(
                        json.dumps(
                            {
                                "event": "relook_complete",
                                "item_id": item_id,
                                "initial_status": initial_status,
                                "new_status": new_status,
                                "recovered": working["recovered"],
                            }
                        )
                    )
                else:
                    LOGGER.info(
                        json.dumps(
                            {
                                "event": "relook_skipped_unchanged",
                                "item_id": item_id,
                                "reason": "relook_returned_identical_query_and_crop",
                            }
                        )
                    )

        working["state"] = "done"
        return working

    except (ShopifyCatalogError, DecisionsCheckerError, Exception) as exc:
        # AGENT_RULES.md §3.5: never fabricate products or probabilities to hide failure.
        working["state"] = "failed"
        working["status"] = None
        working["recovered"] = False
        LOGGER.info(
            json.dumps(
                {
                    "event": "resolve_failed",
                    "item_id": item_id,
                    "error_type": type(exc).__name__,
                    "error": sanitize_for_log(str(exc)),
                }
            )
        )
        return working
