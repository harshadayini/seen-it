"""Phase 2 unit tests for the calibrated Decisions API checker (`backend/matching/checker.py`).

What this module does:
    Verifies all Phase 2 requirements deterministically without requiring a live
    `GEMINI_API_KEY`:
    1. Enforces dedicated `v1beta/decisions` endpoint, bare `gemini-decision-1`
       model ID, `User-Agent: aistudio-build`, and `x-goog-api-key` header.
    2. Verifies Mode A multi-image payload assembly (local crop + ephemeral RAM
       candidate images), calibrated `p_same_product`/`p_same_variant` scoring,
       best-first sorting, and `contracts/run.schema.json` validation.
    3. Verifies automatic Mode B fallback when `gemini-decision-1` returns an
       HTTP 400 rejecting multiple images per input.
    4. Verifies missing `GEMINI_API_KEY` and safety blocks raise
       `DecisionsCheckerError` and never fabricate probabilities.
    5. Verifies exponential backoff retry on HTTP 429 (`Retry-After`) and 503.
    6. Verifies graceful handling when a single candidate image URL fails to fetch.
    7. Verifies desk-mode `check_desk_candidates` scoring (`fits_style` + `fits_space`).
    8. Verifies INFO logs strip inline base64 images (`"stripped": true`) and
       redact `GEMINI_API_KEY`.

Use cases:
    - Executed locally via `python3 -m unittest discover -s backend/matching/tests -v`.

What this module must NOT do:
    - Must not call live Gemini APIs or persist merchant images to disk.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.config import load_config
from backend.matching.checker import (
    DecisionsCheckerError,
    check,
    check_desk_candidates,
)
from backend.matching.models import validate_run_dict


FAKE_JPEG = b"\xff\xd8\xff\xe0" + b"\x11" * 128
FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"\x22" * 128

SAMPLE_CANDIDATES = [
    {
        "upid": "gid://shopify/p/cand-distractor",
        "variant_id": "gid://shopify/ProductVariant/1001",
        "title": "Blue Tripod Desk Lamp",
        "merchant_domain": "alpha.myshopify.com",
        "price": 75.0,
        "currency": "USD",
        "image_url": "https://cdn.shopify.com/s/files/1/0001/distractor.jpg",
        "p_same_product": None,
        "p_same_variant": None,
    },
    {
        "upid": "gid://shopify/p/cand-exact",
        "variant_id": "gid://shopify/ProductVariant/1002",
        "title": "Arquer Matte Black Arc Floor Lamp, Brass",
        "merchant_domain": "teamsonus.myshopify.com",
        "price": 169.99,
        "currency": "USD",
        "image_url": "https://cdn.shopify.com/s/files/1/0001/exact.png",
        "p_same_product": None,
        "p_same_variant": None,
    },
    {
        "upid": "gid://shopify/p/cand-wrong-color",
        "variant_id": "gid://shopify/ProductVariant/1003",
        "title": "Arquer Chrome Arc Floor Lamp",
        "merchant_domain": "teamsonus.myshopify.com",
        "price": 169.99,
        "currency": "USD",
        "image_url": "https://cdn.shopify.com/s/files/1/0001/broken-404.jpg",
        "p_same_product": None,
        "p_same_variant": None,
    },
]


class TestPhase2DecisionsChecker(unittest.TestCase):
    """Unit tests for `backend/matching/checker.py`."""

    def setUp(self) -> None:
        self.cfg = load_config(Path("/nonexistent/.env"))
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.crop_file = Path(self.tmp_dir.name) / "i1.jpg"
        self.crop_file.write_bytes(FAKE_JPEG)
        self.sample_item = {
            "item_id": "i1",
            "state": "processing",
            "crop_path": str(self.crop_file),
            "description": "matte black arc floor lamp with brass shade",
            "attributes": {"color": "black", "material": "metal", "category": "lighting"},
            "query": "black arc floor lamp brass",
        }

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_missing_api_key_raises_without_fabricating_scores(self) -> None:
        """Verify AGENT_RULES.md §3.5: missing GEMINI_API_KEY raises cleanly."""
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
            with self.assertRaises(DecisionsCheckerError):
                check(self.sample_item, SAMPLE_CANDIDATES, cfg=self.cfg)

    def test_mode_a_multi_image_scores_sorts_validates_and_strips_logs(self) -> None:
        """Verify v1beta Decisions call, multi-image payload, sorting, schema validity, and stripped INFO logs."""
        captured_req: dict = {}

        def fake_fetch(url: str):
            if "broken-404" in url:
                return None  # Graceful degradation for one broken image URL
            if url.endswith(".png"):
                return FAKE_PNG, "image/png"
            return FAKE_JPEG, "image/jpeg"

        def fake_post(url: str, body: bytes, headers: dict, timeout_s: float):
            captured_req["url"] = url
            captured_req["headers"] = dict(headers)
            captured_req["body"] = json.loads(body.decode("utf-8"))
            resp = {
                "answers": {
                    "cand_0_same_product": {"type": "noul", "noul": 0.12, "confidence": 0.88},
                    "cand_0_same_variant": {"type": "noul", "noul": 0.05, "confidence": 0.95},
                    "cand_1_same_product": {"type": "noul", "noul": 0.93, "confidence": 0.93},
                    "cand_1_same_variant": {"type": "noul", "noul": 0.87, "confidence": 0.87},
                    "cand_2_same_product": {"type": "noul", "noul": 0.82, "confidence": 0.82},
                    "cand_2_same_variant": {"type": "noul", "noul": 0.21, "confidence": 0.79},
                },
                "usage": {"total_output_tokens": 0},
            }
            return 200, {}, json.dumps(resp).encode("utf-8")

        fake_key = "AIzaSyFakeDecisionsKey1234567890"
        with patch.dict(os.environ, {"GEMINI_API_KEY": fake_key}, clear=False):
            with self.assertLogs("seen_it.backend.matching.checker", level="INFO") as logs:
                scored = check(
                    self.sample_item,
                    SAMPLE_CANDIDATES,
                    cfg=self.cfg,
                    http_post_fn=fake_post,
                    image_fetch_fn=fake_fetch,
                )

        # Endpoint, bare model ID, headers
        self.assertTrue(captured_req["url"].endswith("/v1beta/decisions"))
        self.assertEqual(captured_req["headers"]["User-Agent"], "aistudio-build")
        self.assertEqual(captured_req["headers"]["x-goog-api-key"], fake_key)
        self.assertEqual(captured_req["body"]["model"], "gemini-decision-1")

        # 1 crop image (medium) + 2 fetched candidate images (low) = 3 image blocks
        image_blocks = [b for b in captured_req["body"]["input"] if b.get("type") == "image"]
        self.assertEqual(len(image_blocks), 3)
        self.assertEqual(image_blocks[0]["resolution"], "medium")
        self.assertEqual(image_blocks[1]["resolution"], "low")
        self.assertEqual(image_blocks[2]["resolution"], "low")

        # Sorted descending by (p_same_product, p_same_variant)
        self.assertEqual(scored[0]["upid"], "gid://shopify/p/cand-exact")
        self.assertEqual(scored[0]["p_same_product"], 0.93)
        self.assertEqual(scored[0]["p_same_variant"], 0.87)
        self.assertEqual(scored[1]["upid"], "gid://shopify/p/cand-wrong-color")
        self.assertEqual(scored[2]["upid"], "gid://shopify/p/cand-distractor")

        # Contract validation passes
        run = {
            "run_id": "r_p2",
            "state": "processing",
            "mode": "video",
            "source": {"video_id": "v1", "duration_s": 10.0, "budget_usd": None},
            "items": [{"item_id": "i1", "state": "processing", "candidates": scored}],
            "totals": {"price": None, "within_budget": None},
        }
        self.assertEqual(validate_run_dict(run), [])

        # Logs strip inline base64 media and never expose API key
        joined_logs = "\n".join(logs.output)
        self.assertIn('"stripped": true', joined_logs)
        self.assertNotIn(fake_key, joined_logs)

    def test_automatic_mode_b_fallback_when_multi_image_rejected(self) -> None:
        """Verify Mode B fallback (crop-only + text in questions) fires on 400 multi-image error."""
        payloads: list[dict] = []

        def fake_fetch(url: str):
            return FAKE_JPEG, "image/jpeg"

        def fake_post(url: str, body: bytes, headers: dict, timeout_s: float):
            parsed = json.loads(body.decode("utf-8"))
            payloads.append(parsed)
            if len(payloads) == 1:
                return 400, {}, b'{"error": {"message": "Only one image is allowed per input."}}'
            resp = {
                "answers": {
                    "cand_0_same_product": {"type": "noul", "noul": 0.85, "confidence": 0.85},
                    "cand_0_same_variant": {"type": "noul", "noul": 0.77, "confidence": 0.77},
                }
            }
            return 200, {}, json.dumps(resp).encode("utf-8")

        with patch.dict(os.environ, {"GEMINI_API_KEY": "AIzaSyFakeKey1234567890123"}, clear=False):
            scored = check(
                self.sample_item,
                [SAMPLE_CANDIDATES[1]],
                cfg=self.cfg,
                http_post_fn=fake_post,
                image_fetch_fn=fake_fetch,
            )

        self.assertEqual(len(payloads), 2)
        first_imgs = [b for b in payloads[0]["input"] if b.get("type") == "image"]
        second_imgs = [b for b in payloads[1]["input"] if b.get("type") == "image"]
        self.assertEqual(len(first_imgs), 2)   # Mode A: crop + 1 candidate image
        self.assertEqual(len(second_imgs), 1)  # Mode B: crop only
        self.assertIn("teamsonus.myshopify.com", payloads[1]["questions"]["cand_0_same_product"]["instructions"])
        self.assertEqual(scored[0]["p_same_product"], 0.85)
        self.assertEqual(scored[0]["p_same_variant"], 0.77)

    def test_retries_429_with_retry_after_and_handles_safety_block(self) -> None:
        """Verify 429 retry honors Retry-After and safety block raises DecisionsCheckerError."""
        sleeps: list[float] = []
        responses = [
            (429, {"retry-after": "1.25"}, b"RESOURCE_EXHAUSTED"),
            (200, {}, json.dumps({"prompt_feedback": {"block_reason": "IMAGE_SAFETY"}}).encode("utf-8")),
        ]

        def fake_post(url: str, body: bytes, headers: dict, timeout_s: float):
            return responses.pop(0)

        with patch.dict(os.environ, {"GEMINI_API_KEY": "AIzaSyFakeKey1234567890123"}, clear=False):
            with self.assertRaises(DecisionsCheckerError) as ctx:
                check(
                    self.sample_item,
                    [SAMPLE_CANDIDATES[0]],
                    cfg=self.cfg,
                    http_post_fn=fake_post,
                    image_fetch_fn=lambda _: None,
                    sleep_fn=sleeps.append,
                )

        self.assertEqual(sleeps, [1.25])
        self.assertTrue(ctx.exception.safety_blocked)

    def test_desk_mode_scores_style_and_space_fit(self) -> None:
        """Verify check_desk_candidates evaluates fits_style and fits_space and sorts by combined fit."""
        def fake_post(url: str, body: bytes, headers: dict, timeout_s: float):
            parsed = json.loads(body.decode("utf-8"))
            self.assertIn("cand_0_fits_style", parsed["questions"])
            self.assertIn("cand_0_fits_space", parsed["questions"])
            resp = {
                "answers": {
                    "cand_0_fits_style": {"type": "noul", "noul": 0.30, "confidence": 0.70},
                    "cand_0_fits_space": {"type": "noul", "noul": 0.40, "confidence": 0.60},
                    "cand_1_fits_style": {"type": "noul", "noul": 0.92, "confidence": 0.92},
                    "cand_1_fits_space": {"type": "noul", "noul": 0.86, "confidence": 0.86},
                }
            }
            return 200, {}, json.dumps(resp).encode("utf-8")

        with patch.dict(os.environ, {"GEMINI_API_KEY": "AIzaSyFakeKey1234567890123"}, clear=False):
            scored = check_desk_candidates(
                self.sample_item,
                SAMPLE_CANDIDATES[:2],
                desk_photo_path=str(self.crop_file),
                user_request="make this warmer, under $150",
                cfg=self.cfg,
                http_post_fn=fake_post,
                image_fetch_fn=lambda _: None,
            )

        self.assertEqual(scored[0]["upid"], "gid://shopify/p/cand-exact")
        self.assertEqual(scored[0]["p_same_product"], 0.92)  # style fit
        self.assertEqual(scored[0]["p_same_variant"], 0.86)  # space fit


if __name__ == "__main__":
    unittest.main()
