#!/usr/bin/env bash
# Stub smoke test. Real Gemini/Shopify checks get added as those pieces land.
cd "$(dirname "$0")/.." || exit 1
fail=0
check() { if [ -f "$1" ]; then echo "PASS  $1 exists"; else echo "FAIL  $1 missing"; fail=1; fi; }
check CLAUDE.md
check fixtures/sample_run.json
check contracts/run.schema.json

if [ -f fixtures/sample_run.json ] && [ -f contracts/run.schema.json ]; then
  python3 - <<'PY' || fail=1
import json, sys
try:
    sample = json.load(open("fixtures/sample_run.json"))
    schema = json.load(open("contracts/run.schema.json"))
except Exception as e:
    print(f"FAIL  invalid JSON: {e}"); sys.exit(1)
try:
    import jsonschema
except ImportError:
    print("PASS  sample and schema are valid JSON (jsonschema not installed, skipped validation)"); sys.exit(0)
try:
    jsonschema.validate(sample, schema)
    print("PASS  sample_run.json validates against run.schema.json")
except jsonschema.ValidationError as e:
    print(f"FAIL  schema validation: {e.message}"); sys.exit(1)
PY
fi

echo
if [ $fail -eq 0 ]; then echo "SMOKE: PASS"; else echo "SMOKE: FAIL"; fi
exit $fail
