#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT="$ROOT/work/results/l5_rmsnorm256"
RUN="$ROOT/scripts/run_memory_capped.sh"
VERILATOR="$ROOT/work/toolchain/conda/bin/verilator"
PYTHON="$ROOT/work/toolchain/cnn_py312/bin/python"
mkdir -p "$OUT"

taskset -c 8-25 "$PYTHON" "$ROOT/scripts/generate_rmsnorm256_vectors.py" \
  --output "$OUT/vectors.memh" --manifest "$OUT/vectors.json"

SOURCES=(
  "$ROOT/work/generated/l5_all_primitives/HeteroAllPrimitives.sv"
  "$ROOT/rtl/sfu/fp32_reduce16.sv"
  "$ROOT/rtl/sfu/fp32_rsqrt_nr.sv"
  "$ROOT/rtl/sfu/fp32_rmsnorm256_chunked.sv"
  "$ROOT/tb/tb_fp32_rmsnorm256_chunked.sv"
)
COMMON=(--timing -Wall -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL)

MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=8G MEMORY_MAX=10G "$RUN" \
  "$VERILATOR" --lint-only "${COMMON[@]}" \
  --top-module tb_fp32_rmsnorm256_chunked "${SOURCES[@]}" \
  >"$OUT/lint.log" 2>&1

MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=8G MEMORY_MAX=10G "$RUN" \
  "$VERILATOR" --binary "${COMMON[@]}" -j 4 \
  -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" \
  --top-module tb_fp32_rmsnorm256_chunked --Mdir "$OUT/obj" -o tb \
  "${SOURCES[@]}" >"$OUT/build.log" 2>&1

cd "$ROOT"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=8G MEMORY_MAX=10G "$RUN" \
  "$OUT/obj/tb" | tee "$OUT/tb.log"
grep -q 'FP32_RMSNORM256_CHUNKED_PASS vectors=1000' "$OUT/tb.log"
echo L5_RMSNORM256_GATE_PASS
