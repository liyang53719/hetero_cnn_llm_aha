#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd)
cd "$ROOT"
OUT=work/results/residual_l2_tile_control
mkdir -p "$OUT"
run(){ MIN_AVAILABLE_KIB=10485760 bash scripts/run_memory_capped.sh timeout 600 "$@"; }
run iverilog -Wall -g2012 -s tb_residual_l2_tile_control -o "$OUT/test" \
 rtl/integration/bf16_residual_gearbox.sv rtl/integration/residual_l2_stream_reader.sv rtl/integration/residual_l2_stream_writer.sv \
 rtl/sfu/fp32_residual_stream.sv rtl/integration/residual_l2_tile.sv tb/tb_residual_l2_tile_control.sv > "$OUT/build.log" 2>&1
if rg -q 'implicit definition' "$OUT/build.log";then exit 1;fi
run vvp "$OUT/test" | tee "$OUT/test.log"
rg -q 'RESIDUAL_L2_TILE_CONTROL_PASS cases=8' "$OUT/test.log"
