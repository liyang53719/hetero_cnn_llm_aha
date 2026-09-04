#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
DB=/home/yang/tools/arm/tsmc/cln22ul/sc6p5mcpp140z_base_svt_c35/r3p0/db/sc6p5mcpp140z_cln22ul_base_svt_c35_tt_typical_max_0p80v_25c.db
DC=/home/yang/tools/synopsys/syn/X-2025.06-SP3/bin/dc_shell
GEN="$ROOT/generated/operator_primitives_v3/primitives"
# Keep the canonical 25-module gate isolated from historical exploratory FP32
# subdirectories so the collector cannot silently widen the inventory.
OUT="$ROOT/work/results/operator_dc_800mhz/primitives_authoritative"
mkdir -p "$OUT"
failed=0
while IFS=$'\t' read -r key top; do
  rtl="$GEN/$key.sv"
  run="$OUT/$key"
  mkdir -p "$run"
  if [[ ${RESUME:-0} == 1 && -s "$run/status.txt" ]]; then
    continue
  fi
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
done < <(/usr/bin/python3 - "$GEN/rtl_generation_audit.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1]))
for key in sorted(d['modules']):
    print(f"{key}\t{d['modules'][key]['declared_modules'][-1]}")
PY
)
"$ROOT/scripts/collect_operator_dc_800mhz.py" primitives "$OUT" \
  "$ROOT/reports/execution/OPERATOR_PRIMITIVE_DC_800MHZ.json"
exit "$failed"
