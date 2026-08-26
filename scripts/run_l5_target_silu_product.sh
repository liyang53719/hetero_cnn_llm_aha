#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
GATE_UP="$ROOT/work/results/l5_target_gate_up/vectors"
OUT="$ROOT/work/results/l5_target_silu_product"
RUN="$ROOT/scripts/run_memory_capped.sh"
VERILATOR="$ROOT/work/toolchain/conda/bin/verilator"
PYTHON="$ROOT/work/toolchain/cnn_py312/bin/python"
mkdir -p "$OUT/vectors"

taskset -c 8-25 "$PYTHON" "$ROOT/scripts/generate_l5_target_silu_product_vectors.py" \
  --gate "$GATE_UP/gate.memh" --up "$GATE_UP/up.memh" --out "$OUT/vectors"
SOURCES=(
  "$ROOT/work/generated/l5_all_primitives/HeteroAllPrimitives.sv"
  "$ROOT/rtl/sfu/fp32_exp2_pwl.sv"
  "$ROOT/rtl/sfu/fp32_reciprocal_nr.sv"
  "$ROOT/rtl/sfu/fp32_silu.sv"
  "$ROOT/rtl/sfu/fp32_vector_alu.sv"
  "$ROOT/tb/tb_l5_target_silu_product.sv"
)
COMMON=(--timing -Wall -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL)
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=8G MEMORY_MAX=10G "$RUN" \
  "$VERILATOR" --lint-only "${COMMON[@]}" --top-module tb_l5_target_silu_product \
  "${SOURCES[@]}" >"$OUT/lint.log" 2>&1
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=8G MEMORY_MAX=10G "$RUN" \
  "$VERILATOR" --binary "${COMMON[@]}" -j 4 \
  -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" \
  --top-module tb_l5_target_silu_product --Mdir "$OUT/obj" -o tb \
  "${SOURCES[@]}" >"$OUT/build.log" 2>&1
cd "$ROOT"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=8G MEMORY_MAX=10G "$RUN" \
  "$OUT/obj/tb" | tee "$OUT/tb.log"
grep -q 'L5_TARGET_SILU_PRODUCT_PASS lanes=8960 product_chunks=560' "$OUT/tb.log"
echo L5_TARGET_SILU_PRODUCT_GATE_PASS
