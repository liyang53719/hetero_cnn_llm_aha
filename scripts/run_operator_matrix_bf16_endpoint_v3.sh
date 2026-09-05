#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);OUT=$ROOT/work/results/operator_matrix_bf16_endpoint_v3
TOP=${TOP:-tb_operator_matrix_bf16_endpoint_v3}
if [[ "$TOP" == tb_matrix_memory_runtime_k ]]; then OUT=$ROOT/work/results/matrix_memory_runtime_k; fi
if [[ "$TOP" != tb_operator_matrix_bf16_endpoint_v3 && "$TOP" != tb_matrix_memory_runtime_k ]]; then exit 2; fi
test "$(df --output=avail -k "$ROOT" | tail -1)" -gt 52428800
R=$ROOT/scripts/run_memory_capped.sh;V=$ROOT/work/toolchain/conda/bin/verilator;mkdir -p "$OUT"
S=("$ROOT/work/generated/l5_all_primitives/HeteroAllPrimitives.sv"
 "$ROOT/rtl/matrix/bf16_outer_product_array_glue512.sv"
 "$ROOT/rtl/matrix/candidates/rev8b_a/bf16_operand_distribution512_rev8b_a_candidate.sv"
 "$ROOT/rtl/matrix/candidates/rev8b_b/bf16_context_scheduler5_rev8b_b_candidate.sv"
 "$ROOT/rtl/matrix/candidates/rev8b_b/bf16_outer_product_array_control5_rev8b_b_candidate.sv"
 "$ROOT/rtl/matrix/candidates/rev8b_b/bf16_context_tag_pipeline5_rev8b_b_candidate.sv"
 "$ROOT/rtl/matrix/candidates/rev8b_b/bf16_context_fma_pipeline_lane5_rev8b_b_candidate.sv"
 "$ROOT/rtl/matrix/candidates/rev8b_b/bf16_context_lane_cluster16_rev8b_b_candidate.sv"
 "$ROOT/rtl/matrix/candidates/rev8b_b/bf16_cluster_flags_glue32_rev8b_b_candidate.sv"
 "$ROOT/rtl/matrix/candidates/rev8b_b/bf16_context_front_control5_rev8b_b_candidate.sv"
 "$ROOT/rtl/matrix/candidates/rev8b_b/bf16_front_to_cluster_broadcast32_rev8b_b_candidate.sv"
 "$ROOT/rtl/matrix/candidates/rev8b_b/bf16_outer_product_context_array_rev8b_b_candidate.sv"
 "$ROOT/rtl/integration/matrix_tile_step_guard.sv" "$ROOT/rtl/integration/operator_matrix_bf16_endpoint_v3.sv"
 "$ROOT/rtl/integration/qwen2_shared_l2_matrix_tile16_payload.sv"
 "$ROOT/tb/$TOP.sv")
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" timeout --foreground --signal=INT --kill-after=30s 600s \
 "$V" --binary --threads 4 --timing -Wall -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL -Wno-UNOPTTHREADS -Wno-WIDTH -j 4 \
 -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" --top-module "$TOP" --Mdir "$OUT/obj" -o tb "${S[@]}" >"$OUT/build.log" 2>&1
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" timeout --foreground --signal=INT --kill-after=30s 600s "$OUT/obj/tb"|tee "$OUT/test.log"
if [[ "$TOP" == tb_matrix_memory_runtime_k ]]; then
 grep -q 'MATRIX_MEMORY_RUNTIME_K_PASS cases=7' "$OUT/test.log"
else
 grep -q 'OPERATOR_MATRIX_BF16_ENDPOINT_V3_PASS opcodes=6' "$OUT/test.log"
fi
