#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd)
cd "$ROOT"
OUT=work/results/projection_precision_decode
mkdir -p "$OUT"
run(){ MIN_AVAILABLE_KIB=10485760 bash scripts/run_memory_capped.sh timeout 600 "$@"; }
for mode in 0 1;do
 run iverilog -g2012 -Ptb_projection_precision_decode.ENABLE="$mode" -s tb_projection_precision_decode \
  -o "$OUT/test$mode" rtl/integration/qwen2_projection_descriptor_context.sv tb/tb_projection_precision_decode.sv
 run vvp "$OUT/test$mode" | tee "$OUT/test$mode.log"
 rg -q "PROJECTION_PRECISION_DECODE_PASS enable=$mode cases=8" "$OUT/test$mode.log"
done
