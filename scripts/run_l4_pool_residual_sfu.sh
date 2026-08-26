#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);OUT=$ROOT/work/results/l4_pool_residual;mkdir -p "$OUT";R=$ROOT/scripts/run_memory_capped.sh;V=$ROOT/work/toolchain/conda/bin/verilator
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" "$V" --lint-only --timing -Wall --top-module tb_int8_pool_residual_sfu "$ROOT/rtl/sfu/int8_pool_residual_sfu.sv" "$ROOT/tb/tb_int8_pool_residual_sfu.sv" >"$OUT/lint.log" 2>&1
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" "$V" --binary --timing -Wall -j 8 -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" -GTARGET=100000 --top-module tb_int8_pool_residual_sfu --Mdir "$OUT/obj_100k" -o tb_100k "$ROOT/rtl/sfu/int8_pool_residual_sfu.sv" "$ROOT/tb/tb_int8_pool_residual_sfu.sv" >"$OUT/build.log" 2>&1
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" "$OUT/obj_100k/tb_100k"|tee "$OUT/tb.log"
grep -q 'INT8_POOL_RESIDUAL_SFU_100K_PASS operations=100000' "$OUT/tb.log"
echo L4_POOL_RESIDUAL_SFU_RTL_GATE_PASS
