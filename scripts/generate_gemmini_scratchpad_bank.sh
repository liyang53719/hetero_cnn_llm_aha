#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
CHIPYARD=${CHIPYARD_ROOT:-$ROOT/work/upstream/chipyard_gemmini}
OUT=${OUT:-$ROOT/work/generated/l3_gemmini_scratchpad_bank}
JAVA=${JAVA:-$ROOT/work/toolchain/conda/bin/java}
SBT_LAUNCHER="$CHIPYARD/scripts/sbt-launch.jar"
SOURCE_FILE="$ROOT/integration/gemmini/EmitHeteroScratchpadBank.scala"
RUN_CAPPED="$ROOT/scripts/run_memory_capped.sh"

mkdir -p "$OUT"
test -x "$JAVA"
test -f "$SBT_LAUNCHER"
test -x "$ROOT/work/toolchain/riscv/bin/firtool"
test -z "$(git -C "$CHIPYARD" status --porcelain)" || {
  echo "canonical Chipyard is dirty" >&2
  exit 3
}

export PATH="$ROOT/work/toolchain/riscv/bin:$ROOT/work/toolchain/conda/bin:$PATH"
SBT_COMMAND=";project chipyard;set Global / concurrentRestrictions := Seq(Tags.limitAll(8));set Compile / unmanagedSources += file(\"$SOURCE_FILE\");runMain gemmini.EmitHeteroScratchpadBank $OUT/ScratchpadBank.sv"

pushd "$CHIPYARD" >/dev/null
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$RUN_CAPPED" \
  "$JAVA" -Xmx8G -jar "$SBT_LAUNCHER" \
  -Dsbt.ivy.home="$CHIPYARD/.ivy2" \
  -Dsbt.global.base="$CHIPYARD/.sbt" \
  -Dsbt.boot.directory="$CHIPYARD/.sbt/boot" \
  -Dsbt.color=never -Dsbt.supershell=false "$SBT_COMMAND" \
  >"$OUT/generate.log" 2>&1
popd >/dev/null

test -s "$OUT/ScratchpadBank.sv"
sha256sum "$OUT/ScratchpadBank.sv" >"$OUT/ScratchpadBank.sv.sha256"
git -C "$CHIPYARD" rev-parse HEAD >"$OUT/upstream.commit"
git -C "$CHIPYARD" status --porcelain >"$OUT/upstream.status"
test ! -s "$OUT/upstream.status"

echo GEMMINI_SCRATCHPAD_BANK_GENERATE_PASS
