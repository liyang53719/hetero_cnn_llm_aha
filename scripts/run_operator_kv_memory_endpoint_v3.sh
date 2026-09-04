#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);OUT=$ROOT/work/results/operator_kv_memory_endpoint_v3;R=$ROOT/scripts/run_memory_capped.sh;V=$ROOT/work/toolchain/conda/bin/verilator;mkdir -p "$OUT"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" timeout --foreground --signal=INT --kill-after=30s 600s "$V" --binary --threads 4 --timing -Wall -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL -Wno-UNOPTTHREADS -Wno-WIDTH -Wno-SYNCASYNCNET -j 4 -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" --top-module tb_operator_kv_memory_endpoint_v3 --Mdir "$OUT/obj" -o tb "$ROOT/rtl/kv/kv_ddr_pte_resolver_v3.sv" "$ROOT/rtl/integration/operator_kv_memory_endpoint_v3.sv" "$ROOT/tb/tb_operator_kv_memory_endpoint_v3.sv" >"$OUT/build.log" 2>&1
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" timeout --foreground --signal=INT --kill-after=30s 600s "$OUT/obj/tb"|tee "$OUT/test.log"
grep -q 'OPERATOR_KV_MEMORY_ENDPOINT_V3_PASS successful=101 errors=2 q1024_pages=64' "$OUT/test.log"
