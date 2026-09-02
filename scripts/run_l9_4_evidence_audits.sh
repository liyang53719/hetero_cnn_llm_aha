#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
PYTHON=${PYTHON:-python3}
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

"$PYTHON" "$ROOT/scripts/audit_existing_rtl_evidence.py" \
  --root "$ROOT" \
  --output "$ROOT/reports/execution/L9_4_EXISTING_RTL_EVIDENCE.json"

"$PYTHON" "$ROOT/scripts/report_l9_4_payload_coverage.py" \
  --root "$ROOT" \
  --output "$ROOT/reports/execution/L9_4_LAYER0_PAYLOAD_COVERAGE.json"

"$PYTHON" "$ROOT/scripts/audit_l9_4_layer0_contract.py" \
  --manifest "$ROOT/reports/execution/llama_cpp_qwen2_graph_lowering_manifest.jsonl" \
  --layer 0 \
  --expected-total-commands 588 \
  --output "$ROOT/reports/execution/L9_4_LAYER0_MANIFEST_CONTRACT.json"

if [[ -n "${ACTUAL_LOGITS:-}" || -n "${REFERENCE_LOGITS:-}" ]]; then
  : "${ACTUAL_LOGITS:?set both ACTUAL_LOGITS and REFERENCE_LOGITS}"
  : "${REFERENCE_LOGITS:?set both ACTUAL_LOGITS and REFERENCE_LOGITS}"
  "$PYTHON" "$ROOT/scripts/compare_p3_logits.py" \
    --actual "$ACTUAL_LOGITS" \
    --reference "$REFERENCE_LOGITS" \
    --expected-count 151936 \
    --output "$ROOT/reports/execution/L5_6D_P3_FULL_LOGITS_PARITY.json"
else
  echo "full-logit comparison skipped: set ACTUAL_LOGITS and REFERENCE_LOGITS" >&2
fi
