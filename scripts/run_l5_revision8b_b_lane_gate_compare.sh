#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd);R="$ROOT/scripts/run_memory_capped.sh";VCS=${VCS_BIN:-/home/yang/tools/synopsys/vcs/W-2024.09/bin/vcs}
GEN="$ROOT/work/generated/l5_all_primitives/HeteroAllPrimitives.sv";RTL="$ROOT/rtl/matrix/candidates/rev8b_b/bf16_context_fma_pipeline_lane5_rev8b_b_candidate.sv"
NET="$ROOT/work/generated/l5_matrix_rev8b_b/lane/bf16_context_fma_pipeline_lane5_rev8b_b_candidate.mapped.v";CELLS=${STD_CELL_VERILOG:-/home/yang/tools/arm/tsmc/cln22ul/sc6p5mcpp140z_base_svt_c35/r3p0/verilog/sc6p5mcpp140z_cln22ul_base_svt_c35.v}
TB="$ROOT/tb/tb_l5_revision8b_b_lane_gate_compare.sv";OUT="$ROOT/work/results/l5_matrix_rev8b_b/lane_gate_compare";REPORT="$ROOT/reports/execution/l5_revision8b_b_lane_gate_compare_result.json"
[[ -s "$ROOT/work/generated/l5_matrix_rev8b_b/lane/accepted" ]]||{ echo 'lane DC first' >&2;exit 4;};mkdir -p "$OUT/rtl" "$OUT/gate";rm -f "$OUT/rtl/trace.txt" "$OUT/gate/trace.txt"
run(){ local lim=$1;shift;MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" timeout --foreground --signal=INT --kill-after=30s "$lim" "$@";}
(cd "$OUT/rtl";run 600s "$VCS" -full64 -sverilog -timescale=1ns/1ps +vcs+lic+wait -j4 -top tb_l5_revision8b_b_lane_gate_compare "$GEN" "$RTL" "$TB" -o "$OUT/rtl/simv" >"$OUT/rtl/compile.log" 2>&1)
(cd "$OUT/gate";run 600s "$VCS" -full64 -sverilog -timescale=1ns/1ps +vcs+lic+wait +nospecify -j4 -top tb_l5_revision8b_b_lane_gate_compare "$CELLS" "$NET" "$TB" -o "$OUT/gate/simv" >"$OUT/gate/compile.log" 2>&1)
run 300s "$OUT/rtl/simv" "+TRACE=$OUT/rtl/trace.txt" >"$OUT/rtl/run.log" 2>&1
run 300s "$OUT/gate/simv" +notimingcheck "+TRACE=$OUT/gate/trace.txt" >"$OUT/gate/run.log" 2>&1
[[ $(wc -l <"$OUT/rtl/trace.txt")==120032 && $(wc -l <"$OUT/gate/trace.txt")==120032 ]];cmp "$OUT/rtl/trace.txt" "$OUT/gate/trace.txt"
taskset -c 8-23 python3 - "$REPORT" "$RTL" "$NET" "$TB" "$OUT/rtl/trace.txt" <<'PY'
import hashlib,json,sys
from pathlib import Path
out,rtl,net,tb,trace=map(Path,sys.argv[1:]);sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
r={'schema_version':1,'revision':'8B-B','status':'PASS','method':'lane_post_synthesis_gate_compare','compared_cycles':120032,'mismatches':0,'unknown_outputs':0,'hashes':{'rtl':sha(rtl),'netlist':sha(net),'testbench':sha(tb),'trace':sha(trace)},'limitations':['zero-delay','not SDF']};out.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print(json.dumps(r,indent=2,sort_keys=True))
PY
