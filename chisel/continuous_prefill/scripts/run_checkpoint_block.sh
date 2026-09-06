#!/usr/bin/env bash
# No code edits: pass a build directory, local checkpoint, token IDs, fresh output.
set -euo pipefail
BUILD=$(realpath "${1:?validated real-profile build directory}")
CHECKPOINT=$(realpath "${2:?local GGUF or safetensors checkpoint}")
TOKENS=$(realpath "${3:?JSON token ID array, at most 1024}")
OUT=$(python3 -c 'from pathlib import Path;import sys;print(Path(sys.argv[1]).resolve())' "${4:?fresh output directory}")
ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
[[ ! -e $OUT ]] || { echo 'Refusing to overwrite output' >&2; exit 2; };mkdir -p "$OUT"
python3 "$ROOT/chisel/continuous_prefill/scripts/pack_qwen2_block.py" --layout "$BUILD/generated/layout.json" \
 --checkpoint "$CHECKPOINT" --tokens-json "$TOKENS" --out "$OUT/readonly.bin" | tee "$OUT/pack.log"
N=$(python3 -c 'import json,sys;print(len(json.load(open(sys.argv[1]))))' "$TOKENS")
timeout "${RUN_TIMEOUT_SECONDS:-86400}" "$BUILD/obj/VQwen2AxiBlockTop" "$N" "$OUT/readonly.bin" | tee "$OUT/run.log"
# A local checkpoint run remains a block recipe comparison, not a 28-layer proof.
grep -q '^CONTINUOUS_QWEN2_BLOCK_PASS ' "$OUT/run.log"
sha256sum "$OUT/readonly.bin" "$OUT/run.log" > "$OUT/SHA256SUMS"
printf '%s\n' 'LOCAL_CHECKPOINT_BLOCK_FINISHED full_model=false; backend identity is recorded in generated/layout.json'
