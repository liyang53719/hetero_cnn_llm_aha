#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT=${OUT:-$ROOT/work/results/l5_matrix_context_revision8b_b/e1}
R="$ROOT/scripts/run_memory_capped.sh";V=${VERILATOR:-$ROOT/work/toolchain/conda/bin/verilator}
mkdir -p "$OUT";"$ROOT/scripts/generate_all_hardfloat_primitives.sh"
rm -f "$OUT/tb.log"
SOURCES=(
 "$ROOT/work/generated/l5_all_primitives/HeteroAllPrimitives.sv"
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
 "$ROOT/tb/tb_bf16_outer_product_context_array_rev8b_b.sv")
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" timeout --foreground --signal=INT --kill-after=30s 600s \
 "$V" --binary --threads 4 --timing -Wall -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL -Wno-UNOPTTHREADS -Wno-WIDTH -j 8 \
 -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" --top-module tb_bf16_outer_product_context_array_rev8b_b \
 --Mdir "$OUT/obj" -o tb "${SOURCES[@]}" >"$OUT/build.log" 2>&1
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" timeout --foreground --signal=INT --kill-after=30s 600s \
 "$OUT/obj/tb" | tee "$OUT/tb.log"
grep -q 'BF16_CONTEXT5_ARRAY_E1_PASS main_steps=1000000 random_steps=10000 contexts=5 lanes=512' "$OUT/tb.log"
