#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);OUT=$ROOT/work/results/l5_toy_block;mkdir -p "$OUT/vectors";R=$ROOT/scripts/run_memory_capped.sh;V=$ROOT/work/toolchain/conda/bin/verilator;PY=$ROOT/work/toolchain/cnn_py312/bin/python
"$ROOT/scripts/generate_all_hardfloat_primitives.sh";taskset -c 8-23 "$PY" "$ROOT/scripts/generate_l5_toy_block_vectors.py" --out "$OUT/vectors"
S=("$ROOT/work/generated/l5_all_primitives/HeteroAllPrimitives.sv" "$ROOT/rtl/matrix/bf16_outer_product_array.sv" "$ROOT/rtl/sfu/fp32_rsqrt_nr.sv" "$ROOT/rtl/sfu/fp32_rmsnorm16.sv" "$ROOT/rtl/sfu/fp32_rope_pair.sv" "$ROOT/rtl/sfu/fp32_dot4_scaled.sv" "$ROOT/rtl/sfu/fp32_exp2_pwl.sv" "$ROOT/rtl/sfu/fp32_online_softmax.sv" "$ROOT/rtl/sfu/fp32_reciprocal_nr.sv" "$ROOT/rtl/sfu/fp32_silu.sv" "$ROOT/rtl/sfu/fp32_vector_alu.sv" "$ROOT/tb/tb_l5_toy_bf16_block.sv")
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" "$V" --lint-only --timing -Wall -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL --top-module tb_l5_toy_bf16_block "${S[@]}" >"$OUT/lint.log" 2>&1
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" "$V" --binary --timing -Wall -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL -j 8 -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" --top-module tb_l5_toy_bf16_block --Mdir "$OUT/obj" -o tb "${S[@]}" >"$OUT/build.log" 2>&1
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" "$OUT/obj/tb"|tee "$OUT/tb.log";grep -q 'L5_TOY_BF16_BLOCK_PASS hidden=16' "$OUT/tb.log";echo L5_TOY_BF16_BLOCK_GATE_PASS
