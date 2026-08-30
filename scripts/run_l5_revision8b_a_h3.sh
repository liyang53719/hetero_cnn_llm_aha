#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
R="$ROOT/scripts/run_memory_capped.sh"
DC=${DC_SHELL:-/home/yang/tools/synopsys/syn/X-2025.06-SP3/bin/dc_shell}
DB=${STD_CELL_DB:-/home/yang/tools/arm/tsmc/cln22ul/sc6p5mcpp140z_base_svt_c35/r3p0/db/sc6p5mcpp140z_cln22ul_base_svt_c35_tt_typical_max_0p80v_25c.db}
REV8A_GEN="$ROOT/work/generated/l5_matrix_rev8a"
GEN="$ROOT/work/generated/l5_matrix_rev8b_a/top"
RES="$ROOT/work/results/l5_matrix_rev8b_a/top"
DECISION="$ROOT/reports/execution/l5_revision8b_a_phase_decision.json"
TOP="$ROOT/rtl/matrix/candidates/rev8b_a/bf16_outer_product_context_array_rev8b_a_candidate.sv"
FRONT="$REV8A_GEN/front/bf16_context_front_control_rev8_candidate.ddc"
CLUSTER="$REV8A_GEN/cluster16/bf16_context_lane_cluster16_rev8_candidate.ddc"
BROADCAST="$ROOT/work/generated/l5_matrix_rev8b_a/broadcast32/bf16_front_to_cluster_broadcast32_rev8b_a_candidate.ddc"
OPERAND="$ROOT/work/generated/l5_matrix_rev8b_a/operand_distribution/bf16_operand_distribution512_rev8b_a_candidate.ddc"
GLUE="$ROOT/work/generated/l5_matrix_hier_dc/shell/bf16_outer_product_array_glue512.ddc"
for f in "$TOP" "$FRONT" "$CLUSTER" "$BROADCAST" "$OPERAND" "$GLUE" "$DB"; do [[ -s "$f" ]] || { echo "missing prerequisite: $f" >&2; exit 4; }; done
[[ -s "$ROOT/work/generated/l5_matrix_rev8b_a/broadcast32/accepted" ]] || { echo 'broadcast32 not accepted' >&2; exit 4; }
[[ -s "$ROOT/work/generated/l5_matrix_rev8b_a/operand_distribution/accepted" ]] || { echo 'operand distribution not accepted' >&2; exit 4; }
mkdir -p "$GEN" "$RES"

run_one() {
  local effort=$1 high=$2
  local out="$RES/$effort"
  mkdir -p "$out"
  set +e
  MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" \
    timeout --foreground --signal=INT --kill-after=30s 600s env \
    TOP_RTL="$TOP" FRONT_DDC="$FRONT" BROADCAST_DDC="$BROADCAST" OPERAND_DDC="$OPERAND" \
    CLUSTER_DDC="$CLUSTER" GLUE_DDC="$GLUE" STD_CELL_DB="$DB" \
    OUT_DIR="$out" DDC_OUT="$GEN/bf16_outer_product_context_array_rev8b_a_candidate.ddc" \
    CLOCK_PERIOD_NS=1.0 DC_MAX_CORES=8 DC_TIMING_HIGH_EFFORT="$high" \
    "$DC" -64bit -f "$ROOT/dc/synth_l5_bf16_context_top_rev8b_a.tcl" \
    >"$out/dc.log" 2>&1
  rc=$?; set -e
  printf 'exit_code=%s\n' "$rc" >"$out/run.meta"
  if (( rc==124 || rc==130 || rc==137 )); then return 75; fi
  return "$rc"
}

audit() {
  python3 - "$1" <<'PY'
from pathlib import Path
import json,re,sys
d=Path(sys.argv[1]);s=dict(x.split('=',1) for x in (d/'status.txt').read_text().splitlines() if '=' in x);q=(d/'qor.rpt').read_text(errors='replace')
def metric(label):
 m=re.search(rf'{re.escape(label)}\s*:\s*([0-9]+)',q);return int(m.group(1)) if m else None
r={'wns_ns':float(s['WORST_SLACK_NS']),'unmapped':int(s['UNMAPPED_CELLS']),'unresolved':int(s['UNRESOLVED_REFERENCES']),'front':int(s['FRONT_CONTROL_INSTANCES']),'broadcast':int(s['BROADCAST32_INSTANCES']),'operand':int(s['OPERAND_DISTRIBUTION_INSTANCES']),'clusters':int(s['CLUSTER16_INSTANCES']),'lanes':int(s['PHYSICAL_LANES']),'glue':int(s['GLUE_INSTANCES']),'max_transition':metric('Max Trans Violations'),'max_cap':metric('Max Cap Violations')}
print(json.dumps(r,sort_keys=True))
if None in (r['max_transition'],r['max_cap']):raise SystemExit(5)
if r['unmapped'] or r['unresolved'] or (r['front'],r['broadcast'],r['operand'],r['clusters'],r['lanes'],r['glue'])!=(1,1,1,32,512,1):raise SystemExit(4)
raise SystemExit(0 if r['wns_ns']>=0 and r['max_transition']==0 and r['max_cap']==0 else 10)
PY
}

rm -f "$DECISION"
run_one normal 0
set +e; audit "$RES/normal"; rc=$?; set -e
if (( rc==0 )); then chosen="$RES/normal"; final_rc=0
elif (( rc==10 )); then
  run_one high 1
  set +e; audit "$RES/high"; final_rc=$?; set -e
  chosen="$RES/high"
else exit "$rc"
fi
python3 - "$chosen" "$DECISION" "$final_rc" <<'PY'
from pathlib import Path
import json,re,sys
d,out,rc=Path(sys.argv[1]),Path(sys.argv[2]),int(sys.argv[3]);s=dict(x.split('=',1) for x in (d/'status.txt').read_text().splitlines() if '=' in x);q=(d/'qor.rpt').read_text(errors='replace')
def metric(label):
 m=re.search(rf'{re.escape(label)}\s*:\s*([0-9]+)',q);return int(m.group(1)) if m else None
wns=float(s['WORST_SLACK_NS']);trans=metric('Max Trans Violations');cap=metric('Max Cap Violations')
if rc==0:decision='REVISION8B_A_PASS'
elif trans==0 and cap==0 and wns<0:decision='TRIGGER_REVISION8B_B_5STAGE_5CONTEXT'
else:decision='REVISION8B_A_DRC_NOT_ELIMINATED'
r={'schema_version':1,'status':'PASS' if rc==0 else 'FAIL','decision':decision,'revision':'8B-A','wns_ns':wns,'max_transition_violations':trans,'max_cap_violations':cap,'unmapped':int(s['UNMAPPED_CELLS']),'unresolved':int(s['UNRESOLVED_REFERENCES']),'effort':d.name}
out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print(json.dumps(r,indent=2,sort_keys=True))
PY
if (( final_rc==0 )); then
  cp "$chosen/status.txt" "$RES/accepted_status.txt"
  cp "$chosen/qor.rpt" "$RES/accepted_qor.rpt"
  printf 'accepted=1\n' >"$GEN/accepted"
else
  exit 10
fi
