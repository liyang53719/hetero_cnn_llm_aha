#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);MODEL=${MODEL:-$ROOT/work/models/qwen2_1p5b_instruct_ba1cf184};OUT=${OUT:-$ROOT/work/results/l5_qwen2_contiguous_groups};R=$ROOT/scripts/run_memory_capped.sh;mkdir -p "$OUT"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" timeout --foreground --signal=INT --kill-after=30s 600s python3 "$ROOT/scripts/run_qwen2_contiguous_groups_reference.py" --model "$MODEL" --sequence 1024 --output "$OUT/reference_result.json"|tee "$OUT/reference.log"
grep -q '"status": "PASS_7_CONTIGUOUS_REFERENCE_GROUPS"' "$OUT/reference.log"
