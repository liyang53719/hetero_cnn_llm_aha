#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd)
cd "$ROOT"
OUT=work/results/matrix_writeback_precision
mkdir -p "$OUT"
run(){ MIN_AVAILABLE_KIB=10485760 bash scripts/run_memory_capped.sh timeout 600 "$@"; }
run iverilog -g2012 -s tb_matrix_writeback_precision -o "$OUT/test" \
 rtl/integration/qwen2_shared_l2_matrix_tile16_payload.sv tb/tb_matrix_writeback_precision.sv > "$OUT/build.log" 2>&1
run vvp "$OUT/test" | tee "$OUT/test.log"
rg -q 'MATRIX_WRITEBACK_PRECISION_PASS cases=10 checked=15360' "$OUT/test.log"
