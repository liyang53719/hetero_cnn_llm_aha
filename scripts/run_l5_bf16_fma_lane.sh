#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);OUT=$ROOT/work/results/l5_bf16_fma;mkdir -p "$OUT";R=$ROOT/scripts/run_memory_capped.sh;V=$ROOT/work/toolchain/conda/bin/verilator
"$ROOT/scripts/generate_bf16_fma_lane.sh"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" "$ROOT/work/toolchain/cnn_py312/bin/python" "$ROOT/scripts/generate_bf16_fma_vectors.py" --output "$OUT/vectors.memh" --manifest "$OUT/vectors.json"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" "$V" --lint-only --timing -Wall -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL --top-module tb_bf16_fma_lane "$ROOT/work/generated/l5_bf16_fma/HeteroBF16FmaLane.sv" "$ROOT/tb/tb_bf16_fma_lane.sv" >"$OUT/lint.log" 2>&1
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" "$V" --binary --timing -Wall -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL -j 8 -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" --top-module tb_bf16_fma_lane --Mdir "$OUT/obj" -o tb "$ROOT/work/generated/l5_bf16_fma/HeteroBF16FmaLane.sv" "$ROOT/tb/tb_bf16_fma_lane.sv" >"$OUT/build.log" 2>&1
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" "$OUT/obj/tb"|tee "$OUT/tb.log"
grep -q 'BF16_FP32_FMA_LANE_PASS vectors=10000' "$OUT/tb.log";echo L5_BF16_FMA_LANE_GATE_PASS
