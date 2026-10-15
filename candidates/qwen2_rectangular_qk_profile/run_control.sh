#!/usr/bin/env bash
# Emits and simulates CONTROL_ONLY Verilator RTL, not the Matrix arithmetic array.
set -euo pipefail
export MAKEFLAGS="${MAKEFLAGS:--j1 VM_PARALLEL_BUILDS=0 VK_PCH_I_FAST= VK_PCH_I_SLOW=}"
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
CANDIDATE="$ROOT/candidates/qwen2_rectangular_qk_profile"
cd "$ROOT/chisel/continuous_prefill"
sbt \
  "set Compile / unmanagedSources += file(\"$CANDIDATE/src/main/scala/heteronpu/continuous/QkRectangularProfile.scala\")" \
  "set Test / unmanagedSources := Seq(file(\"$CANDIDATE/src/test/scala/heteronpu/continuous/QkRectangularProfileSpec.scala\"))" \
  'testOnly heteronpu.continuous.QkRectangularProfileSpec'
