#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);OUT=${OUT:-$ROOT/work/results/qwen2_real_command_submission};SRC=$ROOT/reports/execution/llama_cpp_qwen2_graph_lowering_result.json;R=$ROOT/scripts/run_memory_capped.sh;V=${VERILATOR:-$ROOT/work/toolchain/conda/bin/verilator};MACRO=$ROOT/work/generated/l10_sram/ct_sp_4096x128wm_base_0p8v_tt25/ctsp4096x128wm.v;mkdir -p "$OUT" "$ROOT/work/results/llama_cpp_qwen2_baseline"
taskset -c 8-23 python3 - "$SRC" "$ROOT/work/results/llama_cpp_qwen2_baseline/commands.memh" <<'PY'
import json,sys
r=json.load(open(sys.argv[1]));open(sys.argv[2],'w').write(''.join(x.removeprefix('0x')+'\n'for x in r['lowering']['command_words']))
PY
S=("$ROOT/rtl/memory/ct_sp4096x128_macro_wrapper.sv" "$ROOT/rtl/common/rv_fifo.sv" "$ROOT/rtl/top/command_dispatch.sv" "$ROOT/rtl/integration/command_event_scoreboard_sram.sv" "$ROOT/rtl/integration/command_event_frontend_sram.sv" "$ROOT/rtl/integration/engine_completion_rr_arbiter.sv" "$ROOT/rtl/fabric/shared_l2_client_arbiter.sv" "$ROOT/rtl/integration/hetero_l3_command_fabric.sv" "$ROOT/tb/tb_qwen2_real_command_submission.sv")
run(){ local t=$1;shift;MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" timeout --foreground --signal=INT --kill-after=30s "$t" "$@";}
run 600s "$V" --binary --timing --assert -Wall -Wno-fatal -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-UNUSEDSIGNAL -Wno-WIDTH -Wno-SYNCASYNCNET -Wno-PROCASSINIT -DARM_DISABLE_EMA_CHECK -j 8 -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" --top-module tb_qwen2_real_command_submission --Mdir "$OUT/obj" -o tb "$MACRO" "${S[@]}">"$OUT/build.log" 2>&1
cd "$ROOT";run 600s "$OUT/obj/tb"|tee "$OUT/tb.log";grep -q 'QWEN2_REAL_COMMAND_SUBMISSION_PASS commands=252 completions=252 matrix=140 sfu=112' "$OUT/tb.log"
