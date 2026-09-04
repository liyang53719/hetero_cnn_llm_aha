#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT="$ROOT/work/results/operator_vision_endpoint_v3"
RUN="$ROOT/scripts/run_memory_capped.sh"
VERILATOR="$ROOT/work/toolchain/conda/bin/verilator"
mkdir -p "$OUT"
SOURCES=(
  "$ROOT/generated/operator_primitives_v3/primitives/mrope_section_map.sv"
  "$ROOT/generated/operator_primitives_v3/primitives/vision_window_address.sv"
  "$ROOT/generated/operator_primitives_v3/primitives/vision_patch_merge_address.sv"
  "$ROOT/generated/operator_primitives_v3/primitives/vision_bilinear_index.sv"
  "$ROOT/generated/operator_primitives_v3/primitives/ple_ngram_hash.sv"
  "$ROOT/generated/operator_primitives_v3/primitives/vision_patch3d_address.sv"
  "$ROOT/rtl/integration/operator_vision_endpoint_v3.sv"
  "$ROOT/tb/tb_operator_vision_endpoint_v3.sv"
)
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$RUN" \
  timeout --foreground --signal=INT --kill-after=30s 600s "$VERILATOR" \
  --binary --threads 4 --timing -Wall -Wno-DECLFILENAME \
  -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL -Wno-UNOPTTHREADS -Wno-WIDTH \
  -Wno-SYNCASYNCNET -Wno-MODDUP -Wno-PINCONNECTEMPTY -j 4 \
  -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" \
  --top-module tb_operator_vision_endpoint_v3 --Mdir "$OUT/obj" -o tb \
  "${SOURCES[@]}" >"$OUT/build.log" 2>&1
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$RUN" \
  timeout --foreground --signal=INT --kill-after=30s 600s "$OUT/obj/tb" \
  | tee "$OUT/test.log"
grep -q 'OPERATOR_VISION_ENDPOINT_V3_PASS successful=100 opcodes=6 generated_controllers=6' "$OUT/test.log"
