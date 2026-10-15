#!/usr/bin/env bash
# Actual native Matrix payload/service regression, never RTL or a cycle model.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
cd "$ROOT"
PYTHON=${PYTHON:-python3}
BUILD=$(mktemp -d "${TMPDIR:-/tmp}/qk-profile-native.XXXXXX")
g++ -shared -fPIC -O2 -ffp-contract=off -fno-fast-math \
  candidates/qwen2_resident_matrix/ffn_attention/matrix_numeric.cpp -o "$BUILD/matrix_numeric.so"
PYTHONPATH="$ROOT/candidates/qwen2_resident_matrix/ffn_attention:$ROOT" \
MATRIX_SERVICE_LIBRARY="$BUILD/matrix_numeric.so" MATRIX_SERVICE_EVIDENCE_DIR="$BUILD" \
  "$PYTHON" -m unittest -q test_matrix_service test_rectangular_profile
"$PYTHON" -m pytest -q candidates/qwen2_rectangular_qk_payload/test_model.py
"$PYTHON" -m pytest -q candidates/qwen2_rectangular_qk_phase/test_model.py
# The old helpers write local synthetic reports. They are deliberately NOT CI artifacts.
