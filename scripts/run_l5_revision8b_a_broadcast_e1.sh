#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT=${OUT:-$ROOT/work/results/l5_matrix_rev8b_a/broadcast_e1}
R="$ROOT/scripts/run_memory_capped.sh"
IVERILOG=${IVERILOG:-/usr/bin/iverilog}
VVP=${VVP:-/usr/bin/vvp}
mkdir -p "$OUT"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" \
  "$IVERILOG" -g2012 -s tb_bf16_front_to_cluster_broadcast32_rev8b_a \
  -o "$OUT/tb.vvp" \
  "$ROOT/rtl/matrix/candidates/rev8b_a/bf16_front_to_cluster_broadcast32_rev8b_a_candidate.sv" \
  "$ROOT/tb/tb_bf16_front_to_cluster_broadcast32_rev8b_a.sv" \
  >"$OUT/build.log" 2>&1
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" \
  "$VVP" "$OUT/tb.vvp" | tee "$OUT/tb.log"
grep -q 'L5_REV8B_A_BROADCAST_E1_PASS operations=100000 leaves=32 width=11' "$OUT/tb.log"
