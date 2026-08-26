#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
MACRO_ROOT=${MACRO_ROOT:-$ROOT/work/generated/l10_sram/l2_sp_6144x128wm_base_0p8v_tt25}
MACRO=$MACRO_ROOT/l2sp6144x128wm.v
OUT=${OUT:-$ROOT/work/results/l3_macro_fabric}
TARGET=${TARGET:-100000}
VERILATOR=${VERILATOR:-$ROOT/work/toolchain/conda/bin/verilator}
[[ -f "$MACRO" ]] || { echo "missing generated macro: $MACRO" >&2; exit 2; }
mkdir -p "$OUT"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G \
  "$ROOT/scripts/run_memory_capped.sh" iverilog -g2012 \
  -DARM_DISABLE_EMA_CHECK -DUSE_MACRO_BACKEND \
  -Ptb_shared_l2_fabric.TARGET="$TARGET" -s tb_shared_l2_fabric -o "$OUT/tb" \
  "$MACRO" "$ROOT/rtl/memory/l2_sp6144x128_macro_wrapper.sv" \
  "$ROOT/rtl/memory/l2_512b_macro_bank_group.sv" \
  "$ROOT/rtl/fabric/shared_l2_macro_fabric.sv" "$ROOT/tb/tb_shared_l2_fabric.sv"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G \
  "$ROOT/scripts/run_memory_capped.sh" vvp "$OUT/tb" | tee "$OUT/tb.log"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G \
  "$ROOT/scripts/run_memory_capped.sh" "$VERILATOR" --lint-only --timing \
  -Wall -Wno-fatal -DARM_DISABLE_EMA_CHECK "$MACRO" \
  "$ROOT/rtl/memory/l2_sp6144x128_macro_wrapper.sv" \
  "$ROOT/rtl/memory/l2_512b_macro_bank_group.sv" \
  "$ROOT/rtl/fabric/shared_l2_macro_fabric.sv" \
  --top-module shared_l2_macro_fabric >"$OUT/verilator_lint.log" 2>&1
echo L3_SHARED_L2_MACRO_FABRIC_GATE_PASS target="$TARGET"
