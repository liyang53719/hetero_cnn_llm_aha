#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT="$ROOT/work/results/l5_block128_merge"
R="$ROOT/scripts/run_memory_capped.sh"
V="$ROOT/work/toolchain/conda/bin/verilator"
PY="$ROOT/work/toolchain/cnn_py312/bin/python"
mkdir -p "$OUT"

taskset -c 8-23 env PYTHONPATH="$ROOT/src" "$PY" \
  "$ROOT/scripts/generate_block128_vectors.py" >"$OUT/vector_generation.log"

SOURCES=(
  "$ROOT/work/generated/l5_all_primitives/HeteroAllPrimitives.sv"
  "$ROOT/rtl/sfu/fp32_exp2_pwl_rawpipe.sv"
  "$ROOT/rtl/sfu/fp32_mlo_merge_coeff_rawpipe.sv"
  "$ROOT/rtl/sfu/fp32_mlo_merge_beat_rawpipe.sv"
  "$ROOT/rtl/sfu/fp32_mlo_summary_merge_stream_rawpipe.sv"
  "$ROOT/rtl/sfu/fp32_mlo_summary_merge_stream.sv"
  "$ROOT/tb/tb_fp32_mlo_summary_merge_stream.sv"
)

MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" "$V" \
  --binary --timing -Wall -Wno-DECLFILENAME -Wno-TIMESCALEMOD \
  -Wno-UNUSEDSIGNAL -Wno-PINCONNECTEMPTY -Wno-PINMISSING \
  -j 8 -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" \
  --top-module tb_fp32_mlo_summary_merge_stream \
  --Mdir "$OUT/obj" -o tb "${SOURCES[@]}" >"$OUT/build.log" 2>&1

cd "$ROOT"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" \
  "$OUT/obj/tb" | tee "$OUT/tb.log"
grep -q 'BLOCK128_MLO_VECTOR_PASS cases=132 stream_beats=32' "$OUT/tb.log"
echo L5_BLOCK128_MERGE_E1_PASS
