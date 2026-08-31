#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);OUT=$ROOT/work/results/l5_q128_mlo;R=$ROOT/scripts/run_memory_capped.sh;V=$ROOT/work/toolchain/conda/bin/verilator;PY=$ROOT/work/toolchain/cnn_py312/bin/python;mkdir -p "$OUT/vectors"
run_capped(){ local limit=$1;shift;MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" timeout --foreground --signal=INT --kill-after=30s "$limit" "$@";}
run_capped 600s "$PY" "$ROOT/scripts/generate_l5_q128_mlo_vectors.py" --rope-dir "$ROOT/work/results/l5_q128_rope_gqa/vectors" --tokens 128 --out "$OUT/vectors"
S=("$ROOT/work/generated/l5_all_primitives/HeteroAllPrimitives.sv" "$ROOT/rtl/sfu/fp32_reduce16.sv" "$ROOT/rtl/sfu/fp32_dot128_scaled.sv" "$ROOT/rtl/sfu/fp32_exp2_pwl.sv" "$ROOT/rtl/sfu/fp32_online_softmax.sv" "$ROOT/rtl/sfu/fp32_reciprocal_nr.sv" "$ROOT/rtl/sfu/fp32_vector_alu.sv" "$ROOT/tb/tb_l5_q128_mlo.sv")
run_capped 600s "$V" --lint-only --timing -Wall -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL --top-module tb_l5_q128_mlo "${S[@]}" >"$OUT/lint.log" 2>&1
run_capped 600s "$V" --binary --timing -Wall -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL -j 8 -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" --top-module tb_l5_q128_mlo --Mdir "$OUT/obj" -o tb "${S[@]}" >"$OUT/build.log" 2>&1
cd "$ROOT";run_capped 600s "$OUT/obj/tb" +WORKLOAD=128|tee "$OUT/tb.log";grep -q 'L5_Q_PREFILL_MLO_PASS workload=128 updates=99072 reciprocals=1536' "$OUT/tb.log";echo L5_Q128_MLO_GATE_PASS
