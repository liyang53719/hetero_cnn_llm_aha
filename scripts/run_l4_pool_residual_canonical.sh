#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);OUT=$ROOT/work/results/l4_pool_residual_canonical;mkdir -p "$OUT";R=$ROOT/scripts/run_memory_capped.sh;V=$ROOT/work/toolchain/conda/bin/verilator
S=("$ROOT/rtl/common/tensor_stream_skid.sv" "$ROOT/rtl/fabric/matrix_direct_streams.sv" "$ROOT/rtl/integration/gemmini_spad_tensor_gateway.sv" "$ROOT/rtl/integration/aha_garnet_proc_packet_writer.sv" "$ROOT/rtl/integration/aha_tensor_stream_endpoint.sv" "$ROOT/rtl/sfu/int8_pool_residual_sfu.sv" "$ROOT/rtl/integration/sfu_stream_endpoint_mux.sv" "$ROOT/rtl/integration/kv_tensor_stream_endpoint.sv" "$ROOT/rtl/integration/hetero_l3_stream_complex.sv" "$ROOT/tb/tb_hetero_l3_stream_complex.sv")
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=8G MEMORY_MAX=10G "$R" "$V" --lint-only --timing -Wall --top-module tb_hetero_l3_stream_complex "${S[@]}" >"$OUT/lint.log" 2>&1
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=8G MEMORY_MAX=10G "$R" "$V" --binary --timing -Wall -j 4 -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" -GTARGET=0 -GDEDICATED_TARGET=10000 --top-module tb_hetero_l3_stream_complex --Mdir "$OUT/obj_10k" -o tb "${S[@]}" >"$OUT/build.log" 2>&1
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=8G MEMORY_MAX=10G "$R" "$OUT/obj_10k/tb"|tee "$OUT/tb.log"
grep -q 'dedicated=10000' "$OUT/tb.log";echo L4_POOL_RESIDUAL_CANONICAL_GATE_PASS
