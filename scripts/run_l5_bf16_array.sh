#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);OUT=$ROOT/work/results/l5_bf16_array;mkdir -p "$OUT";R=$ROOT/scripts/run_memory_capped.sh;V=$ROOT/work/toolchain/conda/bin/verilator;PY=$ROOT/work/toolchain/cnn_py312/bin/python;LANE=$ROOT/work/generated/l5_bf16_fma/HeteroBF16FmaLane.sv
"$ROOT/scripts/generate_bf16_fma_lane.sh"
run_case(){ local rows=$1 cols=$2 tag=$3;taskset -c 8-25 "$PY" "$ROOT/scripts/generate_bf16_array_expected.py" --rows "$rows" --cols "$cols" --steps 4 --output "$OUT/expected.memh"
 MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=8G MEMORY_MAX=10G "$R" "$V" --lint-only --timing -Wall -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL -GROWS="$rows" -GCOLS="$cols" --top-module tb_bf16_outer_product_array "$LANE" "$ROOT/rtl/matrix/bf16_outer_product_array.sv" "$ROOT/tb/tb_bf16_outer_product_array.sv" >"$OUT/lint_$tag.log" 2>&1
 MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=8G MEMORY_MAX=10G "$R" "$V" --binary --timing -Wall -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL -j 4 -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" -GROWS="$rows" -GCOLS="$cols" --top-module tb_bf16_outer_product_array --Mdir "$OUT/obj_$tag" -o tb "$LANE" "$ROOT/rtl/matrix/bf16_outer_product_array.sv" "$ROOT/tb/tb_bf16_outer_product_array.sv" >"$OUT/build_$tag.log" 2>&1
 MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=8G MEMORY_MAX=10G "$R" "$OUT/obj_$tag/tb"|tee "$OUT/tb_$tag.log";}
run_case 2 2 2x2
run_case 16 32 16x32
grep -q 'rows=16 cols=32 steps=4 macs_per_step=512.*burst=8 interval=1' "$OUT/tb_16x32.log"
echo L5_BF16_ARRAY_GATE_PASS
