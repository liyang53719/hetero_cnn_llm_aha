#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd)
OUT=${OUT:-$ROOT/work/results/descriptor_public_encoding_rtl}
mkdir -p "$OUT"
taskset -c 8-23 timeout --foreground --signal=INT --kill-after=10s 60s iverilog -g2012 \
  -s tb_descriptor_public_record_decode -o "$OUT/tb" \
  "$ROOT/rtl/integration/descriptor_public_record_decode.sv" \
  "$ROOT/tb/tb_descriptor_public_record_decode.sv"
taskset -c 8-23 timeout --foreground --signal=INT --kill-after=10s 60s vvp "$OUT/tb" | tee "$OUT/tb.log"
grep -q 'DESCRIPTOR_PUBLIC_RECORD_DECODE_PASS cases=12' "$OUT/tb.log"
