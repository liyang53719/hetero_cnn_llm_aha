#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);OUT=$ROOT/work/results/l5_exp2;mkdir -p "$OUT";R=$ROOT/scripts/run_memory_capped.sh;V=$ROOT/work/toolchain/conda/bin/verilator;PY=$ROOT/work/toolchain/cnn_py312/bin/python
"$ROOT/scripts/generate_fp32_primitives.sh";taskset -c 8-23 "$PY" "$ROOT/scripts/generate_exp2_pwl_coeffs.py" --svh "$ROOT/rtl/sfu/fp32_exp2_coeffs.svh" --json "$ROOT/config/fp32_exp2_pwl_coeffs.json"
taskset -c 8-23 "$PY" "$ROOT/scripts/generate_exp2_pwl_vectors.py" --coeff-json "$ROOT/config/fp32_exp2_pwl_coeffs.json" --output "$OUT/vectors.memh" --manifest "$OUT/vectors.json"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" "$V" --lint-only --timing -Wall -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL --top-module tb_fp32_exp2_pwl "$ROOT/work/generated/l5_fp32_primitives/HeteroFP32Primitives.sv" "$ROOT/rtl/sfu/fp32_exp2_pwl.sv" "$ROOT/tb/tb_fp32_exp2_pwl.sv" >"$OUT/lint.log" 2>&1
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" "$V" --binary --timing -Wall -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL -j 8 -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" --top-module tb_fp32_exp2_pwl --Mdir "$OUT/obj" -o tb "$ROOT/work/generated/l5_fp32_primitives/HeteroFP32Primitives.sv" "$ROOT/rtl/sfu/fp32_exp2_pwl.sv" "$ROOT/tb/tb_fp32_exp2_pwl.sv" >"$OUT/build.log" 2>&1
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" "$OUT/obj/tb"|tee "$OUT/tb.log";grep -q 'FP32_EXP2_PWL_PASS vectors=10000' "$OUT/tb.log";echo L5_EXP2_PWL_GATE_PASS
