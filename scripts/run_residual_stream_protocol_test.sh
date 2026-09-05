#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd)
cd "$ROOT"
OUT=work/results/fp32_residual_stream
mkdir -p "$OUT"
run(){ MIN_AVAILABLE_KIB=10485760 bash scripts/run_memory_capped.sh timeout 600 "$@"; }
run iverilog -g2012 -s tb_fp32_residual_stream_protocol -o "$OUT/protocol" rtl/sfu/fp32_residual_stream.sv tb/tb_fp32_residual_stream_protocol.sv
run vvp "$OUT/protocol" | tee "$OUT/protocol.log"
rg -q 'FP32_RESIDUAL_STREAM_PROTOCOL_PASS packets=100' "$OUT/protocol.log"
