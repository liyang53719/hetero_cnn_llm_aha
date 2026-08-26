#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);OUT=$ROOT/work/results/l5_q128_trace_controller;R=$ROOT/scripts/run_memory_capped.sh;V=$ROOT/work/toolchain/conda/bin/verilator;mkdir -p "$OUT";S=("$ROOT/rtl/control/l5_q128_count_controller.sv" "$ROOT/rtl/control/l5_q128_trace_controller.sv" "$ROOT/tb/tb_l5_q128_trace_controller.sv")
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" "$V" --binary --timing -Wall -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL -j 8 -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" --top-module tb_l5_q128_trace_controller --Mdir "$OUT/obj" -o tb "${S[@]}" >"$OUT/build.log" 2>&1
cd "$ROOT";MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" "$OUT/obj/tb"|tee "$OUT/tb.log";grep -q 'L5_Q128_TRACE_CONTROLLER_PASS commands=24 matrix_steps=11698176 busy_cycles=61101824' "$OUT/tb.log";echo L5_Q128_TRACE_CONTROLLER_GATE_PASS
