#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT=${OUT:-$ROOT/work/results/l3_aha_kv_endpoints}
VERILATOR=${VERILATOR:-$ROOT/work/toolchain/conda/bin/verilator}
RUN_CAPPED="$ROOT/scripts/run_memory_capped.sh"
OBJ="$OUT/obj_100k"
mkdir -p "$OUT"

SOURCES=(
  "$ROOT/rtl/common/tensor_stream_skid.sv"
  "$ROOT/rtl/fabric/matrix_direct_streams.sv"
  "$ROOT/rtl/integration/aha_garnet_proc_packet_writer.sv"
  "$ROOT/rtl/integration/aha_tensor_stream_endpoint.sv"
  "$ROOT/rtl/integration/kv_tensor_stream_endpoint.sv"
  "$ROOT/tb/tb_aha_kv_tensor_stream_endpoints.sv"
)

MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=8G MEMORY_MAX=10G "$RUN_CAPPED" \
  "$VERILATOR" --lint-only --timing -Wall \
  --top-module tb_aha_kv_tensor_stream_endpoints "${SOURCES[@]}" \
  >"$OUT/verilator_lint.log" 2>&1

MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=8G MEMORY_MAX=10G "$RUN_CAPPED" \
  "$VERILATOR" --binary --timing -Wall -j 4 \
  -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" \
  -GTARGET=100000 --top-module tb_aha_kv_tensor_stream_endpoints \
  --Mdir "$OBJ" -o tb_100k "${SOURCES[@]}" \
  >"$OUT/verilator_build.log" 2>&1

MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=8G MEMORY_MAX=10G "$RUN_CAPPED" \
  "$OBJ/tb_100k" | tee "$OUT/tb_100k.log"
grep -q "AHA_KV_TENSOR_ENDPOINTS_100K_PASS transfers=100000" "$OUT/tb_100k.log"
echo L3_AHA_KV_TENSOR_ENDPOINTS_GATE_PASS
