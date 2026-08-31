#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);DB=${STD_CELL_DB:-/home/yang/tools/arm/tsmc/cln22ul/sc6p5mcpp140z_base_svt_c35/r3p0/db/sc6p5mcpp140z_cln22ul_base_svt_c35_tt_typical_max_0p80v_25c.db};DC=${DC_SHELL:-/home/yang/tools/synopsys/syn/X-2025.06-SP3/bin/dc_shell};OUT=${OUT:-$ROOT/work/results/l5_blocked_attention_controller_dc};mkdir -p "$OUT"
TOP=blocked_attention_stream_controller RTL_FILELIST="$ROOT/dc/filelists/l5_blocked_attention_controller.f" STD_CELL_DBS="$DB" CLOCK_PERIOD_NS=1.0 CLOCK_PORT=clk_i OUT_DIR="$OUT" DC_MAX_CORES=8 DC_TIMING_HIGH_EFFORT=1 MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$ROOT/scripts/run_memory_capped.sh" timeout --foreground --signal=INT --kill-after=30s 600s "$DC" -64bit -f "$ROOT/dc/synth_22nm.tcl">"$OUT/dc.log" 2>&1
python3 - "$OUT/status.txt" <<'PY'
import sys
f=dict(line.strip().split('=',1) for line in open(sys.argv[1]) if '=' in line);u=int(f['UNMAPPED_CELLS']);w=float(f['WORST_SLACK_NS'])
if u or w<0:raise SystemExit(f'L5_ATTENTION_CONTROLLER_DC_FAIL WNS={w} unmapped={u}')
print(f'L5_ATTENTION_CONTROLLER_DC_PASS WNS={w}')
PY
