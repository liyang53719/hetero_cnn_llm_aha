#!/usr/bin/env bash
set -euo pipefail

CHIPYARD_ROOT=${CHIPYARD_ROOT:?set CHIPYARD_ROOT to the cloned Chipyard directory}
OUT=${OUT:-"$PWD/work/results/gemmini_baseline"}
CONFIG=${GEMMINI_CONFIG:-GemminiRocketConfig}
RUN_SETUP=${RUN_SETUP:-0}
mkdir -p "$OUT"
exec > >(tee "$OUT/reproduce.log") 2>&1

if [[ ! -f "$CHIPYARD_ROOT/env.sh" ]]; then
  if [[ "$RUN_SETUP" != 1 ]]; then
    echo "Chipyard env.sh is absent. Re-run with RUN_SETUP=1 after installing Chipyard prerequisites." >&2
    exit 2
  fi
  (cd "$CHIPYARD_ROOT" && ./build-setup.sh)
fi

# shellcheck disable=SC1091
source "$CHIPYARD_ROOT/env.sh"
GEMMINI_ROOT="$CHIPYARD_ROOT/generators/gemmini"
test -d "$GEMMINI_ROOT"

git -C "$CHIPYARD_ROOT" rev-parse HEAD | tee "$OUT/chipyard.commit"
git -C "$GEMMINI_ROOT" rev-parse HEAD | tee "$OUT/gemmini.commit"
if [[ -n "$(git -C "$CHIPYARD_ROOT" status --porcelain)" ]]; then
  echo "Chipyard tree is dirty before baseline reproduction" >&2
  exit 3
fi

make -C "$GEMMINI_ROOT/software/libgemmini" install
(
  cd "$GEMMINI_ROOT/software/gemmini-rocc-tests"
  ./build.sh
)

MVIN=$(find "$GEMMINI_ROOT/software/gemmini-rocc-tests/build" -type f -name 'mvin_mvout-baremetal' | head -n1)
MATMUL=$(find "$GEMMINI_ROOT/software/gemmini-rocc-tests/build" -type f \( -name 'matmul-baremetal' -o -name 'matmul_os-baremetal' \) | head -n1)
RESNET=$(find "$GEMMINI_ROOT/software/gemmini-rocc-tests/build" -type f -name 'resnet50-baremetal' | head -n1)
test -n "$MVIN"
test -n "$MATMUL"

if command -v spike >/dev/null 2>&1; then
  spike --extension=gemmini "$MVIN" | tee "$OUT/spike_mvin.log"
  spike --extension=gemmini "$MATMUL" | tee "$OUT/spike_matmul.log"
  if [[ -n "$RESNET" ]]; then
    spike --extension=gemmini "$RESNET" | tee "$OUT/spike_resnet50.log"
  fi
else
  echo "spike is unavailable; functional baseline gate is not closed" >&2
  exit 4
fi

(
  cd "$CHIPYARD_ROOT/sims/verilator"
  make CONFIG="$CONFIG"
  make CONFIG="$CONFIG" run-binary BINARY="$MVIN" | tee "$OUT/verilator_mvin.log"
  make CONFIG="$CONFIG" run-binary BINARY="$MATMUL" | tee "$OUT/verilator_matmul.log"
)

GEN_DIR="$CHIPYARD_ROOT/sims/verilator/generated-src"
find "$GEN_DIR" -type f \( -name '*.v' -o -name '*.sv' \) -print0 \
  | sort -z | xargs -0 sha256sum > "$OUT/generated_rtl.sha256"

python3 - "$OUT" <<'PY'
import json, pathlib, sys
out=pathlib.Path(sys.argv[1])
required=["spike_mvin.log","spike_matmul.log","verilator_mvin.log","verilator_matmul.log","generated_rtl.sha256"]
missing=[x for x in required if not (out/x).exists() or (out/x).stat().st_size == 0]
status={"status":"PASS" if not missing else "FAIL","missing":missing}
(out/"result.json").write_text(json.dumps(status,indent=2)+"\n")
if missing: raise SystemExit(1)
PY

echo GEMMINI_BASELINE_PASS
