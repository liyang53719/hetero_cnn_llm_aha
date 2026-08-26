#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT=${OUT:-$ROOT/work/results/l3_spad_gateway}
GENERATED=${GENERATED:-$ROOT/work/generated/l3_gemmini_scratchpad_bank}
VERILATOR=${VERILATOR:-$ROOT/work/toolchain/conda/bin/verilator}
RUN_CAPPED="$ROOT/scripts/run_memory_capped.sh"
OBJ="$OUT/obj_pinned_100k"
mkdir -p "$OUT"

"$ROOT/scripts/generate_gemmini_scratchpad_bank.sh"

COMMON=(
  --timing --assert -Wall
  -Wno-DECLFILENAME
  -Wno-TIMESCALEMOD
  -Wno-UNUSEDSIGNAL
  -Wno-SYNCASYNCNET
  --top-module tb_gemmini_scratchpad_gateway_integration
  "$GENERATED/ScratchpadBank.sv"
  "$ROOT/rtl/common/tensor_stream_skid.sv"
  "$ROOT/rtl/fabric/matrix_direct_streams.sv"
  "$ROOT/rtl/integration/gemmini_spad_tensor_gateway.sv"
  "$ROOT/tb/tb_gemmini_scratchpad_gateway_integration.sv"
)

MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=8G MEMORY_MAX=10G "$RUN_CAPPED" \
  "$VERILATOR" --lint-only "${COMMON[@]}" \
  >"$OUT/verilator_pinned_lint.log" 2>&1

MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=8G MEMORY_MAX=10G "$RUN_CAPPED" \
  "$VERILATOR" --binary -j 4 \
  -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" \
  -GTARGET=100000 --Mdir "$OBJ" -o tb_pinned_100k \
  "${COMMON[@]}" >"$OUT/verilator_pinned_build.log" 2>&1

MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=8G MEMORY_MAX=10G "$RUN_CAPPED" \
  "$OBJ/tb_pinned_100k" | tee "$OUT/pinned_100k.log"

grep -q "GEMMINI_PINNED_SPAD_GATEWAY_PASS transfers=100000" \
  "$OUT/pinned_100k.log"
echo L3_GEMMINI_PINNED_SPAD_INTEGRATION_GATE_PASS
