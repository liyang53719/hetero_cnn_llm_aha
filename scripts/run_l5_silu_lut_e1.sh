#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);OUT=${OUT:-$ROOT/work/results/l5_silu_lut_e1};R=$ROOT/scripts/run_memory_capped.sh;V=${VERILATOR:-$ROOT/work/toolchain/conda/bin/verilator};PY=${PYTHON:-python3};mkdir -p "$OUT"
PYTHONPATH="$ROOT/src" "$PY" "$ROOT/scripts/generate_silu_lut_vectors.py" --cases 4096 --output "$OUT/vectors.txt">"$OUT/vector_generation.log";"$ROOT/scripts/generate_all_hardfloat_primitives.sh"
SOURCES=("$ROOT/work/generated/l5_all_primitives/HeteroAllPrimitives.sv" "$ROOT/rtl/common/rv_fifo.sv" "$ROOT/rtl/sfu/bf16_silu_mul_lut_lane.sv" "$ROOT/rtl/sfu/bf16_silu_mul_lut_array.sv" "$ROOT/tb/tb_bf16_silu_mul_lut_array.sv")
for LANES in 1 2;do D="$OUT/lanes$LANES";mkdir -p "$D";MIN_AVAILABLE_KIB=4194304 MEMORY_HIGH=12G MEMORY_MAX=16G "$R" "$V" --binary --timing -Wall -I"$ROOT/rtl/sfu" -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL -Wno-WIDTHEXPAND -Wno-WIDTHTRUNC -GLANES=$LANES -j 8 --top-module tb_bf16_silu_mul_lut_array --Mdir "$D/obj" -o tb "${SOURCES[@]}">"$D/build.log" 2>&1;MIN_AVAILABLE_KIB=4194304 MEMORY_HIGH=12G MEMORY_MAX=16G "$R" "$D/obj/tb" +VECTORS="$OUT/vectors.txt"|tee "$D/tb.log";grep -q "TB_PASS LANES=$LANES cases=4096" "$D/tb.log";done
echo L5_FUSED_SILU_LUT_E1_PASS
