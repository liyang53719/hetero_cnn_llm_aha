#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
DB=/home/yang/tools/arm/tsmc/cln22ul/sc6p5mcpp140z_base_svt_c35/r3p0/db/sc6p5mcpp140z_cln22ul_base_svt_c35_tt_typical_max_0p80v_25c.db
DC=/home/yang/tools/synopsys/syn/X-2025.06-SP3/bin/dc_shell
OUT="$ROOT/work/results/operator_dc_800mhz/roots"
mkdir -p "$OUT"
failed=0
for rtl in "$ROOT"/generated/operator_primitives_v3/roots/*.sv; do
  top=$(basename "$rtl" .sv)
  run="$OUT/$top"
  mkdir -p "$run"
  set +e
  MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G \
    "$ROOT/scripts/run_memory_capped.sh" \
    timeout --foreground --signal=INT --kill-after=30s 600s \
    env TOP="$top" RTL_FILES="$rtl" STD_CELL_DB="$DB" CLOCK_PORT=clock \
    OUT_DIR="$run" "$DC" -64bit -f "$ROOT/dc/synth_operator_module_800mhz.tcl" \
    >"$run/dc.log" 2>&1
  rc=$?
  set -e
  if [[ $rc -ne 0 || ! -s "$run/status.txt" ]]; then
    printf 'STATUS=FAIL_TOOL\nTOP=%s\nEXIT_CODE=%s\n' "$top" "$rc" > "$run/status.txt"
    failed=1
  elif ! grep -q '^STATUS=PASS$' "$run/status.txt"; then
    failed=1
  fi
done
"$ROOT/scripts/collect_operator_dc_800mhz.py" roots "$OUT" \
  "$ROOT/reports/execution/OPERATOR_ROOT_DC_800MHZ.json"
exit "$failed"
