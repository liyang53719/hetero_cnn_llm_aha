#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);R=$ROOT/scripts/run_memory_capped.sh;V=$ROOT/work/toolchain/conda/bin/verilator;PY=$ROOT/work/toolchain/cnn_py312/bin/python
"$ROOT/scripts/generate_fp32_alu.sh";"$ROOT/scripts/generate_fp32_primitives.sh";A=$ROOT/work/results/l5_fp32_alu;mkdir -p "$A"
taskset -c 8-25 "$PY" "$ROOT/scripts/generate_fp32_alu_vectors.py" --output "$A/vectors.memh" --manifest "$A/vectors.json"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=8G MEMORY_MAX=10G "$R" "$V" --binary --timing -Wall -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL -j 4 -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" --top-module tb_fp32_alu --Mdir "$A/obj" -o tb "$ROOT/work/generated/l5_fp32_alu/HeteroFP32Alu.sv" "$ROOT/tb/tb_fp32_alu.sv" >"$A/build.log" 2>&1
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=8G MEMORY_MAX=10G "$R" "$A/obj/tb"|tee "$A/tb.log"
B=$ROOT/work/results/l5_fp32_reduce;mkdir -p "$B";taskset -c 8-25 "$PY" "$ROOT/scripts/generate_fp32_reduce_vectors.py" --output "$B/vectors.memh"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=8G MEMORY_MAX=10G "$R" "$V" --lint-only --timing -Wall -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL --top-module tb_fp32_reduce16 "$ROOT/work/generated/l5_fp32_primitives/HeteroFP32Primitives.sv" "$ROOT/rtl/sfu/fp32_reduce16.sv" "$ROOT/tb/tb_fp32_reduce16.sv" >"$B/lint.log" 2>&1
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=8G MEMORY_MAX=10G "$R" "$V" --binary --timing -Wall -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL -j 4 -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" --top-module tb_fp32_reduce16 --Mdir "$B/obj" -o tb "$ROOT/work/generated/l5_fp32_primitives/HeteroFP32Primitives.sv" "$ROOT/rtl/sfu/fp32_reduce16.sv" "$ROOT/tb/tb_fp32_reduce16.sv" >"$B/build.log" 2>&1
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=8G MEMORY_MAX=10G "$R" "$B/obj/tb"|tee "$B/tb.log"
grep -q 'FP32_HARDFLOAT_ALU_PASS vectors=10000' "$A/tb.log";grep -q 'FP32_REDUCE16_PASS vectors=10000' "$B/tb.log";echo L5_FP32_REDUCE_GATE_PASS
