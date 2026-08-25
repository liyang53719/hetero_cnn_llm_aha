#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT=${OUT:-$ROOT/work/results/l3_direct_streams}
VERILATOR=${VERILATOR:-$ROOT/work/toolchain/conda/bin/verilator}
mkdir -p "$OUT"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=4G MEMORY_MAX=6G \
  "$ROOT/scripts/run_memory_capped.sh" iverilog -g2012 -Wall \
  -s tb_matrix_direct_streams -o "$OUT/tb" \
  "$ROOT/rtl/common/tensor_stream_skid.sv" \
  "$ROOT/rtl/fabric/matrix_direct_streams.sv" \
  "$ROOT/tb/tb_matrix_direct_streams.sv"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=4G MEMORY_MAX=6G \
  "$ROOT/scripts/run_memory_capped.sh" vvp "$OUT/tb" | tee "$OUT/tb.log"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=4G MEMORY_MAX=6G \
  "$ROOT/scripts/run_memory_capped.sh" "$VERILATOR" --lint-only --timing \
  -Wall -Wno-fatal "$ROOT/rtl/common/tensor_stream_skid.sv" \
  "$ROOT/rtl/fabric/matrix_direct_streams.sv" \
  --top-module matrix_direct_streams >"$OUT/verilator_lint.log" 2>&1
echo L3_DIRECT_STREAMS_GATE_PASS
