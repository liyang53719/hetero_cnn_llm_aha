#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);DB=${STD_CELL_DB:-/home/yang/tools/arm/tsmc/cln22ul/sc6p5mcpp140z_base_svt_c35/r3p0/db/sc6p5mcpp140z_cln22ul_base_svt_c35_tt_typical_max_0p80v_25c.db};DC=${DC_SHELL:-/home/yang/tools/synopsys/syn/X-2025.06-SP3/bin/dc_shell};R=$ROOT/scripts/run_memory_capped.sh;"$ROOT/scripts/generate_all_hardfloat_primitives.sh"
for LANES in 1 2;do TOP=bf16_silu_mul_lut_${LANES}lane;OUT=${OUT_ROOT:-$ROOT/work/results/l5_silu_lut_dc}/lanes$LANES;mkdir -p "$OUT";TOP="$TOP" RTL_FILELIST="$ROOT/dc/filelists/l5_silu_lut.f" STD_CELL_DBS="$DB" CLOCK_PERIOD_NS=1.0 CLOCK_PORT=clk_i OUT_DIR="$OUT" DC_MAX_CORES=8 DC_TIMING_HIGH_EFFORT=1 MIN_AVAILABLE_KIB=4194304 MEMORY_HIGH=12G MEMORY_MAX=16G "$R" "$DC" -64bit -f "$ROOT/dc/synth_22nm.tcl">"$OUT/dc.log" 2>&1;python3 - "$OUT/status.txt" "$LANES" <<'PY'
import sys
f=dict(line.strip().split('=',1) for line in open(sys.argv[1]) if '=' in line);w=float(f['WORST_SLACK_NS']);u=int(f['UNMAPPED_CELLS'])
if u or w<0:raise SystemExit(f'L5_SILU_DC_FAIL lanes={sys.argv[2]} WNS={w} unmapped={u}')
print(f'L5_SILU_DC_PASS lanes={sys.argv[2]} WNS={w} area={f.get("CELL_AREA","NA")}')
PY
done
