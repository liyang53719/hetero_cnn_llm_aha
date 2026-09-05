#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd)
cd "$ROOT"
OUT=work/results/residual_l2_writer
mkdir -p "$OUT"
run(){ MIN_AVAILABLE_KIB=10485760 bash scripts/run_memory_capped.sh timeout 600 "$@"; }
run iverilog -Wall -g2012 -s tb_residual_l2_stream_writer -o "$OUT/test" rtl/integration/residual_l2_stream_writer.sv tb/tb_residual_l2_stream_writer.sv > "$OUT/build.log" 2>&1
run vvp "$OUT/test" | tee "$OUT/test.log"
rg -q 'RESIDUAL_L2_WRITER_PASS data_cases=8 protocol_errors=4 range_errors=4' "$OUT/test.log"
