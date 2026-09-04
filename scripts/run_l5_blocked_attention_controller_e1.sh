#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);OUT=${OUT:-$ROOT/work/results/l5_blocked_attention_controller_e1};R=$ROOT/scripts/run_memory_capped.sh;V=${VERILATOR:-$ROOT/work/toolchain/conda/bin/verilator};mkdir -p "$OUT"
SOURCES=("$ROOT/rtl/common/rv_fifo.sv" "$ROOT/rtl/attention/blocked_attention_stream_controller.sv" "$ROOT/tb/tb_blocked_attention_stream_controller.sv")
run_capped(){ local limit=$1;shift;MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" timeout --foreground --signal=INT --kill-after=30s "$limit" "$@";}
run_capped 600s "$V" --binary --threads 4 --timing -Wall -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL -Wno-WIDTHEXPAND -Wno-WIDTHTRUNC -Wno-SYNCASYNCNET -j 4 -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" --top-module tb_blocked_attention_stream_controller --Mdir "$OUT/obj" -o tb "${SOURCES[@]}" >"$OUT/build.log" 2>&1
rm -f "$OUT/task_trace.txt" "$OUT/tb.log";SEEDS=(1aceb00c 00000001 00000007 00000026 0000a77e 13579bdf 2468ace1 deadbeef)
for i in "${!SEEDS[@]}";do ARGS=(+SEED="${SEEDS[$i]}");if [[ $i == 0 ]];then ARGS+=(+TRACE="$OUT/task_trace.txt");fi;run_capped 600s "$OUT/obj/tb" "${ARGS[@]}"|tee -a "$OUT/tb.log";done
[[ $(grep -c 'CASE_PASS .* seq=128 tasks=240 merges=0 .*loss=0 duplicate=0 reorder=0 deadlock=0' "$OUT/tb.log") == 8 ]];[[ $(grep -c 'CASE_PASS .* seq=384 tasks=1872 merges=4608 .*loss=0 duplicate=0 reorder=0 deadlock=0' "$OUT/tb.log") == 8 ]];[[ $(grep -c 'CASE_PASS .* seq=1024 tasks=12672 merges=43008 .*loss=0 duplicate=0 reorder=0 deadlock=0' "$OUT/tb.log") == 8 ]];[[ $(grep -c 'TB_PASS seed=' "$OUT/tb.log") == 8 ]];echo L5_BLOCKED_ATTENTION_CONTROLLER_PROTOCOL_E1_PASS seeds=8 tasks=118272
