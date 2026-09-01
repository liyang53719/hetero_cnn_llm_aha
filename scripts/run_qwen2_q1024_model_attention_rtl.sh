#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT=${OUT:-$ROOT/work/results/qwen2_q1024_model_attention_rtl}
BUILD=${BUILD:-$ROOT/work/results/l5_q1024_attention_sampled}
RUN=$ROOT/scripts/run_memory_capped.sh
mkdir -p "$OUT"

if [[ ! -x "$BUILD/obj/tb" ]]; then
  MODE=sampled1024a OUT="$BUILD" "$ROOT/scripts/run_l5_q128_attention_integrated_e2.sh"
fi
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$RUN" \
  timeout --foreground --signal=INT --kill-after=30s 600s \
  taskset -c 8-23 python3 "$ROOT/scripts/generate_qwen2_q1024_model_attention_rtl_vectors.py" \
  | tee "$OUT/vector_generation.log"
for shard in 0 1; do
  MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$RUN" \
    timeout --foreground --signal=INT --kill-after=30s 600s \
    taskset -c 8-23 "$BUILD/obj/tb" +VECTORS="$OUT/vectors" +SAMPLED_1024 +SHARD="$shard" \
    | tee "$OUT/tb_shard${shard}.log"
done
taskset -c 8-23 python3 "$ROOT/scripts/collect_qwen2_q1024_model_attention_rtl.py"
