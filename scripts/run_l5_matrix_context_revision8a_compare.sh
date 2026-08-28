#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT=${OUT:-$ROOT/work/results/l5_matrix_context_revision8a/rev7_vs_rev8a}
R="$ROOT/scripts/run_memory_capped.sh"
V=${VERILATOR:-$ROOT/work/toolchain/conda/bin/verilator}
mkdir -p "$OUT"
"$ROOT/scripts/generate_all_hardfloat_primitives.sh"
SOURCES=(
  "$ROOT/work/generated/l5_all_primitives/HeteroAllPrimitives.sv"
  "$ROOT/rtl/matrix/bf16_context_scheduler4.sv"
  "$ROOT/rtl/matrix/bf16_context_fma_pipeline_lane4.sv"
  "$ROOT/rtl/matrix/candidates/rev8/bf16_context_tag_pipeline4_rev8_candidate.sv"
  "$ROOT/rtl/matrix/candidates/rev8/bf16_context_fma_pipeline_lane4_rev8_candidate.sv"
  "$ROOT/rtl/matrix/candidates/rev8/bf16_outer_product_array_control_rev8_candidate.sv"
  "$ROOT/tb/tb_bf16_context_lane_rev7_vs_rev8a.sv"
)
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" "$V" \
  --binary --timing -Wall -Wno-DECLFILENAME -Wno-TIMESCALEMOD \
  -Wno-UNUSEDSIGNAL -Wno-UNOPTTHREADS -j 4 \
  -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" \
  --top-module tb_bf16_context_lane_rev7_vs_rev8a \
  --Mdir "$OUT/obj" -o tb "${SOURCES[@]}" >"$OUT/build.log" 2>&1
cd "$ROOT"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" \
  "$OUT/obj/tb" | tee "$OUT/tb.log"
grep -q 'BF16_CONTEXT_REV7_VS_REV8A_PASS compared=120000' "$OUT/tb.log"
echo L5_MATRIX_CONTEXT_REV7_VS_REV8A_E1_PASS
