#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);OUT=${OUT:-$ROOT/work/results/l5_block32_softmax_weight_e1};R=$ROOT/scripts/run_memory_capped.sh;V=${VERILATOR:-$ROOT/work/toolchain/conda/bin/verilator};mkdir -p "$OUT";"$ROOT/scripts/generate_all_hardfloat_primitives.sh"
S=("$ROOT/work/generated/l5_all_primitives/HeteroAllPrimitives.sv" "$ROOT/rtl/sfu/fp32_exp2_pwl_rawpipe.sv" "$ROOT/rtl/attention/fp32_block32_softmax_weights.sv" "$ROOT/tb/tb_fp32_block32_softmax_weights.sv")
run(){ local limit=$1;shift;MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" timeout --foreground --signal=INT --kill-after=30s "$limit" "$@";}
run 600s "$V" --binary --timing -Wall -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL -Wno-SYNCASYNCNET -j 8 -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" --top-module tb_fp32_block32_softmax_weights --Mdir "$OUT/obj" -o tb "${S[@]}" >"$OUT/build.log" 2>&1
run 600s "$OUT/obj/tb"|tee "$OUT/tb.log";grep -q 'BLOCK32_SOFTMAX_WEIGHT_PASS rows=2 weights=64' "$OUT/tb.log"
