#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd)
cd "$ROOT"
OUT=work/results/group8_output_precision
mkdir -p "$OUT"
run(){ MIN_AVAILABLE_KIB=10485760 bash scripts/run_memory_capped.sh timeout 600 "$@"; }
run iverilog -g2012 -s tb_group8_output_precision -o "$OUT/test" \
 rtl/integration/qwen2_projection_descriptor_context.sv rtl/integration/qwen2_norm_tile16_loader.sv \
 rtl/integration/bf16_tile_transpose_stager.sv rtl/integration/qwen2_shared_l2_matrix_tile16_payload.sv \
 rtl/integration/qwen2_projection_q1024_group8_controller.sv tb/tb_group8_output_precision.sv > "$OUT/build.log" 2>&1
run vvp "$OUT/test" | tee "$OUT/test.log"
rg -q 'GROUP8_OUTPUT_PRECISION_CONTROL_PASS cases=4 checked=11264 numerical_matrix_mocked=1' "$OUT/test.log"
