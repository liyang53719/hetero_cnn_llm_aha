#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
DB=${STD_CELL_DB:-/home/yang/tools/arm/tsmc/cln22ul/sc6p5mcpp140z_base_svt_c35/r3p0/db/sc6p5mcpp140z_cln22ul_base_svt_c35_tt_typical_max_0p80v_25c.db}
DC=${DC_SHELL:-/home/yang/tools/synopsys/syn/X-2025.06-SP3/bin/dc_shell}
BASE=${OUT:-$ROOT/work/results/l5_fp32_pipelines}

run_top() {
  local top=$1 filelist=$2 out=$3
  mkdir -p "$out"
  TOP="$top" RTL_FILELIST="$ROOT/$filelist" STD_CELL_DBS="$DB" \
  CLOCK_PERIOD_NS=1.0 CLOCK_PORT=clock OUT_DIR="$out" DC_MAX_CORES=8 \
  MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G \
    "$ROOT/scripts/run_memory_capped.sh" "$DC" -64bit \
    -f "$ROOT/dc/synth_22nm.tcl" >"$out/dc.log" 2>&1
  grep -q '^UNMAPPED_CELLS=0$' "$out/status.txt"
  taskset -c 8-23 python3 - "$out/status.txt" "$top" <<'PY'
import sys
fields = dict(line.strip().split('=', 1) for line in open(sys.argv[1]) if '=' in line)
wns = float(fields['WORST_SLACK_NS'])
if wns < 0:
    raise SystemExit(f'L5_FP32_PIPE_DC_TIMING_FAIL TOP={sys.argv[2]} WNS={wns}')
print(f'L5_FP32_PIPE_DC_PASS TOP={sys.argv[2]} WNS_NS={wns} UNMAPPED=0')
PY
}

run_top HeteroFP32MulPipeTag12 dc/filelists/l5_fp32_mul_pipe.f "$BASE/dc_mul"
run_top HeteroFP32AddPipeTag12 dc/filelists/l5_fp32_add_pipe.f "$BASE/dc_add"
echo L5_FP32_RAW_ROUND_PIPELINES_E4_PASS
