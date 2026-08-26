#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);OUT=$ROOT/work/results/l5_hidden256_gemv;mkdir -p "$OUT/vectors";R=$ROOT/scripts/run_memory_capped.sh;V=$ROOT/work/toolchain/conda/bin/verilator;PY=$ROOT/work/toolchain/cnn_py312/bin/python
"$ROOT/scripts/generate_all_hardfloat_primitives.sh";taskset -c 8-25 "$PY" "$ROOT/scripts/generate_l5_hidden256_gemv_vectors.py" --out "$OUT/vectors"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=8G MEMORY_MAX=10G "$R" "$V" --lint-only --timing -Wall -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL --top-module tb_l5_hidden256_gemv "$ROOT/work/generated/l5_all_primitives/HeteroAllPrimitives.sv" "$ROOT/rtl/matrix/bf16_outer_product_array.sv" "$ROOT/tb/tb_l5_hidden256_gemv.sv" >"$OUT/lint.log" 2>&1
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=8G MEMORY_MAX=10G "$R" "$V" --binary --timing -Wall -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL -j 4 -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" --top-module tb_l5_hidden256_gemv --Mdir "$OUT/obj" -o tb "$ROOT/work/generated/l5_all_primitives/HeteroAllPrimitives.sv" "$ROOT/rtl/matrix/bf16_outer_product_array.sv" "$ROOT/tb/tb_l5_hidden256_gemv.sv" >"$OUT/build.log" 2>&1
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=8G MEMORY_MAX=10G "$R" "$OUT/obj/tb"|tee "$OUT/tb.log";grep -q 'L5_HIDDEN256_GEMV_PASS steps=2048' "$OUT/tb.log";echo L5_HIDDEN256_GEMV_GATE_PASS
