#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);OUT=${OUT:-$ROOT/work/results/l5_balanced_summary_scheduler};RUN=$ROOT/scripts/run_memory_capped.sh;V=${VERILATOR:-$ROOT/work/toolchain/conda/bin/verilator};mkdir -p "$OUT"
run(){ local limit=$1;shift;MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$RUN" timeout --foreground --signal=INT --kill-after=30s "$limit" taskset -c 8-23 "$@";}
run 600s env PYTHONPATH="$ROOT/src" python3 "$ROOT/scripts/generate_balanced_summary_scheduler_vectors.py"|tee "$OUT/vector_generation.log"
run 600s "$ROOT/scripts/generate_all_hardfloat_primitives.sh"
S=("$ROOT/work/generated/l5_all_primitives/HeteroAllPrimitives.sv" "$ROOT/rtl/sfu/fp32_exp2_pwl_rawpipe.sv" "$ROOT/rtl/sfu/fp32_mlo_merge_coeff_rawpipe.sv" "$ROOT/rtl/sfu/fp32_mlo_merge_beat_rawpipe.sv" "$ROOT/rtl/sfu/fp32_mlo_summary_merge_stream_rawpipe.sv" "$ROOT/rtl/attention/fp32_mlo_balanced_summary_scheduler.sv" "$ROOT/tb/tb_fp32_mlo_balanced_summary_scheduler.sv")
run 600s "$V" --binary --timing --assert -Wall -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL -Wno-WIDTH -Wno-SYNCASYNCNET -Wno-PINCONNECTEMPTY -j 8 -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" --top-module tb_fp32_mlo_balanced_summary_scheduler --Mdir "$OUT/obj" -o tb "${S[@]}">"$OUT/build.log" 2>&1
run 600s "$OUT/obj/tb"|tee "$OUT/tb.log";grep -q 'BALANCED_SUMMARY_SCHEDULER_PASS cases=4 input_summaries=17 merges=13' "$OUT/tb.log"
