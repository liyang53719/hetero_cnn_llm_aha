#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Preserve any previous build/evidence; caller should use a new checkout for each
# validation run. The build uses Chisel source, never an edited SV artifact.
if [[ -e generated ]]; then
  echo "Refusing to overwrite generated/: use a new validation checkout." >&2
  exit 2
fi
export MAKEFLAGS="${MAKEFLAGS:+$MAKEFLAGS }VM_PARALLEL_BUILDS=0"
sbt -batch compile Test/compile test
sbt -batch 'runMain heteronpu.p0.EmitP0Safety generated'
python3 scripts/check_emission.py generated
python3 scripts/verify_emitted_abi.py generated
