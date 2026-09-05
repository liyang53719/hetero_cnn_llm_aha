#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
OUT=$ROOT/work/results/checkpoint_continuity
run() { MIN_AVAILABLE_KIB=10485760 "$ROOT/scripts/run_memory_capped.sh" timeout 600 "$@"; }
run "$OUT/simv" -ucli -do scripts/checkpoint_chain_save.tcl | tee "$OUT/chain_save.log"
run "$OUT/simv" -ucli -do scripts/checkpoint_chain_restore.tcl | tee "$OUT/chain_restored.log" | rg 'CHAIN_|CONTINUITY_PASS|Error|Fatal'
if rg 'Error:|Error-\[|Fatal:' "$OUT/chain_save.log" "$OUT/chain_restored.log"; then exit 1; fi
rg -q '^CHAIN_ENTRY 78$' "$OUT/chain_save.log"
rg -q '^CHAIN_SAVED 158$' "$OUT/chain_save.log"
rg -q '^CHAIN_RESTORED 158$' "$OUT/chain_restored.log"
test "$(rg -c '^CHECK_STATE_' "$OUT/chain_restored.log")" = 235
cmp <(rg '^CHECK_STATE_' "$OUT/baseline.log") <(rg '^CHECK_STATE_' "$OUT/chain_restored.log")
echo CHECKPOINT_CHAIN_PASS
