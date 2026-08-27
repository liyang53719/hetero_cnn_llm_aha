#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);OUT=${OUT:-$ROOT/work/results/l5_fp32_pipelines};R=$ROOT/scripts/run_memory_capped.sh;V=${VERILATOR:-$ROOT/work/toolchain/conda/bin/verilator};PY=${PYTHON:-$ROOT/work/toolchain/cnn_py312/bin/python};mkdir -p "$OUT"
taskset -c 8-23 env PYTHONPATH="$ROOT/src" "$PY" "$ROOT/scripts/generate_fp32_pipeline_vectors.py">"$OUT/vector_generation.log";"$ROOT/scripts/generate_all_hardfloat_primitives.sh"
SOURCES=("$ROOT/work/generated/l5_all_primitives/HeteroAllPrimitives.sv" "$ROOT/tb/tb_fp32_pipelines.sv")
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" "$V" --binary --timing -Wall -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL -Wno-PINCONNECTEMPTY -Wno-PINMISSING -j 8 -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" --top-module tb_fp32_pipelines --Mdir "$OUT/obj" -o tb "${SOURCES[@]}">"$OUT/build.log" 2>&1
cd "$ROOT";MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" "$OUT/obj/tb"|tee "$OUT/tb.log";grep -q 'FP32_PIPELINE_PASS mul=512 add=512' "$OUT/tb.log";echo L5_FP32_RAW_ROUND_PIPELINES_E1_PASS
