#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);BASE=$ROOT/work/results/l5_q128_gate_up;OUT=$BASE/mt4;R=$ROOT/scripts/run_memory_capped.sh;V=$ROOT/work/toolchain/conda/bin/verilator;PY=$ROOT/work/toolchain/cnn_py312/bin/python;mkdir -p "$OUT"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" /usr/bin/g++ -O2 -fopenmp "$ROOT/cpp/l5_q128_gate_up_golden.cpp" -o "$OUT/golden"
S=("$ROOT/work/generated/l5_all_primitives/HeteroAllPrimitives.sv" "$ROOT/rtl/matrix/bf16_outer_product_array.sv" "$ROOT/tb/tb_l5_q128_gate_up_batch.sv")
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" "$V" --binary --threads 8 --timing -Wall -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL -j 8 -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" --top-module tb_l5_q128_gate_up_batch --Mdir "$OUT/obj" -o tb "${S[@]}" >"$OUT/build_all.log" 2>&1
cd "$ROOT"
for batch in 1 2 3 4 5 6 7;do
  B=$BASE/batch$batch;mkdir -p "$B"
  OMP_NUM_THREADS=8 MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" "$OUT/golden" "$ROOT/work/results/l5_q128_oproj/batch$batch/norm2.memh" "$ROOT/work/results/l5_target_gate_up/vectors/gate_weights_bf16.memh" "$ROOT/work/results/l5_target_gate_up/vectors/up_weights_bf16.memh" "$B/gate.memh" "$B/up.memh"
  taskset -c 8-23 "$PY" "$ROOT/scripts/manifest_l5_q128_gate_up_batch.py" --batch "$batch" --norm2 "$ROOT/work/results/l5_q128_oproj/batch$batch/norm2.memh" --gate "$B/gate.memh" --up "$B/up.memh" --output "$B/manifest.json"
  for mode in 0 1;do
    MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" "$OUT/obj/tb" +BATCH="$batch" +MODE="$mode"|tee "$B/mode$mode.log"
    grep -q "L5_Q128_GATE_UP_BATCH_PASS batch=$batch mode=$mode" "$B/mode$mode.log"
  done
done
echo L5_Q128_GATE_UP_REMAINING_GATE_PASS
