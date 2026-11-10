#!/bin/bash
set -euo pipefail
W=/workspace/scratch/f28987e955ed
R=$W/round_20261110T0833/host_real_interface
export IDMA_EXPORT=$R/idma_export_bc_attempt/idma_export
source "$W/hetero_cnn_llm_aha/chisel/continuous_prefill/scripts/retained_sources.sh"
mapfile -t IDMA_OPTIONS < <(grep -E "^\+(incdir|define)\+" "$R/real_idma/idma.f" | sort -u)
exec "$W/runtime_recovery_0133/verilator-runtime/verilator" --cc "${IDMA_OPTIONS[@]}" --hierarchical "$W/hetero_cnn_llm_aha/chisel/continuous_prefill/tests/native_weight_hierarchy.vlt" --top-module HostBlockTopV4 -Wno-fatal --output-split 20000 --Mdir "$W/round_20261110T0933/host/obj_hier" -f "$R/real_idma/idma.f" "$R/HostBlockTopV4.sv" "$R/RetainedMath.sv" "${RETAINED_SOURCES[@]}" "$W/hetero_cnn_llm_aha/rtl/integration/idma_backend_rw_axi_flat_wrap.sv"
