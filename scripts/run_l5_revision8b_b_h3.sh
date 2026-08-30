#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd);R="$ROOT/scripts/run_memory_capped.sh";DC=${DC_SHELL:-/home/yang/tools/synopsys/syn/X-2025.06-SP3/bin/dc_shell}
DB=${STD_CELL_DB:-/home/yang/tools/arm/tsmc/cln22ul/sc6p5mcpp140z_base_svt_c35/r3p0/db/sc6p5mcpp140z_cln22ul_base_svt_c35_tt_typical_max_0p80v_25c.db}
GEN="$ROOT/work/generated/l5_matrix_rev8b_b";RES="$ROOT/work/results/l5_matrix_rev8b_b/top";mkdir -p "$GEN/top" "$RES";rm -f "$RES/status.txt"
for f in "$GEN/lane/accepted" "$GEN/cluster16/accepted" "$GEN/front/accepted" "$GEN/broadcast32/accepted" "$GEN/flags_glue32/accepted" "$ROOT/work/generated/l5_matrix_rev8b_a/operand_distribution/accepted";do [[ -s "$f" ]]||{ echo "missing $f" >&2;exit 4;};done
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" timeout --foreground --signal=INT --kill-after=30s 600s env \
 TOP_RTL="$ROOT/rtl/matrix/candidates/rev8b_b/bf16_outer_product_context_array_rev8b_b_candidate.sv" \
 FRONT_DDC="$GEN/front/bf16_context_front_control5_rev8b_b_candidate.ddc" BROADCAST_DDC="$GEN/broadcast32/bf16_front_to_cluster_broadcast32_rev8b_b_candidate.ddc" \
 OPERAND_DDC="$ROOT/work/generated/l5_matrix_rev8b_a/operand_distribution/bf16_operand_distribution512_rev8b_a_candidate.ddc" CLUSTER_DDC="$GEN/cluster16/bf16_context_lane_cluster16_rev8b_b_candidate.ddc" \
 GLUE_DDC="$ROOT/work/generated/l5_matrix_hier_dc/shell/bf16_outer_product_array_glue512.ddc" STD_CELL_DB="$DB" OUT_DIR="$RES" DDC_OUT="$GEN/top/bf16_outer_product_context_array_rev8b_b_candidate.ddc" \
 FLAGS_GLUE_DDC="$GEN/flags_glue32/bf16_cluster_flags_glue32_rev8b_b_candidate.ddc" \
 "$DC" -64bit -f "$ROOT/dc/synth_l5_bf16_context_top_rev8b_b.tcl" >"$RES/dc.log" 2>&1
[[ -s "$RES/status.txt" ]]||{ tail -100 "$RES/dc.log" >&2;exit 4;}
taskset -c 8-23 python3 - "$RES" "$ROOT/reports/execution/l5_revision8b_b_h3_result.json" <<'PY'
from pathlib import Path
import json,re,sys
d,out=Path(sys.argv[1]),Path(sys.argv[2]);s=dict(x.split('=',1) for x in (d/'status.txt').read_text().splitlines() if '=' in x);q=(d/'qor.rpt').read_text(errors='replace')
def m(x):
 z=re.search(rf'{re.escape(x)}\s*:\s*([0-9]+)',q);return int(z.group(1)) if z else 0
r={'schema_version':1,'revision':'8B-B','status':'PASS' if float(s['WORST_SLACK_NS'])>=0 and m('Max Trans Violations')==0 and m('Max Cap Violations')==0 else 'FAIL','wns_ns':float(s['WORST_SLACK_NS']),'max_transition':m('Max Trans Violations'),'max_cap':m('Max Cap Violations'),'unmapped':int(s['UNMAPPED_CELLS']),'unresolved':int(s['UNRESOLVED_REFERENCES']),'clusters':int(s['CLUSTER16_INSTANCES']),'lanes':int(s['PHYSICAL_LANES'])}
out.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print(json.dumps(r,indent=2,sort_keys=True));raise SystemExit(0 if r['status']=='PASS' else 10)
PY
