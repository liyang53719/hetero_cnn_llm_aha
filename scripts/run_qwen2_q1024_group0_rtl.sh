#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
BASE=${BASE:-$ROOT/work/results/qwen2_q1024_group0_rtl}
RUN=$ROOT/scripts/run_memory_capped.sh
mkdir -p "$BASE"
run() { local limit=$1; shift; MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$RUN" timeout --foreground --signal=INT --kill-after=30s "$limit" taskset -c 8-23 "$@"; }

"$ROOT/scripts/run_qwen2_q1024_layer0_tail_rtl.sh"
BIN=$ROOT/work/results/qwen2_q1024_layer0_tail_rtl/obj/tb
for layer in 1 2 3; do
  OUT=$BASE/layer$layer
  mkdir -p "$OUT"
  run 600s python3 "$ROOT/scripts/generate_qwen2_q1024_layer0_tail_rtl_vectors.py" \
    --layer "$layer" --out "$OUT/vectors" | tee "$OUT/vector_generation.log"
  run 600s "$BIN" +LAYER="$layer" +VECTOR_DIR="$OUT/vectors" | tee "$OUT/tb.log"
done
run 600s python3 "$ROOT/scripts/collect_qwen2_q1024_group0_rtl.py"
