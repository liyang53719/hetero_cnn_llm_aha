#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
QKV="$ROOT/work/results/l5_target_qkv_segment/vectors"
OUT="$ROOT/work/results/l5_target_rope_gqa"
RUN="$ROOT/scripts/run_memory_capped.sh"
VERILATOR="$ROOT/work/toolchain/conda/bin/verilator"
PYTHON="$ROOT/work/toolchain/cnn_py312/bin/python"
mkdir -p "$QKV" "$OUT/vectors"

taskset -c 8-25 "$PYTHON" "$ROOT/scripts/generate_l5_target_qkv_segment_vectors.py" \
  --out "$QKV"
taskset -c 8-25 "$PYTHON" "$ROOT/scripts/generate_l5_target_rope_gqa_vectors.py" \
  --input-dir "$QKV" --out "$OUT/vectors"
SOURCES=(
  "$ROOT/work/generated/l5_all_primitives/HeteroAllPrimitives.sv"
  "$ROOT/rtl/sfu/fp32_rope_pair.sv"
  "$ROOT/rtl/sfu/qwen_gqa_multicast16.sv"
  "$ROOT/tb/tb_l5_target_rope_gqa.sv"
)
COMMON=(--timing -Wall -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL)
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=8G MEMORY_MAX=10G "$RUN" \
  "$VERILATOR" --lint-only "${COMMON[@]}" --top-module tb_l5_target_rope_gqa \
  "${SOURCES[@]}" >"$OUT/lint.log" 2>&1
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=8G MEMORY_MAX=10G "$RUN" \
  "$VERILATOR" --binary "${COMMON[@]}" -j 4 \
  -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" \
  --top-module tb_l5_target_rope_gqa --Mdir "$OUT/obj" -o tb \
  "${SOURCES[@]}" >"$OUT/build.log" 2>&1
cd "$ROOT"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=8G MEMORY_MAX=10G "$RUN" \
  "$OUT/obj/tb" | tee "$OUT/tb.log"
grep -q 'L5_TARGET_ROPE_GQA_PASS rope_pairs=1024' "$OUT/tb.log"
echo L5_TARGET_ROPE_GQA_GATE_PASS
