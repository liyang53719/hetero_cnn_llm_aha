#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
command -v dc_shell >/dev/null || { echo "dc_shell is required" >&2; exit 2; }
: "${STD_CELL_DBS:?colon-separated 22nm .db paths are required}"
CLOCK_PERIOD_NS=${CLOCK_PERIOD_NS:-1.0}
OUT_BASE=${OUT_BASE:-"$ROOT/work/results/dc22"}
mkdir -p "$OUT_BASE"

run_top() {
  local top=$1 flist=$2
  TOP=$top \
  RTL_FILELIST="$ROOT/$flist" \
  STD_CELL_DBS="$STD_CELL_DBS" \
  CLOCK_PERIOD_NS="$CLOCK_PERIOD_NS" \
  OUT_DIR="$OUT_BASE/$top" \
  dc_shell -64bit -f "$ROOT/dc/synth_22nm.tcl" \
    | tee "$OUT_BASE/$top.dc.log"
  test -s "$OUT_BASE/$top/status.txt"
  grep -q '^UNMAPPED_CELLS=0$' "$OUT_BASE/$top/status.txt"
}

run_top hetero_npu_shell dc/filelists/shell.f
run_top matrix_engine_int8_tile dc/filelists/matrix_contract.f
run_top cgra_sfu_vector dc/filelists/sfu_contract.f
run_top kv_cache_engine dc/filelists/kv_contract.f
run_top hetero_npu_numerical_integration_v0 dc/filelists/numerical_integration.f

echo "DC22_CONTRACT_MODELS_PASS"
