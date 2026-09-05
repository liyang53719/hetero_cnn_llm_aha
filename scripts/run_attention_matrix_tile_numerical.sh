#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
# The continuous Q replay owns this lock. Wait for completion, never rebuild
# or run a second heavy task alongside its frozen simulator.
mkdir -p work/results/q1024_continuous
exec 9>work/results/q1024_continuous/coordinator.lock
flock 9
test "$(df --output=avail -k . | tail -1)" -gt 52428800
OUT=work/results/attention_matrix_tile_numerical
mkdir -p "$OUT"
GEN=work/generated/l5_all_primitives/HeteroAllPrimitives.sv
test -s "$GEN"
sha256sum "$GEN" > "$OUT/generated_input.sha256"
S=("$GEN" rtl/common/rv_fifo.sv rtl/matrix/bf16_outer_product_array_glue512.sv
 rtl/matrix/candidates/rev8b_a/bf16_operand_distribution512_rev8b_a_candidate.sv)
for name in bf16_context_scheduler5 bf16_outer_product_array_control5 bf16_context_tag_pipeline5 \
 bf16_context_fma_pipeline_lane5 bf16_context_lane_cluster16 bf16_cluster_flags_glue32 \
 bf16_context_front_control5 bf16_front_to_cluster_broadcast32 bf16_outer_product_context_array; do
 S+=("rtl/matrix/candidates/rev8b_b/${name}_rev8b_b_candidate.sv")
done
S+=(rtl/attention/attention_matrix_tile_sequencer.sv tb/tb_attention_matrix_tile_numerical.sv)
run(){ MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G \
 bash scripts/run_memory_capped.sh timeout --signal=INT --kill-after=30s 600 "$@"; }
run "${HETERO_VERILATOR:-$ROOT/work/toolchain/conda/bin/verilator}" --binary --timing --threads 4 \
 -Wno-fatal -j 4 -MAKEFLAGS 'AR=/usr/bin/ar CXX=/usr/bin/g++' \
 --top-module tb_attention_matrix_tile_numerical --Mdir "$ROOT/$OUT/obj" -o tb \
 "${S[@]}" > "$OUT/build.log" 2>&1
run "$OUT/obj/tb" | tee "$OUT/test.log"
sha256sum --check "$OUT/generated_input.sha256"
rg -q 'ATTENTION_MATRIX_NUMERICAL_PASS comparisons=7168' "$OUT/test.log"
