#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT=${OUT:-"$ROOT/work/results/open_rtl"}
mkdir -p "$OUT"
HETERO_VERILATOR=${HETERO_VERILATOR:-$(command -v verilator || true)}

if [[ -n "$HETERO_VERILATOR" ]]; then
  "$HETERO_VERILATOR" --version | tee "$OUT/verilator.version"
  "$HETERO_VERILATOR" --lint-only --timing -Wall -Wno-fatal \
    "$ROOT/rtl/common/rv_fifo.sv" \
    "$ROOT/rtl/top/command_dispatch.sv" \
    "$ROOT/rtl/top/hetero_npu_shell.sv" \
    --top-module hetero_npu_shell |& tee "$OUT/shell_lint.log"
  "$HETERO_VERILATOR" --lint-only --timing -Wall -Wno-fatal \
    "$ROOT/rtl/matrix/matrix_engine_int8_tile.sv" |& tee "$OUT/matrix_lint.log"
  "$HETERO_VERILATOR" --lint-only --timing -Wall -Wno-fatal \
    "$ROOT/rtl/sfu/cgra_sfu_vector.sv" |& tee "$OUT/sfu_lint.log"
  "$HETERO_VERILATOR" --lint-only --timing -Wall -Wno-fatal \
    "$ROOT/rtl/kv/kv_cache_engine.sv" |& tee "$OUT/kv_lint.log"
  "$HETERO_VERILATOR" --lint-only --timing -Wall \
    "$ROOT/rtl/kv/kv_idma_basic_core.sv" "$ROOT/rtl/kv/kv_descriptor_v2_idma_adapter.sv" \
    --top-module kv_descriptor_v2_idma_adapter |& tee "$OUT/kv_idma_basic_lint.log"
  "$HETERO_VERILATOR" --lint-only --timing -Wall -Wno-fatal \
    "$ROOT/rtl/common/rv_fifo.sv" \
    "$ROOT/rtl/top/command_dispatch.sv" \
    "$ROOT/rtl/top/hetero_npu_shell.sv" \
    "$ROOT/rtl/integration/command_event_scoreboard.sv" \
    "$ROOT/rtl/integration/engine_contract_adapter.sv" \
    "$ROOT/rtl/integration/hetero_npu_integrated_v0.sv" \
    --top-module hetero_npu_integrated_v0 |& tee "$OUT/integrated_v0_lint.log"
  "$HETERO_VERILATOR" --lint-only --timing -Wall -Wno-fatal \
    "$ROOT/rtl/fabric/shared_l2_fabric.sv" \
    --top-module shared_l2_fabric |& tee "$OUT/shared_l2_lint.log"
  "$HETERO_VERILATOR" --lint-only --timing -Wall \
    "$ROOT/rtl/fabric/shared_l2_client_arbiter.sv" \
    --top-module shared_l2_client_arbiter |& tee "$OUT/shared_l2_client_arbiter_lint.log"
  "$HETERO_VERILATOR" --lint-only --timing -Wall -Wno-fatal \
    "$ROOT/rtl/fabric/shared_l2_descriptor_port.sv" \
    --top-module shared_l2_descriptor_port |& tee "$OUT/shared_l2_descriptor_port_lint.log"
  "$HETERO_VERILATOR" --lint-only --timing -Wall -Wno-fatal \
    "$ROOT/rtl/integration/hetero_npu_numerical_integration_v0.sv" \
    "$ROOT/rtl/matrix/matrix_engine_int8_tile.sv" \
    "$ROOT/rtl/sfu/cgra_sfu_vector.sv" \
    "$ROOT/rtl/kv/kv_cache_engine.sv" \
    --top-module hetero_npu_numerical_integration_v0 |& tee "$OUT/numerical_integration_lint.log"
  "$HETERO_VERILATOR" --lint-only --timing -Wall -Wno-fatal \
    "$ROOT/rtl/integration/gemmini_rocc_command_adapter.sv" \
    --top-module gemmini_rocc_command_adapter |& tee "$OUT/gemmini_rocc_adapter_lint.log"
  "$HETERO_VERILATOR" --lint-only --timing -Wall -Wno-fatal \
    "$ROOT/rtl/integration/gemmini_rocc_program_adapter.sv" \
    --top-module gemmini_rocc_program_adapter |& tee "$OUT/gemmini_rocc_program_adapter_lint.log"
  "$HETERO_VERILATOR" --lint-only --timing -Wall -Wno-fatal \
    "$ROOT/rtl/integration/gemmini_descriptor_sequencer.sv" \
    --top-module gemmini_descriptor_sequencer |& tee "$OUT/gemmini_descriptor_sequencer_lint.log"
  "$HETERO_VERILATOR" --lint-only --timing -Wall \
    "$ROOT/rtl/integration/matrix_descriptor_v2_snapshot.sv" \
    --top-module matrix_descriptor_v2_snapshot |& tee "$OUT/matrix_descriptor_v2_snapshot_lint.log"
  "$HETERO_VERILATOR" --lint-only --timing -Wall \
    "$ROOT/rtl/integration/matrix_descriptor_v2_decode.sv" \
    --top-module matrix_descriptor_v2_decode |& tee "$OUT/matrix_descriptor_v2_decode_lint.log"
  "$HETERO_VERILATOR" --lint-only --timing -Wall \
    "$ROOT/rtl/integration/gemmini_descriptor_v2_emitter.sv" \
    --top-module gemmini_descriptor_v2_emitter |& tee "$OUT/gemmini_descriptor_v2_emitter_lint.log"
  "$HETERO_VERILATOR" --lint-only --timing -Wall -Wno-fatal \
    "$ROOT/rtl/integration/aha_garnet_axi_config_loader.sv" \
    --top-module aha_garnet_axi_config_loader |& tee "$OUT/aha_garnet_axi_loader_lint.log"
  "$HETERO_VERILATOR" --lint-only --timing -Wall -Wno-fatal \
    "$ROOT/rtl/integration/aha_garnet_proc_packet_writer.sv" \
    --top-module aha_garnet_proc_packet_writer |& tee "$OUT/aha_garnet_proc_packet_writer_lint.log"
  "$HETERO_VERILATOR" --lint-only --timing -Wall -Wno-fatal \
    "$ROOT/rtl/integration/aha_garnet_axi_config_loader.sv" \
    "$ROOT/rtl/integration/aha_garnet_proc_packet_writer.sv" \
    "$ROOT/rtl/integration/aha_garnet_microsequencer.sv" \
    --top-module aha_garnet_microsequencer |& tee "$OUT/aha_garnet_microsequencer_lint.log"
  "$HETERO_VERILATOR" --lint-only --timing -Wall -Wno-fatal \
    "$ROOT/rtl/common/rv_fifo.sv" "$ROOT/rtl/top/command_dispatch.sv" \
    "$ROOT/rtl/top/hetero_npu_shell.sv" "$ROOT/rtl/integration/command_event_scoreboard.sv" \
    "$ROOT/rtl/integration/engine_contract_adapter.sv" "$ROOT/rtl/integration/matrix_descriptor_v2_snapshot.sv" \
    "$ROOT/rtl/integration/matrix_descriptor_v2_decode.sv" "$ROOT/rtl/integration/gemmini_descriptor_v2_emitter.sv" \
    "$ROOT/rtl/integration/gemmini_rocc_program_adapter.sv" "$ROOT/rtl/integration/gemmini_descriptor_v2_pipeline.sv" \
    "$ROOT/rtl/kv/kv_idma_basic_core.sv" "$ROOT/rtl/kv/kv_descriptor_v2_idma_adapter.sv" \
    "$ROOT/rtl/integration/hetero_npu_gemmini_rocc_integration_v0.sv" \
    --top-module hetero_npu_gemmini_rocc_integration_v0 |& tee "$OUT/gemmini_rocc_integration_lint.log"
else
  echo "Verilator is absent; using Icarus compile/run coverage only." \
    | tee "$OUT/verilator_missing.txt"
fi

if command -v iverilog >/dev/null 2>&1; then
  iverilog -g2012 -s tb_hetero_npu_shell -o "$OUT/tb_shell" \
    "$ROOT/rtl/common/rv_fifo.sv" \
    "$ROOT/rtl/top/command_dispatch.sv" \
    "$ROOT/rtl/top/hetero_npu_shell.sv" \
    "$ROOT/tb/tb_hetero_npu_shell.sv"
  vvp "$OUT/tb_shell" | tee "$OUT/tb_shell.log"
  iverilog -g2012 -s tb_hetero_npu_integrated_v0 -o "$OUT/tb_integrated_v0" \
    "$ROOT/rtl/common/rv_fifo.sv" \
    "$ROOT/rtl/top/command_dispatch.sv" \
    "$ROOT/rtl/top/hetero_npu_shell.sv" \
    "$ROOT/rtl/integration/command_event_scoreboard.sv" \
    "$ROOT/rtl/integration/engine_contract_adapter.sv" \
    "$ROOT/rtl/integration/hetero_npu_integrated_v0.sv" \
    "$ROOT/tb/tb_hetero_npu_integrated_v0.sv"
  vvp "$OUT/tb_integrated_v0" | tee "$OUT/tb_integrated_v0.log"
  iverilog -g2012 -s tb_shared_l2_fabric -o "$OUT/tb_shared_l2" \
    "$ROOT/rtl/fabric/shared_l2_fabric.sv" \
    "$ROOT/tb/tb_shared_l2_fabric.sv"
  vvp "$OUT/tb_shared_l2" | tee "$OUT/tb_shared_l2.log"
  iverilog -g2012 -s tb_shared_l2_descriptor_port -o "$OUT/tb_shared_l2_descriptor_port" \
    "$ROOT/rtl/fabric/shared_l2_descriptor_port.sv" \
    "$ROOT/tb/tb_shared_l2_descriptor_port.sv"
  vvp "$OUT/tb_shared_l2_descriptor_port" | tee "$OUT/tb_shared_l2_descriptor_port.log"
  iverilog -g2012 -s tb_matrix_engine_int8_tile -o "$OUT/tb_matrix" \
    "$ROOT/rtl/matrix/matrix_engine_int8_tile.sv" "$ROOT/tb/tb_matrix_engine_int8_tile.sv"
  vvp "$OUT/tb_matrix" | tee "$OUT/tb_matrix.log"
  iverilog -g2012 -s tb_cgra_sfu_vector -o "$OUT/tb_sfu" \
    "$ROOT/rtl/sfu/cgra_sfu_vector.sv" "$ROOT/tb/tb_cgra_sfu_vector.sv"
  vvp "$OUT/tb_sfu" | tee "$OUT/tb_sfu.log"
  iverilog -g2012 -s tb_kv_cache_engine -o "$OUT/tb_kv" \
    "$ROOT/rtl/kv/kv_cache_engine.sv" "$ROOT/tb/tb_kv_cache_engine.sv"
  vvp "$OUT/tb_kv" | tee "$OUT/tb_kv.log"
  iverilog -g2012 -s tb_kv_descriptor_v2_idma_adapter -o "$OUT/tb_kv_idma_basic" \
    "$ROOT/rtl/kv/kv_idma_basic_core.sv" "$ROOT/rtl/kv/kv_descriptor_v2_idma_adapter.sv" \
    "$ROOT/tb/tb_kv_descriptor_v2_idma_adapter.sv"
  vvp "$OUT/tb_kv_idma_basic" | tee "$OUT/tb_kv_idma_basic.log"
  iverilog -g2012 -s tb_hetero_npu_numerical_integration_v0 -o "$OUT/tb_numerical_integration" \
    "$ROOT/rtl/integration/hetero_npu_numerical_integration_v0.sv" \
    "$ROOT/rtl/matrix/matrix_engine_int8_tile.sv" \
    "$ROOT/rtl/sfu/cgra_sfu_vector.sv" \
    "$ROOT/rtl/kv/kv_cache_engine.sv" \
    "$ROOT/tb/tb_hetero_npu_numerical_integration_v0.sv"
  vvp "$OUT/tb_numerical_integration" | tee "$OUT/tb_numerical_integration.log"
  iverilog -g2012 -s tb_gemmini_rocc_command_adapter -o "$OUT/tb_gemmini_rocc_adapter" \
    "$ROOT/rtl/integration/gemmini_rocc_command_adapter.sv" \
    "$ROOT/tb/tb_gemmini_rocc_command_adapter.sv"
  vvp "$OUT/tb_gemmini_rocc_adapter" | tee "$OUT/tb_gemmini_rocc_adapter.log"
  iverilog -g2012 -s tb_gemmini_rocc_program_adapter -o "$OUT/tb_gemmini_rocc_program_adapter" \
    "$ROOT/rtl/integration/gemmini_rocc_program_adapter.sv" \
    "$ROOT/tb/tb_gemmini_rocc_program_adapter.sv"
  vvp "$OUT/tb_gemmini_rocc_program_adapter" | tee "$OUT/tb_gemmini_rocc_program_adapter.log"
  iverilog -g2012 -s tb_gemmini_descriptor_sequencer -o "$OUT/tb_gemmini_descriptor_sequencer" \
    "$ROOT/rtl/integration/gemmini_descriptor_sequencer.sv" \
    "$ROOT/tb/tb_gemmini_descriptor_sequencer.sv"
  vvp "$OUT/tb_gemmini_descriptor_sequencer" | tee "$OUT/tb_gemmini_descriptor_sequencer.log"
  iverilog -g2012 -s tb_matrix_descriptor_v2_snapshot -o "$OUT/tb_matrix_descriptor_v2_snapshot" \
    "$ROOT/rtl/integration/matrix_descriptor_v2_snapshot.sv" \
    "$ROOT/rtl/integration/matrix_descriptor_v2_decode.sv" \
    "$ROOT/tb/tb_matrix_descriptor_v2_snapshot.sv"
  vvp "$OUT/tb_matrix_descriptor_v2_snapshot" | tee "$OUT/tb_matrix_descriptor_v2_snapshot.log"
  iverilog -g2012 -s tb_gemmini_descriptor_v2_pipeline -o "$OUT/tb_gemmini_descriptor_v2_pipeline" \
    "$ROOT/rtl/integration/matrix_descriptor_v2_snapshot.sv" \
    "$ROOT/rtl/integration/matrix_descriptor_v2_decode.sv" \
    "$ROOT/rtl/integration/gemmini_descriptor_v2_emitter.sv" \
    "$ROOT/tb/tb_gemmini_descriptor_v2_pipeline.sv"
  (cd "$ROOT" && vvp "$OUT/tb_gemmini_descriptor_v2_pipeline") | tee "$OUT/tb_gemmini_descriptor_v2_pipeline.log"
  iverilog -g2012 -s tb_command_event_scoreboard -o "$OUT/tb_command_event_scoreboard" \
    "$ROOT/rtl/integration/command_event_scoreboard.sv" \
    "$ROOT/tb/tb_command_event_scoreboard.sv"
  vvp "$OUT/tb_command_event_scoreboard" | tee "$OUT/tb_command_event_scoreboard.log"
  iverilog -g2012 -s tb_aha_garnet_axi_config_loader -o "$OUT/tb_aha_garnet_axi_loader" \
    "$ROOT/rtl/integration/aha_garnet_axi_config_loader.sv" \
    "$ROOT/tb/tb_aha_garnet_axi_config_loader.sv"
  vvp "$OUT/tb_aha_garnet_axi_loader" | tee "$OUT/tb_aha_garnet_axi_loader.log"
  iverilog -g2012 -s tb_aha_garnet_proc_packet_writer -o "$OUT/tb_aha_garnet_proc_packet_writer" \
    "$ROOT/rtl/integration/aha_garnet_proc_packet_writer.sv" \
    "$ROOT/tb/tb_aha_garnet_proc_packet_writer.sv"
  vvp "$OUT/tb_aha_garnet_proc_packet_writer" | tee "$OUT/tb_aha_garnet_proc_packet_writer.log"
  iverilog -g2012 -s tb_aha_garnet_microsequencer -o "$OUT/tb_aha_garnet_microsequencer" \
    "$ROOT/rtl/integration/aha_garnet_axi_config_loader.sv" \
    "$ROOT/rtl/integration/aha_garnet_proc_packet_writer.sv" \
    "$ROOT/rtl/integration/aha_garnet_microsequencer.sv" \
    "$ROOT/tb/tb_aha_garnet_microsequencer.sv"
  vvp "$OUT/tb_aha_garnet_microsequencer" | tee "$OUT/tb_aha_garnet_microsequencer.log"
  iverilog -g2012 -s tb_hetero_npu_gemmini_rocc_integration_v0 -o "$OUT/tb_gemmini_rocc_integration" \
    "$ROOT/rtl/common/rv_fifo.sv" "$ROOT/rtl/top/command_dispatch.sv" "$ROOT/rtl/top/hetero_npu_shell.sv" \
    "$ROOT/rtl/integration/command_event_scoreboard.sv" "$ROOT/rtl/integration/engine_contract_adapter.sv" \
    "$ROOT/rtl/integration/matrix_descriptor_v2_snapshot.sv" "$ROOT/rtl/integration/matrix_descriptor_v2_decode.sv" \
    "$ROOT/rtl/integration/gemmini_descriptor_v2_emitter.sv" "$ROOT/rtl/integration/gemmini_rocc_program_adapter.sv" \
    "$ROOT/rtl/integration/gemmini_descriptor_v2_pipeline.sv" "$ROOT/rtl/kv/kv_idma_basic_core.sv" \
    "$ROOT/rtl/kv/kv_descriptor_v2_idma_adapter.sv" "$ROOT/rtl/integration/hetero_npu_gemmini_rocc_integration_v0.sv" \
    "$ROOT/tb/tb_hetero_npu_gemmini_rocc_integration_v0.sv"
  vvp "$OUT/tb_gemmini_rocc_integration" | tee "$OUT/tb_gemmini_rocc_integration.log"
else
  echo "Icarus is absent; supplied SV testbenches were not run." \
    | tee "$OUT/iverilog_missing.txt"
fi

if [[ -z "$HETERO_VERILATOR" ]] && ! command -v iverilog >/dev/null 2>&1; then
  echo "No SystemVerilog compiler is available." >&2
  exit 2
fi

echo OPEN_RTL_GATE_PASS
