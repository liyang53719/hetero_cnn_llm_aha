#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
BASE="$ROOT/work/results/l5_target_qkv_segment/vectors"
SHARED="$ROOT/work/results/l5_q128_qkv/shared"
OUT="$ROOT/work/results/l5_q128_qkv"
RUN="$ROOT/scripts/run_memory_capped.sh"
VERILATOR="$ROOT/work/toolchain/conda/bin/verilator"
PYTHON="$ROOT/work/toolchain/cnn_py312/bin/python"
mkdir -p "$BASE" "$SHARED" "$OUT"

taskset -c 8-23 "$PYTHON" "$ROOT/scripts/generate_l5_target_qkv_segment_vectors.py" --out "$BASE"
for batch in 0 1 2 3 4 5 6 7; do
  mkdir -p "$OUT/batch$batch"
  taskset -c 8-23 "$PYTHON" "$ROOT/scripts/generate_l5_q128_qkv_batch_vectors.py" \
    --base-dir "$BASE" --tokens 128 --batch-index "$batch" --shared-out "$SHARED" \
    --out "$OUT/batch$batch"
done
SOURCES=(
  "$ROOT/work/generated/l5_all_primitives/HeteroAllPrimitives.sv"
  "$ROOT/rtl/matrix/bf16_outer_product_array.sv"
  "$ROOT/rtl/sfu/fp32_reduce16.sv"
  "$ROOT/rtl/sfu/fp32_rsqrt_nr.sv"
  "$ROOT/rtl/sfu/fp32_rmsnorm1536_chunked.sv"
  "$ROOT/rtl/sfu/fp32_vector_alu.sv"
  "$ROOT/tb/tb_l5_q128_qkv_batch0.sv"
)
COMMON=(--timing -Wall -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL)
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$RUN" \
  "$VERILATOR" --lint-only "${COMMON[@]}" --top-module tb_l5_q128_qkv_batch0 \
  "${SOURCES[@]}" >"$OUT/all_lint.log" 2>&1
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$RUN" \
  "$VERILATOR" --binary "${COMMON[@]}" -j 8 \
  -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" \
  --top-module tb_l5_q128_qkv_batch0 --Mdir "$OUT/all_obj" -o tb \
  "${SOURCES[@]}" >"$OUT/all_build.log" 2>&1
cd "$ROOT"
for batch in 0 1 2 3 4 5 6 7; do
  MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$RUN" \
    "$OUT/all_obj/tb" +WORKLOAD=128 +BATCH="$batch" | tee "$OUT/batch$batch/tb_all.log"
  grep -q "L5_Q_PREFILL_QKV_BATCH_PASS workload=128 batch=$batch" "$OUT/batch$batch/tb_all.log"
done
echo L5_Q128_QKV_ALL_BATCHES_GATE_PASS
