#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
R="$ROOT/scripts/run_memory_capped.sh"
DC=${DC_SHELL:-/home/yang/tools/synopsys/syn/X-2025.06-SP3/bin/dc_shell}
DB=${STD_CELL_DB:-/home/yang/tools/arm/tsmc/cln22ul/sc6p5mcpp140z_base_svt_c35/r3p0/db/sc6p5mcpp140z_cln22ul_base_svt_c35_tt_typical_max_0p80v_25c.db}
RTL="$ROOT/rtl/matrix/candidates/rev8b_a/bf16_front_to_cluster_broadcast32_rev8b_a_candidate.sv"
GEN="$ROOT/work/generated/l5_matrix_rev8b_a/broadcast32"
RES="$ROOT/work/results/l5_matrix_rev8b_a/broadcast32"
mkdir -p "$GEN" "$RES"

run_one() {
  local effort=$1 high=$2
  local out="$RES/$effort"
  mkdir -p "$out"
  MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" \
    timeout --foreground --signal=INT --kill-after=30s 600s env \
    BROADCAST_RTL="$RTL" STD_CELL_DB="$DB" OUT_DIR="$out" \
    DDC_OUT="$GEN/bf16_front_to_cluster_broadcast32_rev8b_a_candidate.ddc" \
    NETLIST_OUT="$GEN/bf16_front_to_cluster_broadcast32_rev8b_a_candidate.mapped.v" \
    SDC_OUT="$GEN/bf16_front_to_cluster_broadcast32_rev8b_a_candidate.sdc" \
    CLOCK_PERIOD_NS=1.0 DC_TIMING_HIGH_EFFORT="$high" \
    "$DC" -64bit -f "$ROOT/dc/synth_l5_bf16_broadcast32_rev8b_a.tcl" \
    >"$out/dc.log" 2>&1
}

check_one() {
  python3 - "$1" <<'PY'
from pathlib import Path
import re,sys
d=Path(sys.argv[1]); status=dict(x.split('=',1) for x in (d/'status.txt').read_text().splitlines() if '=' in x)
q=(d/'qor.rpt').read_text(errors='replace')
def metric(label):
 m=re.search(rf'{re.escape(label)}\s*:\s*([0-9]+)',q);return int(m.group(1)) if m else None
trans=metric('Max Trans Violations');cap=metric('Max Cap Violations')
wns=float(status['WORST_SLACK_NS']);cells=int(status['MAPPED_CELL_COUNT'])
print(f'REV8B_A_BROADCAST WNS={wns} CELLS={cells} MAX_TRANS={trans} MAX_CAP={cap}')
if status.get('LINK_STATUS')!='1' or status.get('UNMAPPED_CELLS')!='0' or cells<=0: raise SystemExit(4)
if trans is None or cap is None: raise SystemExit(5)
raise SystemExit(0 if wns>=0 and trans==0 and cap==0 else 10)
PY
}

run_one normal 0
set +e; check_one "$RES/normal"; rc=$?; set -e
if (( rc==10 )); then
  run_one high 1
  check_one "$RES/high"
  chosen="$RES/high"
elif (( rc==0 )); then
  chosen="$RES/normal"
else
  exit "$rc"
fi
cp "$chosen/status.txt" "$RES/accepted_status.txt"
cp "$chosen/qor.rpt" "$RES/accepted_qor.rpt"
printf 'accepted=1\n' >"$GEN/accepted"
