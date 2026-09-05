#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd)
cd "$ROOT"
mkdir -p work/results/q1024_continuous
exec 9>work/results/q1024_continuous/coordinator.lock
flock 9
test "$(df --output=avail -k . | tail -1)" -gt 52428800
OUT=work/results/attention_sequencer_e2
mkdir -p "$OUT"
GEN=work/generated/l5_all_primitives/HeteroAllPrimitives.sv
test -s "$GEN"
S=("$GEN" rtl/common/rv_fifo.sv rtl/matrix/bf16_outer_product_array_glue512.sv
 rtl/matrix/candidates/rev8b_a/bf16_operand_distribution512_rev8b_a_candidate.sv)
for name in bf16_context_scheduler5 bf16_outer_product_array_control5 bf16_context_tag_pipeline5 \
 bf16_context_fma_pipeline_lane5 bf16_context_lane_cluster16 bf16_cluster_flags_glue32 \
 bf16_context_front_control5 bf16_front_to_cluster_broadcast32 bf16_outer_product_context_array; do
 S+=("rtl/matrix/candidates/rev8b_b/${name}_rev8b_b_candidate.sv")
done
S+=(rtl/attention/attention_matrix_tile_sequencer.sv rtl/attention/blocked_attention_stream_controller.sv
 rtl/attention/fp32_probability_to_bf16_hilo.sv rtl/sfu/fp32_exp2_pwl_rawpipe.sv
 rtl/attention/fp32_block32_softmax_weights.sv rtl/sfu/fp32_mlo_merge_coeff_rawpipe.sv
 rtl/sfu/fp32_mlo_merge_beat_rawpipe.sv rtl/sfu/fp32_mlo_summary_merge_stream_rawpipe.sv
 rtl/sfu/fp32_reciprocal_nr.sv rtl/sfu/fp32_vector_alu.sv tb/tb_l5_q128_attention_integrated.sv)
run(){ MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G \
 bash scripts/run_memory_capped.sh timeout --signal=INT --kill-after=30s 600 "$@"; }
sha256sum "${S[@]}" tb/attention_matrix_sequencer_adapter.svh > "$OUT/inputs.sha256"
run "${HETERO_VERILATOR:-$ROOT/work/toolchain/conda/bin/verilator}" --binary --timing --threads 4 \
 -Wno-fatal -Wno-SHORTREAL -I"$ROOT/tb" -j 4 -MAKEFLAGS 'AR=/usr/bin/ar CXX=/usr/bin/g++' \
 --top-module tb_l5_q128_attention_integrated --Mdir "$ROOT/$OUT/obj" -o tb \
 "${S[@]}" > "$OUT/build.log" 2>&1
VECTORS=work/results/l5_q128_attention_integrated/vectors
test -s "$VECTORS/q_bf16.memh"
# Continuous direct diagnostic followed by full q128 operator numerical replay.
# No vector regeneration and no claim of complete decoder / DDR performance.
run "$OUT/obj/tb" +VECTORS="$VECTORS" +DIRECT_DIAG | tee "$OUT/direct.log"
rg -q 'L5_ONE_TASK_QK_SFU_PV_PASS' "$OUT/direct.log"
run "$OUT/obj/tb" +VECTORS="$VECTORS" | tee "$OUT/q128.log"
rg -q 'L5_Q128_SINGLE_SIM_E2_PASS rows=1536 tasks=240' "$OUT/q128.log"
sha256sum --check "$OUT/inputs.sha256"
