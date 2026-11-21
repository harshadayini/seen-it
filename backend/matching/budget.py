"""Desk-mode budget optimizer for Seen It (P2).

What this module does:
    Implements the agreed P2 `pick_within_budget(items: list[dict], budget: float) -> list[dict]`
    function from `CLAUDE.md` sections 6 & 15e. Given desk "slot" items (e.g.,
    lamp, plant, desk mat) whose candidates have been scored via Decisions API
    on style fit (`p_same_product`) and space fit (`p_same_variant`):
    1. Takes the top `K` (`CONFIG.desk_top_candidates_per_slot`, default 3)
       priced candidates per slot.
    2. Runs exact combinatorial search over all `(K + 1)^S` combinations (for
       up to 10 slots; greedy fallback for larger inputs) to select **at most
       one candidate per slot** with total price `<= budget` that maximizes the
       sum of candidate fit scores (breaking ties by more slots filled, then
       lower total price).
    3. Reorders/filters each item's `candidates` and `status` cleanly so
       `backend/api.py`'s `_best(item)` and `_totals(items, budget)` pick the
       exact same winning candidates and report `within_budget: True`.

Use cases:
    - Called in desk mode (`POST /run` with `mode="desk"` and `budget` set) to
      select the best-fitting bundle under the user's spending cap.
    - Also exports `compute_totals(items, budget)` for consistent total price
      and budget-compliance calculations across API and evaluation code.

What this module must NOT do:
    - Must NEVER mutate the caller's input list or dictionaries in place.
    - Must NEVER fabricate fake prices or select a bundle exceeding `budget`.
    - Must NEVER break `contracts/run.schema.json` validation.
"""

from __future__ import annotations

import copy
import itertools
import json
from typing import Any

from backend.config import CONFIG, AppConfig
from backend.matching.logging_utils import get_logger, log_function_call


LOGGER = get_logger(__name__)

# Maximum slots for exact brute-force (4^10 = 1,048,576; typical desk mode has 3-6 slots).
_EXACT_SEARCH_MAX_SLOTS = 8


def candidate_fit_score(candidate: dict[str, Any]) -> float:
    """Compute a combined `[0.0, 1.0]` desk-mode fit score for a candidate.

    Averages `p_same_product` (style fit) and `p_same_variant` (space fit) when
    both are present, falling back cleanly if only one score is available.

    Args:
        candidate: Scored candidate dictionary.

    Returns:
        Combined fit score float in `[0.0, 1.0]`.

    Side effects:
        None.
    """
    p_style = candidate.get("p_same_product")
    p_space = candidate.get("p_same_variant")
    has_style = isinstance(p_style, (int, float)) and not isinstance(p_style, bool)
    has_space = isinstance(p_space, (int, float)) and not isinstance(p_space, bool)
    if has_style and has_space:
        return (float(p_style) + float(p_space)) / 2.0
    if has_style:
        return float(p_style)
    if has_space:
        return float(p_space)
    return 0.0


def _eligible_slot_candidates(item: dict[str, Any], top_k: int) -> list[dict[str, Any]]:
    """Return up to `top_k` priced, scored candidates for a desk slot ordered best-first.

    Args:
        item: Desk slot item dictionary.
        top_k: Maximum candidates to consider for this slot (default 3).

    Returns:
        List of candidate dicts having a valid non-negative numeric `price`.

    Side effects:
        None.
    """
    raw = item.get("candidates")
    if not isinstance(raw, list) or not raw:
        return []
    priced = [
        c
        for c in raw
        if isinstance(c, dict)
        and isinstance(c.get("price"), (int, float))
        and not isinstance(c.get("price"), bool)
        and float(c["price"]) >= 0.0
    ]
    priced.sort(key=lambda c: (candidate_fit_score(c), -float(c["price"])), reverse=True)
    return priced[: max(1, top_k)]


def _solve_exact(
    slot_options: list[list[dict[str, Any] | None]],
    budget: float,
) -> tuple[dict[str, Any] | None, ...]:
    """Brute-force exact solver finding the highest-scoring combination `<= budget`.

    Each slot chooses either `None` (skip slot) or one of its top-K candidates.
    Objective tuple (maximized):
        `(round(total_score, 6), num_selected_slots, -round(total_price, 2))`

    Args:
        slot_options: Per-slot list of `[None, cand_0, cand_1, ...]`.
        budget: Non-negative maximum allowed total price in major currency units.

    Returns:
        Tuple of chosen candidate (or `None`) for each slot.

    Side effects:
        None.
    """
    best_combo: tuple[dict[str, Any] | None, ...] = tuple(None for _ in slot_options)
    best_objective: tuple[float, int, float] = (-1.0, 0, 0.0)

    for combo in itertools.product(*slot_options):
        total_price = 0.0
        total_score = 0.0
        selected_count = 0
        exceeded = False

        for choice in combo:
            if choice is None:
                continue
            total_price += float(choice["price"])
            if total_price > budget + 1e-9:
                exceeded = True
                break
            total_score += candidate_fit_score(choice)
            selected_count += 1

        if exceeded:
            continue

        objective = (round(total_score, 6), selected_count, -round(total_price, 2))
        if objective > best_objective:
            best_objective = objective
            best_combo = combo

    return best_combo


def _solve_greedy_fallback(
    slot_candidates: list[list[dict[str, Any]]],
    budget: float,
) -> tuple[dict[str, Any] | None, ...]:
    """Greedy fallback optimizer when slot count exceeds exact brute-force bound.

    Args:
        slot_candidates: Per-slot list of top-K candidate dicts.
        budget: Non-negative maximum allowed total price.

    Returns:
        Tuple of chosen candidate (or `None`) for each slot.

    Side effects:
        None.
    """
    chosen: list[dict[str, Any] | None] = [None] * len(slot_candidates)
    remaining = budget

    # Rank slots by best score-per-dollar candidate.
    ranked_entries: list[tuple[float, float, int, dict[str, Any]]] = []
    for slot_idx, cands in enumerate(slot_candidates):
        for cand in cands:
            price = float(cand["price"])
            score = candidate_fit_score(cand)
            density = score / max(price, 0.01)
            ranked_entries.append((density, score, slot_idx, cand))

    ranked_entries.sort(key=lambda row: (row[0], row[1]), reverse=True)
    for _density, _score, slot_idx, cand in ranked_entries:
        if chosen[slot_idx] is not None:
            continue
        price = float(cand["price"])
        if price <= remaining + 1e-9:
            chosen[slot_idx] = cand
            remaining -= price

    return tuple(chosen)


def compute_totals(items: list[dict[str, Any]], budget: float | None = None) -> dict[str, Any]:
    """Compute contract-compliant `totals` (`price`, `within_budget`) matching `backend/api.py`.

    Uses the exact same best-candidate selection rule as `backend/api.py`
    (`status in ("exact", "similar")` and highest `p_same_product` among priced
    candidates).

    Args:
        items: List of item dictionaries.
        budget: Optional maximum budget in major currency units.

    Returns:
        Dictionary `{"price": float, "within_budget": bool}`.

    Side effects:
        None.
    """
    total = 0.0
    for item in items:
        if item.get("status") not in ("exact", "similar"):
            continue
        priced = [
            c
            for c in item.get("candidates") or []
            if isinstance(c, dict)
            and isinstance(c.get("price"), (int, float))
            and not isinstance(c.get("price"), bool)
        ]
        if not priced:
            continue
        best = max(priced, key=lambda c: c.get("p_same_product") or 0.0)
        total += float(best["price"])

    total_rounded = round(total, 2)
    return {
        "price": total_rounded,
        "within_budget": True if budget is None else total_rounded <= float(budget) + 1e-9,
    }


def pick_within_budget(
    items: list[dict[str, Any]],
    budget: float,
    *,
    top_k_per_slot: int | None = None,
    cfg: AppConfig = CONFIG,
) -> list[dict[str, Any]]:
    """Select the highest-scoring combination of at most one item per desk slot under `budget`.

    Matches the agreed P2 signature in `CLAUDE.md` section 6:
    `pick_within_budget(items: list[Item], budget: float) -> list[Item]`.

    For each selected slot, places the winning candidate first and excludes any
    higher-probability unaffordable candidates from that item's `candidates`
    list so `backend/api.py`'s `_best(item)` and `_totals(items, budget)` select
    the exact same affordable combination. Skipped slots are marked
    `status = "none"` with `candidates = []`.

    Args:
        items: List of resolved desk-slot item dictionaries.
        budget: Spending ceiling in major currency units (e.g. `150.0`).
        top_k_per_slot: Optional override for candidates considered per slot
            (defaults to `cfg.desk_top_candidates_per_slot`, i.e. 3).
        cfg: Active `AppConfig`.

    Returns:
        New list of contract-compliant item dictionaries representing the
        budget-optimal selection.

    Side effects:
        Emits structured INFO logs with selected slot count and total price.
        Never mutates input `items`.
    """
    top_k = top_k_per_slot if top_k_per_slot is not None else cfg.desk_top_candidates_per_slot
    safe_budget = float(budget)
    log_function_call(
        LOGGER,
        "matching.budget.pick_within_budget",
        {"slot_count": len(items), "budget": safe_budget, "top_k_per_slot": top_k},
    )

    working_items = [copy.deepcopy(i) for i in items]
    if not working_items:
        return []

    if safe_budget <= 0.0:
        for item in working_items:
            item["candidates"] = []
            item["status"] = "none"
        return working_items

    slot_candidates = [_eligible_slot_candidates(item, top_k) for item in working_items]

    if len(working_items) <= _EXACT_SEARCH_MAX_SLOTS:
        options: list[list[dict[str, Any] | None]] = [[None, *cands] for cands in slot_candidates]
        chosen_combo = _solve_exact(options, safe_budget)
    else:
        chosen_combo = _solve_greedy_fallback(slot_candidates, safe_budget)

    selected_count = 0
    for item, chosen in zip(working_items, chosen_combo):
        if chosen is None:
            item["candidates"] = []
            item["status"] = "none"
            continue

        selected_count += 1
        # Keep the winning candidate at index 0; retain only strictly lower-or-equal
        # p_same_product alternatives so backend/api.py::_best() always picks `chosen`.
        chosen_p = float(chosen.get("p_same_product") or 0.0)
        chosen_vid = chosen.get("variant_id")
        chosen_upid = chosen.get("upid")
        secondary = [
            c
            for c in item.get("candidates") or []
            if isinstance(c, dict)
            and (c.get("upid"), c.get("variant_id")) != (chosen_upid, chosen_vid)
            and float(c.get("p_same_product") or 0.0) < chosen_p
        ]
        item["candidates"] = [copy.deepcopy(chosen), *secondary]
        if item.get("status") not in ("exact", "similar"):
            item["status"] = "similar"
        item.setdefault("state", "done")

    totals = compute_totals(working_items, safe_budget)
    LOGGER.info(
        json.dumps(
            {
                "event": "desk_budget_selected",
                "slots_total": len(working_items),
                "slots_selected": selected_count,
                "budget": safe_budget,
                "total_price": totals["price"],
                "within_budget": totals["within_budget"],
            }
        )
    )
    return working_items
