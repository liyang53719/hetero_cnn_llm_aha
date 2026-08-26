#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT=${OUT:-$ROOT/work/results/l3_spad_gateway}
VERILATOR=${VERILATOR:-$ROOT/work/toolchain/conda/bin/verilator}
RUN_CAPPED="$ROOT/scripts/run_memory_capped.sh"
mkdir -p "$OUT"

MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$RUN_CAPPED" \
  iverilog -g2012 -Wall \
  -Ptb_gemmini_spad_tensor_gateway.TARGET=100000 \
  -s tb_gemmini_spad_tensor_gateway -o "$OUT/tb_100k" \
  "$ROOT/rtl/common/tensor_stream_skid.sv" \
  "$ROOT/rtl/fabric/matrix_direct_streams.sv" \
  "$ROOT/rtl/integration/gemmini_spad_tensor_gateway.sv" \
  "$ROOT/tb/tb_gemmini_spad_tensor_gateway.sv" \
  >"$OUT/iverilog.log" 2>&1

MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$RUN_CAPPED" \
  vvp "$OUT/tb_100k" | tee "$OUT/tb_100k.log"

MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$RUN_CAPPED" \
  "$VERILATOR" --lint-only --timing -Wall \
  --top-module gemmini_spad_tensor_gateway \
  "$ROOT/rtl/integration/gemmini_spad_tensor_gateway.sv" \
  >"$OUT/verilator_lint.log" 2>&1

echo L3_GEMMINI_SPAD_GATEWAY_GATE_PASS
