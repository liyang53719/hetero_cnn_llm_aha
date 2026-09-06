#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
PIN=c1105e6ac6a0dd90fc80893efc4830ab609005d3
DEST=${HARDFLOAT_SOURCE:-$ROOT/work/upstream/hardfloat_continuous}
if [[ ! -d $DEST/.git ]]; then
  if [[ -e $DEST ]]; then echo 'Refuse to overwrite existing dependency path' >&2; exit 2; fi
  mkdir -p "$(dirname "$DEST")"
  git clone --no-checkout https://github.com/ucb-bar/berkeley-hardfloat.git "$DEST"
  git -C "$DEST" checkout --detach "$PIN"
fi
[[ $(git -C "$DEST" rev-parse HEAD) == "$PIN" ]]
[[ -z $(git -C "$DEST" status --porcelain) ]]
printf '%s\n' "$DEST"
