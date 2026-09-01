#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);OUT=${OUT:-$ROOT/work/results/qwen2_tile_dma_plan};mkdir -p "$OUT"
taskset -c 8-23 timeout --foreground --signal=INT --kill-after=10s 60s iverilog -g2012 -s tb_qwen2_tile_dma_plan -o "$OUT/tb" "$ROOT/rtl/integration/qwen2_tile_dma_plan.sv" "$ROOT/tb/tb_qwen2_tile_dma_plan.sv"
cd "$ROOT";taskset -c 8-23 timeout --foreground --signal=INT --kill-after=10s 60s vvp "$OUT/tb"|tee "$OUT/tb.log"
grep -q 'QWEN2_TILE_DMA_PLAN_PASS requests=4' "$OUT/tb.log"
