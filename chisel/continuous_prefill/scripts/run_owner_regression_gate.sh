#!/usr/bin/env bash
# Fixed execution-only regression. No source, generated RTL, or old result edits.
# tiny: complete protocol/tail/address/request/99-fault/multilayer suite.
# real-cross: real H1536/F8960, 17-token relocated original Host graph only.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
P="$ROOT/chisel/continuous_prefill"
PROFILE=${1:?tiny|real-cross}
OUT=${2:?absolute NEW output directory}
[[ "$PROFILE" = tiny || "$PROFILE" = real-cross ]] || exit 2
[[ "$OUT" = /* && ! -e "$OUT" ]] || exit 2
for tool in python3 java g++ git; do
  command -v "$tool" >/dev/null || { echo "BLOCKED_MISSING_TOOL:$tool"; exit 77; }
done
python3 -c 'import numpy,yaml' || { echo BLOCKED_PYTHON_DEPENDENCIES; exit 77; }
[[ -n ${IDMA_EXPORT:-} && -f "$IDMA_EXPORT/idma.f.in" ]] || { echo BLOCKED_PINNED_IDMA; exit 77; }
mkdir -p "$OUT"
trap 'code=$?;echo "$code" > "$OUT/gate.exit";exit "$code"' EXIT
git -C "$ROOT" rev-parse HEAD > "$OUT/source_commit.txt"
if [[ "$PROFILE" = real-cross ]]; then
  bash "$P/scripts/run_host_block_gate.sh" real "$OUT/real17" 17 9467985920
  python3 "$P/scripts/audit_owner_block_abi.py" "$OUT/real17" --output "$OUT/real17/PUBLIC_ABI.json"
  python3 "$P/scripts/seal_owner_regression.py" --repo "$ROOT" --root "$OUT" --profile real-cross
  exit 0
fi
bash "$P/scripts/run_host_block_unit.sh" "$OUT/unit"
bash "$P/scripts/run_host_block_gate.sh" tiny "$OUT/base17" 17
source "$P/scripts/prepare_verilator_runtime.sh" "$OUT"
replay() {
  local name=$1; shift
  python3 "$P/scripts/run_owner_replay_gate.py" --repo "$ROOT" --build "$OUT/base17" --output "$OUT/$name" "$@" > "$OUT/${name}_console.log" 2>&1
}
replay relocated32 --tokens 32 --relocate 9467985920 --swap --seed 77331
replay relocated33 --tokens 33 --relocate 9467985920 --swap --seed 928337
replay high48_33 --tokens 33 --relocate 281474976710656 --swap --seed 901921
python3 "$P/scripts/run_owner_lifecycle_gate.py" --repo "$ROOT" --build "$OUT/base17" --output "$OUT/repeat" --case repeat:0 --seed 88821 > "$OUT/repeat_console.log" 2>&1
# QK/Softmax logical tensors do not have standalone payload operations. The
# fused physical Attention owner is PC12, while metadata faults cover all PCs.
for group in metadata payload; do
  ARGS=()
  if [[ "$group" = metadata ]]; then MODES=(command-read-error descriptor-read-error);else MODES=(read-error write-error last-write-error);fi
  for mode in "${MODES[@]}";do
    for ((pc=0;pc<21;pc++));do
      if [[ "$group" = payload && ( "$pc" = 10 || "$pc" = 11 ) ]];then continue;fi
      ARGS+=(--case "$mode:$pc")
    done
  done
  python3 "$P/scripts/run_owner_lifecycle_gate.py" --repo "$ROOT" --build "$OUT/base17" --output "$OUT/fault_$group" "${ARGS[@]}" --seed 909100 > "$OUT/fault_${group}_console.log" 2>&1
 done
replay layers2_17 --tokens 17 --layers 2 --relocate 9467985920 --seed 925173
replay layers3_33 --tokens 33 --layers 3 --relocate 9467985920 --seed 625173
export OWNER_STACK_EVIDENCE="$OUT/layers3_33" OWNER_TEST_ARTIFACTS="$OUT/negative_artifacts"
python3 "$P/tests/test_owner_extended_regression.py" > "$OUT/python_tests.log" 2>&1
python3 -O "$P/tests/test_owner_extended_regression.py" > "$OUT/python_optimized_tests.log" 2>&1
python3 "$P/scripts/seal_owner_regression.py" --repo "$ROOT" --root "$OUT" --profile tiny
