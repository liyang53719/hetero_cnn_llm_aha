#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd)
cd "$ROOT"
OUT=work/results/bf16_residual_gearbox
mkdir -p "$OUT"
run(){ MIN_AVAILABLE_KIB=10485760 bash scripts/run_memory_capped.sh timeout 600 "$@"; }
run iverilog -g2012 -s tb_bf16_residual_gearbox -o "$OUT/test" rtl/integration/bf16_residual_gearbox.sv tb/tb_bf16_residual_gearbox.sv
run vvp "$OUT/test" | tee "$OUT/test.log"
rg -q 'BF16_RESIDUAL_GEARBOX_PASS input_beats=100 output_chunks=140' "$OUT/test.log"
