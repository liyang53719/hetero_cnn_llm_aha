#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);OUT=$ROOT/work/results/l5_unified_prefill_count;R=$ROOT/scripts/run_memory_capped.sh;V=$ROOT/work/toolchain/conda/bin/verilator;mkdir -p "$OUT";S=("$ROOT/rtl/control/l5_prefill_count_controller.sv" "$ROOT/tb/tb_l5_prefill_count_controller.sv")
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" "$V" --binary --timing -Wall -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL -j 8 -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" --top-module tb_l5_prefill_count_controller --Mdir "$OUT/obj" -o tb "${S[@]}" >"$OUT/build.log" 2>&1
cd "$ROOT";MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" "$OUT/obj/tb"|tee "$OUT/tb.log";grep -q 'L5_UNIFIED_PREFILL_COUNT_CONTROLLER_PASS same_binary=1' "$OUT/tb.log";echo L5_UNIFIED_PREFILL_COUNT_GATE_PASS
