#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);OUT=$ROOT/work/results/l5_q384_silu_product;R=$ROOT/scripts/run_memory_capped.sh;V=$ROOT/work/toolchain/conda/bin/verilator;PY=$ROOT/work/toolchain/cnn_py312/bin/python;mkdir -p "$OUT/vectors"
taskset -c 8-23 "$PY" "$ROOT/scripts/generate_l5_q128_silu_product_vectors.py" --workload 384 --base "$ROOT/work/results/l5_q384_gate_up" --out "$OUT/vectors"
S=("$ROOT/work/generated/l5_all_primitives/HeteroAllPrimitives.sv" "$ROOT/rtl/sfu/fp32_exp2_pwl.sv" "$ROOT/rtl/sfu/fp32_reciprocal_nr.sv" "$ROOT/rtl/sfu/fp32_silu.sv" "$ROOT/rtl/sfu/fp32_vector_alu.sv" "$ROOT/tb/tb_l5_q128_silu_product.sv")
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" "$V" --lint-only --timing -Wall -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL --top-module tb_l5_q128_silu_product "${S[@]}" >"$OUT/lint.log" 2>&1
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" "$V" --binary --timing -Wall -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL -j 8 -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" --top-module tb_l5_q128_silu_product --Mdir "$OUT/obj" -o tb "${S[@]}" >"$OUT/build.log" 2>&1
cd "$ROOT"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" "$OUT/obj/tb" +WORKLOAD=384 | tee "$OUT/tb.log"
grep -q 'L5_Q_PREFILL_SILU_PRODUCT_PASS workload=384 lanes=3440640 product_chunks=215040' "$OUT/tb.log"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" "$OUT/obj/tb" +WORKLOAD=128 | tee "$OUT/q128_compat.log"
grep -q 'L5_Q_PREFILL_SILU_PRODUCT_PASS workload=128 lanes=1146880 product_chunks=71680' "$OUT/q128_compat.log"
echo L5_Q384_SILU_PRODUCT_GATE_PASS
