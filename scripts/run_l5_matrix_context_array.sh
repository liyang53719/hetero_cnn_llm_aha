#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT="$ROOT/work/results/l5_matrix_context_array"
R="$ROOT/scripts/run_memory_capped.sh"
V="$ROOT/work/toolchain/conda/bin/verilator"
mkdir -p "$OUT"

"$ROOT/scripts/generate_all_hardfloat_primitives.sh"
SOURCES=(
  "$ROOT/work/generated/l5_all_primitives/HeteroAllPrimitives.sv"
  "$ROOT/rtl/matrix/bf16_outer_product_array.sv"
  "$ROOT/rtl/matrix/bf16_outer_product_context_array.sv"
  "$ROOT/tb/tb_bf16_outer_product_context_array.sv"
)
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" "$V" \
  --binary --threads 4 --timing -Wall -Wno-DECLFILENAME -Wno-TIMESCALEMOD \
  -Wno-UNUSEDSIGNAL -Wno-UNOPTTHREADS -Wno-WIDTHCONCAT -j 8 \
  -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" \
  --top-module tb_bf16_outer_product_context_array \
  --Mdir "$OUT/obj" -o tb "${SOURCES[@]}" >"$OUT/build.log" 2>&1
cd "$ROOT"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" \
  "$OUT/obj/tb" | tee "$OUT/tb.log"
grep -q 'BF16_CONTEXT_ARRAY_E1_PASS main_steps=1000000 random_steps=10000 contexts=4 lanes=512' "$OUT/tb.log"
echo L5_MATRIX_CONTEXT_ARRAY_E1_PASS
