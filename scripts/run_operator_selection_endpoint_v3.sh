#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);OUT=$ROOT/work/results/operator_selection_endpoint_v3;R=$ROOT/scripts/run_memory_capped.sh;V=$ROOT/work/toolchain/conda/bin/verilator;mkdir -p "$OUT"
S=("$ROOT/rtl/selection/selection_topk_sram_v3.sv" "$ROOT/generated/operator_primitives_v3/primitives/moe_route_dispatch.sv" "$ROOT/generated/operator_primitives_v3/primitives/block_pool_address.sv" "$ROOT/generated/operator_primitives_v3/primitives/mtp_verify.sv" "$ROOT/rtl/integration/operator_selection_endpoint_v3.sv" "$ROOT/tb/tb_operator_selection_endpoint_v3.sv")
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" timeout --foreground --signal=INT --kill-after=30s 600s "$V" --binary --threads 4 --timing -Wall -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL -Wno-UNOPTTHREADS -Wno-WIDTH -Wno-SYNCASYNCNET -j 4 -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" --top-module tb_operator_selection_endpoint_v3 --Mdir "$OUT/obj" -o tb "${S[@]}" >"$OUT/build.log" 2>&1
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" timeout --foreground --signal=INT --kill-after=30s 600s "$OUT/obj/tb"|tee "$OUT/test.log"
grep -q 'OPERATOR_SELECTION_ENDPOINT_V3_PASS successful=100 opcodes=6 topk_external_sram=1' "$OUT/test.log"
