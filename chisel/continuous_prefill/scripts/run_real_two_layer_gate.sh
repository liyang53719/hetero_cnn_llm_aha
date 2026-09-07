#!/usr/bin/env bash
# Fixed real16 two-layer numerical gate. No changes to DUT or old evidence.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
P="$ROOT/chisel/continuous_prefill"
OUT=${1:?absolute NEW output directory}
[[ "$OUT" = /* && ! -e "$OUT" ]] || { echo OUTPUT_MUST_BE_NEW >&2; exit 2; }
bash "$P/scripts/run_host_block_gate.sh" real "$OUT" 16 9467985920 2
python3 "$P/scripts/verify_real_two_layer.py" --repo "$ROOT" --evidence "$OUT" \
  --output "$OUT/REAL2_ACCEPTANCE.json" > "$OUT/real2_verification.log"
cat "$OUT/real2_verification.log"
