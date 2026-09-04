#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT="$ROOT/work/results/operator_dma_endpoint_v3"
mkdir -p "$OUT"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G \
  "$ROOT/scripts/run_memory_capped.sh" timeout --foreground --signal=INT --kill-after=30s 600s \
  iverilog -g2012 -s tb_operator_dma_endpoint_v3 -o "$OUT/tb" \
  "$ROOT/rtl/integration/qwen2_tile_idma_expand.sv" \
  "$ROOT/rtl/integration/operator_dma_endpoint_v3.sv" \
  "$ROOT/tb/tb_operator_dma_endpoint_v3.sv"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G \
  "$ROOT/scripts/run_memory_capped.sh" timeout --foreground --signal=INT --kill-after=30s 600s \
  vvp "$OUT/tb" | tee "$OUT/test.log"
grep -q 'OPERATOR_DMA_ENDPOINT_V3_PASS' "$OUT/test.log"
