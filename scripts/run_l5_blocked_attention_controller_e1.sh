#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);OUT=${OUT:-$ROOT/work/results/l5_blocked_attention_controller_e1};R=$ROOT/scripts/run_memory_capped.sh;V=${VERILATOR:-$ROOT/work/toolchain/conda/bin/verilator};mkdir -p "$OUT"
SOURCES=("$ROOT/rtl/common/rv_fifo.sv" "$ROOT/rtl/attention/blocked_attention_stream_controller.sv" "$ROOT/tb/tb_blocked_attention_stream_controller.sv")
run_capped(){ local limit=$1;shift;MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" timeout --foreground --signal=INT --kill-after=30s "$limit" "$@";}
run_capped 600s "$V" --binary --timing -Wall -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL -Wno-WIDTHEXPAND -Wno-WIDTHTRUNC -Wno-SYNCASYNCNET -j 8 -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" --top-module tb_blocked_attention_stream_controller --Mdir "$OUT/obj" -o tb "${SOURCES[@]}" >"$OUT/build.log" 2>&1
run_capped 600s "$OUT/obj/tb"|tee "$OUT/tb.log"
grep -q 'CASE_PASS seq=128 tasks=240 merges=0' "$OUT/tb.log";grep -q 'CASE_PASS seq=384 tasks=1872 merges=4608' "$OUT/tb.log";grep -q 'CASE_PASS seq=1024 tasks=12672 merges=43008' "$OUT/tb.log";grep -q 'TB_PASS' "$OUT/tb.log";echo L5_BLOCKED_ATTENTION_CONTROLLER_PROTOCOL_E1_PASS
