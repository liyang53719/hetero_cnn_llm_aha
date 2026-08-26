#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd)
CHIP=$ROOT/work/upstream/chipyard_gemmini
OUT=${OUT:-$ROOT/work/generated/l5_bf16_fma}
RUN=$ROOT/scripts/run_memory_capped.sh
JAVA=$ROOT/work/toolchain/conda/bin/java
SRC=$ROOT/integration/gemmini/EmitHeteroBF16Fma.scala
mkdir -p "$OUT"
test -z "$(git -C "$CHIP" status --porcelain)"||{ echo canonical Chipyard dirty >&2;exit 3;}
CMD=";project chipyard;set Global / concurrentRestrictions := Seq(Tags.limitAll(8));set Compile / unmanagedSources += file(\"$SRC\");runMain gemmini.EmitHeteroBF16Fma $OUT/HeteroBF16FmaLane.sv"
pushd "$CHIP">/dev/null
MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$RUN" \
  "$JAVA" -Xmx8G -jar "$CHIP/scripts/sbt-launch.jar" \
  -Dsbt.ivy.home="$CHIP/.ivy2" -Dsbt.global.base="$CHIP/.sbt" \
  -Dsbt.boot.directory="$CHIP/.sbt/boot" -Dsbt.color=never \
  -Dsbt.supershell=false "$CMD" >"$OUT/generate.log" 2>&1
popd>/dev/null
test -s "$OUT/HeteroBF16FmaLane.sv"
sha256sum "$OUT/HeteroBF16FmaLane.sv">"$OUT/HeteroBF16FmaLane.sv.sha256"
git -C "$CHIP/generators/hardfloat" rev-parse HEAD >"$OUT/hardfloat.commit"
git -C "$CHIP" status --porcelain >"$OUT/upstream.status"
test ! -s "$OUT/upstream.status"
echo L5_BF16_FMA_GENERATE_PASS
