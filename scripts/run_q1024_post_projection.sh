#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd)
cd "$ROOT"
mkdir -p work/results/q1024_continuous
exec 9>work/results/q1024_continuous/coordinator.lock
flock 9
test "$(df --output=avail -k . | tail -1)" -gt 52428800
OUT=$ROOT/work/results/q1024_post_projection
mkdir -p "$OUT/build"
RUN=$ROOT/scripts/run_memory_capped.sh
run(){ MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G \
 bash "$RUN" timeout --signal=INT --kill-after=30s 600 "$@"; }
run python3 scripts/generate_q1024_post_projection_vectors.py | tee "$OUT/vectors.log"
GEN=$ROOT/work/generated/l5_all_primitives/HeteroAllPrimitives.sv
B=("$GEN" "$ROOT/rtl/sfu/bf16_bias_add_tile32.sv" "$ROOT/rtl/integration/qwen2_bias_descriptor_context.sv"
 "$ROOT/rtl/integration/qwen2_shared_l2_bias_payload.sv" "$ROOT/rtl/integration/qwen2_bias_tile16_controller.sv"
 "$ROOT/tb/tb_qwen2_bias_q1024_model.sv")
R=("$GEN" "$ROOT/rtl/sfu/fp32_rope_pair.sv" "$ROOT/rtl/sfu/qwen2_rope_base_coeff64.sv"
 "$ROOT/rtl/sfu/qwen2_rope_base_coeff_q46.sv" "$ROOT/rtl/integration/qwen2_rope_descriptor_context.sv"
 "$ROOT/rtl/integration/qwen2_shared_l2_rope_payload.sv" "$ROOT/rtl/integration/qwen2_rope_tile16_controller.sv"
 "$ROOT/tb/tb_qwen2_rope_q1024_model.sv")
sha256sum "${B[@]}" "${R[@]}" > "$OUT/sources.sha256"
cd "$OUT/build"
run vlogan -sverilog -full64 -timescale=1ns/1ps +define+SYNTHESIS "${B[@]}" "${R[@]:1}" > "$OUT/analyze.log" 2>&1
for kind in bias rope;do
 run vcs -full64 -top "tb_qwen2_${kind}_q1024_model" -o "simv_$kind" > "$OUT/${kind}_build.log" 2>&1
done
cd "$ROOT"
D=$ROOT/work/results/qwen2_bias_rope_q1024_repeated
for p in 0 1 2;do
 run "$OUT/build/simv_bias" +PROJECTION="$p" +COMMANDS="$D/bias_commands.memh" +RECORDS="$D/records.memh" | tee "$OUT/bias_p$p.log"
 rg -q "QWEN2_BIAS_Q1024_MODEL_PASS projection=$p" "$OUT/bias_p$p.log"
done
for p in 0 1;do
 run "$OUT/build/simv_rope" +PROJECTION="$p" +COMMANDS="$D/rope_commands.memh" +RECORDS="$D/records.memh" | tee "$OUT/rope_p$p.log"
 rg -q "QWEN2_ROPE_Q1024_MODEL_PASS projection=$p" "$OUT/rope_p$p.log"
done
sha256sum --check "$OUT/sources.sha256"
