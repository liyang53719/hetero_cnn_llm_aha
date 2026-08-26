#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);BASE=$ROOT/work/results/l5_target_qkv_segment/vectors;OUT=$ROOT/work/results/l5_q384_qkv;SHARED=$OUT/shared;R=$ROOT/scripts/run_memory_capped.sh;V=$ROOT/work/toolchain/conda/bin/verilator;PY=$ROOT/work/toolchain/cnn_py312/bin/python;mkdir -p "$BASE" "$SHARED"
taskset -c 8-23 "$PY" "$ROOT/scripts/generate_l5_target_qkv_segment_vectors.py" --out "$BASE"
for b in $(seq 0 23);do mkdir -p "$OUT/batch$b";taskset -c 8-23 "$PY" "$ROOT/scripts/generate_l5_q128_qkv_batch_vectors.py" --base-dir "$BASE" --tokens 384 --batch-index "$b" --shared-out "$SHARED" --out "$OUT/batch$b";done
S=("$ROOT/work/generated/l5_all_primitives/HeteroAllPrimitives.sv" "$ROOT/rtl/matrix/bf16_outer_product_array.sv" "$ROOT/rtl/sfu/fp32_reduce16.sv" "$ROOT/rtl/sfu/fp32_rsqrt_nr.sv" "$ROOT/rtl/sfu/fp32_rmsnorm1536_chunked.sv" "$ROOT/rtl/sfu/fp32_vector_alu.sv" "$ROOT/tb/tb_l5_q128_qkv_batch0.sv")
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" "$V" --binary --threads 4 --timing -Wall -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL -j 8 -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" --top-module tb_l5_q128_qkv_batch0 --Mdir "$OUT/obj" -o tb "${S[@]}" >"$OUT/build.log" 2>&1
cd "$ROOT";for b in $(seq 0 23);do MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" "$OUT/obj/tb" +WORKLOAD=384 +BATCH="$b"|tee "$OUT/batch$b/tb.log";grep -q "L5_Q_PREFILL_QKV_BATCH_PASS workload=384 batch=$b" "$OUT/batch$b/tb.log";done;echo L5_Q384_QKV_ALL_BATCHES_GATE_PASS
