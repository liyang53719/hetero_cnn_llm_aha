#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd);OUT=${OUT:-$ROOT/work/results/l3_client_arbiter}
VERILATOR=${VERILATOR:-$ROOT/work/toolchain/conda/bin/verilator};mkdir -p "$OUT"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$ROOT/scripts/run_memory_capped.sh" \
  iverilog -g2012 -Ptb_shared_l2_client_arbiter.TARGET=100000 -s tb_shared_l2_client_arbiter \
  -o "$OUT/tb" "$ROOT/rtl/fabric/shared_l2_client_arbiter.sv" \
  "$ROOT/rtl/fabric/shared_l2_fabric.sv" "$ROOT/tb/tb_shared_l2_client_arbiter.sv"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$ROOT/scripts/run_memory_capped.sh" \
  vvp "$OUT/tb" | tee "$OUT/tb.log"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$ROOT/scripts/run_memory_capped.sh" \
  "$VERILATOR" --lint-only -Wall --top-module shared_l2_client_arbiter \
  "$ROOT/rtl/fabric/shared_l2_client_arbiter.sv" >"$OUT/lint.log" 2>&1
echo L3_CLIENT_ARBITER_GATE_PASS
