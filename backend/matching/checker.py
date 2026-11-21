"""Calibrated Decisions API candidate verifier for Seen It (P2).

What this module does:
    Implements the agreed P2 `check(item: dict, candidates: list[dict]) -> list[dict]`
    function from `CLAUDE.md` section 6 using the Gemini Decisions API
    (`gemini-decision-1` on `v1beta`). Evaluates all Shopify candidates for an
    item in a single batched zero-output-token call, populating calibrated
    `p_same_product` and `p_same_variant` probabilities (and desk-mode
    `fits_style` / `fits_space` scores via `check_desk_candidates`).

    Supports two multimodal evaluation modes:
    - **Mode A (multi-image, default):** Sends the item's cropped video frame
      plus each candidate's Shopify image (fetched into ephemeral RAM only) in
      one shared multimodal `input` array, with two `noul` questions per
      candidate (`cand_{k}_same_product`, `cand_{k}_same_variant`).
    - **Mode B (single-image fallback, per CLAUDE.md §3 & §13):** If
      `decisions_multi_image_enabled` is False or the Decisions endpoint rejects
      multi-image input, automatically sends only the item crop image as `input`
      and embeds each candidate's title, price, currency, and merchant domain
      directly in the question `instructions`.

Use cases:
    - Called by `backend/matching/status.py` (`resolve()`) right after
      `backend.matching.catalog.search()`.
    - Called by `backend/matching/budget.py` / desk mode to score candidate
      style fit and space fit against a desk photo and user request.
    - Called by `eval/run_eval.py` for build-set threshold calibration and
      held-out accuracy/calibration measurement.

What this module must NOT do:
    - Must NEVER call `generateContent` or `interactions.create` for
      `gemini-decision-1` (must use `v1beta/decisions` exclusively).
    - Must NEVER write, cache, or re-host merchant product images on disk or
      persist image bytes beyond the single in-flight Decisions request.
    - Must NEVER fabricate probabilities, heuristic scores, or matches when
      `GEMINI_API_KEY` is missing or the upstream Decisions call fails.
    - Must NEVER log raw `GEMINI_API_KEY` or raw base64/binary image data.
"""

from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
import copy
import json
import mimetypes
from pathlib import Path
import random
import threading
import time
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from backend.config import CONFIG, AppConfig, get_secret
from backend.matching.logging_utils import (
    get_logger,
    log_function_call,
    log_genai_call,
    sanitize_for_log,
)


LOGGER = get_logger(__name__)

# Concurrency cap across parallel Gemini Decisions calls (AGENT_RULES.md §3.4).
_GEMINI_SEMAPHORE = threading.BoundedSemaphore(max(1, CONFIG.max_parallel_gemini))

_SUPPORTED_IMAGE_MIMES = frozenset(
    {"image/jpeg", "image/png", "image/webp", "image/gif"}
)


class DecisionsCheckerError(RuntimeError):
    """Structured error raised when `gemini-decision-1` verification fails."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        safety_blocked: bool = False,
        retryable: bool = False,
    ) -> None:
        """Initialize a structured Decisions API checker exception.

        Args:
            message: Redacted human-readable diagnostic message.
            status_code: HTTP status code from the Decisions endpoint, if any.
            safety_blocked: True if input was blocked by API safety filters.
            retryable: True if the upstream error is transient (429/5xx/network).

        Side effects:
            None.
        """
        super().__init__(message)
        self.status_code = status_code
        self.safety_blocked = safety_blocked
        self.retryable = retryable


def _detect_image_mime(data: bytes, hint: str | None = None) -> str:
    """Infer a supported image MIME type from magic bytes or a URL/path hint.

    Args:
        data: Raw image bytes held transiently in memory.
        hint: Optional Content-Type header, filename, or URL.

    Returns:
        MIME type string (defaults to `"image/jpeg"` when unrecognized).

    Side effects:
        None.
    """
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"

    if hint:
        cleaned = hint.split(";", 1)[0].strip().lower()
        if cleaned in _SUPPORTED_IMAGE_MIMES:
            return cleaned
        guessed, _ = mimetypes.guess_type(hint.split("?", 1)[0])
        if guessed in _SUPPORTED_IMAGE_MIMES:
            return guessed
    return "image/jpeg"


def _read_local_crop_bytes(crop_path: str | None, max_bytes: int) -> tuple[bytes, str] | None:
    """Read an item's local cropped video frame into memory if the file exists.

    Args:
        crop_path: Filesystem path to the local video frame crop (or `None`).
        max_bytes: Maximum allowed image size in bytes.

    Returns:
        Tuple of `(image_bytes, mime_type)`, or `None` if `crop_path` is unset or
        not present on disk.

    Raises:
        DecisionsCheckerError: If the local crop exceeds `max_bytes`.

    Side effects:
        Reads local frame bytes from `crop_path` into memory.
    """
    if not crop_path:
        return None
    path = Path(crop_path)
    if not path.is_file() and not path.is_absolute():
        candidate_path = CONFIG.project_root / path
        if candidate_path.is_file():
            path = candidate_path
    if not path.is_file():
        return None
    raw = path.read_bytes()
    if len(raw) > max_bytes:
        raise DecisionsCheckerError(
            f"Local crop '{crop_path}' ({len(raw)} bytes) exceeds max {max_bytes} bytes."
        )
    if not raw:
        return None
    return raw, _detect_image_mime(raw, hint=str(path))


def _fetch_ephemeral_image_bytes(
    image_url: str,
    *,
    timeout_s: float,
    max_bytes: int,
) -> tuple[bytes, str] | None:
    """Fetch a merchant product image strictly into ephemeral RAM (never cached/saved).

    Per `AGENT_RULES.md` §2.2, merchant image bytes are held in memory solely
    for the length of a single Decisions API call and immediately discarded.
    Network/404 errors on a single candidate image return `None` rather than
    crashing the whole batch.

    Args:
        image_url: Public HTTPS merchant/Shopify CDN image URL.
        timeout_s: Socket timeout in seconds.
        max_bytes: Hard byte cap (`CONFIG.decisions_max_image_bytes`, 15 MB).

    Returns:
        Tuple of `(image_bytes, mime_type)` in RAM, or `None` if fetch failed or
        exceeded `max_bytes`.

    Side effects:
        Performs an ephemeral HTTPS GET request; writes zero files to disk.
    """
    if not image_url or not image_url.startswith(("http://", "https://")):
        return None
    req = urllib_request.Request(
        image_url,
        headers={
            "User-Agent": "seen-it-ephemeral-verifier/0.1",
            "Accept": "image/*",
        },
        method="GET",
    )
    try:
        with urllib_request.urlopen(req, timeout=timeout_s) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read(max_bytes + 1)
            if not raw or len(raw) > max_bytes:
                return None
            return raw, _detect_image_mime(raw, hint=content_type or image_url)
    except Exception:
        return None


def _fetch_candidate_images_ephemeral(
    candidates: list[dict[str, Any]],
    *,
    cfg: AppConfig,
    image_fetch_fn: Any = None,
) -> dict[int, tuple[bytes, str]]:
    """Concurrently fetch candidate images into a short-lived RAM dict keyed by index.

    Args:
        candidates: Candidate dicts containing optional `image_url`.
        cfg: Active `AppConfig` supplying byte limits and timeout.
        image_fetch_fn: Optional injectable `(url) -> (bytes, mime) | None` for tests.

    Returns:
        Mapping `{candidate_index: (image_bytes, mime_type)}` held only in RAM.

    Side effects:
        Performs concurrent HTTPS GET requests for candidate image URLs.
    """
    fetcher = image_fetch_fn or (
        lambda url: _fetch_ephemeral_image_bytes(
            url,
            timeout_s=min(10.0, cfg.http_timeout_s),
            max_bytes=cfg.decisions_max_image_bytes,
        )
    )
    urls = [
        (idx, cand.get("image_url"))
        for idx, cand in enumerate(candidates)
        if isinstance(cand.get("image_url"), str) and cand["image_url"].strip()
    ]
    if not urls:
        return {}

    workers = min(len(urls), max(1, cfg.max_parallel_gemini))
    results: dict[int, tuple[bytes, str]] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetcher, url): idx for idx, url in urls}
        for fut, idx in futures.items():
            try:
                loaded = fut.result()
                if loaded is not None:
                    results[idx] = loaded
            except Exception:
                continue
    return results


def _raw_decisions_post(
    url: str,
    body: bytes,
    headers: dict[str, str],
    timeout_s: float,
) -> tuple[int, dict[str, str], bytes]:
    """Execute a raw HTTPS POST to the Gemini `v1beta/decisions` endpoint.

    Args:
        url: Full `v1beta/decisions` URL.
        body: UTF-8 JSON request payload bytes.
        headers: Request headers including `x-goog-api-key` and `User-Agent`.
        timeout_s: Socket timeout in seconds.

    Returns:
        Tuple of `(http_status, lowercased_headers, response_bytes)`.

    Raises:
        DecisionsCheckerError: On socket/DNS/timeout network errors (retryable).

    Side effects:
        Performs an outbound HTTPS POST request.
    """
    req = urllib_request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib_request.urlopen(req, timeout=timeout_s) as resp:
            resp_headers = {k.lower(): v for k, v in resp.headers.items()}
            return int(resp.status), resp_headers, resp.read()
    except urllib_error.HTTPError as exc:
        resp_headers = {k.lower(): v for k, v in exc.headers.items()} if exc.headers else {}
        err_body = exc.read() if exc.fp is not None else b""
        return int(exc.code), resp_headers, err_body
    except (urllib_error.URLError, TimeoutError, OSError) as exc:
        raise DecisionsCheckerError(
            f"Network error contacting Gemini Decisions API: {exc}",
            retryable=True,
        ) from exc


def _parse_retry_after(headers: dict[str, str]) -> float | None:
    """Parse numeric `Retry-After` seconds from HTTP headers if present.

    Args:
        headers: Lowercased HTTP response headers dictionary.

    Returns:
        Wait time in seconds, or `None` if absent/unparseable.

    Side effects:
        None.
    """
    raw = headers.get("retry-after")
    if not raw:
        return None
    try:
        return max(0.0, float(raw.strip()))
    except ValueError:
        return None


def _is_multi_image_rejection(status_code: int, error_text: str) -> bool:
    """Detect whether an HTTP 400 error specifically rejected multiple images in `input`.

    Args:
        status_code: HTTP status code returned by `v1beta/decisions`.
        error_text: Decoded response error text.

    Returns:
        True if the error indicates multi-image input is unsupported and Mode B
        fallback should be attempted.

    Side effects:
        None.
    """
    if status_code != 400:
        return False
    lower = error_text.lower()
    indicators = (
        "multiple image",
        "at most one image",
        "too many image",
        "only one image",
        "single image",
        "maximum number of image",
    )
    return any(tok in lower for tok in indicators)


def _is_safety_block(status_code: int, error_text: str) -> bool:
    """Detect whether an HTTP 400 Decisions API error was caused by safety filtering.

    Args:
        status_code: HTTP status code returned by `v1beta/decisions`.
        error_text: Decoded response error text.

    Returns:
        True if the response matches documented Decisions safety block reasons.

    Side effects:
        None.
    """
    if status_code != 400:
        return False
    lower = error_text.lower()
    return any(
        tok in lower
        for tok in ("safety", "prohibited_content", "blocklist", "image_safety", "content_blocked")
    )


def _invoke_decisions_api(
    *,
    input_blocks: list[dict[str, Any]],
    questions: dict[str, dict[str, Any]],
    cfg: AppConfig,
    http_post_fn: Any = None,
    sleep_fn: Any = time.sleep,
    jitter_fn: Any = random.uniform,
    semaphore: threading.BoundedSemaphore | None = None,
) -> tuple[dict[str, Any], float]:
    """Execute one `v1beta/decisions` call with concurrency cap, retries, and INFO logging.

    Args:
        input_blocks: Shared multimodal `input` content block list (`snake_case`).
        questions: Mapping of `1..1,000` question keys to `noul`/`choice`/`score` specs.
        cfg: Active `AppConfig` providing model ID, API base URL, version, and retry limits.
        http_post_fn: Optional injectable HTTP POST callable for unit testing.
        sleep_fn: Injectable sleep function for deterministic backoff testing.
        jitter_fn: Injectable jitter generator `(0.0, cap) -> float`.
        semaphore: Concurrency semaphore capping parallel Gemini calls (defaults to module cap).

    Returns:
        Tuple of `(parsed_response_dict, latency_ms)`.

    Raises:
        DecisionsCheckerError: On missing `GEMINI_API_KEY`, safety block, HTTP/network
            failure, or missing `answers` object in the response.

    Side effects:
        Performs an HTTPS POST to `{cfg.gemini_api_base_url}/{cfg.gemini_decision_api_version}/decisions`
        and emits a sanitized INFO log via `log_genai_call()`.
    """
    try:
        api_key = get_secret("GEMINI_API_KEY", required=True)
    except RuntimeError as exc:
        raise DecisionsCheckerError(str(exc), retryable=False) from exc
    assert api_key is not None

    if not input_blocks:
        raise DecisionsCheckerError("Decisions API requires non-empty input blocks.")
    if not (1 <= len(questions) <= cfg.decisions_max_questions):
        raise DecisionsCheckerError(
            f"Decisions API requires 1..{cfg.decisions_max_questions} questions, got {len(questions)}."
        )

    # Always pass bare model ID (e.g. "gemini-decision-1", never "models/...").
    model_id = cfg.gemini_decision_model.removeprefix("models/")
    base = cfg.gemini_api_base_url.rstrip("/")
    api_version = cfg.gemini_decision_api_version.strip("/")
    url = f"{base}/{api_version}/decisions"

    request_payload = {
        "model": model_id,
        "input": input_blocks,
        "questions": questions,
    }
    encoded_body = json.dumps(request_payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "x-goog-api-key": api_key,
        "User-Agent": "aistudio-build",
    }

    post = http_post_fn or _raw_decisions_post
    sem = semaphore or _GEMINI_SEMAPHORE
    max_attempts = max(1, cfg.retry_max_attempts)

    t0 = time.monotonic()
    status = 0
    resp_headers: dict[str, str] = {}
    resp_bytes = b""

    with sem:
        for attempt in range(1, max_attempts + 1):
            try:
                status, resp_headers, resp_bytes = post(url, encoded_body, headers, cfg.http_timeout_s)
            except DecisionsCheckerError as exc:
                if not exc.retryable or attempt == max_attempts:
                    log_genai_call(
                        LOGGER,
                        model=model_id,
                        api_surface="decisions.create",
                        prompt_or_input=input_blocks,
                        config={"api_version": api_version, "question_count": len(questions)},
                        error=str(exc),
                        latency_ms=(time.monotonic() - t0) * 1000.0,
                    )
                    raise
                delay = min(cfg.retry_max_delay_s, cfg.retry_base_delay_s * (2 ** (attempt - 1)))
                sleep_fn(jitter_fn(0.0, delay))
                continue

            if status not in (429, 500, 502, 503, 504) or attempt == max_attempts:
                break

            retry_after = _parse_retry_after(resp_headers)
            exp_cap = min(cfg.retry_max_delay_s, cfg.retry_base_delay_s * (2 ** (attempt - 1)))
            wait_s = (
                min(cfg.retry_max_delay_s, retry_after)
                if retry_after is not None
                else jitter_fn(0.0, exp_cap)
            )
            sleep_fn(wait_s)

    latency_ms = (time.monotonic() - t0) * 1000.0
    resp_text = resp_bytes.decode("utf-8", errors="replace")

    if status >= 400:
        safety = _is_safety_block(status, resp_text)
        err_msg = f"Decisions API HTTP {status}: {sanitize_for_log(resp_text[:400])}"
        log_genai_call(
            LOGGER,
            model=model_id,
            api_surface="decisions.create",
            prompt_or_input=input_blocks,
            config={"api_version": api_version, "question_count": len(questions)},
            error=err_msg,
            latency_ms=latency_ms,
        )
        raise DecisionsCheckerError(
            err_msg,
            status_code=status,
            safety_blocked=safety,
            retryable=status in (429, 500, 502, 503, 504),
        )

    try:
        parsed = json.loads(resp_text)
    except json.JSONDecodeError as exc:
        raise DecisionsCheckerError(f"Decisions API returned invalid JSON: {exc}") from exc

    answers = parsed.get("answers")
    if not isinstance(answers, dict):
        feedback = parsed.get("prompt_feedback") or parsed.get("promptFeedback")
        err_msg = f"Decisions API returned no 'answers' (prompt_feedback={sanitize_for_log(feedback)})."
        log_genai_call(
            LOGGER,
            model=model_id,
            api_surface="decisions.create",
            prompt_or_input=input_blocks,
            config={"api_version": api_version, "question_count": len(questions)},
            output=parsed,
            error=err_msg,
            latency_ms=latency_ms,
        )
        raise DecisionsCheckerError(err_msg, safety_blocked=bool(feedback))

    log_genai_call(
        LOGGER,
        model=model_id,
        api_surface="decisions.create",
        prompt_or_input=input_blocks,
        config={
            "api_version": api_version,
            "question_count": len(questions),
            "question_keys": list(questions.keys()),
        },
        output={
            "answer_count": len(answers),
            "usage": parsed.get("usage"),
            "answers": answers,
        },
        latency_ms=latency_ms,
    )
    return parsed, latency_ms


def _format_candidate_summary(idx: int, cand: dict[str, Any]) -> str:
    """Format compact candidate metadata text for Decisions API inputs/questions.

    Args:
        idx: Zero-based candidate index inside the current batch.
        cand: Normalized candidate dict.

    Returns:
        Single-line text summary of title, price/currency, and merchant domain.

    Side effects:
        None.
    """
    title = str(cand.get("title") or "Unknown product").strip()
    price = cand.get("price")
    currency = cand.get("currency") or "USD"
    price_str = f"{price:.2f} {currency}" if isinstance(price, (int, float)) else "price unknown"
    merchant = cand.get("merchant_domain") or "unknown merchant"
    return f"Candidate {idx}: {title} | Price: {price_str} | Merchant: {merchant}"


def _build_video_mode_payload(
    item: dict[str, Any],
    candidates: list[dict[str, Any]],
    *,
    crop_image: tuple[bytes, str] | None,
    candidate_images: dict[int, tuple[bytes, str]],
    include_candidate_images: bool,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Construct Decisions API `input` blocks and `noul` questions for product verification.

    Args:
        item: Target extracted item dict (`description`, `attributes`, `query`, `crop_path`).
        candidates: List of normalized Shopify candidate dicts to evaluate.
        crop_image: Optional `(bytes, mime_type)` tuple for the target video crop.
        candidate_images: Ephemeral RAM dict `{index: (bytes, mime_type)}` for candidates.
        include_candidate_images: True for Mode A (multi-image), False for Mode B
            (crop-only + candidate attributes embedded in questions).

    Returns:
        Tuple of `(input_blocks, questions_dict)`.

    Side effects:
        None.
    """
    target_meta = {
        "target_item": {
            "description": item.get("description"),
            "attributes": item.get("attributes") or {},
            "query": item.get("query"),
        }
    }
    input_blocks: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                "Target purchasable product observed in the user's video:\n"
                f"{json.dumps(target_meta, ensure_ascii=False)}\n"
            ),
        }
    ]
    if crop_image is not None:
        crop_bytes, crop_mime = crop_image
        input_blocks.append(
            {
                "type": "image",
                "data": base64.b64encode(crop_bytes).decode("ascii"),
                "mime_type": crop_mime,
                "resolution": "medium",
            }
        )
        input_blocks.append({"type": "text", "text": "\n"})

    questions: dict[str, dict[str, Any]] = {}
    for idx, cand in enumerate(candidates):
        summary = _format_candidate_summary(idx, cand)
        if include_candidate_images:
            input_blocks.append({"type": "text", "text": f"{summary}\n"})
            if idx in candidate_images:
                img_bytes, img_mime = candidate_images[idx]
                input_blocks.append(
                    {
                        "type": "image",
                        "data": base64.b64encode(img_bytes).decode("ascii"),
                        "mime_type": img_mime,
                        "resolution": "low",
                    }
                )
                input_blocks.append({"type": "text", "text": "\n"})
            else:
                input_blocks.append({"type": "text", "text": "(Candidate image unavailable)\n"})

            prod_instr = (
                f"Compare Candidate {idx} ({cand.get('title', '')}) against the target item from the video. "
                "Is Candidate "
                f"{idx} the exact same product model and design (ignoring color, finish, or size differences)?"
            )
            var_instr = (
                f"Compare Candidate {idx} ({cand.get('title', '')}) against the target item from the video. "
                "Is Candidate "
                f"{idx} the exact same product AND the exact same color, finish, and material variant?"
            )
        else:
            # Mode B fallback: candidate metadata embedded directly inside each question.
            prod_instr = (
                f"Given the target item from the video and its crop image, is this Shopify listing the exact "
                f"same product model and design (ignoring color/size)? Listing -> {summary}"
            )
            var_instr = (
                f"Given the target item from the video and its crop image, is this Shopify listing the exact "
                f"same product AND the exact same color, finish, and material variant? Listing -> {summary}"
            )

        questions[f"cand_{idx}_same_product"] = {
            "type": "noul",
            "instructions": prod_instr,
            "criteria": {
                "true_description": (
                    "Same underlying product model, silhouette, and structural design as the target item."
                ),
                "false_description": (
                    "Different product model, merely similar look-alike, or wrong product category."
                ),
            },
        }
        questions[f"cand_{idx}_same_variant"] = {
            "type": "noul",
            "instructions": var_instr,
            "criteria": {
                "true_description": (
                    "Same product model AND matching color, material, and surface finish."
                ),
                "false_description": (
                    "Different product model, or same model in a noticeably different colorway/finish/material."
                ),
            },
        }

    return input_blocks, questions


def _extract_noul_prob(answers: dict[str, Any], key: str) -> float | None:
    """Safely extract and bound a `noul` probability in `[0.0, 1.0]` from Decisions answers.

    Args:
        answers: `result["answers"]` dictionary returned by `gemini-decision-1`.
        key: Question key (e.g. `"cand_0_same_product"`).

    Returns:
        Probability rounded to 4 decimals, or `None` if key is missing/malformed.

    Side effects:
        None.
    """
    entry = answers.get(key)
    if not isinstance(entry, dict):
        return None
    raw = entry.get("noul")
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        clamped = max(0.0, min(1.0, float(raw)))
        return round(clamped, 4)
    return None


def check(
    item: dict[str, Any],
    candidates: list[dict[str, Any]],
    *,
    cfg: AppConfig = CONFIG,
    http_post_fn: Any = None,
    image_fetch_fn: Any = None,
    sleep_fn: Any = time.sleep,
    jitter_fn: Any = random.uniform,
    semaphore: threading.BoundedSemaphore | None = None,
) -> list[dict[str, Any]]:
    """Score Shopify candidates against an extracted item using `gemini-decision-1`.

    Matches the agreed P2 signature in `CLAUDE.md` section 6:
    `check(item: Item, candidates: list[Candidate]) -> list[Candidate]`.

    Fetches candidate images strictly into ephemeral RAM, evaluates all
    candidates in one batched zero-output-token Decisions API call on `v1beta`,
    fills `p_same_product` and `p_same_variant`, drops all image buffers
    immediately, and returns candidates sorted descending by
    `(p_same_product, p_same_variant)`.

    Args:
        item: Extracted item dictionary (`item_id`, `crop_path`, `description`,
            `attributes`, `query`).
        candidates: Candidate dicts returned by `backend.matching.catalog.search()`.
        cfg: Active `AppConfig`.
        http_post_fn: Optional injectable HTTP POST callable for unit testing.
        image_fetch_fn: Optional injectable image fetcher `(url) -> (bytes, mime) | None`.
        sleep_fn: Injectable sleep function for retry testing.
        jitter_fn: Injectable jitter generator for retry testing.
        semaphore: Optional concurrency semaphore override.

    Returns:
        New list of candidate dicts with `p_same_product` and `p_same_variant`
        populated and sorted best-first.

    Raises:
        DecisionsCheckerError: If `GEMINI_API_KEY` is missing, input is safety-blocked,
            or the Decisions API fails (never fabricates probabilities).

    Side effects:
        Reads local `crop_path` if present, transiently fetches candidate images
        into RAM (released in `finally`), calls `v1beta/decisions`, and logs at INFO.
    """
    if not candidates:
        return []

    max_batch = min(cfg.decisions_max_candidates, cfg.decisions_max_questions // 2)
    batch = [copy.deepcopy(c) for c in candidates[:max_batch]]

    log_function_call(
        LOGGER,
        "matching.checker.check",
        {
            "item_id": item.get("item_id"),
            "candidate_count": len(batch),
            "crop_path": item.get("crop_path"),
            "multi_image_enabled": cfg.decisions_multi_image_enabled,
        },
    )

    crop_image = _read_local_crop_bytes(
        item.get("crop_path"),
        max_bytes=cfg.decisions_max_image_bytes,
    )
    candidate_images: dict[int, tuple[bytes, str]] = {}
    used_multi_image = cfg.decisions_multi_image_enabled

    try:
        if used_multi_image:
            candidate_images = _fetch_candidate_images_ephemeral(
                batch,
                cfg=cfg,
                image_fetch_fn=image_fetch_fn,
            )

        input_blocks, questions = _build_video_mode_payload(
            item,
            batch,
            crop_image=crop_image,
            candidate_images=candidate_images,
            include_candidate_images=used_multi_image,
        )

        try:
            response, latency_ms = _invoke_decisions_api(
                input_blocks=input_blocks,
                questions=questions,
                cfg=cfg,
                http_post_fn=http_post_fn,
                sleep_fn=sleep_fn,
                jitter_fn=jitter_fn,
                semaphore=semaphore,
            )
        except DecisionsCheckerError as exc:
            # Mode B automatic fallback per CLAUDE.md §3 & §13 if multi-image is rejected.
            if used_multi_image and exc.status_code == 400 and _is_multi_image_rejection(
                exc.status_code, str(exc)
            ):
                LOGGER.info(
                    json.dumps(
                        {
                            "event": "decisions_fallback_mode_b",
                            "item_id": item.get("item_id"),
                            "reason": "multi_image_rejected",
                        }
                    )
                )
                used_multi_image = False
                input_blocks, questions = _build_video_mode_payload(
                    item,
                    batch,
                    crop_image=crop_image,
                    candidate_images={},
                    include_candidate_images=False,
                )
                response, latency_ms = _invoke_decisions_api(
                    input_blocks=input_blocks,
                    questions=questions,
                    cfg=cfg,
                    http_post_fn=http_post_fn,
                    sleep_fn=sleep_fn,
                    jitter_fn=jitter_fn,
                    semaphore=semaphore,
                )
            else:
                raise
    finally:
        # Explicitly release ephemeral merchant image bytes from RAM immediately.
        candidate_images.clear()
        crop_image = None

    answers = response.get("answers", {})
    for idx, cand in enumerate(batch):
        cand["p_same_product"] = _extract_noul_prob(answers, f"cand_{idx}_same_product")
        cand["p_same_variant"] = _extract_noul_prob(answers, f"cand_{idx}_same_variant")

    batch.sort(
        key=lambda c: (
            c["p_same_product"] if c.get("p_same_product") is not None else -1.0,
            c["p_same_variant"] if c.get("p_same_variant") is not None else -1.0,
        ),
        reverse=True,
    )

    LOGGER.info(
        json.dumps(
            {
                "event": "decisions_check_complete",
                "item_id": item.get("item_id"),
                "candidates_checked": len(batch),
                "questions_evaluated": len(batch) * 2,
                "mode": "multi_image" if used_multi_image else "crop_plus_text_fallback",
                "latency_ms": round(latency_ms, 2),
                "top_p_same_product": batch[0].get("p_same_product"),
                "top_p_same_variant": batch[0].get("p_same_variant"),
            }
        )
    )
    return batch


def check_desk_candidates(
    slot_item: dict[str, Any],
    candidates: list[dict[str, Any]],
    *,
    desk_photo_path: str | None = None,
    user_request: str = "",
    cfg: AppConfig = CONFIG,
    http_post_fn: Any = None,
    image_fetch_fn: Any = None,
    sleep_fn: Any = time.sleep,
    jitter_fn: Any = random.uniform,
    semaphore: threading.BoundedSemaphore | None = None,
) -> list[dict[str, Any]]:
    """Score desk-mode candidates on style fit and space fit via `gemini-decision-1`.

    Per `CLAUDE.md` §3 & §15e, desk mode evaluates each candidate on
    `"fits this style?"` and `"fits this space?"` against the user's empty desk
    photo and prompt (e.g. `"make this warmer, under $150"`). Maps style fit to
    `p_same_product` and space fit to `p_same_variant` so results remain 100%
    valid against `contracts/run.schema.json` while ready for `budget.py`.

    Args:
        slot_item: Desk slot item dict (`item_id`, `description`, `query`, `crop_path`).
        candidates: Candidate dicts returned for this desk slot.
        desk_photo_path: Optional path to the full desk photo (falls back to `slot_item["crop_path"]`).
        user_request: Free-text user styling prompt (e.g. `"make this warmer, under $150"`).
        cfg: Active `AppConfig`.
        http_post_fn: Optional injectable HTTP POST callable for unit testing.
        image_fetch_fn: Optional injectable image fetcher for unit testing.
        sleep_fn: Injectable sleep function for retry testing.
        jitter_fn: Injectable jitter generator for retry testing.
        semaphore: Optional concurrency semaphore override.

    Returns:
        New list of candidate dicts sorted descending by combined fit score
        (`0.5 * style_fit + 0.5 * space_fit`), with `p_same_product` storing
        style fit and `p_same_variant` storing space fit.

    Raises:
        DecisionsCheckerError: If the Decisions API call fails or credentials are missing.

    Side effects:
        Transiently holds candidate images in RAM, calls `v1beta/decisions`, and logs at INFO.
    """
    if not candidates:
        return []

    max_batch = min(cfg.decisions_max_candidates, cfg.decisions_max_questions // 2)
    batch = [copy.deepcopy(c) for c in candidates[:max_batch]]
    photo_path = desk_photo_path or slot_item.get("crop_path")

    log_function_call(
        LOGGER,
        "matching.checker.check_desk_candidates",
        {
            "item_id": slot_item.get("item_id"),
            "candidate_count": len(batch),
            "desk_photo_path": photo_path,
            "user_request": user_request,
        },
    )

    desk_image = _read_local_crop_bytes(photo_path, max_bytes=cfg.decisions_max_image_bytes)
    candidate_images: dict[int, tuple[bytes, str]] = {}
    used_multi_image = cfg.decisions_multi_image_enabled

    try:
        if used_multi_image:
            candidate_images = _fetch_candidate_images_ephemeral(
                batch,
                cfg=cfg,
                image_fetch_fn=image_fetch_fn,
            )

        def _build_desk_payload(include_cand_imgs: bool) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
            blocks: list[dict[str, Any]] = [
                {
                    "type": "text",
                    "text": (
                        "Desk styling request:\n"
                        f"{json.dumps({'slot': slot_item.get('description') or slot_item.get('query'), 'request': user_request}, ensure_ascii=False)}\n"
                    ),
                }
            ]
            if desk_image is not None:
                d_bytes, d_mime = desk_image
                blocks.append(
                    {
                        "type": "image",
                        "data": base64.b64encode(d_bytes).decode("ascii"),
                        "mime_type": d_mime,
                        "resolution": "medium",
                    }
                )
                blocks.append({"type": "text", "text": "\n"})

            qs: dict[str, dict[str, Any]] = {}
            for idx, cand in enumerate(batch):
                summary = _format_candidate_summary(idx, cand)
                if include_cand_imgs:
                    blocks.append({"type": "text", "text": f"{summary}\n"})
                    if idx in candidate_images:
                        ib, im = candidate_images[idx]
                        blocks.append(
                            {
                                "type": "image",
                                "data": base64.b64encode(ib).decode("ascii"),
                                "mime_type": im,
                                "resolution": "low",
                            }
                        )
                        blocks.append({"type": "text", "text": "\n"})
                qs[f"cand_{idx}_fits_style"] = {
                    "type": "noul",
                    "instructions": (
                        f"Does Candidate {idx} ({summary}) match the requested aesthetic and style "
                        f"('{user_request}') for this desk?"
                    ),
                    "criteria": {
                        "true_description": "Cohesive with the requested aesthetic, materials, and color palette.",
                        "false_description": "Clashes with the requested style or is off-theme.",
                    },
                }
                qs[f"cand_{idx}_fits_space"] = {
                    "type": "noul",
                    "instructions": (
                        f"Does Candidate {idx} ({summary}) fit the physical desk space, scale, and layout "
                        "shown in the photo?"
                    ),
                    "criteria": {
                        "true_description": "Appropriate size, form factor, and placement for the desk.",
                        "false_description": "Oversized, incompatible form factor, or impractical for the desk.",
                    },
                }
            return blocks, qs

        blocks, qs = _build_desk_payload(used_multi_image)
        try:
            response, _latency_ms = _invoke_decisions_api(
                input_blocks=blocks,
                questions=qs,
                cfg=cfg,
                http_post_fn=http_post_fn,
                sleep_fn=sleep_fn,
                jitter_fn=jitter_fn,
                semaphore=semaphore,
            )
        except DecisionsCheckerError as exc:
            if used_multi_image and exc.status_code == 400 and _is_multi_image_rejection(
                exc.status_code, str(exc)
            ):
                blocks, qs = _build_desk_payload(False)
                response, _latency_ms = _invoke_decisions_api(
                    input_blocks=blocks,
                    questions=qs,
                    cfg=cfg,
                    http_post_fn=http_post_fn,
                    sleep_fn=sleep_fn,
                    jitter_fn=jitter_fn,
                    semaphore=semaphore,
                )
            else:
                raise
    finally:
        candidate_images.clear()
        desk_image = None

    answers = response.get("answers", {})
    for idx, cand in enumerate(batch):
        cand["p_same_product"] = _extract_noul_prob(answers, f"cand_{idx}_fits_style")
        cand["p_same_variant"] = _extract_noul_prob(answers, f"cand_{idx}_fits_space")

    batch.sort(
        key=lambda c: (
            ((c.get("p_same_product") or 0.0) + (c.get("p_same_variant") or 0.0)) / 2.0
        ),
        reverse=True,
    )
    return batch
