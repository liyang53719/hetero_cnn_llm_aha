#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);OUT=${OUT:-$ROOT/work/results/qwen2_token0_qk_rope};R=$ROOT/scripts/run_memory_capped.sh;V=${HETERO_VERILATOR:-$ROOT/work/toolchain/conda/bin/verilator};mkdir -p "$OUT";taskset -c 8-23 python3 "$ROOT/scripts/generate_qwen2_shared_l2_tile_vectors.py";taskset -c 8-23 python3 "$ROOT/scripts/generate_qwen2_kv_projection_vectors.py"
run(){ local limit=$1;shift;MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" timeout --foreground --signal=INT --kill-after=30s "$limit" "$@";}
run 600s "$V" --binary --timing --assert -Wall -Wno-fatal -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL -Wno-WIDTH -Wno-SYNCASYNCNET -Wno-PROCASSINIT -j 8 -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" --top-module tb_qwen2_token0_qk_rope --Mdir "$OUT/obj" -o tb "$ROOT/work/generated/l5_all_primitives/HeteroAllPrimitives.sv" "$ROOT/rtl/sfu/fp32_rope_pair.sv" "$ROOT/tb/tb_qwen2_token0_qk_rope.sv" >"$OUT/build.log" 2>&1
cd "$ROOT";run 600s "$OUT/obj/tb"|tee "$OUT/tb.log";grep -q 'QWEN2_TOKEN0_QK_ROPE_PASS Q_pairs=768 K_pairs=128' "$OUT/tb.log"
