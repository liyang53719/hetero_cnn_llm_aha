#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT="$ROOT/work/results/l5_hidden256_block"
RUN="$ROOT/scripts/run_memory_capped.sh"
VERILATOR="$ROOT/work/toolchain/conda/bin/verilator"
PYTHON="$ROOT/work/toolchain/cnn_py312/bin/python"
mkdir -p "$OUT/vectors"

"$ROOT/scripts/generate_all_hardfloat_primitives.sh"
taskset -c 8-23 "$PYTHON" "$ROOT/scripts/generate_l5_hidden256_block_vectors.py" \
  --out "$OUT/vectors"

SOURCES=(
  "$ROOT/work/generated/l5_all_primitives/HeteroAllPrimitives.sv"
  "$ROOT/rtl/matrix/bf16_outer_product_array.sv"
  "$ROOT/rtl/sfu/fp32_reduce16.sv"
  "$ROOT/rtl/sfu/fp32_rsqrt_nr.sv"
  "$ROOT/rtl/sfu/fp32_rmsnorm256_chunked.sv"
  "$ROOT/rtl/sfu/fp32_rope_pair.sv"
  "$ROOT/rtl/sfu/fp32_dot64_scaled.sv"
  "$ROOT/rtl/sfu/fp32_exp2_pwl.sv"
  "$ROOT/rtl/sfu/fp32_online_softmax.sv"
  "$ROOT/rtl/sfu/fp32_reciprocal_nr.sv"
  "$ROOT/rtl/sfu/fp32_silu.sv"
  "$ROOT/rtl/sfu/fp32_vector_alu.sv"
  "$ROOT/tb/tb_l5_hidden256_block.sv"
)
COMMON=(--timing -Wall -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL)

MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$RUN" \
  "$VERILATOR" --lint-only "${COMMON[@]}" --top-module tb_l5_hidden256_block \
  "${SOURCES[@]}" >"$OUT/lint.log" 2>&1
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$RUN" \
  "$VERILATOR" --binary "${COMMON[@]}" -j 8 \
  -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" \
  --top-module tb_l5_hidden256_block --Mdir "$OUT/obj" -o tb \
  "${SOURCES[@]}" >"$OUT/build.log" 2>&1
cd "$ROOT"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$RUN" \
  "$OUT/obj/tb" | tee "$OUT/tb.log"
grep -q 'L5_HIDDEN256_BLOCK_PASS hidden=256' "$OUT/tb.log"
echo L5_HIDDEN256_BLOCK_GATE_PASS
