#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
BASE=${BASE:-$ROOT/work/results/qwen2_q1024_group0_attention_rtl}
BUILD=$BASE/build
RUN=$ROOT/scripts/run_memory_capped.sh
mkdir -p "$BASE"
run() { local limit=$1; shift; MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$RUN" timeout --foreground --signal=INT --kill-after=30s "$limit" taskset -c 8-23 "$@"; }

BUILD_ONLY=1 MODE=sampled1024a OUT="$BUILD" "$ROOT/scripts/run_l5_q128_attention_integrated_e2.sh"
BIN=$BUILD/obj/tb
for layer in 1 2 3; do
  OUT=$BASE/layer$layer
  mkdir -p "$OUT"
  run 600s python3 "$ROOT/scripts/generate_qwen2_q1024_model_attention_rtl_vectors.py" \
    --layer "$layer" --out "$OUT/vectors" | tee "$OUT/vector_generation.log"
  pids=()
  for shard in 0 1; do
    (MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$RUN" \
      timeout --foreground --signal=INT --kill-after=30s 600s taskset -c 8-23 \
      "$BIN" +VECTORS="$OUT/vectors" +SAMPLED_1024 +SHARD="$shard" \
      >"$OUT/tb_shard${shard}.log" 2>&1) &
    pids+=("$!")
  done
  for pid in "${pids[@]}"; do wait "$pid"; done
  grep -q 'L5_Q1024_REVIEWED_SHARD_PASS shard=0 compared_rows=960 tasks=306' "$OUT/tb_shard0.log"
  grep -q 'L5_Q1024_REVIEWED_SHARD_PASS shard=1 compared_rows=480 tasks=756' "$OUT/tb_shard1.log"
  tail -n 6 "$OUT/tb_shard0.log"
  tail -n 6 "$OUT/tb_shard1.log"
done
run 600s python3 "$ROOT/scripts/collect_qwen2_q1024_group0_attention_rtl.py"
