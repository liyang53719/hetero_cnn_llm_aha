#!/usr/bin/env bash
# Same real16 two-layer graph, Matrix4096 and original iDMA; only supply changes.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../.." && pwd);P="$ROOT/chisel/continuous_prefill"
OUT=${1:?absolute NEW output}
BASELINE=${2:-$ROOT/reports/execution/MATRIX4096_REAL2_d3571eecf96f/numerical}
[[ "$OUT" = /* && ! -e "$OUT" && ! -L "$OUT" ]] || exit 2
[[ -f "$BASELINE/gate.exit" && -f "$BASELINE/PERFORMANCE_COMPARISON.json" ]] || { echo BLOCKED_FROZEN_MATRIX4096_PROOF;exit 77; }
mkdir -p "$(dirname "$OUT")";mkdir "$OUT"
trap 'c=$?;echo "$c" >"$OUT/gate.exit";exit "$c"' EXIT
export WEIGHT_READ_BEATS=16 MATRIX_MACS=4096
bash "$P/scripts/run_idma_weight_burst_probe.sh" "$OUT/probe"
python3 "$P/tests/test_weight_burst_metrics.py" >"$OUT/metrics.log" 2>&1
python3 -O "$P/tests/test_weight_burst_metrics.py" >"$OUT/metrics_optimized.log" 2>&1
bash "$P/scripts/run_real_two_layer_gate.sh" "$OUT/numerical"
python3 "$P/scripts/compare_weight_burst_real2.py" --current "$OUT/numerical" --baseline "$BASELINE" \
  --output "$OUT/WEIGHT_BURST_COMPARISON.json" >"$OUT/comparison.log"
python3 "$P/scripts/compare_matrix4096_real2.py" --current "$OUT/numerical" \
  --baseline "$ROOT/reports/execution/REAL16_TWO_LAYER_9f06249ca11f/numerical" \
  --output "$OUT/OVERALL_VS_512.json" >"$OUT/comparison_512.log"
cat "$OUT/comparison.log"
