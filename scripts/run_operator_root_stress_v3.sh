#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
V=${VERILATOR_BIN:-$ROOT/work/toolchain/conda/bin/verilator}
RUN=$ROOT/scripts/run_memory_capped.sh
MANIFEST=$ROOT/generated/operator_primitives_v3/roots/MANIFEST.txt
OUT=$ROOT/work/results/operator_root_stress_v3
mkdir -p "$OUT"

tail -n +2 "$MANIFEST" | while IFS=, read -r top phases; do
  run="$OUT/$top";mkdir -p "$run"
  MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$RUN" \
    timeout --foreground --signal=INT --kill-after=30s 600s \
    "$V" --binary --threads 4 --timing -Wall -Wno-DECLFILENAME \
    -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL -Wno-WIDTH -Wno-SYNCASYNCNET \
    -j 4 -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" \
    -DROOT_MODULE="$top" -DEXPECTED_PHASES="$phases" \
    --top-module tb_operator_root_stress_v3 --Mdir "$run/obj" -o tb \
    "$ROOT/generated/operator_primitives_v3/roots/$top.sv" \
    "$ROOT/tb/tb_operator_root_stress_v3.sv" >"$run/build.log" 2>&1
  : >"$run/test.log"
  for seed in $(seq 1 20); do
    MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$RUN" \
      timeout --foreground --signal=INT --kill-after=30s 600s \
      "$run/obj/tb" +SEED="$seed" >>"$run/test.log" 2>&1
  done
  test "$(grep -c 'ROOT_STRESS_V3_PASS' "$run/test.log")" -eq 20
  echo "ROOT_STRESS_V3_ROOT_PASS root=$top seeds=20 transactions=2000 phases=$phases"
done | tee "$OUT/summary.log"
test "$(grep -c 'ROOT_STRESS_V3_ROOT_PASS' "$OUT/summary.log")" -eq 18
echo "OPERATOR_ROOT_STRESS_V3_PASS roots=18 seeds_per_root=20 transactions_per_seed=100 total_transactions=36000"
