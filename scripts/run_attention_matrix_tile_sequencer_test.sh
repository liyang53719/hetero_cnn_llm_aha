#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
test "$(df --output=avail -k . | tail -1)" -gt 52428800
OUT=work/results/attention_matrix_tile_sequencer
mkdir -p "$OUT"
MIN_AVAILABLE_KIB=10485760 bash scripts/run_memory_capped.sh timeout 600 \
  iverilog -g2012 -s tb_attention_matrix_tile_sequencer -o "$OUT/test" \
  rtl/attention/attention_matrix_tile_sequencer.sv tb/tb_attention_matrix_tile_sequencer.sv
MIN_AVAILABLE_KIB=10485760 bash scripts/run_memory_capped.sh timeout 600 \
  vvp "$OUT/test" | tee "$OUT/test.log"
