"""Settings read from the environment, with .env loaded if present (no extra dependency)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


_load_dotenv(ROOT / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_ARGON_MODEL = os.getenv("GEMINI_ARGON_MODEL", "gemini-4-argon")
GEMINI_FAST_MODEL = os.getenv("GEMINI_FAST_MODEL", "")
GEMINI_DECISION_MODEL = os.getenv("GEMINI_DECISION_MODEL", "gemini-decision-1")
GEMINI_IMAGE_MODEL = os.getenv("GEMINI_IMAGE_MODEL", "")
SHOPIFY_CLIENT_ID = os.getenv("SHOPIFY_CLIENT_ID", "")
SHOPIFY_CLIENT_SECRET = os.getenv("SHOPIFY_CLIENT_SECRET", "")
SHOPIFY_AGENT_PROFILE_URL = os.getenv(
    "SHOPIFY_AGENT_PROFILE_URL",
    "https://shopify.dev/ucp/agent-profiles/examples/2026-04-08/cart-and-checkout.json",
)

FIXTURE_PATH = ROOT / "fixtures" / "sample_run.json"
SCHEMA_PATH = ROOT / "contracts" / "run.schema.json"

FRAMES_DIR = ROOT / "frames"  # extracted crops (gitignored); never commit frames
USE_STUBS = os.getenv("SEEN_IT_STUBS", "") == "1"  # tests set this so no network is used
CROP_PADDING = float(os.getenv("CROP_PADDING", "0.10"))  # grow each bbox side by this fraction of the box size
