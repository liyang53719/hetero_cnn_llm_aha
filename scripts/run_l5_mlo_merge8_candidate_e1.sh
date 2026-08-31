#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);OUT=${OUT:-$ROOT/work/results/l5_mlo_merge8_candidate_e1};R=$ROOT/scripts/run_memory_capped.sh;V=${VERILATOR:-$ROOT/work/toolchain/conda/bin/verilator};mkdir -p "$OUT";"$ROOT/scripts/generate_all_hardfloat_primitives.sh"
S=("$ROOT/work/generated/l5_all_primitives/HeteroAllPrimitives.sv" "$ROOT/rtl/common/rv_fifo.sv" "$ROOT/rtl/sfu/fp32_exp2_pwl_rawpipe.sv" "$ROOT/rtl/sfu/fp32_mlo_merge_coeff_rawpipe.sv" "$ROOT/rtl/sfu/fp32_mlo_merge_beat_rawpipe.sv" "$ROOT/rtl/sfu/fp32_mlo_summary_merge_stream_rawpipe.sv" "$ROOT/rtl/attention/fp32_mlo_merge8_candidate.sv" "$ROOT/tb/tb_fp32_mlo_merge8_candidate.sv")
run(){ local limit=$1;shift;MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" timeout --foreground --signal=INT --kill-after=30s "$limit" "$@";}
run 600s "$V" --binary --timing -Wall -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL -Wno-WIDTH -Wno-SYNCASYNCNET -Wno-PINCONNECTEMPTY -Wno-PINMISSING -j 8 -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" --top-module tb_fp32_mlo_merge8_candidate --Mdir "$OUT/obj" -o tb "${S[@]}" >"$OUT/build.log" 2>&1
run 600s "$OUT/obj/tb"|tee "$OUT/tb.log";grep -q 'MLO_MERGE8_CANDIDATE_PASS rows=8 beats=32' "$OUT/tb.log";run 600s "$OUT/obj/tb" +NOSTALL|tee "$OUT/tb_nominal.log";grep -q 'nominal=1' "$OUT/tb_nominal.log"
