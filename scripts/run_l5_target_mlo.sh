#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
QKV="$ROOT/work/results/l5_target_qkv_segment/vectors"
ROPE="$ROOT/work/results/l5_target_rope_gqa/vectors"
OUT="$ROOT/work/results/l5_target_mlo"
RUN="$ROOT/scripts/run_memory_capped.sh"
VERILATOR="$ROOT/work/toolchain/conda/bin/verilator"
PYTHON="$ROOT/work/toolchain/cnn_py312/bin/python"
mkdir -p "$QKV" "$ROPE" "$OUT/vectors"

taskset -c 8-23 "$PYTHON" "$ROOT/scripts/generate_l5_target_qkv_segment_vectors.py" \
  --out "$QKV"
taskset -c 8-23 "$PYTHON" "$ROOT/scripts/generate_l5_target_rope_gqa_vectors.py" \
  --input-dir "$QKV" --out "$ROPE"
taskset -c 8-23 "$PYTHON" "$ROOT/scripts/generate_l5_target_mlo_vectors.py" \
  --rope-dir "$ROPE" --qkv-dir "$QKV" --out "$OUT/vectors"
SOURCES=(
  "$ROOT/work/generated/l5_all_primitives/HeteroAllPrimitives.sv"
  "$ROOT/rtl/sfu/fp32_reduce16.sv"
  "$ROOT/rtl/sfu/fp32_dot128_scaled.sv"
  "$ROOT/rtl/sfu/fp32_exp2_pwl.sv"
  "$ROOT/rtl/sfu/fp32_online_softmax.sv"
  "$ROOT/rtl/sfu/fp32_reciprocal_nr.sv"
  "$ROOT/rtl/sfu/fp32_vector_alu.sv"
  "$ROOT/tb/tb_l5_target_mlo.sv"
)
COMMON=(--timing -Wall -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL)
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$RUN" \
  "$VERILATOR" --lint-only "${COMMON[@]}" --top-module tb_l5_target_mlo \
  "${SOURCES[@]}" >"$OUT/lint.log" 2>&1
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$RUN" \
  "$VERILATOR" --binary "${COMMON[@]}" -j 8 \
  -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" \
  --top-module tb_l5_target_mlo --Mdir "$OUT/obj" -o tb \
  "${SOURCES[@]}" >"$OUT/build.log" 2>&1
cd "$ROOT"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$RUN" \
  "$OUT/obj/tb" | tee "$OUT/tb.log"
grep -q 'L5_TARGET_MLO_PASS heads=12 tokens=2 scores_streamed=24 score_matrix=0' "$OUT/tb.log"
echo L5_TARGET_MLO_GATE_PASS
