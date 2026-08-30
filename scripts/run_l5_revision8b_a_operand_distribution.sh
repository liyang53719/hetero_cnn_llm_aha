#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
R="$ROOT/scripts/run_memory_capped.sh"
DC=${DC_SHELL:-/home/yang/tools/synopsys/syn/X-2025.06-SP3/bin/dc_shell}
V=${VERILATOR:-$ROOT/work/toolchain/conda/bin/verilator}
DB=${STD_CELL_DB:-/home/yang/tools/arm/tsmc/cln22ul/sc6p5mcpp140z_base_svt_c35/r3p0/db/sc6p5mcpp140z_cln22ul_base_svt_c35_tt_typical_max_0p80v_25c.db}
RTL="$ROOT/rtl/matrix/candidates/rev8b_a/bf16_operand_distribution512_rev8b_a_candidate.sv"
TB="$ROOT/tb/tb_bf16_operand_distribution512_rev8b_a.sv"
GEN="$ROOT/work/generated/l5_matrix_rev8b_a/operand_distribution"
RES="$ROOT/work/results/l5_matrix_rev8b_a/operand_distribution"
mkdir -p "$GEN" "$RES/e1" "$RES/normal" "$RES/high"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" \
  timeout --foreground --signal=INT --kill-after=30s 600s "$V" --binary --timing \
  -Wall -Wno-DECLFILENAME -Wno-TIMESCALEMOD -Wno-WIDTH -Wno-UNUSEDSIGNAL \
  -j 8 -MAKEFLAGS "AR=/usr/bin/ar CXX=/usr/bin/g++" \
  --top-module tb_bf16_operand_distribution512_rev8b_a \
  --Mdir "$RES/e1/obj" -o tb "$RTL" "$TB" >"$RES/e1/build.log" 2>&1
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" \
  timeout --foreground --signal=INT --kill-after=30s 600s "$RES/e1/obj/tb" | tee "$RES/e1/tb.log"
grep -q 'L5_REV8B_A_OPERAND_DISTRIBUTION_E1_PASS operations=10000 lanes=512' "$RES/e1/tb.log"
run_dc() {
  local out=$1 high=$2
  MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" \
    timeout --foreground --signal=INT --kill-after=30s 600s env \
    OPERAND_RTL="$RTL" STD_CELL_DB="$DB" OUT_DIR="$out" \
    DDC_OUT="$GEN/bf16_operand_distribution512_rev8b_a_candidate.ddc" \
    NETLIST_OUT="$GEN/bf16_operand_distribution512_rev8b_a_candidate.mapped.v" \
    CLOCK_PERIOD_NS=1.0 DC_TIMING_HIGH_EFFORT="$high" \
    "$DC" -64bit -f "$ROOT/dc/synth_l5_bf16_operand_distribution512_rev8b_a.tcl" \
    >"$out/dc.log" 2>&1
}
audit_dc() { python3 - "$1" <<'PY'
from pathlib import Path
import re,sys
d=Path(sys.argv[1]);s=dict(x.split('=',1) for x in (d/'status.txt').read_text().splitlines() if '=' in x);q=(d/'qor.rpt').read_text(errors='replace')
def metric(label):
 m=re.search(rf'{re.escape(label)}\s*:\s*([0-9]+)',q);return int(m.group(1)) if m else None
w=float(s['WORST_SLACK_NS']);t=metric('Max Trans Violations');c=metric('Max Cap Violations');f=metric('Max Fanout Violations');f=0 if f is None else f;cells=int(s['MAPPED_CELL_COUNT'])
print(f'REV8B_A_OPERAND_DISTRIBUTION EFFORT={s.get("EFFORT")} WNS={w} CELLS={cells} MAX_TRANS={t} MAX_CAP={c} MAX_FANOUT={f}')
if s['UNMAPPED_CELLS']!='0' or cells<=0:raise SystemExit(4)
if w<0 or t!=0 or c!=0 or f!=0:raise SystemExit(10)
PY
}
if [[ -s "$RES/dc/status.txt" && ! -s "$RES/normal/status.txt" ]]; then
  cp "$RES/dc/status.txt" "$RES/normal/status.txt"
  cp "$RES/dc/qor.rpt" "$RES/normal/qor.rpt"
  cp "$RES/dc/constraint_violators.rpt" "$RES/normal/constraint_violators.rpt"
fi
if [[ ! -s "$RES/normal/status.txt" ]]; then run_dc "$RES/normal" 0; fi
set +e; audit_dc "$RES/normal"; rc=$?; set -e
if (( rc==0 )); then chosen="$RES/normal"
elif (( rc==10 )); then
  if [[ ! -s "$RES/high/status.txt" ]]; then run_dc "$RES/high" 1; fi
  audit_dc "$RES/high"
  chosen="$RES/high"
else exit "$rc"
fi
cp "$chosen/status.txt" "$RES/accepted_status.txt"
cp "$chosen/qor.rpt" "$RES/accepted_qor.rpt"
printf 'accepted=1\n' >"$GEN/accepted"
