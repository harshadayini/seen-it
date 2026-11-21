"""Seen It matching package initialization.

What this module does:
    Marks `backend.matching` as a Python package and exports the agreed P2
    public pipeline functions (`search`, `check`, `resolve`, `pick_within_budget`)
    expected by `backend/api.py`, alongside P2's typed contract models and
    secret-safe INFO logging helpers.

Use cases:
    - Imported by `backend/api.py` (`from backend.matching import resolve`).
    - Imported by P2 matching modules and `eval/` evaluation harness.

What this module must NOT do:
    - Must not execute network calls or import P1/P3 private internals at import time.
"""

from backend.matching.budget import pick_within_budget
from backend.matching.catalog import search
from backend.matching.checker import check
from backend.matching.logging_utils import (
    get_logger,
    log_function_call,
    log_genai_call,
    sanitize_for_log,
)
from backend.matching.models import (
    Candidate,
    CartRef,
    Item,
    Preview,
    Run,
    Source,
    Totals,
    validate_run_dict,
)
from backend.matching.status import resolve

__all__ = [
    "Candidate",
    "CartRef",
    "Item",
    "Preview",
    "Run",
    "Source",
    "Totals",
    "check",
    "get_logger",
    "log_function_call",
    "log_genai_call",
    "pick_within_budget",
    "resolve",
    "sanitize_for_log",
    "search",
    "validate_run_dict",
]
