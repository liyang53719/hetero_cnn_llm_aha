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
