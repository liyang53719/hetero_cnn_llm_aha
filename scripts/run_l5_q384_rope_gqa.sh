#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);OUT=$ROOT/work/results/l5_q384_rope_gqa;R=$ROOT/scripts/run_memory_capped.sh;V=$ROOT/work/toolchain/conda/bin/verilator;PY=$ROOT/work/toolchain/cnn_py312/bin/python;mkdir -p "$OUT/vectors"
taskset -c 8-23 "$PY" "$ROOT/scripts/generate_l5_q128_rope_gqa_vectors.py" --qkv-dir "$ROOT/work/results/l5_q384_qkv" --tokens 384 --out "$OUT/vectors"
S=("$ROOT/work/generated/l5_all_primitives/HeteroAllPrimitives.sv" "$ROOT/rtl/sfu/fp32_rope_pair.sv" "$ROOT/rtl/sfu/qwen_gqa_multicast16.sv" "$ROOT/tb/tb_l5_q128_rope_gqa.sv")
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" "$V" --binary --timing -Wall -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL -j 8 -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" --top-module tb_l5_q128_rope_gqa --Mdir "$OUT/obj" -o tb "${S[@]}" >"$OUT/build.log" 2>&1
cd "$ROOT";MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" "$OUT/obj/tb" +WORKLOAD=384|tee "$OUT/tb.log";grep -q 'L5_Q_PREFILL_ROPE_GQA_PASS workload=384 rope_pairs=344064' "$OUT/tb.log";MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" "$OUT/obj/tb" +WORKLOAD=128|tee "$OUT/q128_compat.log";grep -q 'L5_Q_PREFILL_ROPE_GQA_PASS workload=128 rope_pairs=114688' "$OUT/q128_compat.log";echo L5_Q384_ROPE_GQA_GATE_PASS
