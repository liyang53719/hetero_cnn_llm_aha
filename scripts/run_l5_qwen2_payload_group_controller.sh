#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);OUT=${OUT:-$ROOT/work/results/l5_qwen2_payload_group_controller};R=$ROOT/scripts/run_memory_capped.sh;V=${VERILATOR:-$ROOT/work/toolchain/conda/bin/verilator};mkdir -p "$OUT"
run(){ local t=$1;shift;MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" timeout --foreground --signal=INT --kill-after=30s "$t" "$@";}
run 600s "$V" --binary --timing --assert -Wall -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL -Wno-WIDTH -Wno-PROCASSINIT -Wno-SYNCASYNCNET -j 8 -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" --top-module tb_qwen2_payload_group_controller --Mdir "$OUT/obj" -o tb "$ROOT/rtl/control/qwen2_payload_group_controller.sv" "$ROOT/tb/tb_qwen2_payload_group_controller.sv">"$OUT/build.log" 2>&1
run 600s "$OUT/obj/tb"|tee "$OUT/tb.log";grep -q 'QWEN2_PAYLOAD_GROUP_CONTROLLER_PASS groups=7 layers=28 commands=168 completions=168 reference_injections_inside_groups=0' "$OUT/tb.log"
