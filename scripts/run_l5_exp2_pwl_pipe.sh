#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);OUT=$ROOT/work/results/l5_exp2_pipe;R=$ROOT/scripts/run_memory_capped.sh;V=$ROOT/work/toolchain/conda/bin/verilator;mkdir -p "$OUT"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" timeout --foreground --signal=INT --kill-after=30s 600s "$V" --binary --threads 4 --timing -Wall -Wno-fatal -Wno-TIMESCALEMOD -Wno-DECLFILENAME -Wno-UNOPTTHREADS -Wno-WIDTH -j 4 -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" --top-module tb_fp32_exp2_pwl_pipe --Mdir "$OUT/obj" -o tb "$ROOT/work/generated/l5_all_primitives/HeteroAllPrimitives.sv" "$ROOT/rtl/sfu/fp32_exp2_pwl_pipe.sv" "$ROOT/tb/tb_fp32_exp2_pwl_pipe.sv" >"$OUT/build.log" 2>&1
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" timeout --foreground --signal=INT --kill-after=30s 600s "$OUT/obj/tb"|tee "$OUT/test.log";grep -q 'FP32_EXP2_PWL_PIPE_PASS vectors=10000' "$OUT/test.log"
