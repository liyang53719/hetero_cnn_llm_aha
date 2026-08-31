#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT=${OUT:-$ROOT/work/results/l5_qwen2_full_model_trace}
R=$ROOT/scripts/run_memory_capped.sh
V=${VERILATOR:-$ROOT/work/toolchain/conda/bin/verilator}
mkdir -p "$OUT"
run(){ local limit=$1;shift;MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" timeout --foreground --signal=INT --kill-after=30s "$limit" "$@";}
run 600s "$V" --binary --timing --assert -Wall -Wno-DECLFILENAME \
  -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL -Wno-WIDTH -Wno-PROCASSINIT \
  -Wno-SYNCASYNCNET -j 8 \
  -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" \
  --top-module tb_l5_qwen2_full_model_trace_controller \
  --Mdir "$OUT/obj" -o tb \
  "$ROOT/rtl/control/l5_qwen2_full_model_trace_controller.sv" \
  "$ROOT/tb/tb_l5_qwen2_full_model_trace_controller.sv" \
  >"$OUT/build.log" 2>&1
run 600s "$OUT/obj/tb" | tee "$OUT/tb.log"
grep -q 'L5_QWEN2_FULL_MODEL_TRACE_PASS records=30 blocks=28 final_rmsnorm=1 last_token_lm_head=1 total_cycles=3192103543' "$OUT/tb.log"
