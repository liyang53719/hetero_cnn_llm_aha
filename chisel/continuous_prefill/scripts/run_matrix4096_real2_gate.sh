#!/usr/bin/env bash
# Execution-only: freeze source -> actual DUT -> compare every old/new output.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../.." && pwd);P="$ROOT/chisel/continuous_prefill"
OUT=${1:?absolute NEW output}
BASELINE=${2:-$ROOT/reports/execution/REAL16_TWO_LAYER_9f06249ca11f/numerical}
[[ "$OUT" = /* && ! -e "$OUT" && ! -L "$OUT" ]] || { echo OUTPUT_MUST_BE_NEW >&2;exit 2; }
[[ -f "$BASELINE/gate.exit" && -f "$BASELINE/all_owner_elements.csv.gz" ]] || { echo BLOCKED_MISSING_FROZEN_512_PROOF >&2;exit 77; }
[[ -n ${IDMA_EXPORT:-} && -f "$IDMA_EXPORT/idma.f.in" ]] || { echo BLOCKED_PINNED_IDMA >&2;exit 77; }
python3 -c 'import numpy,yaml' || { echo BLOCKED_PYTHON_DEPENDENCIES >&2;exit 77; }
mkdir -p "$(dirname "$OUT")";mkdir "$OUT"
trap 'c=$?;echo "$c" >"$OUT/gate.exit";exit "$c"' EXIT
export MATRIX_MACS=4096
bash "$P/scripts/run_matrix4096_join_gate.sh" "$OUT/join"
python3 "$P/tests/test_matrix_topology.py" >"$OUT/topology_tests.log" 2>&1
python3 "$P/tests/test_matrix4096_metrics.py" >"$OUT/metric_tests.log" 2>&1
python3 -O "$P/tests/test_matrix4096_metrics.py" >"$OUT/metric_optimized_tests.log" 2>&1
bash "$P/scripts/run_real_two_layer_gate.sh" "$OUT/numerical"
python3 "$P/scripts/compare_matrix4096_real2.py" --current "$OUT/numerical" --baseline "$BASELINE" \
 --output "$OUT/PERFORMANCE_COMPARISON.json" >"$OUT/comparison.log"
cat "$OUT/comparison.log"
