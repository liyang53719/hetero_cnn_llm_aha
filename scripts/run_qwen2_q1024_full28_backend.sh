#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
INPUTS=$ROOT/work/results/qwen2_q1024_full28_inputs
OUTPUTS=${OUTPUTS:-$ROOT/work/results/qwen2_q1024_full28_backend}
RUN=$ROOT/scripts/run_memory_capped.sh
BIN=$OUTPUTS/generic_layer_backend
mkdir -p "$INPUTS" "$OUTPUTS"
run() { local limit=$1; shift; MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$RUN" timeout --foreground --signal=INT --kill-after=30s "$limit" taskset -c 8-23 "$@"; }

run 600s python3 "$ROOT/scripts/generate_qwen2_q1024_group0_inputs.py" \
  --start-layer 0 --end-layer 27 --out "$INPUTS" | tee "$OUTPUTS/input.log"
run 600s g++ -std=c++20 -O3 -march=native -fopenmp -ffp-contract=off -Wno-return-type \
  -DQWEN2_ATTENTION_BLOCKED_RTL -DQWEN2_ATTENTION_EXP2_EXT32 \
  "$ROOT/src/qwen2_q1024_generic_layer_backend.cpp" -o "$BIN"
for layer in $(seq 0 27); do
  INPUT=$INPUTS/layer$layer
  OUTPUT=$OUTPUTS/layer$layer
  if [[ $layer -eq 0 ]]; then PREDECESSOR=$INPUTS/embedding; else PREDECESSOR=$OUTPUTS/layer$((layer-1)); fi
  mkdir -p "$OUTPUT"
  for stage in pre attention oproj gate up down; do
    run 600s env OMP_NUM_THREADS=8 OMP_PROC_BIND=true \
      "$BIN" "$stage" "$layer" "$INPUT" "$PREDECESSOR" "$OUTPUT" | tee "$OUTPUT/$stage.log"
  done
done
run 600s python3 "$ROOT/scripts/collect_qwen2_q1024_full28_backend.py"
