"""Centralized configuration for the Seen It backend.

What this module does:
    Loads and exposes every configurable setting for the Seen It pipeline from
    environment variables (with an optional local `.env` fallback for developer
    machines), including Gemini 4 and Decisions API model IDs, Shopify UCP
    endpoints, status classification thresholds, concurrency limits, retry
    backoff parameters, and batch sizes.

Use cases:
    - Imported by P1 (`backend/video/`), P2 (`backend/matching/`,
      `backend/shopify/catalog.py`, `eval/`), and P3 (`backend/shopify/cart.py`)
      so no model IDs, thresholds, URLs, or limits are hardcoded across modules.
    - Supports freezing calibrated status thresholds after build-set sweeps and
      before held-out evaluation runs.
    - Provides `safe_config_summary()` for startup/diagnostic INFO logs with all
      secrets stripped.

What this module must NOT do:
    - Must never hardcode API keys, client secrets, bearer tokens, or cookies.
    - Must never allow deprecated Gemini models (`gemini-1.5-*`, `gemini-2.0-*`,
      `gemini-pro`) or restricted `gemini-4-carbon` without explicit approval.
    - Must never write secrets to disk or expose secrets in serialized summaries.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"

_BANNED_MODEL_PATTERNS = (
    re.compile(r"^gemini-1\.5-", re.IGNORECASE),
    re.compile(r"^gemini-2\.0-", re.IGNORECASE),
    re.compile(r"^gemini-pro$", re.IGNORECASE),
    re.compile(r"^gemini-4-carbon$", re.IGNORECASE),
)


def load_dotenv_file(env_path: Path = DEFAULT_ENV_PATH) -> dict[str, str]:
    """Load key=value pairs from a local `.env` file into `os.environ` without overriding.

    Args:
        env_path: Filesystem path to the `.env` file to inspect.

    Returns:
        A dictionary of keys that were newly loaded (values masked as
        `"<loaded>"` to avoid accidental secret leakage if logged).

    Side effects:
        Populates missing keys in `os.environ` from `env_path` when the file exists.
    """
    loaded: dict[str, str] = {}
    if not env_path.is_file():
        return loaded

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if key and key not in os.environ and value != "":
            os.environ[key] = value
            loaded[key] = "<loaded>"
    return loaded


def validate_model_id(model_id: str, field_name: str) -> str:
    """Validate that a configured Gemini model ID is non-empty and allowed by policy.

    Args:
        model_id: Candidate model identifier string.
        field_name: Config field name used in error reporting.

    Returns:
        The normalized (stripped) model identifier string.

    Raises:
        ValueError: If `model_id` is empty or matches a deprecated/restricted model.

    Side effects:
        None.
    """
    cleaned = model_id.strip()
    if not cleaned:
        raise ValueError(f"{field_name} must not be empty.")
    for pattern in _BANNED_MODEL_PATTERNS:
        if pattern.match(cleaned):
            raise ValueError(
                f"Disallowed model ID '{cleaned}' for {field_name}. "
                "Deprecated models (gemini-1.5-*, gemini-2.0-*, gemini-pro) "
                "and restricted gemini-4-carbon are prohibited by AGENT_RULES.md."
            )
    return cleaned


def _get_env_str(name: str, default: str) -> str:
    """Read a string environment variable with a fallback default.

    Args:
        name: Environment variable name.
        default: Default value used when the variable is unset or blank.

    Returns:
        The trimmed environment value or `default`.

    Side effects:
        None.
    """
    val = os.environ.get(name, "").strip()
    return val if val else default


def _get_env_float(name: str, default: float) -> float:
    """Read a float environment variable with a fallback default.

    Args:
        name: Environment variable name.
        default: Default float value when unset or blank.

    Returns:
        Parsed float value.

    Raises:
        ValueError: If the variable is set to a non-numeric value.

    Side effects:
        None.
    """
    raw = os.environ.get(name, "").strip()
    return float(raw) if raw else default


def _get_env_int(name: str, default: int) -> int:
    """Read an integer environment variable with a fallback default.

    Args:
        name: Environment variable name.
        default: Default integer value when unset or blank.

    Returns:
        Parsed integer value.

    Raises:
        ValueError: If the variable is set to a non-integer value.

    Side effects:
        None.
    """
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw else default


def _get_env_bool(name: str, default: bool) -> bool:
    """Read a boolean environment variable with a fallback default.

    Args:
        name: Environment variable name.
        default: Default boolean value when unset or blank.

    Returns:
        Parsed boolean value (`1`, `true`, `yes` -> True; `0`, `false`, `no` -> False).

    Side effects:
        None.
    """
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    raise ValueError(f"Invalid boolean value '{raw}' for environment variable {name}.")


@dataclass(frozen=True)
class ThresholdConfig:
    """Calibrated confidence thresholds used to assign item match status.

    Initial values are pre-calibration starting points from `CLAUDE.md` section 4.
    They MUST be tuned on the 12-video `build` split and frozen (`frozen=True`)
    before running the 6-video `heldout` evaluation split.
    """

    exact_product: float = 0.80
    exact_variant: float = 0.70
    similar_product: float = 0.50
    frozen: bool = False

    def validate(self) -> None:
        """Verify that thresholds lie strictly within Decisions API bounds (0.01, 0.99).

        Returns:
            None.

        Raises:
            ValueError: If thresholds are out of range or `similar_product > exact_product`.

        Side effects:
            None.
        """
        for label, val in (
            ("exact_product", self.exact_product),
            ("exact_variant", self.exact_variant),
            ("similar_product", self.similar_product),
        ):
            if not (0.01 < val < 0.99):
                raise ValueError(
                    f"Threshold '{label}'={val} must be strictly between 0.01 and 0.99 "
                    "(Decisions API noul probabilities are clamped to [0.01, 0.99])."
                )
        if self.similar_product > self.exact_product:
            raise ValueError(
                f"similar_product ({self.similar_product}) cannot exceed "
                f"exact_product ({self.exact_product})."
            )


@dataclass(frozen=True)
class AppConfig:
    """Immutable container for all non-secret runtime configuration values."""

    # Gemini model identifiers (validated on construction)
    gemini_argon_model: str
    gemini_fast_model: str
    gemini_decision_model: str
    gemini_image_model: str

    # Gemini API endpoints and versions
    gemini_api_base_url: str
    gemini_decision_api_version: str

    # Shopify Agentic Commerce (UCP) endpoints — Global Catalog MCP only
    shopify_catalog_mcp_url: str
    shopify_auth_token_url: str
    shopify_agent_profile_url: str
    shopify_default_currency: str
    shopify_default_country: str
    shopify_use_compact_view: bool

    # Matching & Decisions status thresholds
    thresholds: ThresholdConfig

    # Concurrency, batching, and retry limits
    max_parallel_gemini: int
    retry_max_attempts: int
    retry_base_delay_s: float
    retry_max_delay_s: float
    http_timeout_s: float
    token_expiry_buffer_s: float
    shopify_lookup_batch_size: int
    shopify_search_default_limit: int
    decisions_max_candidates: int
    decisions_max_questions: int
    decisions_max_image_bytes: int
    decisions_multi_image_enabled: bool
    desk_top_candidates_per_slot: int

    # Paths
    contracts_schema_path: Path
    fixtures_sample_run_path: Path
    eval_data_dir: Path
    eval_results_dir: Path

    def safe_summary(self) -> dict[str, Any]:
        """Return a JSON-serializable, secret-free summary suitable for INFO logs.

        Returns:
            Dictionary containing non-secret configuration parameters and boolean
            presence flags for required credentials.

        Side effects:
            Reads environment presence (not values) for credential status flags.
        """
        return {
            "models": {
                "argon": self.gemini_argon_model,
                "fast": self.gemini_fast_model,
                "decision": self.gemini_decision_model,
                "image": self.gemini_image_model,
            },
            "endpoints": {
                "gemini_api_base_url": self.gemini_api_base_url,
                "gemini_decision_api_version": self.gemini_decision_api_version,
                "shopify_catalog_mcp_url": self.shopify_catalog_mcp_url,
                "shopify_auth_token_url": self.shopify_auth_token_url,
                "shopify_agent_profile_url": self.shopify_agent_profile_url,
            },
            "thresholds": {
                "exact_product": self.thresholds.exact_product,
                "exact_variant": self.thresholds.exact_variant,
                "similar_product": self.thresholds.similar_product,
                "frozen": self.thresholds.frozen,
            },
            "limits": {
                "max_parallel_gemini": self.max_parallel_gemini,
                "retry_max_attempts": self.retry_max_attempts,
                "shopify_lookup_batch_size": self.shopify_lookup_batch_size,
                "decisions_max_candidates": self.decisions_max_candidates,
                "decisions_multi_image_enabled": self.decisions_multi_image_enabled,
                "desk_top_candidates_per_slot": self.desk_top_candidates_per_slot,
            },
            "credentials_present": {
                "GEMINI_API_KEY": bool(os.environ.get("GEMINI_API_KEY", "").strip()),
                "SHOPIFY_CLIENT_ID": bool(os.environ.get("SHOPIFY_CLIENT_ID", "").strip()),
                "SHOPIFY_CLIENT_SECRET": bool(os.environ.get("SHOPIFY_CLIENT_SECRET", "").strip()),
            },
        }


def get_secret(env_var: str, required: bool = True) -> str | None:
    """Retrieve a server-side secret directly from environment variables.

    Secrets are deliberately kept out of `AppConfig` fields so they cannot be
    accidentally serialized in repr/dataclass dumps.

    Args:
        env_var: Name of the environment variable holding the secret.
        required: If True, raises `RuntimeError` when the secret is missing.

    Returns:
        The secret string, or `None` when `required=False` and unset.

    Raises:
        RuntimeError: If `required=True` and the environment variable is unset/empty.

    Side effects:
        None.
    """
    value = os.environ.get(env_var, "").strip()
    if not value:
        if required:
            raise RuntimeError(
                f"Missing required server environment variable '{env_var}'. "
                "Set it in the server environment or local .env (never commit secrets)."
            )
        return None
    return value


def load_config(env_path: Path = DEFAULT_ENV_PATH) -> AppConfig:
    """Build and validate an `AppConfig` instance from environment variables.

    Args:
        env_path: Optional path to a `.env` file loaded before reading env vars.

    Returns:
        A fully validated immutable `AppConfig`.

    Raises:
        ValueError: If any model ID violates policy or thresholds are invalid.

    Side effects:
        Loads unset environment variables from `env_path` if present.
    """
    load_dotenv_file(env_path)

    argon_model = validate_model_id(
        _get_env_str("GEMINI_ARGON_MODEL", "gemini-4-argon"),
        "GEMINI_ARGON_MODEL",
    )
    fast_model = validate_model_id(
        _get_env_str("GEMINI_FAST_MODEL", "gemini-4-hydrogen"),
        "GEMINI_FAST_MODEL",
    )
    decision_model = validate_model_id(
        _get_env_str("GEMINI_DECISION_MODEL", "gemini-decision-1"),
        "GEMINI_DECISION_MODEL",
    )
    image_model = validate_model_id(
        _get_env_str("GEMINI_IMAGE_MODEL", "gemini-nano-banana-2.1"),
        "GEMINI_IMAGE_MODEL",
    )

    thresholds = ThresholdConfig(
        exact_product=_get_env_float("SEEN_IT_EXACT_PRODUCT_THRESHOLD", 0.80),
        exact_variant=_get_env_float("SEEN_IT_EXACT_VARIANT_THRESHOLD", 0.70),
        similar_product=_get_env_float("SEEN_IT_SIMILAR_PRODUCT_THRESHOLD", 0.50),
        frozen=_get_env_bool("SEEN_IT_THRESHOLDS_FROZEN", False),
    )
    thresholds.validate()

    return AppConfig(
        gemini_argon_model=argon_model,
        gemini_fast_model=fast_model,
        gemini_decision_model=decision_model,
        gemini_image_model=image_model,
        gemini_api_base_url=_get_env_str(
            "GEMINI_API_BASE_URL", "https://generativelanguage.googleapis.com"
        ),
        gemini_decision_api_version=_get_env_str("GEMINI_DECISION_API_VERSION", "v1beta"),
        shopify_catalog_mcp_url=_get_env_str(
            "SHOPIFY_CATALOG_MCP_URL", "https://catalog.shopify.com/api/ucp/mcp"
        ),
        shopify_auth_token_url=_get_env_str(
            "SHOPIFY_AUTH_TOKEN_URL", "https://api.shopify.com/auth/access_token"
        ),
        shopify_agent_profile_url=_get_env_str(
            "SHOPIFY_AGENT_PROFILE_URL",
            "https://shopify.dev/ucp/agent-profiles/2026-08-25/valid-with-capabilities.json",
        ),
        shopify_default_currency=_get_env_str("SHOPIFY_DEFAULT_CURRENCY", "USD").upper(),
        shopify_default_country=_get_env_str("SHOPIFY_DEFAULT_COUNTRY", "US").upper(),
        shopify_use_compact_view=_get_env_bool("SHOPIFY_USE_COMPACT_VIEW", True),
        thresholds=thresholds,
        max_parallel_gemini=_get_env_int("MAX_PARALLEL_GEMINI", 5),
        retry_max_attempts=_get_env_int("RETRY_MAX_ATTEMPTS", 4),
        retry_base_delay_s=_get_env_float("RETRY_BASE_DELAY_S", 0.5),
        retry_max_delay_s=_get_env_float("RETRY_MAX_DELAY_S", 10.0),
        http_timeout_s=_get_env_float("HTTP_TIMEOUT_S", 20.0),
        token_expiry_buffer_s=_get_env_float("TOKEN_EXPIRY_BUFFER_S", 60.0),
        shopify_lookup_batch_size=_get_env_int("SHOPIFY_LOOKUP_BATCH_SIZE", 50),
        shopify_search_default_limit=_get_env_int("SHOPIFY_SEARCH_DEFAULT_LIMIT", 12),
        decisions_max_candidates=_get_env_int("DECISIONS_MAX_CANDIDATES", 12),
        decisions_max_questions=_get_env_int("DECISIONS_MAX_QUESTIONS", 1000),
        decisions_max_image_bytes=_get_env_int(
            "DECISIONS_MAX_IMAGE_BYTES", 15 * 1024 * 1024
        ),
        decisions_multi_image_enabled=_get_env_bool(
            "DECISIONS_MULTI_IMAGE_ENABLED", True
        ),
        desk_top_candidates_per_slot=_get_env_int("DESK_TOP_CANDIDATES_PER_SLOT", 3),
        contracts_schema_path=PROJECT_ROOT / "contracts" / "run.schema.json",
        fixtures_sample_run_path=PROJECT_ROOT / "fixtures" / "sample_run.json",
        eval_data_dir=PROJECT_ROOT / "data" / "eval",
        eval_results_dir=PROJECT_ROOT / "eval" / "results",
    )


# Default singleton configuration loaded on import for convenience.
CONFIG = load_config()

# Backward-compatible module-level exports expected by `backend/fixture.py` and `tests/test_contract.py`.
ROOT = PROJECT_ROOT
FIXTURE_PATH = CONFIG.fixtures_sample_run_path
SCHEMA_PATH = CONFIG.contracts_schema_path

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_ARGON_MODEL = CONFIG.gemini_argon_model
GEMINI_FAST_MODEL = CONFIG.gemini_fast_model
GEMINI_DECISION_MODEL = CONFIG.gemini_decision_model
GEMINI_IMAGE_MODEL = CONFIG.gemini_image_model

SHOPIFY_CLIENT_ID = os.getenv("SHOPIFY_CLIENT_ID", "")
SHOPIFY_CLIENT_SECRET = os.getenv("SHOPIFY_CLIENT_SECRET", "")
SHOPIFY_AGENT_PROFILE_URL = CONFIG.shopify_agent_profile_url

# P1 (video extraction) settings.
FRAMES_DIR = ROOT / "frames"  # extracted crops (gitignored); never commit frames
USE_STUBS = os.getenv("SEEN_IT_STUBS", "") == "1"  # tests set this so no network is used
CROP_PADDING = float(os.getenv("CROP_PADDING", "0.10"))  # grow each bbox side by this fraction of the box size
