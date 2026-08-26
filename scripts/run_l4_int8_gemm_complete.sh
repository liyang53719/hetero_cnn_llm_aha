#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT=${OUT:-$ROOT/work/results/l4_int8_gemm_l3_trace}
MACRO=${MACRO:-$ROOT/work/generated/l10_sram/ct_sp_4096x128wm_base_0p8v_tt25/ctsp4096x128wm.v}
VERILATOR=${VERILATOR:-$ROOT/work/toolchain/conda/bin/verilator}
PYTHON=${CNN_PYTHON:-$ROOT/work/toolchain/cnn_py312/bin/python}
RUN="$ROOT/scripts/run_memory_capped.sh";mkdir -p "$OUT";test -f "$MACRO"
PROJECT=(
  "$ROOT/rtl/memory/ct_sp4096x128_macro_wrapper.sv" "$ROOT/rtl/common/rv_fifo.sv"
  "$ROOT/rtl/common/tensor_stream_skid.sv" "$ROOT/rtl/top/command_dispatch.sv"
  "$ROOT/rtl/integration/command_event_scoreboard_sram.sv"
  "$ROOT/rtl/integration/command_event_frontend_sram.sv"
  "$ROOT/rtl/integration/engine_completion_rr_arbiter.sv"
  "$ROOT/rtl/fabric/shared_l2_client_arbiter.sv" "$ROOT/rtl/fabric/shared_l2_fabric.sv"
  "$ROOT/rtl/fabric/matrix_direct_streams.sv"
  "$ROOT/rtl/integration/gemmini_spad_tensor_gateway.sv"
  "$ROOT/rtl/integration/aha_garnet_proc_packet_writer.sv"
  "$ROOT/rtl/integration/aha_tensor_stream_endpoint.sv"
  "$ROOT/rtl/integration/kv_tensor_stream_endpoint.sv"
  "$ROOT/rtl/integration/hetero_l3_command_fabric.sv"
  "$ROOT/rtl/integration/hetero_l3_stream_complex.sv"
  "$ROOT/rtl/integration/hetero_l3_production_top.sv"
  "$ROOT/tb/tb_l4_int8_gemm_l3_trace.sv"
)
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=8G MEMORY_MAX=10G "$RUN" \
  "$VERILATOR" --lint-only --timing -Wall --top-module tb_l4_int8_gemm_l3_trace \
  "$ROOT/tb/ctsp4096x128wm_lint_stub.sv" "${PROJECT[@]}" >"$OUT/lint.log" 2>&1
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=8G MEMORY_MAX=10G "$RUN" \
  "$VERILATOR" --binary --timing --assert -Wall -Wno-fatal -DARM_DISABLE_EMA_CHECK \
  -j 4 -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" --top-module tb_l4_int8_gemm_l3_trace \
  --Mdir "$OUT/obj" -o tb "$MACRO" "${PROJECT[@]}" >"$OUT/build.log" 2>&1
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=8G MEMORY_MAX=10G "$RUN" \
  "$OUT/obj/tb" | tee "$OUT/tb.log"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=8G MEMORY_MAX=10G "$RUN" \
  iverilog -g2012 -s tb_gemmini_descriptor_v2_pipeline -o "$OUT/descriptor_tb" \
  "$ROOT/rtl/integration/matrix_descriptor_v2_snapshot.sv" \
  "$ROOT/rtl/integration/matrix_descriptor_v2_decode.sv" \
  "$ROOT/rtl/integration/gemmini_descriptor_v2_emitter.sv" \
  "$ROOT/tb/tb_gemmini_descriptor_v2_pipeline.sv"
(cd "$ROOT" && MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=8G MEMORY_MAX=10G \
  "$RUN" vvp "$OUT/descriptor_tb") | tee "$OUT/descriptor.log"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=8G MEMORY_MAX=10G "$RUN" \
  "$PYTHON" "$ROOT/scripts/audit_l4_int8_gemm_complete.py" \
  --payload "$ROOT/reports/execution/l4_int8_gemm_payload_result.json" \
  --trace-log "$OUT/tb.log" --descriptor-log "$OUT/descriptor.log" \
  --output "$ROOT/reports/execution/l4_int8_gemm_result.json"
echo L4_INT8_GEMM_COMPLETE_GATE_PASS
