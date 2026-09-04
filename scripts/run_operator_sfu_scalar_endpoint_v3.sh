#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);OUT=$ROOT/work/results/operator_sfu_scalar_endpoint_v3;R=$ROOT/scripts/run_memory_capped.sh;V=$ROOT/work/toolchain/conda/bin/verilator;mkdir -p "$OUT"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" timeout --foreground --signal=INT --kill-after=30s 600s "$V" --binary --threads 4 --timing -Wall -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL -Wno-UNOPTTHREADS -Wno-WIDTH -j 4 -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" --top-module tb_operator_sfu_scalar_endpoint_v3 --Mdir "$OUT/obj" -o tb "$ROOT/work/generated/l5_all_primitives/HeteroAllPrimitives.sv" "$ROOT/rtl/sfu/fp32_rsqrt_nr2.sv" "$ROOT/rtl/sfu/fp32_reciprocal_nr2.sv" "$ROOT/rtl/sfu/fp32_exp2_pwl_pipe.sv" "$ROOT/rtl/integration/operator_sfu_scalar_endpoint_v3.sv" "$ROOT/tb/tb_operator_sfu_scalar_endpoint_v3.sv" >"$OUT/build.log" 2>&1
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" timeout --foreground --signal=INT --kill-after=30s 600s "$OUT/obj/tb"|tee "$OUT/test.log"
grep -q 'OPERATOR_SFU_SCALAR_ENDPOINT_V3_PASS opcodes=3' "$OUT/test.log"
