#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);DB=${STD_CELL_DB:-/home/yang/tools/arm/tsmc/cln22ul/sc6p5mcpp140z_base_svt_c35/r3p0/db/sc6p5mcpp140z_cln22ul_base_svt_c35_tt_typical_max_0p80v_25c.db};DC=${DC_SHELL:-/home/yang/tools/synopsys/syn/X-2025.06-SP3/bin/dc_shell};OUT=${OUT:-$ROOT/work/results/l5_block32_softmax_weight_dc};mkdir -p "$OUT";"$ROOT/scripts/generate_all_hardfloat_primitives.sh"
TOP=fp32_block32_softmax_weights RTL_FILELIST="$ROOT/dc/filelists/l5_block32_softmax_weight.f" STD_CELL_DBS="$DB" CLOCK_PERIOD_NS=1.0 CLOCK_PORT=clk_i OUT_DIR="$OUT" DC_MAX_CORES=8 DC_TIMING_HIGH_EFFORT=1 MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$ROOT/scripts/run_memory_capped.sh" timeout --foreground --signal=INT --kill-after=30s 600s "$DC" -64bit -f "$ROOT/dc/synth_22nm.tcl">"$OUT/dc.log" 2>&1
taskset -c 8-23 python3 - "$OUT" <<'PY'
from pathlib import Path
import re,sys
d=Path(sys.argv[1]);s=dict(x.split('=',1) for x in (d/'status.txt').read_text().splitlines() if '=' in x);q=(d/'qor.rpt').read_text(errors='replace');m=re.search(r'Cell Area:\s*([0-9.]+)',q);w=float(s['WORST_SLACK_NS']);u=int(s['UNMAPPED_CELLS']);area=float(m.group(1)) if m else None
print(f'L5_BLOCK32_WEIGHT_DC WNS={w} AREA={area} UNMAPPED={u}')
if u or w<0:raise SystemExit(10)
PY
