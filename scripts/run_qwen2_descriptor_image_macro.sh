#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd)
OUT=${OUT:-$ROOT/work/results/qwen2_descriptor_image_macro}
MACRO=${MACRO:-$ROOT/work/generated/l10_sram/l2_sp_6144x128wm_base_0p8v_tt25/l2sp6144x128wm.v}
R=$ROOT/scripts/run_memory_capped.sh
mkdir -p "$OUT"
taskset -c 8-23 python3 "$ROOT/scripts/generate_qwen2_descriptor_macro_vectors.py" \
  --packed-records "$ROOT/work/generated/qwen2_q1024_descriptor_image/packed_records.jsonl" --out "$OUT"
run(){ local limit=$1;shift;MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" \
  timeout --foreground --signal=INT --kill-after=30s "$limit" "$@";}
run 600s iverilog -g2012 -DARM_DISABLE_EMA_CHECK -s tb_qwen2_descriptor_image_macro \
  -o "$OUT/tb" "$MACRO" "$ROOT/rtl/memory/l2_sp6144x128_macro_wrapper.sv" \
  "$ROOT/rtl/memory/l2_512b_macro_bank_group.sv" "$ROOT/rtl/fabric/shared_l2_macro_fabric.sv" \
  "$ROOT/rtl/fabric/shared_l2_descriptor_port.sv" "$ROOT/rtl/fabric/shared_l2_macro_descriptor_fabric.sv" \
  "$ROOT/tb/tb_qwen2_descriptor_image_macro.sv" >"$OUT/build.log" 2>&1
cd "$ROOT";run 600s vvp "$OUT/tb"|tee "$OUT/tb.log"
grep -q 'QWEN2_DESCRIPTOR_IMAGE_MACRO_SAMPLE_PASS formal_records=6188 sampled_beats=4 descriptor_bytes=164544' "$OUT/tb.log"
