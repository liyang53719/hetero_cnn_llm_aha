#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../../.." && pwd)
PACKAGE="$ROOT/integration/gemmini/operator_primitives"
REPORT="$ROOT/reports/execution/operator_primitive_coverage_800mhz.json"
PACKAGE_REPORT="$PACKAGE/reports/operator_primitive_coverage_800mhz.json"
export PYTHONPATH="$PACKAGE${PYTHONPATH:+:$PYTHONPATH}"
python3 -m pytest -q "$PACKAGE/tests"
python3 "$PACKAGE/scripts/audit_operator_coverage.py" --output "$REPORT"
mkdir -p "$(dirname "$PACKAGE_REPORT")"
cp "$REPORT" "$PACKAGE_REPORT"
python3 "$PACKAGE/scripts/generate_reference_vectors.py" --output "$PACKAGE/vectors/operator_primitives_reference_v1.json" --check
python3 -m compileall -q "$PACKAGE/reference" "$PACKAGE/scripts"
bash -n "$PACKAGE/scripts/run_sandbox_tests.sh"
bash -n "$PACKAGE/scripts/generate_all_primitives.sh"
git -C "$ROOT" diff --check
python3 - "$REPORT" <<'PY'
import json, sys
p=sys.argv[1]; d=json.load(open(p))
assert d['status']=='PASS_OPERATOR_PRIMITIVE_COVERAGE'
assert d['operator_ids']==48 and d['catalog_modules']==25 and d['terminal_binding_count']==58
assert all(not m['missing'] and not m['unbound_terminal_opcodes'] for m in d['models'].values())
print('PASS_SANDBOX_QWEN_OPERATOR_PRIMITIVES_800MHZ')
PY
