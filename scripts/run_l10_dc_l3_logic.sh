#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
DB=${STD_CELL_DB:-/home/yang/tools/arm/tsmc/cln22ul/sc6p5mcpp140z_base_svt_c35/r3p0/db/sc6p5mcpp140z_cln22ul_base_svt_c35_tt_typical_max_0p80v_25c.db}
OUT=${OUT:-$ROOT/work/results/l10_dc_readiness}
DC=${DC_SHELL:-/home/yang/tools/synopsys/syn/X-2025.06-SP3/bin/dc_shell}
mkdir -p "$OUT"

run_top() {
  local top=$1 filelist=$2 out_dir=$OUT/$top
  mkdir -p "$out_dir"
  TOP=$top RTL_FILELIST=$ROOT/$filelist STD_CELL_DBS=$DB \
  CLOCK_PERIOD_NS=1.0 CLOCK_PORT=clk_i OUT_DIR=$out_dir DC_MAX_CORES=4 \
  MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G \
    "$ROOT/scripts/run_memory_capped.sh" "$DC" -64bit -f "$ROOT/dc/synth_22nm.tcl" \
    >"$OUT/$top.dc.log" 2>&1
  grep -q '^UNMAPPED_CELLS=0$' "$out_dir/status.txt"
}

run_top matrix_direct_streams dc/filelists/matrix_direct_streams.f
run_top command_event_scoreboard dc/filelists/event_scoreboard.f
echo L10_DC_L3_LOGIC_GATE_PASS
