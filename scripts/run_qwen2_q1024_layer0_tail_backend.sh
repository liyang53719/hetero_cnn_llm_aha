#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
INPUT=$ROOT/work/results/qwen2_q1024_layer0_tail_inputs
ATTENTION=$ROOT/work/results/qwen2_q1024_attention_backend
OUT=${OUT:-$ROOT/work/results/qwen2_q1024_layer0_tail_backend}
RUN=$ROOT/scripts/run_memory_capped.sh
mkdir -p "$INPUT" "$OUT"

run() {
  local limit=$1
  shift
  MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$RUN" \
    timeout --foreground --signal=INT --kill-after=30s "$limit" taskset -c 8-23 "$@"
}

run 600s python3 "$ROOT/scripts/generate_qwen2_q1024_layer0_tail_inputs.py" | tee "$OUT/input.log"
run 600s g++ -std=c++20 -O3 -march=native -fopenmp -ffp-contract=off \
  "$ROOT/src/qwen2_q1024_layer0_tail_backend.cpp" -o "$OUT/backend"
for stage in oproj gate up down; do
  run 600s env OMP_NUM_THREADS=8 OMP_PROC_BIND=true \
    "$OUT/backend" "$stage" "$INPUT" "$ATTENTION" "$OUT" | tee "$OUT/$stage.log"
done
run 600s python3 "$ROOT/scripts/collect_qwen2_q1024_layer0_tail_backend.py"
