"""Seen It matching package initialization.

What this module does:
    Marks `backend.matching` as a Python package and re-exports Phase 0 shared
    contracts (`Candidate`, `Item`, `Run`, `Source`, `Totals`, `Preview`,
    `CartRef`, `validate_run_dict`) and structured logging utilities for P2's
    matching and evaluation pipeline.

Use cases:
    - Clean imports across `backend/matching/`, `backend/api.py`, and `eval/`.

What this module must NOT do:
    - Must not execute network calls, mutate global state, or import P1/P3
      private modules at import time.
"""

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

__all__ = [
    "Candidate",
    "CartRef",
    "Item",
    "Preview",
    "Run",
    "Source",
    "Totals",
    "get_logger",
    "log_function_call",
    "log_genai_call",
    "sanitize_for_log",
    "validate_run_dict",
]
