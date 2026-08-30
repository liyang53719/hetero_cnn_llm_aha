#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd);R="$ROOT/scripts/run_memory_capped.sh";DC=${DC_SHELL:-/home/yang/tools/synopsys/syn/X-2025.06-SP3/bin/dc_shell}
DB=${STD_CELL_DB:-/home/yang/tools/arm/tsmc/cln22ul/sc6p5mcpp140z_base_svt_c35/r3p0/db/sc6p5mcpp140z_cln22ul_base_svt_c35_tt_typical_max_0p80v_25c.db}
GENRTL="$ROOT/work/generated/l5_all_primitives/HeteroAllPrimitives.sv";RTL="$ROOT/rtl/matrix/candidates/rev8b_b/bf16_context_fma_pipeline_lane5_rev8b_b_candidate.sv"
GEN="$ROOT/work/generated/l5_matrix_rev8b_b/lane";RES="$ROOT/work/results/l5_matrix_rev8b_b/lane";mkdir -p "$GEN" "$RES/normal" "$RES/high";"$ROOT/scripts/generate_all_hardfloat_primitives.sh"
run_dc(){ local out=$1 high=$2;rm -f "$out/status.txt";MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" timeout --foreground --signal=INT --kill-after=30s 600s env GENERATED_SV="$GENRTL" LANE_RTL="$RTL" STD_CELL_DB="$DB" OUT_DIR="$out" DDC_OUT="$GEN/bf16_context_fma_pipeline_lane5_rev8b_b_candidate.ddc" NETLIST_OUT="$GEN/bf16_context_fma_pipeline_lane5_rev8b_b_candidate.mapped.v" SDC_OUT="$GEN/bf16_context_fma_pipeline_lane5_rev8b_b_candidate.sdc" DC_TIMING_HIGH_EFFORT="$high" "$DC" -64bit -f "$ROOT/dc/synth_l5_bf16_context_lane5_rev8b_b.tcl" >"$out/dc.log" 2>&1;[[ -s "$out/status.txt" ]]||{ tail -80 "$out/dc.log" >&2;return 4;};}
audit(){ python3 - "$1" <<'PY'
from pathlib import Path
import re,sys
d=Path(sys.argv[1]);s=dict(x.split('=',1) for x in (d/'status.txt').read_text().splitlines() if '=' in x);q=(d/'qor.rpt').read_text(errors='replace')
def m(x):
 z=re.search(rf'{re.escape(x)}\s*:\s*([0-9]+)',q);return int(z.group(1)) if z else 0
w=float(s['WORST_SLACK_NS']);print(f'REV8B_B_LANE5 EFFORT={s["EFFORT"]} WNS={w} TRANS={m("Max Trans Violations")} CAP={m("Max Cap Violations")}')
if s['UNMAPPED_CELLS']!='0':raise SystemExit(4)
raise SystemExit(0 if w>=0 and m('Max Trans Violations')==0 and m('Max Cap Violations')==0 else 10)
PY
}
run_dc "$RES/normal" 0;set +e;audit "$RES/normal";rc=$?;set -e
if ((rc==0));then chosen="$RES/normal";elif ((rc==10));then run_dc "$RES/high" 1;audit "$RES/high";chosen="$RES/high";else exit "$rc";fi
cp "$chosen/status.txt" "$RES/accepted_status.txt";cp "$chosen/qor.rpt" "$RES/accepted_qor.rpt";printf 'accepted=1\n' >"$GEN/accepted"
