#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);OUT=$ROOT/work/results/l5_recip_nr2;R=$ROOT/scripts/run_memory_capped.sh;V=$ROOT/work/toolchain/conda/bin/verilator;mkdir -p "$OUT"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" timeout --foreground --signal=INT --kill-after=30s 600s "$V" --binary --threads 4 --timing -Wall -Wno-fatal -Wno-TIMESCALEMOD -Wno-DECLFILENAME -Wno-UNOPTTHREADS -Wno-WIDTH -j 4 -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" --top-module tb_fp32_reciprocal_nr2 --Mdir "$OUT/obj" -o tb "$ROOT/work/generated/l5_all_primitives/HeteroAllPrimitives.sv" "$ROOT/rtl/sfu/fp32_reciprocal_nr2.sv" "$ROOT/tb/tb_fp32_reciprocal_nr2.sv" >"$OUT/build.log" 2>&1
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" timeout --foreground --signal=INT --kill-after=30s 600s "$OUT/obj/tb"|tee "$OUT/test.log";grep -q 'FP32_RECIPROCAL_NR2_PASS vectors=10000' "$OUT/test.log"
