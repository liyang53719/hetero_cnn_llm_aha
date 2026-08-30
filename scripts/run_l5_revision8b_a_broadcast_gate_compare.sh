#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
R="$ROOT/scripts/run_memory_capped.sh"
VCS=${VCS_BIN:-/home/yang/tools/synopsys/vcs/W-2024.09/bin/vcs}
RTL="$ROOT/rtl/matrix/candidates/rev8b_a/bf16_front_to_cluster_broadcast32_rev8b_a_candidate.sv"
NET="$ROOT/work/generated/l5_matrix_rev8b_a/broadcast32/bf16_front_to_cluster_broadcast32_rev8b_a_candidate.mapped.v"
CELLS=${STD_CELL_VERILOG:-/home/yang/tools/arm/tsmc/cln22ul/sc6p5mcpp140z_base_svt_c35/r3p0/verilog/sc6p5mcpp140z_cln22ul_base_svt_c35.v}
TB="$ROOT/tb/tb_bf16_front_to_cluster_broadcast32_rev8b_a.sv"
OUT="$ROOT/work/results/l5_matrix_rev8b_a/broadcast_gate_compare"
REPORT="$ROOT/reports/execution/l5_revision8b_a_broadcast_gate_compare_result.json"
[[ -s "$ROOT/work/generated/l5_matrix_rev8b_a/broadcast32/accepted" ]] || { echo 'run broadcast DC first' >&2; exit 4; }
mkdir -p "$OUT/rtl" "$OUT/gate"
rm -f "$OUT/rtl/trace.txt" "$OUT/gate/trace.txt" "$REPORT"
run_capped(){ local limit=$1;shift; MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" timeout --foreground --signal=INT --kill-after=30s "$limit" "$@"; }
(
 cd "$OUT/rtl"
 run_capped 10m "$VCS" -full64 -sverilog -timescale=1ns/1ps +vcs+lic+wait -j4 \
   -top tb_bf16_front_to_cluster_broadcast32_rev8b_a "$RTL" "$TB" -o "$OUT/rtl/simv" \
   >"$OUT/rtl/compile.log" 2>&1
)
(
 cd "$OUT/gate"
 run_capped 10m "$VCS" -full64 -sverilog -timescale=1ns/1ps +vcs+lic+wait +nospecify -j4 \
   -top tb_bf16_front_to_cluster_broadcast32_rev8b_a "$CELLS" "$NET" "$TB" -o "$OUT/gate/simv" \
   >"$OUT/gate/compile.log" 2>&1
)
run_capped 5m "$OUT/rtl/simv" "+TRACE=$OUT/rtl/trace.txt" >"$OUT/rtl/run.log" 2>&1
run_capped 5m "$OUT/gate/simv" +notimingcheck "+TRACE=$OUT/gate/trace.txt" >"$OUT/gate/run.log" 2>&1
[[ $(wc -l <"$OUT/rtl/trace.txt") -eq 100000 && $(wc -l <"$OUT/gate/trace.txt") -eq 100000 ]]
cmp "$OUT/rtl/trace.txt" "$OUT/gate/trace.txt"
taskset -c 8-23 python3 - "$REPORT" "$RTL" "$NET" "$CELLS" "$TB" "$OUT/rtl/trace.txt" <<'PY'
import hashlib,json,sys
from pathlib import Path
out,rtl,net,cells,tb,trace=map(Path,sys.argv[1:])
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
r={'schema_version':1,'revision':'8B-A','status':'PASS','method':'broadcast_post_synthesis_gate_compare','comparison_mode':'functional_zero_delay_no_SDF','compared_vectors':100000,'mismatches':0,'unknown_outputs':0,'hashes':{'rtl_sha256':sha(rtl),'mapped_netlist_sha256':sha(net),'std_cell_verilog_sha256':sha(cells),'testbench_sha256':sha(tb),'trace_sha256':sha(trace)},'limitations':['not SDF timing simulation','broadcast component only']}
out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print(json.dumps(r,indent=2,sort_keys=True))
PY
echo L5_REV8B_A_BROADCAST_GATE_COMPARE_PASS
