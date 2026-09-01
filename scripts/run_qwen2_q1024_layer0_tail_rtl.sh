#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT=${OUT:-$ROOT/work/results/qwen2_q1024_layer0_tail_rtl}
RUN=$ROOT/scripts/run_memory_capped.sh
VERILATOR=${VERILATOR:-$ROOT/work/toolchain/conda/bin/verilator}
mkdir -p "$OUT"
run() { local limit=$1; shift; MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$RUN" timeout --foreground --signal=INT --kill-after=30s "$limit" taskset -c 8-23 "$@"; }

run 600s python3 "$ROOT/scripts/generate_qwen2_q1024_layer0_tail_rtl_vectors.py" | tee "$OUT/vector_generation.log"
run 600s "$ROOT/scripts/generate_all_hardfloat_primitives.sh"
C=$ROOT/rtl/matrix/candidates
S=(
  "$ROOT/work/generated/l5_all_primitives/HeteroAllPrimitives.sv"
  "$ROOT/rtl/common/rv_fifo.sv"
  "$ROOT/rtl/matrix/bf16_outer_product_array_glue512.sv"
  "$C/rev8b_a/bf16_operand_distribution512_rev8b_a_candidate.sv"
  "$C/rev8b_b/bf16_context_scheduler5_rev8b_b_candidate.sv"
  "$C/rev8b_b/bf16_outer_product_array_control5_rev8b_b_candidate.sv"
  "$C/rev8b_b/bf16_context_tag_pipeline5_rev8b_b_candidate.sv"
  "$C/rev8b_b/bf16_context_fma_pipeline_lane5_rev8b_b_candidate.sv"
  "$C/rev8b_b/bf16_context_lane_cluster16_rev8b_b_candidate.sv"
  "$C/rev8b_b/bf16_cluster_flags_glue32_rev8b_b_candidate.sv"
  "$C/rev8b_b/bf16_context_front_control5_rev8b_b_candidate.sv"
  "$C/rev8b_b/bf16_front_to_cluster_broadcast32_rev8b_b_candidate.sv"
  "$C/rev8b_b/bf16_outer_product_context_array_rev8b_b_candidate.sv"
  "$ROOT/rtl/sfu/bf16_silu_mul_lut_lane.sv"
  "$ROOT/rtl/sfu/bf16_silu_mul_lut_array.sv"
  "$ROOT/tb/tb_qwen2_q1024_layer0_tail_rtl.sv"
)
run 600s "$VERILATOR" --binary --threads 4 --timing -Wall -I"$ROOT/rtl/sfu" \
  -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL -Wno-WIDTH \
  -Wno-SYNCASYNCNET -j 8 -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" \
  --top-module tb_qwen2_q1024_layer0_tail_rtl --Mdir "$OUT/obj" -o tb "${S[@]}" \
  >"$OUT/build.log" 2>&1
run 600s "$OUT/obj/tb" | tee "$OUT/tb.log"
run 600s python3 "$ROOT/scripts/collect_qwen2_q1024_layer0_tail_rtl.py"
