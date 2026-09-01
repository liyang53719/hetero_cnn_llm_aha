#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);OUT=${OUT:-$ROOT/work/results/qwen2_kv_bias_add};R=$ROOT/scripts/run_memory_capped.sh;V=${HETERO_VERILATOR:-$ROOT/work/toolchain/conda/bin/verilator};mkdir -p "$OUT";taskset -c 8-23 python3 "$ROOT/scripts/generate_qwen2_shared_l2_tile_vectors.py";taskset -c 8-23 python3 "$ROOT/scripts/generate_qwen2_kv_projection_vectors.py"
run(){ local limit=$1;shift;MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" timeout --foreground --signal=INT --kill-after=30s "$limit" "$@";}
run 600s "$V" --binary --timing --assert -Wall -Wno-fatal -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL -Wno-WIDTH -Wno-SYNCASYNCNET -Wno-PROCASSINIT -j 8 -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" --top-module tb_qwen2_kv_bias_add --Mdir "$OUT/obj" -o tb "$ROOT/work/generated/l5_all_primitives/HeteroAllPrimitives.sv" "$ROOT/rtl/sfu/bf16_bias_add_tile32.sv" "$ROOT/tb/tb_qwen2_kv_bias_add.sv" >"$OUT/build.log" 2>&1
cd "$ROOT";run 600s "$OUT/obj/tb"|tee "$OUT/tb.log";grep -q 'QWEN2_QKV_BIAS_ADD_PASS Q_values=1536 K_values=256 V_values=256' "$OUT/tb.log"
