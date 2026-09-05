#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
test "$(df --output=avail -k . | tail -1)" -gt 52428800
OUT=$ROOT/work/results/checkpoint_continuity
mkdir -p "$OUT"
run() { MIN_AVAILABLE_KIB=10485760 "$ROOT/scripts/run_memory_capped.sh" timeout 600 "$@"; }
run vcs -full64 -sverilog -debug_access+r -top tb_checkpoint_continuity \
  -Mdir="$OUT/csrc" -o "$OUT/simv" tb/tb_checkpoint_continuity.sv >"$OUT/build.log" 2>&1
run "$OUT/simv" | tee "$OUT/baseline.log" | rg 'CONTINUITY_PASS|Fatal:|Error'
run "$OUT/simv" -ucli -do scripts/checkpoint_save_smoke.tcl | tee "$OUT/save.log"
! rg 'Error-\[|Error:|Fatal:' "$OUT/save.log"
test -s "$OUT/first.chk"
run "$OUT/simv" -ucli -do scripts/checkpoint_restore_smoke.tcl | tee "$OUT/restored.log" | rg 'CONTINUITY_PASS|CHECKPOINT_RESTORED_CYCLE|Fatal:|Error'
baseline_marker=$(rg '^SAVE_RESTORE_CONTINUITY_PASS' "$OUT/baseline.log")
restored_marker=$(rg '^SAVE_RESTORE_CONTINUITY_PASS' "$OUT/restored.log")
test "$baseline_marker" = "$restored_marker"
rg -q '^CHECKPOINT_RESTORED_CYCLE 78$' "$OUT/restored.log"
test "$(rg -c '^CHECK_STATE_' "$OUT/baseline.log")" = 235
cmp <(rg '^CHECK_STATE_' "$OUT/baseline.log") <(rg '^CHECK_STATE_' "$OUT/restored.log")
echo CHECKPOINT_CONTINUITY_CROSS_PROCESS_PASS
