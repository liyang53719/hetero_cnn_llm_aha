#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);DB=${STD_CELL_DB:-/home/yang/tools/arm/tsmc/cln22ul/sc6p5mcpp140z_base_svt_c35/r3p0/db/sc6p5mcpp140z_cln22ul_base_svt_c35_tt_typical_max_0p80v_25c.db};DC=${DC_SHELL:-/home/yang/tools/synopsys/syn/X-2025.06-SP3/bin/dc_shell};MERGE=${MERGE_DDC:-$ROOT/work/results/l5_block128_rawpipe_candidate/dc/fp32_mlo_summary_merge_stream_rawpipe.ddc};OUT=${OUT:-$ROOT/work/results/l5_balanced_summary_scheduler/dc_bottomup};RUN=$ROOT/scripts/run_memory_capped.sh;mkdir -p "$OUT";test -f "$MERGE"
TOP=fp32_mlo_balanced_summary_scheduler RTL_FILELIST="$ROOT/dc/filelists/l5_balanced_summary_scheduler_top_only.f" PRECOMPILED_DDCS="$MERGE" DONT_TOUCH_REFS=fp32_mlo_summary_merge_stream_rawpipe STD_CELL_DBS="$DB" CLOCK_PERIOD_NS=1.0 CLOCK_PORT=clk_i OUT_DIR="$OUT" DC_MAX_CORES=8 DC_TIMING_HIGH_EFFORT=1 DC_SKIP_POWER=1 MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$RUN" timeout --foreground --signal=INT --kill-after=30s 600s taskset -c 8-23 "$DC" -64bit -f "$ROOT/dc/synth_22nm.tcl">"$OUT/dc.log" 2>&1
taskset -c 8-23 python3 - "$OUT/status.txt" <<'PY'
import sys
f=dict(line.strip().split('=',1)for line in open(sys.argv[1])if'='in line);w=float(f['WORST_SLACK_NS']);u=int(f['UNMAPPED_CELLS']);a=float(f['CELL_AREA'])
if u or w<0:raise SystemExit(f'BALANCED_SUMMARY_BOTTOMUP_DC_FAIL WNS={w} unmapped={u} area={a}')
print(f'BALANCED_SUMMARY_BOTTOMUP_DC_PASS WNS_NS={w} UNMAPPED={u} AREA={a}')
PY
