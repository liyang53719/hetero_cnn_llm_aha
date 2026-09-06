#!/usr/bin/env bash
# Execute-only closure gate. All children run; no source or tolerance editing.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
P="$ROOT/chisel/continuous_prefill"
OUT=${1:?usage: run_host_command_acceptance.sh /absolute/new/output}
[[ "$OUT" = /* && ! -e "$OUT" ]] || { echo 'new absolute output required' >&2;exit 2; }
[[ -n ${IDMA_EXPORT:-} && -f "$IDMA_EXPORT/idma.f.in" ]] || { echo BLOCKED_PINNED_IDMA >&2;exit 77; }
mkdir -p "$OUT"
trap 'code=$?; printf "%s\n" "$code" >"$OUT/acceptance.exit";exit "$code"' EXIT
source "$P/scripts/prepare_verilator_runtime.sh" "$OUT"
BASE=$(git -C "$ROOT" rev-parse HEAD)
printf '%s\n' "$BASE" >"$OUT/source_commit.txt"
bash "$P/scripts/run_shared_frontend_unit.sh" "$OUT/unit" >"$OUT/unit_console.log" 2>&1
python3 "$P/tests/test_host_delivery_seal.py" >"$OUT/seal_tests.log" 2>&1
python3 -O "$P/tests/test_host_delivery_seal.py" >"$OUT/seal_optimized_tests.log" 2>&1
bash "$P/scripts/run_shared_command_gate.sh" commands "$OUT/commands" >"$OUT/commands_console.log" 2>&1
bash "$P/scripts/run_host_partial_failure_gate.sh" "$OUT/partial_failure" "$OUT/commands" >"$OUT/partial_console.log" 2>&1
bash "$P/scripts/run_shared_command_gate.sh" real "$OUT/real16" 16 >"$OUT/real16_console.log" 2>&1
python3 "$P/scripts/seal_host_command_delivery.py" --unit "$OUT/unit" --commands "$OUT/commands" \
  --real "$OUT/real16" --repo "$ROOT" --source-base "$BASE" --output "$OUT/ACCEPTANCE.json" \
  >"$OUT/seal.log" 2>&1
cat "$OUT/seal.log"
