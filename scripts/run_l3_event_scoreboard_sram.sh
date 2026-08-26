#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
MACRO_ROOT=${MACRO_ROOT:-$ROOT/work/generated/l10_sram/ct_sp_4096x128wm_base_0p8v_tt25}
MACRO=$MACRO_ROOT/ctsp4096x128wm.v
OUT=${OUT:-$ROOT/work/results/l3_event_scoreboard_sram}
VERILATOR=${VERILATOR:-$ROOT/work/toolchain/conda/bin/verilator}
[[ -f "$MACRO" ]] || { echo "missing generated macro: $MACRO" >&2; exit 2; }
mkdir -p "$OUT"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=8G MEMORY_MAX=10G \
  "$ROOT/scripts/run_memory_capped.sh" iverilog -g2012 \
  -DARM_DISABLE_EMA_CHECK -s tb_command_event_scoreboard_sram_100k -o "$OUT/tb" \
  "$MACRO" "$ROOT/rtl/memory/ct_sp4096x128_macro_wrapper.sv" \
  "$ROOT/rtl/common/rv_fifo.sv" \
  "$ROOT/rtl/integration/command_event_scoreboard_sram.sv" \
  "$ROOT/rtl/integration/command_event_frontend_sram.sv" \
  "$ROOT/tb/tb_command_event_scoreboard_sram_100k.sv"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=8G MEMORY_MAX=10G \
  "$ROOT/scripts/run_memory_capped.sh" vvp "$OUT/tb" | tee "$OUT/tb.log"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=8G MEMORY_MAX=10G \
  "$ROOT/scripts/run_memory_capped.sh" "$VERILATOR" --lint-only --timing \
  -Wall -Wno-fatal -DARM_DISABLE_EMA_CHECK "$MACRO" \
  "$ROOT/rtl/memory/ct_sp4096x128_macro_wrapper.sv" \
  "$ROOT/rtl/common/rv_fifo.sv" \
  "$ROOT/rtl/integration/command_event_scoreboard_sram.sv" \
  "$ROOT/rtl/integration/command_event_frontend_sram.sv" \
  --top-module command_event_frontend_sram >"$OUT/verilator_lint.log" 2>&1
echo L3_EVENT_SCOREBOARD_SRAM_GATE_PASS
