#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);DB=${STD_CELL_DB:-/home/yang/tools/arm/tsmc/cln22ul/sc6p5mcpp140z_base_svt_c35/r3p0/db/sc6p5mcpp140z_cln22ul_base_svt_c35_tt_typical_max_0p80v_25c.db};DC=${DC_SHELL:-/home/yang/tools/synopsys/syn/X-2025.06-SP3/bin/dc_shell};OUT=${OUT:-$ROOT/work/results/l5_fp32_pipelines/dc_mul};mkdir -p "$OUT"
TOP=HeteroFP32MulPipeTag12 RTL_FILELIST="$ROOT/dc/filelists/l5_fp32_mul_pipe.f" STD_CELL_DBS="$DB" CLOCK_PERIOD_NS=1.0 CLOCK_PORT=clock OUT_DIR="$OUT" DC_MAX_CORES=8 MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$ROOT/scripts/run_memory_capped.sh" "$DC" -64bit -f "$ROOT/dc/synth_22nm.tcl">"$OUT/dc.log" 2>&1
grep -q '^UNMAPPED_CELLS=0$' "$OUT/status.txt";taskset -c 8-23 python3 - "$OUT/status.txt" <<'PY'
import sys
f=dict(line.strip().split('=',1) for line in open(sys.argv[1]) if '=' in line);w=float(f['WORST_SLACK_NS'])
if w<0:raise SystemExit(f'L5_FP32_MUL_PIPE_DC_TIMING_FAIL WNS={w}')
print(f'L5_FP32_MUL_PIPE_DC_PASS WNS_NS={w} UNMAPPED=0')
PY
