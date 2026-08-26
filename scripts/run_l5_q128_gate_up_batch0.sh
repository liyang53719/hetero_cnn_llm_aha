#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);OUT=$ROOT/work/results/l5_q128_gate_up/batch0;R=$ROOT/scripts/run_memory_capped.sh;V=$ROOT/work/toolchain/conda/bin/verilator;PY=$ROOT/work/toolchain/cnn_py312/bin/python;mkdir -p "$OUT"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" /usr/bin/g++ -O2 -fopenmp "$ROOT/cpp/l5_q128_gate_up_golden.cpp" -o "$OUT/golden"
OMP_NUM_THREADS=8 MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" "$OUT/golden" "$ROOT/work/results/l5_q128_oproj/batch0/norm2.memh" "$ROOT/work/results/l5_target_gate_up/vectors/gate_weights_bf16.memh" "$ROOT/work/results/l5_target_gate_up/vectors/up_weights_bf16.memh" "$OUT/gate.memh" "$OUT/up.memh"
taskset -c 8-23 "$PY" "$ROOT/scripts/manifest_l5_q128_gate_up_batch.py" --workload 128 --batch 0 --norm2 "$ROOT/work/results/l5_q128_oproj/batch0/norm2.memh" --gate "$OUT/gate.memh" --up "$OUT/up.memh" --output "$OUT/manifest.json"
S=("$ROOT/work/generated/l5_all_primitives/HeteroAllPrimitives.sv" "$ROOT/rtl/matrix/bf16_outer_product_array.sv" "$ROOT/tb/tb_l5_q128_gate_up_batch.sv")
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" "$V" --lint-only --timing -Wall -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL --top-module tb_l5_q128_gate_up_batch "${S[@]}" >"$OUT/lint.log" 2>&1
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" "$V" --binary --timing -Wall -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL -j 8 -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" --top-module tb_l5_q128_gate_up_batch --Mdir "$OUT/obj" -o tb "${S[@]}" >"$OUT/build.log" 2>&1
cd "$ROOT";for m in 0 1;do MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" "$OUT/obj/tb" +WORKLOAD=128 +BATCH=0 +MODE="$m"|tee "$OUT/mode$m.log";grep -q "L5_Q_PREFILL_GATE_UP_BATCH_PASS workload=128 batch=0 mode=$m" "$OUT/mode$m.log";done;echo L5_Q128_GATE_UP_BATCH0_GATE_PASS
