#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);OUT=$ROOT/work/results/l5_rope;mkdir -p "$OUT";R=$ROOT/scripts/run_memory_capped.sh;V=$ROOT/work/toolchain/conda/bin/verilator
"$ROOT/scripts/generate_fp32_primitives.sh";taskset -c 8-23 "$ROOT/work/toolchain/cnn_py312/bin/python" "$ROOT/scripts/generate_fp32_rope_vectors.py" --output "$OUT/vectors.memh"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" "$V" --lint-only --timing -Wall -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL --top-module tb_fp32_rope_pair "$ROOT/work/generated/l5_fp32_primitives/HeteroFP32Primitives.sv" "$ROOT/rtl/sfu/fp32_rope_pair.sv" "$ROOT/tb/tb_fp32_rope_pair.sv" >"$OUT/lint.log" 2>&1
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" "$V" --binary --timing -Wall -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL -j 8 -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" --top-module tb_fp32_rope_pair --Mdir "$OUT/obj" -o tb "$ROOT/work/generated/l5_fp32_primitives/HeteroFP32Primitives.sv" "$ROOT/rtl/sfu/fp32_rope_pair.sv" "$ROOT/tb/tb_fp32_rope_pair.sv" >"$OUT/build.log" 2>&1
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" "$OUT/obj/tb"|tee "$OUT/tb.log";grep -q 'FP32_ROPE_PAIR_PASS vectors=10000' "$OUT/tb.log";echo L5_ROPE_GATE_PASS
