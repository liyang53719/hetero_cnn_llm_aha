#!/usr/bin/env bash
# Numerical closure first. Report a distinct nonzero performance exit below 50%.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../.." && pwd);P="$ROOT/chisel/continuous_prefill"
OUT=${1:?absolute NEW directory}
BASE=${2:-$ROOT/reports/execution/PRODUCTION_PIPELINE_REAL2_a3cb4a7307a6/numerical}
[[ "$OUT" = /* && ! -e "$OUT" ]] || exit 2
export MATRIX_MACS=4096 WEIGHT_READ_BEATS=16 PIPELINED_OWNER=1 NATIVE_BF16_WEIGHTS=1
bash "$P/scripts/run_real_two_layer_gate.sh" "$OUT"
set +e
python3 "$P/scripts/compare_native_bf16_real2.py" --current "$OUT" --baseline "$BASE" --output "$OUT/PERFORMANCE.json" >"$OUT/performance.log" 2>&1
rc=$?;set -e;echo "$rc" >"$OUT/performance.exit";cat "$OUT/performance.log"
exit "$rc"
