#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);BASE=$ROOT/work/results/l5_q384_down;OUT=$BASE/mt8;R=$ROOT/scripts/run_memory_capped.sh;V=$ROOT/work/toolchain/conda/bin/verilator;PY=$ROOT/work/toolchain/cnn_py312/bin/python;mkdir -p "$OUT"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" /usr/bin/g++ -O2 -fopenmp "$ROOT/cpp/l5_q128_down_golden.cpp" -o "$OUT/golden"
for batch in $(seq 0 23);do B=$BASE/batch$batch;mkdir -p "$B";OMP_NUM_THREADS=8 MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" "$OUT/golden" "$ROOT/work/results/l5_q384_silu_product/vectors/product.memh" "$ROOT/work/results/l5_q384_oproj/batch$batch/residual1.memh" "$ROOT/work/results/l5_target_down/vectors/weights_bf16.memh" "$batch" "$B/down.memh" "$B/final.memh";taskset -c 8-23 "$PY" "$ROOT/scripts/manifest_l5_q128_down_batch.py" --workload 384 --batch "$batch" --product "$ROOT/work/results/l5_q384_silu_product/vectors/product.memh" --residual "$ROOT/work/results/l5_q384_oproj/batch$batch/residual1.memh" --down "$B/down.memh" --final "$B/final.memh" --output "$B/manifest.json";done
S=("$ROOT/work/generated/l5_all_primitives/HeteroAllPrimitives.sv" "$ROOT/rtl/matrix/bf16_outer_product_array.sv" "$ROOT/rtl/sfu/fp32_vector_alu.sv" "$ROOT/tb/tb_l5_q128_down_batch.sv")
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" "$V" --binary --threads 4 --timing -Wall -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL -j 8 -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" --top-module tb_l5_q128_down_batch --Mdir "$OUT/obj" -o tb "${S[@]}" >"$OUT/build.log" 2>&1
cd "$ROOT"
for first in $(seq 0 2 22);do pids=();for batch in "$first" "$((first+1))";do (MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" "$OUT/obj/tb" +WORKLOAD=384 +BATCH="$batch" >"$BASE/batch$batch/tb.log" 2>&1)&pids+=("$!");done;for pid in "${pids[@]}";do wait "$pid";done;for batch in "$first" "$((first+1))";do cat "$BASE/batch$batch/tb.log";grep -q "L5_Q_PREFILL_DOWN_BATCH_PASS workload=384 batch=$batch" "$BASE/batch$batch/tb.log";done;done
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" "$OUT/obj/tb" +WORKLOAD=128 +BATCH=0 | tee "$BASE/q128_compat.log"
grep -q 'L5_Q_PREFILL_DOWN_BATCH_PASS workload=128 batch=0' "$BASE/q128_compat.log"
echo L5_Q384_DOWN_ALL_BATCHES_GATE_PASS
