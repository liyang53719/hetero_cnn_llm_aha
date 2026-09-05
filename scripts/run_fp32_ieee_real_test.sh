#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd)
cd "$ROOT"
OUT=$ROOT/work/results/fp32_ieee_real_test
mkdir -p "$OUT"
test "$(df --output=avail -k .|tail -1)" -gt 52428800
run(){ MIN_AVAILABLE_KIB=10485760 bash scripts/run_memory_capped.sh timeout 600 "$@"; }
run iverilog -g2012 -I tb/common -s tb_fp32_ieee_real -o "$OUT/iv" tb/tb_fp32_ieee_real.sv
run vvp "$OUT/iv" | tee "$OUT/iverilog.log"
run "$ROOT/work/toolchain/conda/bin/verilator" --binary --timing -j 1 \
 -MAKEFLAGS 'AR=/usr/bin/ar CXX=/usr/bin/g++' -I"$ROOT/tb/common" \
 --top-module tb_fp32_ieee_real --Mdir "$OUT/obj" -o tb tb/tb_fp32_ieee_real.sv > "$OUT/build.log" 2>&1
run "$OUT/obj/tb" | tee "$OUT/verilator.log"
rg -q 'FP32_IEEE_REAL_PASS edge_cases=15 nonzero_error_sentinels=2' "$OUT/iverilog.log"
rg -q 'FP32_IEEE_REAL_PASS edge_cases=15 nonzero_error_sentinels=2' "$OUT/verilator.log"
