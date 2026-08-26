#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT=${OUT:-$ROOT/work/results/l3_stream_complex}
VERILATOR=${VERILATOR:-$ROOT/work/toolchain/conda/bin/verilator}
RUN="$ROOT/scripts/run_memory_capped.sh";mkdir -p "$OUT"
SOURCES=(
  "$ROOT/rtl/common/tensor_stream_skid.sv" "$ROOT/rtl/fabric/matrix_direct_streams.sv"
  "$ROOT/rtl/integration/gemmini_spad_tensor_gateway.sv"
  "$ROOT/rtl/integration/aha_garnet_proc_packet_writer.sv"
  "$ROOT/rtl/integration/aha_tensor_stream_endpoint.sv"
  "$ROOT/rtl/sfu/int8_pool_residual_sfu.sv"
  "$ROOT/rtl/integration/sfu_stream_endpoint_mux.sv"
  "$ROOT/rtl/integration/kv_tensor_stream_endpoint.sv"
  "$ROOT/rtl/integration/hetero_l3_stream_complex.sv"
  "$ROOT/tb/tb_hetero_l3_stream_complex.sv"
)
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=8G MEMORY_MAX=10G "$RUN" \
  "$VERILATOR" --lint-only --timing -Wall --top-module tb_hetero_l3_stream_complex \
  "${SOURCES[@]}" >"$OUT/lint.log" 2>&1
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=8G MEMORY_MAX=10G "$RUN" \
  "$VERILATOR" --binary --timing -Wall -j 4 \
  -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" -GTARGET=100000 \
  --top-module tb_hetero_l3_stream_complex --Mdir "$OUT/obj_100k" -o tb_100k \
  "${SOURCES[@]}" >"$OUT/verilator_100k_build.log" 2>&1
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=8G MEMORY_MAX=10G "$RUN" \
  "$OUT/obj_100k/tb_100k" | tee "$OUT/verilator_100k.log"
grep -q "HETERO_L3_STREAM_COMPLEX_100K_PASS transfers=100000 matrix=150000 aha=50000 kv=50000" \
  "$OUT/verilator_100k.log"
echo L3_STREAM_COMPLEX_GATE_PASS
