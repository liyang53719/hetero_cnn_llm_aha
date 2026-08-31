#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
MODEL=${MODEL:-$ROOT/work/models/qwen2_1p5b_instruct_ba1cf184}
OUT=${OUT:-$ROOT/work/results/l5_qwen2_four_layer_reference}
R=$ROOT/scripts/run_memory_capped.sh
mkdir -p "$OUT"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" \
  timeout --foreground --signal=INT --kill-after=30s 600s \
  python3 "$ROOT/scripts/run_qwen2_four_layer_reference.py" \
  --model "$MODEL" --sequence 1024 --output "$OUT/result.json" \
  --vectors "$OUT/vectors" \
  --cross-vectors "$OUT/cross_vectors" \
  | tee "$OUT/run.log"
grep -q '"status": "PASS_REFERENCE"' "$OUT/run.log"
