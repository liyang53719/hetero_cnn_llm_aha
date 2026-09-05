#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
test "$(df --output=avail -k . | tail -1)" -gt 52428800
OUT=work/results/qwen2_descriptor_tile_plan
mkdir -p "$OUT"
for TOP in tb_bf16_projection_tile_iterator tb_qwen2_descriptor_projection_tile_plan; do
 MIN_AVAILABLE_KIB=10485760 bash scripts/run_memory_capped.sh timeout 600 \
  iverilog -g2012 -s "$TOP" -o "$OUT/$TOP" \
  rtl/integration/qwen2_projection_descriptor_context.sv \
  rtl/integration/bf16_projection_tile_iterator.sv \
  rtl/integration/qwen2_descriptor_projection_tile_plan.sv "tb/$TOP.sv"
 MIN_AVAILABLE_KIB=10485760 bash scripts/run_memory_capped.sh timeout 600 \
  vvp "$OUT/$TOP" | tee "$OUT/$TOP.log"
done
