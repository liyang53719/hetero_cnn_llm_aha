#!/usr/bin/env bash
set -euo pipefail

CHIPYARD_ROOT=${CHIPYARD_ROOT:?set CHIPYARD_ROOT to the cloned Chipyard directory}
PROJECT_ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT=${OUT:-"$PWD/work/results/gemmini_baseline"}
CONFIG=${GEMMINI_CONFIG:-GemminiRocketConfig}
RUN_SETUP=${RUN_SETUP:-0}
SPIKE_BIN=${SPIKE_BIN:-spike}
SPIKE_LIB_DIR=${SPIKE_LIB_DIR:-}
GEMMINI_CNN_ARGS=${GEMMINI_CNN_ARGS:-os}
GEMMINI_LOADMEM=${GEMMINI_LOADMEM:-1}
mkdir -p "$OUT"
exec > >(tee "$OUT/reproduce.log") 2>&1

[[ "$GEMMINI_LOADMEM" == 1 ]] || {
  echo "GEMMINI_LOADMEM must remain 1 for the pinned full WS bare-metal path" >&2
  exit 2
}
export PATH="$PROJECT_ROOT/work/toolchain/conda/bin:$PROJECT_ROOT/work/toolchain/riscv/bin:$PATH"

run_spike() {
  if [[ -n "$SPIKE_LIB_DIR" ]]; then
    test -f "$SPIKE_LIB_DIR/libgemmini.so"
    test -f "$SPIKE_LIB_DIR/libcustomext.so"
    LD_LIBRARY_PATH="$SPIKE_LIB_DIR${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
      LD_PRELOAD="$SPIKE_LIB_DIR/libgemmini.so:$SPIKE_LIB_DIR/libcustomext.so${LD_PRELOAD:+:$LD_PRELOAD}" \
      "$SPIKE_BIN" --extension=gemmini "$@"
  else
    "$SPIKE_BIN" --extension=gemmini "$@"
  fi
}

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
MATMUL_OS=$(find "$GEMMINI_ROOT/software/gemmini-rocc-tests/build" -type f -name 'matmul_os-baremetal' | head -n1)
MATMUL_WS=$(find "$GEMMINI_ROOT/software/gemmini-rocc-tests/build" -type f -name 'matmul_ws-baremetal' | head -n1)
RESNET=$(find "$GEMMINI_ROOT/software/gemmini-rocc-tests/build" -type f -name 'resnet50-baremetal' | head -n1)
test -n "$MVIN"
test -n "$MATMUL_OS"
test -n "$MATMUL_WS"

if command -v "$SPIKE_BIN" >/dev/null 2>&1; then
  run_spike "$MVIN" | tee "$OUT/spike_mvin.log"
  run_spike "$MATMUL_OS" | tee "$OUT/spike_matmul_os.log"
  if [[ -n "$RESNET" ]]; then
    read -r -a cnn_args <<< "$GEMMINI_CNN_ARGS"
    run_spike "$RESNET" "${cnn_args[@]}" | tee "$OUT/spike_resnet50.log"
  fi
else
  echo "spike is unavailable; functional baseline gate is not closed" >&2
  exit 4
fi

(
  cd "$CHIPYARD_ROOT/sims/verilator"
  make CONFIG="$CONFIG"
  make CONFIG="$CONFIG" LOADMEM="$GEMMINI_LOADMEM" run-binary BINARY="$MVIN" | tee "$OUT/verilator_mvin.log"
  make CONFIG="$CONFIG" LOADMEM="$GEMMINI_LOADMEM" run-binary BINARY="$MATMUL_OS" | tee "$OUT/verilator_matmul_os.log"
  make CONFIG="$CONFIG" LOADMEM="$GEMMINI_LOADMEM" run-binary BINARY="$MATMUL_WS" | tee "$OUT/verilator_matmul_ws.log"
)

GEN_DIR="$CHIPYARD_ROOT/sims/verilator/generated-src"
find "$GEN_DIR" -type f \( -name '*.v' -o -name '*.sv' \) -print0 \
  | sort -z | xargs -0 sha256sum > "$OUT/generated_rtl.sha256"

python3 - "$OUT" <<'PY'
import json, pathlib, sys
out=pathlib.Path(sys.argv[1])
required=["spike_mvin.log","spike_matmul_os.log","verilator_mvin.log","verilator_matmul_os.log","verilator_matmul_ws.log","generated_rtl.sha256"]
missing=[x for x in required if not (out/x).exists() or (out/x).stat().st_size == 0]
status={"status":"PASS" if not missing else "FAIL","missing":missing}
(out/"result.json").write_text(json.dumps(status,indent=2)+"\n")
if missing: raise SystemExit(1)
PY

echo GEMMINI_BASELINE_PASS
