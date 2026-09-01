#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
IDMA=${IDMA_ROOT:-$ROOT/work/upstream/idma}
VD=$IDMA/target/sim/vcs
OUT=${OUT:-$ROOT/work/results/qwen2_rope_token01_payload}
RUN=$ROOT/scripts/run_memory_capped.sh
mkdir -p "$OUT"
taskset -c 8-23 python3 "$ROOT/scripts/generate_qwen2_rope_base_coeff_rtl.py" | tee "$OUT/base.log"
taskset -c 8-23 python3 "$ROOT/scripts/generate_qwen2_rope_token01_vectors.py" | tee "$OUT/vectors.log"
cd "$VD"
run(){ local limit=$1;shift;MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$RUN" timeout --foreground --signal=INT --kill-after=30s "$limit" taskset -c 8-23 "$@";}
S=("$ROOT/work/generated/l5_all_primitives/HeteroAllPrimitives.sv" "$ROOT/rtl/sfu/fp32_rope_pair.sv" "$ROOT/rtl/sfu/qwen2_rope_base_coeff64.sv" "$ROOT/rtl/sfu/qwen2_rope_base_coeff_q46.sv" "$ROOT/rtl/integration/qwen2_shared_l2_rope_payload.sv" "$ROOT/tb/tb_qwen2_rope_token01_payload.sv")
run 600s vlogan -sverilog -full64 -timescale=1ns/1ps +define+SYNTHESIS +incdir+"$ROOT" "${S[@]}" >"$OUT/vlogan.log" 2>&1
run 600s vcs -full64 -top tb_qwen2_rope_token01_payload -o simv_rope_token01 >"$OUT/vcs.log" 2>&1
cd "$ROOT"
run 600s "$VD/simv_rope_token01" | tee "$OUT/tb.log"
grep -q 'QWEN2_ROPE_TOKEN01_PAYLOAD_PASS runs=4' "$OUT/tb.log"
