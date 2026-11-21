"""Phase 0 unit tests for centralized config, contract models, and safe logging.

What this module does:
    Verifies all Phase 0 foundations before Phase 1 (Shopify Global Catalog MCP)
    begins:
    1. `backend/config.py` defaults, `.env` loading, banned/deprecated model
       enforcement, threshold bounds, and secret-free summary serialization.
    2. `backend/matching/logging_utils.py` secret redaction (`Authorization`,
       `client_secret`, `GEMINI_API_KEY`, `Bearer ...`) and inline binary/base64
       media stripping (`{mime_type, byte_length, stripped: True}`).
    3. `backend/matching/models.py` round-trip serialization and strict schema
       validation of `fixtures/sample_run.json` against `contracts/run.schema.json`.

Use cases:
    - Executed locally via `python3 -m unittest backend/matching/tests/test_phase0.py`
      as the Phase 0 verification gate.

What this module must NOT do:
    - Must not make live network requests or depend on real API credentials.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.config import ThresholdConfig, load_config, validate_model_id
from backend.matching.logging_utils import get_logger, log_genai_call, sanitize_for_log
from backend.matching.models import Run, validate_run_dict


class TestPhase0Config(unittest.TestCase):
    """Tests for `backend/config.py` validation and safe summary behavior."""

    def test_default_config_loads_and_excludes_secrets_in_summary(self) -> None:
        """Verify default config loads valid models and never leaks secret values."""
        fake_env = {
            "GEMINI_API_KEY": "AIzaSyFakeSecretKey1234567890",
            "SHOPIFY_CLIENT_ID": "fake_client_id",
            "SHOPIFY_CLIENT_SECRET": "shpss_supersecretvalue123456",
        }
        with patch.dict(os.environ, fake_env, clear=False):
            cfg = load_config(Path("/nonexistent/.env"))
            summary = cfg.safe_summary()
            serialized = json.dumps(summary)

        self.assertEqual(cfg.gemini_decision_model, "gemini-decision-1")
        self.assertEqual(cfg.gemini_decision_api_version, "v1beta")
        self.assertEqual(cfg.max_parallel_gemini, 5)
        self.assertEqual(cfg.shopify_lookup_batch_size, 50)
        self.assertNotIn("AIzaSyFakeSecretKey1234567890", serialized)
        self.assertNotIn("shpss_supersecretvalue123456", serialized)
        self.assertTrue(summary["credentials_present"]["GEMINI_API_KEY"])

    def test_banned_and_deprecated_models_are_rejected(self) -> None:
        """Verify AGENT_RULES.md banned models raise ValueError."""
        for disallowed in (
            "gemini-1.5-pro",
            "gemini-1.5-flash",
            "gemini-2.0-flash",
            "gemini-pro",
            "gemini-4-carbon",
        ):
            with self.assertRaises(ValueError):
                validate_model_id(disallowed, "GEMINI_FAST_MODEL")

    def test_thresholds_enforce_decisions_bounds(self) -> None:
        """Verify thresholds stay strictly inside (0.01, 0.99) and ordered."""
        ThresholdConfig(exact_product=0.80, exact_variant=0.70, similar_product=0.50).validate()
        with self.assertRaises(ValueError):
            ThresholdConfig(exact_product=0.99, exact_variant=0.70, similar_product=0.50).validate()
        with self.assertRaises(ValueError):
            ThresholdConfig(exact_product=0.50, exact_variant=0.70, similar_product=0.80).validate()

    def test_dotenv_loads_missing_vars_without_overwriting_existing(self) -> None:
        """Verify local .env populates unset keys while preserving OS environment."""
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text(
                "GEMINI_FAST_MODEL=gemini-4-neon\nMAX_PARALLEL_GEMINI=3\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"MAX_PARALLEL_GEMINI": "4"}, clear=False):
                os.environ.pop("GEMINI_FAST_MODEL", None)
                cfg = load_config(env_file)
            self.assertEqual(cfg.gemini_fast_model, "gemini-4-neon")
            self.assertEqual(cfg.max_parallel_gemini, 4)


class TestPhase0Logging(unittest.TestCase):
    """Tests for `backend/matching/logging_utils.py` redaction and stripping."""

    def test_strips_inline_base64_and_raw_bytes(self) -> None:
        """Verify multimodal image blocks and raw bytes are replaced with metadata."""
        fake_jpeg = b"\xff\xd8\xff\xe0" + b"0" * 400
        b64_jpeg = base64.b64encode(fake_jpeg).decode("ascii")
        payload = {
            "input": [
                {"type": "text", "text": "Target lamp"},
                {"type": "image", "mime_type": "image/jpeg", "data": b64_jpeg},
            ],
            "raw_blob": fake_jpeg,
        }
        sanitized = sanitize_for_log(payload)
        img_data = sanitized["input"][1]["data"]
        self.assertEqual(
            img_data,
            {"mime_type": "image/jpeg", "byte_length": len(fake_jpeg), "stripped": True},
        )
        self.assertEqual(
            sanitized["raw_blob"],
            {
                "mime_type": "application/octet-stream",
                "byte_length": len(fake_jpeg),
                "stripped": True,
            },
        )
        self.assertNotIn(b64_jpeg, json.dumps(sanitized))

    def test_redacts_secrets_and_bearer_tokens(self) -> None:
        """Verify sensitive header keys and inline tokens are redacted."""
        payload = {
            "headers": {"Authorization": "Bearer super_secret_token_xyz"},
            "client_secret": "shpss_abc123456789012345",
            "note": "Failed using Bearer abc123def456 and AIzaSy12345678901234567890",
        }
        sanitized = sanitize_for_log(payload)
        serialized = json.dumps(sanitized)
        self.assertEqual(sanitized["headers"]["Authorization"], "[REDACTED]")
        self.assertEqual(sanitized["client_secret"], "[REDACTED]")
        self.assertNotIn("super_secret_token_xyz", serialized)
        self.assertNotIn("shpss_abc123456789012345", serialized)
        self.assertNotIn("AIzaSy12345678901234567890", serialized)
        self.assertNotIn("abc123def456", serialized)

    def test_log_genai_call_emits_info_record(self) -> None:
        """Verify log_genai_call logs cleanly at INFO with inline data stripped."""
        logger = get_logger("test_phase0")
        with self.assertLogs("seen_it.test_phase0", level="INFO") as captured:
            log_genai_call(
                logger,
                model="gemini-decision-1",
                api_surface="decisions.create",
                prompt_or_input=[{"type": "image", "mime_type": "image/png", "data": b"1234"}],
                config={"api_version": "v1beta"},
                output={"answers": {"cand_0_same_product": {"noul": 0.91}}},
                latency_ms=142.346,
            )
        joined = "\n".join(captured.output)
        self.assertIn("gemini-decision-1", joined)
        self.assertIn('"stripped": true', joined)
        self.assertIn("142.35", joined)


class TestPhase0ModelsAndFixture(unittest.TestCase):
    """Tests for `backend/matching/models.py` and `fixtures/sample_run.json`."""

    def test_sample_run_fixture_validates_and_round_trips(self) -> None:
        """Verify fixtures/sample_run.json matches contracts/run.schema.json exactly."""
        cfg = load_config(Path("/nonexistent/.env"))
        sample_raw = json.loads(cfg.fixtures_sample_run_path.read_text(encoding="utf-8"))
        errors = validate_run_dict(sample_raw)
        self.assertEqual(errors, [])

        run = Run.from_dict(sample_raw)
        self.assertEqual(run.to_dict(), sample_raw)
        self.assertEqual(len(run.items), 3)
        self.assertEqual(run.items[0].status, "exact")
        self.assertTrue(run.items[1].recovered)
        self.assertEqual(run.items[2].status, "none")

    def test_validator_catches_contract_violations(self) -> None:
        """Verify validator rejects invalid enums and out-of-range probabilities."""
        bad_payload = {
            "run_id": "r_bad",
            "state": "unknown_state",
            "mode": "video",
            "source": {},
            "items": [
                {
                    "item_id": "i1",
                    "state": "done",
                    "status": "exact",
                    "candidates": [
                        {"title": "Lamp", "p_same_product": 1.42},
                    ],
                }
            ],
            "totals": {},
        }
        errors = validate_run_dict(bad_payload)
        self.assertTrue(any("state" in e for e in errors))
        self.assertTrue(any("p_same_product" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
