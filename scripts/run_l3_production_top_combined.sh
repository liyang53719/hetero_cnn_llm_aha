#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT=${OUT:-$ROOT/work/results/l3_combined}
MACRO=${MACRO:-$ROOT/work/generated/l10_sram/ct_sp_4096x128wm_base_0p8v_tt25/ctsp4096x128wm.v}
VERILATOR=${VERILATOR:-$ROOT/work/toolchain/conda/bin/verilator}
RUN="$ROOT/scripts/run_memory_capped.sh";mkdir -p "$OUT";test -f "$MACRO"
PROJECT=(
  "$ROOT/rtl/memory/ct_sp4096x128_macro_wrapper.sv"
  "$ROOT/rtl/common/rv_fifo.sv" "$ROOT/rtl/common/tensor_stream_skid.sv"
  "$ROOT/rtl/top/command_dispatch.sv"
  "$ROOT/rtl/integration/command_event_scoreboard_sram.sv"
  "$ROOT/rtl/integration/command_event_frontend_sram.sv"
  "$ROOT/rtl/integration/engine_completion_rr_arbiter.sv"
  "$ROOT/rtl/fabric/shared_l2_client_arbiter.sv"
  "$ROOT/rtl/fabric/shared_l2_fabric.sv"
  "$ROOT/rtl/fabric/matrix_direct_streams.sv"
  "$ROOT/rtl/integration/gemmini_spad_tensor_gateway.sv"
  "$ROOT/rtl/integration/aha_garnet_proc_packet_writer.sv"
  "$ROOT/rtl/integration/aha_tensor_stream_endpoint.sv"
  "$ROOT/rtl/sfu/int8_pool_residual_sfu.sv"
  "$ROOT/rtl/integration/sfu_stream_endpoint_mux.sv"
  "$ROOT/rtl/integration/kv_tensor_stream_endpoint.sv"
  "$ROOT/rtl/integration/hetero_l3_command_fabric.sv"
  "$ROOT/rtl/integration/hetero_l3_stream_complex.sv"
  "$ROOT/rtl/integration/hetero_l3_production_top.sv"
  "$ROOT/tb/tb_hetero_l3_production_top.sv"
)
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=8G MEMORY_MAX=10G "$RUN" \
  "$VERILATOR" --lint-only --timing -Wall \
  --top-module tb_hetero_l3_production_top \
  "$ROOT/tb/ctsp4096x128wm_lint_stub.sv" "${PROJECT[@]}" \
  >"$OUT/verilator_lint.log" 2>&1
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=8G MEMORY_MAX=10G "$RUN" \
  "$VERILATOR" --binary --timing --assert -Wall -Wno-fatal \
  -DARM_DISABLE_EMA_CHECK -j 4 -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" \
  -GCMD_TARGET=100000 -GL2_TARGET=100000 -GSTREAM_TARGET=10000 \
  --top-module tb_hetero_l3_production_top --Mdir "$OUT/obj_100k" -o tb_100k \
  "$MACRO" "${PROJECT[@]}" >"$OUT/verilator_100k_build.log" 2>&1
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=8G MEMORY_MAX=10G "$RUN" \
  "$OUT/obj_100k/tb_100k" | tee "$OUT/verilator_100k.log"
grep -q "HETERO_L3_PRODUCTION_TOP_COMBINED_PASS commands=100003" \
  "$OUT/verilator_100k.log"
echo L3_PRODUCTION_TOP_COMBINED_GATE_PASS
