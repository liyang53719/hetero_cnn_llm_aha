#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT=${OUT:-$ROOT/work/results/l3_event_scoreboard}
VERILATOR=${VERILATOR:-$ROOT/work/toolchain/conda/bin/verilator}
mkdir -p "$OUT"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=4G MEMORY_MAX=6G \
  "$ROOT/scripts/run_memory_capped.sh" iverilog -g2012 -Wall \
  -s tb_command_event_scoreboard_100k -o "$OUT/tb" \
  "$ROOT/rtl/integration/command_event_scoreboard.sv" \
  "$ROOT/tb/tb_command_event_scoreboard_100k.sv"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=4G MEMORY_MAX=6G \
  "$ROOT/scripts/run_memory_capped.sh" vvp "$OUT/tb" | tee "$OUT/tb.log"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=4G MEMORY_MAX=6G \
  "$ROOT/scripts/run_memory_capped.sh" "$VERILATOR" --lint-only --timing \
  -Wall -Wno-fatal "$ROOT/rtl/integration/command_event_scoreboard.sv" \
  --top-module command_event_scoreboard >"$OUT/verilator_lint.log" 2>&1
echo L3_EVENT_SCOREBOARD_GATE_PASS
