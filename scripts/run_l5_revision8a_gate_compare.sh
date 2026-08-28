#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
R="$ROOT/scripts/run_memory_capped.sh"
VCS=${VCS_BIN:-/home/yang/tools/synopsys/vcs/W-2024.09/bin/vcs}
GEN="$ROOT/work/generated/l5_all_primitives/HeteroAllPrimitives.sv"
LANE="$ROOT/rtl/matrix/candidates/rev8/bf16_context_fma_pipeline_lane4_rev8_candidate.sv"
NET="$ROOT/work/generated/l5_matrix_rev8a/lane/bf16_context_fma_pipeline_lane4_rev8_candidate.mapped.v"
CELLS=${STD_CELL_VERILOG:-/home/yang/tools/arm/tsmc/cln22ul/sc6p5mcpp140z_base_svt_c35/r3p0/verilog/sc6p5mcpp140z_cln22ul_base_svt_c35.v}
TB="$ROOT/tb/tb_l5_revision8a_lane_gate_compare.sv"
OUT="$ROOT/work/results/l5_matrix_rev8a/gate_compare"
REPORT="$ROOT/reports/execution/l5_revision8a_gate_compare_result.json"
mkdir -p "$OUT/rtl" "$OUT/gate"
for f in "$VCS" "$GEN" "$LANE" "$NET" "$CELLS" "$TB"; do [[ -s "$f" ]] || { echo "missing: $f" >&2; exit 3; }; done
rm -f "$OUT/rtl/trace.txt" "$OUT/gate/trace.txt" "$REPORT"
run_capped(){ local limit=$1;shift; MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" timeout --foreground --signal=INT --kill-after=30s "$limit" "$@"; }
(
 cd "$OUT/rtl"
 run_capped 10m "$VCS" -full64 -sverilog -timescale=1ns/1ps +vcs+lic+wait -j4 \
   -top tb_l5_revision8a_lane_gate_compare "$GEN" "$LANE" "$TB" -o "$OUT/rtl/simv" \
   >"$OUT/rtl/compile.log" 2>&1
)
(
 cd "$OUT/gate"
 run_capped 10m "$VCS" -full64 -sverilog -timescale=1ns/1ps +vcs+lic+wait +nospecify -j4 \
   -top tb_l5_revision8a_lane_gate_compare "$CELLS" "$NET" "$TB" -o "$OUT/gate/simv" \
   >"$OUT/gate/compile.log" 2>&1
)
run_capped 5m "$OUT/rtl/simv" "+TRACE=$OUT/rtl/trace.txt" >"$OUT/rtl/run.log" 2>&1
run_capped 5m "$OUT/gate/simv" +notimingcheck "+TRACE=$OUT/gate/trace.txt" >"$OUT/gate/run.log" 2>&1
expected=120032
[[ $(wc -l <"$OUT/rtl/trace.txt") -eq $expected && $(wc -l <"$OUT/gate/trace.txt") -eq $expected ]]
cmp "$OUT/rtl/trace.txt" "$OUT/gate/trace.txt"
taskset -c 8-23 python3 - "$REPORT" "$GEN" "$LANE" "$NET" "$CELLS" "$TB" "$OUT/rtl/trace.txt" <<'PY'
import hashlib,json,sys
from pathlib import Path
out,gen,lane,net,cells,tb,trace=map(Path,sys.argv[1:])
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
r={'schema_version':1,'revision':'8A','status':'PASS','method':'post_synthesis_gate_compare','comparison_mode':'functional_zero_delay_no_SDF','compared_cycles':120032,'mismatches':0,'unknown_outputs':0,'hashes':{'generated_rtl_sha256':sha(gen),'lane_rtl_sha256':sha(lane),'mapped_netlist_sha256':sha(net),'std_cell_verilog_sha256':sha(cells),'testbench_sha256':sha(tb),'trace_sha256':sha(trace)},'limitations':['not SDF timing simulation','not full H3 equivalence']}
out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print(json.dumps(r,indent=2,sort_keys=True))
PY
echo REV8A_POST_SYNTHESIS_GATE_COMPARE_PASS
