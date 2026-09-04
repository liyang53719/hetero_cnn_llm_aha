#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);OUT=$ROOT/work/results/operator_sfu_gate_endpoint_v3;R=$ROOT/scripts/run_memory_capped.sh;V=$ROOT/work/toolchain/conda/bin/verilator;mkdir -p "$OUT"
S=("$ROOT/work/generated/l5_all_primitives/HeteroAllPrimitives.sv" "$ROOT/rtl/common/rv_fifo.sv" "$ROOT/rtl/sfu/bf16_silu_mul_lut_lane.sv" "$ROOT/rtl/sfu/bf16_silu_mul_lut_array8_fixed.sv" "$ROOT/rtl/integration/operator_sfu_gate_endpoint_v3.sv" "$ROOT/tb/tb_operator_sfu_gate_endpoint_v3.sv")
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" timeout --foreground --signal=INT --kill-after=30s 600s "$V" --binary --threads 4 --timing -Wall -I"$ROOT/rtl/sfu" -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL -Wno-UNOPTTHREADS -Wno-WIDTH -Wno-SYNCASYNCNET -j 4 -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" --top-module tb_operator_sfu_gate_endpoint_v3 --Mdir "$OUT/obj" -o tb "${S[@]}" >"$OUT/build.log" 2>&1
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" timeout --foreground --signal=INT --kill-after=30s 600s "$OUT/obj/tb"|tee "$OUT/test.log"
grep -q 'OPERATOR_SFU_GATE_ENDPOINT_V3_PASS transactions=100 lane_pairs=800 lanes=8' "$OUT/test.log"
