#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
OUT=$ROOT/work/results/group8_checkpoint
FIXTURES=$ROOT/work/results/qwen2_group8_pinned_idma
mkdir -p "$OUT"
test "$(df --output=avail -k . | tail -1)" -gt 52428800
run() { MIN_AVAILABLE_KIB=10485760 "$ROOT/scripts/run_memory_capped.sh" timeout 600 "$@"; }
run env CHECKPOINT_BUILD_ONLY=1 bash scripts/run_qwen2_group8_pinned_idma_vcs.sh
SIM=$ROOT/work/upstream/idma/target/sim/vcs/simv_group8_checkpoint
ARGS=(+PROJECTION=1 +BATCHES=2 +COMMANDS="$FIXTURES/projection_commands.memh" +RECORDS="$FIXTURES/records.memh" +ADDR="$FIXTURES/projection_addresses.memh" +NEXT_NORM="$ROOT/work/results/qwen2_true_rows16_31/norm_token_major.memh" +NEXT_EXPECTED="$ROOT/work/results/qwen2_true_rows16_31_projection/k_expected_token_major.memh")
run "$SIM" "${ARGS[@]}" | tee "$OUT/baseline.log"
run "$SIM" "${ARGS[@]}" -ucli -do scripts/checkpoint_group8_save.tcl | tee "$OUT/save.log"
! rg 'Error-\[|Error:|Fatal:' "$OUT/save.log"
test -s "$OUT/k.chk"
run "$SIM" "${ARGS[@]}" -ucli -do scripts/checkpoint_group8_restore.tcl | tee "$OUT/restored.log"
baseline_marker=$(rg '^GROUP8_PINNED_IDMA_NUMERICAL_PASS' "$OUT/baseline.log")
restored_marker=$(rg '^GROUP8_PINNED_IDMA_NUMERICAL_PASS' "$OUT/restored.log")
test "$baseline_marker" = "$restored_marker"
saved_cycle=$(sed -n 's/^GROUP8_CHECKPOINT_SAVED_CYCLE //p' "$OUT/save.log")
restored_cycle=$(sed -n 's/^GROUP8_CHECKPOINT_RESTORED_CYCLE //p' "$OUT/restored.log")
test -n "$saved_cycle" && test "$saved_cycle" = "$restored_cycle"
echo GROUP8_REAL_CHECKPOINT_CONTINUITY_PASS
run "$SIM" "${ARGS[@]}" -ucli -do scripts/checkpoint_group8_matrix_save.tcl | tee "$OUT/matrix_save.log"
! rg 'Error-\[|Error:|Fatal:' "$OUT/matrix_save.log"
test -s "$OUT/matrix.chk"
run "$SIM" "${ARGS[@]}" -ucli -do scripts/checkpoint_group8_matrix_restore.tcl | tee "$OUT/matrix_restored.log"
matrix_marker=$(rg '^GROUP8_PINNED_IDMA_NUMERICAL_PASS' "$OUT/matrix_restored.log")
test "$baseline_marker" = "$matrix_marker"
test "$(sed -n 's/^GROUP8_CHECKPOINT_SAVED_CYCLE //p' "$OUT/matrix_save.log")" = "$(sed -n 's/^GROUP8_CHECKPOINT_RESTORED_CYCLE //p' "$OUT/matrix_restored.log")"
test "$(sed -n 's/^GROUP8_CHECKPOINT_PARTIAL_K //p' "$OUT/matrix_save.log")" = "$(sed -n 's/^GROUP8_CHECKPOINT_RESTORED_K //p' "$OUT/matrix_restored.log")"
echo GROUP8_MATRIX_CHECKPOINT_CONTINUITY_PASS
! rg 'Error-\[|Error:|Fatal:' "$OUT/baseline.log" "$OUT/restored.log" "$OUT/matrix_restored.log"
