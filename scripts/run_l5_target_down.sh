#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
PRODUCT="$ROOT/work/results/l5_target_silu_product/vectors/product.memh"
RESIDUAL="$ROOT/work/results/l5_target_oproj/vectors/residual1.memh"
OUT="$ROOT/work/results/l5_target_down"
RUN="$ROOT/scripts/run_memory_capped.sh"
VERILATOR="$ROOT/work/toolchain/conda/bin/verilator"
PYTHON="$ROOT/work/toolchain/cnn_py312/bin/python"
mkdir -p "$OUT/vectors"

taskset -c 8-23 "$PYTHON" "$ROOT/scripts/generate_l5_target_down_vectors.py" \
  --product "$PRODUCT" --residual "$RESIDUAL" --out "$OUT/vectors"
SOURCES=(
  "$ROOT/work/generated/l5_all_primitives/HeteroAllPrimitives.sv"
  "$ROOT/rtl/matrix/bf16_outer_product_array.sv"
  "$ROOT/rtl/sfu/fp32_vector_alu.sv"
  "$ROOT/tb/tb_l5_target_down.sv"
)
COMMON=(--timing -Wall -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL)
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$RUN" \
  "$VERILATOR" --lint-only "${COMMON[@]}" --top-module tb_l5_target_down \
  "${SOURCES[@]}" >"$OUT/lint.log" 2>&1
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$RUN" \
  "$VERILATOR" --binary "${COMMON[@]}" -j 8 \
  -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" \
  --top-module tb_l5_target_down --Mdir "$OUT/obj" -o tb \
  "${SOURCES[@]}" >"$OUT/build.log" 2>&1
cd "$ROOT"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$RUN" \
  "$OUT/obj/tb" | tee "$OUT/tb.log"
grep -q 'L5_TARGET_DOWN_PASS shape=8960x1536 array_steps=430080' "$OUT/tb.log"
echo L5_TARGET_DOWN_GATE_PASS
