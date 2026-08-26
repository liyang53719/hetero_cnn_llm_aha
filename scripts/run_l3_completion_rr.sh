#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT=${OUT:-$ROOT/work/results/l3_completion_rr}
VERILATOR=${VERILATOR:-$ROOT/work/toolchain/conda/bin/verilator}
RUN_CAPPED="$ROOT/scripts/run_memory_capped.sh"
mkdir -p "$OUT"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=8G MEMORY_MAX=10G "$RUN_CAPPED" \
  "$VERILATOR" --binary --timing -Wall -j 4 \
  -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" -GTARGET=100000 \
  --top-module tb_engine_completion_rr_arbiter --Mdir "$OUT/obj_100k" -o tb_100k \
  "$ROOT/rtl/integration/engine_completion_rr_arbiter.sv" \
  "$ROOT/tb/tb_engine_completion_rr_arbiter.sv" >"$OUT/verilator_build.log" 2>&1
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=8G MEMORY_MAX=10G "$RUN_CAPPED" \
  "$OUT/obj_100k/tb_100k" | tee "$OUT/verilator_100k.log"
grep -q "ENGINE_COMPLETION_RR_100K_PASS grants=100000" "$OUT/verilator_100k.log"
echo L3_COMPLETION_RR_GATE_PASS
