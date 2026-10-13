#!/usr/bin/env bash
# Fresh model-only full-N8192 RMS -> QKV gates; no RTL, complete block or Git publication.
# Usage: HETERO_35B_RUNTIME_PROFILE=recovery_20261013 bash scripts/replay_qwen35_35b_prefix.sh RUNTIME PAYLOAD MANIFEST_SHA TAG
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
RUNTIME="$(realpath "${1:?verified isolated runtime directory}")"
PAYLOAD="$(realpath "${2:?verified three-tensor payload directory}")"
MANIFEST_SHA="${3:?independently retained acquisition SHA256}"
TAG="${4:?fresh result directory name}"
[[ "$TAG" =~ ^[A-Za-z0-9_-]+$ ]] || exit 2
[[ "$MANIFEST_SHA" =~ ^[0-9a-f]{64}$ ]] || exit 2
OUT="$ROOT/work/$TAG"
[[ ! -e "$OUT" && ! -L "$OUT" ]] || { echo 'Fresh result directory required' >&2; exit 2; }
mkdir -p "$OUT"
PY="$RUNTIME/python.sh"
"$PY" -m candidates.qwen35_35b_payload.packer verify --include-qkv --output "$PAYLOAD" --manifest-sha256 "$MANIFEST_SHA" > "$OUT/payload_verify.json"
"$PY" scripts/build_shared_matrix_recipe.py --repo . --out "$OUT/matrix" > "$OUT/matrix_build.log"
export MATRIX_SERVICE_LIBRARY="$OUT/matrix/matrix_silu_numeric.so"
export MATRIX_SERVICE_COMPILE_RECEIPT="$OUT/matrix/compile.json"
export GDN_VECTOR16_LIBRARY="$("$PY" -c 'from candidates.qwen35_gdn_prefill.chunk.vector import build_library; import sys; print(build_library(sys.argv[1]))' "$OUT/vector")"
"$PY" -m candidates.qwen35_35b_rms.run_owner --payload "$PAYLOAD" --include-qkv --manifest-sha256 "$MANIFEST_SHA" --output "$OUT/rms" --wall-seconds 180 > "$OUT/rms.log" 2>&1
RMS_SHA="$(sha256sum "$OUT/rms/summary.json" | cut -d' ' -f1)"
for M in 16 128; do
  ONEDNN_VERBOSE=1 ONEDNN_JIT_DUMP=1 "$PY" -m candidates.qwen35_35b_projection_reference.run_reference --m "$M" --payload "$PAYLOAD" --manifest-sha256 "$MANIFEST_SHA" --rms-output "$OUT/rms" --rms-summary-sha256 "$RMS_SHA" --out "$OUT/reference_m$M" > "$OUT/reference_m$M.log" 2>&1
  REFERENCE_SHA="$(sha256sum "$OUT/reference_m$M/report.json" | cut -d' ' -f1)"
  "$PY" -m candidates.qwen35_35b_prefill.run_prefix --payload "$PAYLOAD" --manifest-sha256 "$MANIFEST_SHA" --reference-report "$OUT/reference_m$M/report.json" --reference-report-sha256 "$REFERENCE_SHA" --output "$OUT/prefix_m$M" --tokens "$M" --full-qkv --wall-seconds 300 > "$OUT/prefix_m$M.log" 2>&1
done
printf 'Model-only M16 and M128 prefix reports: %s\n' "$OUT"
