#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
test "$(df --output=avail -k . | tail -1)" -gt 52428800
OUT=work/results/bf16_tile_transpose
mkdir -p "$OUT"
MIN_AVAILABLE_KIB=10485760 bash scripts/run_memory_capped.sh timeout 600 \
  iverilog -g2012 -s tb_bf16_tile_transpose_stager -o "$OUT/test" \
  rtl/integration/bf16_tile_transpose_stager.sv tb/tb_bf16_tile_transpose_stager.sv
MIN_AVAILABLE_KIB=10485760 bash scripts/run_memory_capped.sh timeout 600 \
  vvp "$OUT/test" | tee "$OUT/test.log"
