#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
INPUT_BASE=$ROOT/work/results/qwen2_q1024_group0_inputs
OUT_BASE=${OUT_BASE:-$ROOT/work/results/qwen2_q1024_group0_backend}
LAYER0=$ROOT/work/results/qwen2_q1024_layer0_tail_backend
RUN=$ROOT/scripts/run_memory_capped.sh
BIN=$OUT_BASE/generic_layer_backend
mkdir -p "$OUT_BASE"
run() { local limit=$1; shift; MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$RUN" timeout --foreground --signal=INT --kill-after=30s "$limit" taskset -c 8-23 "$@"; }

run 600s python3 "$ROOT/scripts/generate_qwen2_q1024_group0_inputs.py" | tee "$OUT_BASE/input.log"
run 600s g++ -std=c++20 -O3 -march=native -fopenmp -ffp-contract=off -Wno-return-type \
  "$ROOT/src/qwen2_q1024_generic_layer_backend.cpp" -o "$BIN"
for layer in 1 2 3; do
  INPUT=$INPUT_BASE/layer$layer
  OUTPUT=$OUT_BASE/layer$layer
  if [[ $layer -eq 1 ]]; then PREDECESSOR=$LAYER0; else PREDECESSOR=$OUT_BASE/layer$((layer-1)); fi
  mkdir -p "$OUTPUT"
  for stage in pre attention oproj gate up down; do
    run 600s env OMP_NUM_THREADS=8 OMP_PROC_BIND=true \
      "$BIN" "$stage" "$layer" "$INPUT" "$PREDECESSOR" "$OUTPUT" | tee "$OUTPUT/$stage.log"
  done
done
run 600s python3 "$ROOT/scripts/collect_qwen2_q1024_group0_backend.py"
