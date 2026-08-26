#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);CHIP=$ROOT/work/upstream/chipyard_gemmini;OUT=$ROOT/work/generated/l5_fp32_alu;mkdir -p "$OUT";R=$ROOT/scripts/run_memory_capped.sh;SRC=$ROOT/integration/gemmini/EmitHeteroFP32Alu.scala
test -z "$(git -C "$CHIP" status --porcelain)"||exit 3;CMD=";project chipyard;set Global / concurrentRestrictions := Seq(Tags.limitAll(4));set Compile / unmanagedSources += file(\"$SRC\");runMain gemmini.EmitHeteroFP32Alu $OUT/HeteroFP32Alu.sv"
pushd "$CHIP">/dev/null;MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=8G MEMORY_MAX=10G "$R" "$ROOT/work/toolchain/conda/bin/java" -Xmx8G -jar "$CHIP/scripts/sbt-launch.jar" -Dsbt.ivy.home="$CHIP/.ivy2" -Dsbt.global.base="$CHIP/.sbt" -Dsbt.boot.directory="$CHIP/.sbt/boot" -Dsbt.color=never -Dsbt.supershell=false "$CMD" >"$OUT/generate.log" 2>&1;popd>/dev/null
test -s "$OUT/HeteroFP32Alu.sv";sha256sum "$OUT/HeteroFP32Alu.sv">"$OUT/HeteroFP32Alu.sv.sha256";git -C "$CHIP" status --porcelain>"$OUT/upstream.status";test ! -s "$OUT/upstream.status";echo L5_FP32_ALU_GENERATE_PASS
