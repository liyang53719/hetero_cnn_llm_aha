#!/usr/bin/env bash
# Source from a build script; all entries are unchanged retained project RTL.
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
RETAINED_SOURCES=(
 "$ROOT/rtl/integration/qwen2_matrix_command_endpoint.sv"
 "$ROOT/rtl/matrix/bf16_outer_product_array_glue512.sv"
 "$ROOT/rtl/matrix/candidates/rev8b_a/bf16_operand_distribution512_rev8b_a_candidate.sv"
)
for name in bf16_context_scheduler5 bf16_outer_product_array_control5 bf16_context_tag_pipeline5 bf16_context_fma_pipeline_lane5 bf16_context_lane_cluster16 bf16_cluster_flags_glue32 bf16_context_front_control5 bf16_front_to_cluster_broadcast32 bf16_outer_product_context_array; do
 RETAINED_SOURCES+=("$ROOT/rtl/matrix/candidates/rev8b_b/${name}_rev8b_b_candidate.sv")
done
for source in "${RETAINED_SOURCES[@]}"; do [[ -s $source ]] || { echo "Missing retained RTL: $source" >&2; return 2; }; done
# The full-tile Chisel adapter uses the unchanged latch-based tech-cells ICG.
# Unified iDMA builds include it in idma.f and explicitly skip this duplicate.
if [[ ${RETAINED_SKIP_CLOCK:-0} != 1 ]]; then
 CLOCK_SOURCE=${RETAINED_CLOCK_SOURCE:-${IDMA_EXPORT:-$ROOT/work/upstream/pinned_idma_export}/deps/tech_cells_generic/src/rtl/tc_clk.sv}
 [[ -s "$CLOCK_SOURCE" ]] || { echo 'BLOCKED: set IDMA_EXPORT or RETAINED_CLOCK_SOURCE for pinned tc_clk.sv' >&2; return 77; }
 [[ $(sha256sum "$CLOCK_SOURCE" | cut -d' ' -f1) == 93e9747504fa1da6473560341febbfae6c5e917768633a84fc9ef12299293207 ]] || { echo 'Retained ICG source drift' >&2; return 2; }
 RETAINED_SOURCES+=("$CLOCK_SOURCE")
fi
