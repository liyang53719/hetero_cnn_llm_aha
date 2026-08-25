#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
MACRO_ROOT=${MACRO_ROOT:-$ROOT/work/generated/l10_sram/ct_sp_4096x128wm_base_0p8v_tt25}
MACRO=$MACRO_ROOT/ctsp4096x128wm.v
OUT=${OUT:-$ROOT/work/results/l10_ct_sp_wrapper}
VERILATOR=${VERILATOR:-$ROOT/work/toolchain/conda/bin/verilator}
[[ -f "$MACRO" ]] || { echo "missing generated macro: $MACRO" >&2; exit 2; }
mkdir -p "$OUT"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=4G MEMORY_MAX=6G \
  "$ROOT/scripts/run_memory_capped.sh" iverilog -g2012 -Wall \
  -DARM_DISABLE_EMA_CHECK -s tb_ct_sp4096x128_macro_wrapper -o "$OUT/tb" \
  "$MACRO" "$ROOT/rtl/memory/ct_sp4096x128_macro_wrapper.sv" \
  "$ROOT/tb/tb_ct_sp4096x128_macro_wrapper.sv"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=4G MEMORY_MAX=6G \
  "$ROOT/scripts/run_memory_capped.sh" vvp "$OUT/tb" | tee "$OUT/tb.log"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=6G MEMORY_MAX=8G \
  "$ROOT/scripts/run_memory_capped.sh" "$VERILATOR" --lint-only --timing \
  -Wall -Wno-fatal -DARM_DISABLE_EMA_CHECK "$MACRO" \
  "$ROOT/rtl/memory/ct_sp4096x128_macro_wrapper.sv" \
  --top-module ct_sp4096x128_macro_wrapper >"$OUT/verilator_lint.log" 2>&1
echo L10_SP4096X128_WRAPPER_GATE_PASS
