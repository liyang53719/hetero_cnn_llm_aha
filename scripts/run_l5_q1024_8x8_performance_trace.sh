#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);OUT=${OUT:-$ROOT/work/results/l5_q1024_8x8_performance_trace};R=$ROOT/scripts/run_memory_capped.sh;V=${VERILATOR:-$ROOT/work/toolchain/conda/bin/verilator};mkdir -p "$OUT";S=("$ROOT/rtl/common/rv_fifo.sv" "$ROOT/rtl/attention/blocked_attention_stream_controller.sv" "$ROOT/tb/tb_l5_q1024_8x8_performance_trace.sv")
run(){ local limit=$1;shift;MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" timeout --foreground --signal=INT --kill-after=30s "$limit" "$@";}
run 600s "$V" --binary --timing -Wall -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL -Wno-WIDTH -Wno-SYNCASYNCNET -j 8 -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" --top-module tb_l5_q1024_8x8_performance_trace --Mdir "$OUT/obj" -o tb "${S[@]}" >"$OUT/build.log" 2>&1
run 600s "$OUT/obj/tb"|tee "$OUT/tb.log";grep -q 'L5_Q1024_8X8_PERFORMANCE_TRACE_PASS' "$OUT/tb.log"
