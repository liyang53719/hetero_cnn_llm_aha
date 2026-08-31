#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);OUT=${OUT:-$ROOT/work/results/l5_fp32_rsqrt_nr2_dc};R=$ROOT/scripts/run_memory_capped.sh;DC=${DC_SHELL:-/home/yang/tools/synopsys/syn/X-2025.06-SP3/bin/dc_shell};DB=${STD_CELL_DB:-/home/yang/tools/arm/tsmc/cln22ul/sc6p5mcpp140z_base_svt_c35/r3p0/db/sc6p5mcpp140z_cln22ul_base_svt_c35_tt_typical_max_0p80v_25c.db};mkdir -p "$OUT";rm -f "$OUT/status.txt"
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" timeout --foreground --signal=INT --kill-after=30s 600s env GENERATED_SV="$ROOT/work/generated/l5_all_primitives/HeteroAllPrimitives.sv" BASE_RTL="$ROOT/rtl/sfu/fp32_rsqrt_nr.sv" REFINED_RTL="$ROOT/rtl/sfu/fp32_rsqrt_nr2.sv" STD_CELL_DB="$DB" OUT_DIR="$OUT" "$DC" -64bit -f "$ROOT/dc/synth_l5_fp32_rsqrt_nr2.tcl" >"$OUT/dc.log" 2>&1
python3 - "$OUT" <<'PY'
from pathlib import Path
import re,sys
d=Path(sys.argv[1]);s=dict(x.split('=',1)for x in(d/'status.txt').read_text().splitlines()if'='in x);q=(d/'qor.rpt').read_text(errors='replace')
def n(k):
 m=re.search(rf'{re.escape(k)}\s*:\s*([0-9]+)',q);return int(m.group(1))if m else 0
w=float(s['WORST_SLACK_NS']);am=re.search(r'Cell Area:\s*([0-9.]+)',q);r={'wns_ns':w,'area':float(am.group(1))if am else 0.0,'unmapped':int(s['UNMAPPED_CELLS']),'unresolved':int(s['UNRESOLVED_REFERENCES']),'max_transition_violations':n('Max Trans Violations'),'max_capacitance_violations':n('Max Cap Violations')};print(r)
if w<0 or any(r[k]for k in('unmapped','unresolved','max_transition_violations','max_capacitance_violations')):raise SystemExit(1)
PY
