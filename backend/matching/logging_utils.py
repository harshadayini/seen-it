"""Structured INFO logging utilities with secret redaction and binary stripping.

What this module does:
    Provides standardized JSON-formatted INFO logging for every significant
    function call and every Gemini / Decisions API invocation across P2's
    matching and evaluation modules, strictly complying with `AGENT_RULES.md`
    sections 1.4 and 4.4.

Use cases:
    - Logging function calls with their sanitized parameter payloads at INFO.
    - Logging Gemini 4 and Decisions API requests (model, config, prompt/input,
      questions) and outputs alongside latency metrics.
    - Automatically stripping inline base64 strings and raw `bytes` media into
      `{"mime_type": ..., "byte_length": ..., "stripped": true}` so logs stay
      readable and never dump merchant image bytes.
    - Redacting `Authorization` headers, OAuth bearer tokens, API keys, cookies,
      and `client_secret` values from nested payloads and string values.

What this module must NOT do:
    - Must never log raw API keys, OAuth secrets, bearer tokens, or cookies.
    - Must never persist or emit raw base64/binary image data to logs or disk.
"""

from __future__ import annotations

import base64
from dataclasses import asdict, is_dataclass
import json
import logging
from pathlib import Path
import re
from typing import Any


_SECRET_KEY_PATTERN = re.compile(
    r"(authorization|api[_-]?key|client[_-]?secret|access[_-]?token|"
    r"refresh[_-]?token|bearer|cookie|secret|password|x-goog-api-key)",
    re.IGNORECASE,
)

_SECRET_STRING_PATTERNS = (
    (re.compile(r"(Bearer\s+)[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"\bAIza[0-9A-Za-z\-_]{20,}\b"), "[REDACTED_API_KEY]"),
    (re.compile(r"\bshpat_[0-9A-Za-z]{16,}\b"), "[REDACTED_SHOPIFY_TOKEN]"),
    (re.compile(r"\bshpss_[0-9A-Za-z]{16,}\b"), "[REDACTED_SHOPIFY_SECRET]"),
)

_DATA_URI_PATTERN = re.compile(r"^data:([^;]+);base64,(.+)$", re.DOTALL)
_LIKELY_BASE64_PATTERN = re.compile(r"^[A-Za-z0-9+/=\r\n]{256,}$")


def _estimate_base64_bytes(b64_text: str) -> int:
    """Estimate decoded byte length of a base64 string without retaining decoded bytes.

    Args:
        b64_text: Base64-encoded payload string.

    Returns:
        Exact or approximate decoded byte length as an integer.

    Side effects:
        None.
    """
    compact = "".join(b64_text.split())
    try:
        return len(base64.b64decode(compact, validate=False))
    except Exception:
        padding = compact.count("=")
        return max(0, (len(compact) * 3) // 4 - padding)


def _redact_string(text: str) -> str:
    """Redact known secret/token patterns inside an arbitrary log string.

    Args:
        text: Raw string value.

    Returns:
        String with inline bearer tokens and known API key prefixes redacted.

    Side effects:
        None.
    """
    redacted = text
    for pattern, replacement in _SECRET_STRING_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def sanitize_for_log(value: Any, *, _key_hint: str | None = None) -> Any:
    """Recursively sanitize a value for safe INFO logging.

    Replaces secret keys/tokens with `"[REDACTED]"` and strips inline binary
    or base64 media into `{"mime_type": ..., "byte_length": ..., "stripped": True}`.

    Args:
        value: Any Python object (dict, list, dataclass, bytes, str, primitive).
        _key_hint: Internal key name passed during recursive dict traversal.

    Returns:
        A JSON-serializable, secret-redacted, inline-media-stripped structure.

    Side effects:
        None.
    """
    if _key_hint and _SECRET_KEY_PATTERN.search(_key_hint):
        return "[REDACTED]"

    if value is None or isinstance(value, (bool, int, float)):
        return value

    if isinstance(value, (bytes, bytearray, memoryview)):
        return {
            "mime_type": "application/octet-stream",
            "byte_length": len(value),
            "stripped": True,
        }

    if isinstance(value, Path):
        return str(value)

    if is_dataclass(value) and not isinstance(value, type):
        return sanitize_for_log(asdict(value))

    if isinstance(value, dict):
        # Detect inline multimodal blocks like {"type": "image", "mime_type": ..., "data": "<b64>"}
        # or {"inline_data": {"mime_type": ..., "data": "<b64>"}}
        mime = value.get("mime_type") or value.get("mimeType")
        if mime and "data" in value and isinstance(value["data"], (str, bytes, bytearray)):
            raw_data = value["data"]
            byte_len = (
                len(raw_data)
                if isinstance(raw_data, (bytes, bytearray))
                else _estimate_base64_bytes(raw_data)
            )
            cleaned: dict[str, Any] = {}
            for k, v in value.items():
                if k == "data":
                    cleaned[k] = {
                        "mime_type": str(mime),
                        "byte_length": byte_len,
                        "stripped": True,
                    }
                else:
                    cleaned[k] = sanitize_for_log(v, _key_hint=str(k))
            return cleaned

        return {str(k): sanitize_for_log(v, _key_hint=str(k)) for k, v in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [sanitize_for_log(item) for item in value]

    if isinstance(value, str):
        uri_match = _DATA_URI_PATTERN.match(value)
        if uri_match:
            mime_type, b64_payload = uri_match.group(1), uri_match.group(2)
            return {
                "mime_type": mime_type,
                "byte_length": _estimate_base64_bytes(b64_payload),
                "stripped": True,
            }
        if _LIKELY_BASE64_PATTERN.match(value):
            return {
                "mime_type": "application/octet-stream",
                "byte_length": _estimate_base64_bytes(value),
                "stripped": True,
            }
        return _redact_string(value)

    return _redact_string(str(value))


def get_logger(name: str) -> logging.Logger:
    """Return a configured INFO-level logger with a single concise stream handler.

    Args:
        name: Hierarchical logger name (typically `__name__`).

    Returns:
        Configured `logging.Logger` instance emitting INFO and higher records.

    Side effects:
        Attaches a `StreamHandler` to the root `seen_it` namespace logger once.
    """
    root = logging.getLogger("seen_it")
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        root.addHandler(handler)
        root.setLevel(logging.INFO)
        root.propagate = False

    logger_name = name if name.startswith("seen_it") else f"seen_it.{name}"
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    return logger


def log_function_call(
    logger: logging.Logger,
    function_name: str,
    params: dict[str, Any],
) -> None:
    """Log an application function invocation and its sanitized parameters at INFO level.

    Args:
        logger: Logger returned by `get_logger()`.
        function_name: Fully qualified or module-local function name.
        params: Mapping of parameter names to values passed to the function.

    Returns:
        None.

    Side effects:
        Emits a structured JSON INFO log line.
    """
    payload = {
        "event": "function_call",
        "function": function_name,
        "params": sanitize_for_log(params),
    }
    logger.info(json.dumps(payload, default=str))


def log_genai_call(
    logger: logging.Logger,
    *,
    model: str,
    api_surface: str,
    prompt_or_input: Any,
    config: dict[str, Any] | None = None,
    output: Any = None,
    latency_ms: float | None = None,
    error: str | None = None,
) -> None:
    """Log a Gemini 4 or Decisions API call with sanitized parameters and outputs.

    Args:
        logger: Logger returned by `get_logger()`.
        model: Gemini model identifier (e.g., `gemini-decision-1`, `gemini-4-hydrogen`).
        api_surface: Endpoint/SDK surface used (e.g., `decisions.create`, `generateContent`).
        prompt_or_input: Request input payload (inline media is automatically stripped).
        config: Non-secret request configuration dictionary (e.g., `api_version`, questions).
        output: Parsed API response payload (inline media automatically stripped).
        latency_ms: Round-trip duration in milliseconds if measured.
        error: Structured error description if the call failed.

    Returns:
        None.

    Side effects:
        Emits a structured JSON INFO log line (with secrets redacted and binary stripped).
    """
    payload: dict[str, Any] = {
        "event": "genai_call",
        "model": model,
        "api_surface": api_surface,
        "input": sanitize_for_log(prompt_or_input),
        "config": sanitize_for_log(config or {}),
        "output": sanitize_for_log(output),
    }
    if latency_ms is not None:
        payload["latency_ms"] = round(latency_ms, 2)
    if error is not None:
        payload["error"] = _redact_string(error)
    logger.info(json.dumps(payload, default=str))
