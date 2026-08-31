#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);CHIP=${CHIPYARD_ROOT:-$ROOT/work/upstream/chipyard_gemmini};OUT=${OUT:-$ROOT/work/generated/l5_all_primitives};R=$ROOT/scripts/run_memory_capped.sh;mkdir -p "$OUT"
S0=$ROOT/integration/gemmini/EmitHeteroBF16Fma.scala;S1=$ROOT/integration/gemmini/EmitHeteroFP32Alu.scala;S2=$ROOT/integration/gemmini/EmitHeteroFP32Scale16Floor.scala;S3=$ROOT/integration/gemmini/EmitHeteroFP32Primitives.scala;S4=$ROOT/integration/gemmini/EmitHeteroFP32Pipelines.scala;S5=$ROOT/integration/gemmini/EmitHeteroAllPrimitives.scala
test -z "$(git -C "$CHIP" status --porcelain)"||exit 3
INPUT_STAMP="$OUT/HeteroAllPrimitives.inputs.sha256"
INPUT_DIGEST=$( { sha256sum "$S0" "$S1" "$S2" "$S3" "$S4" "$S5";git -C "$CHIP" rev-parse HEAD; } | sha256sum | awk '{print $1}')
cache_valid=1
[[ -s "$OUT/HeteroAllPrimitives.sv" && -s "$OUT/HeteroAllPrimitives.sv.sha256" ]]||cache_valid=0
if ((cache_valid));then sha256sum -c "$OUT/HeteroAllPrimitives.sv.sha256">/dev/null||cache_valid=0;fi
for source in "$S0" "$S1" "$S2" "$S3" "$S4" "$S5";do [[ "$OUT/HeteroAllPrimitives.sv" -nt "$source" ]]||cache_valid=0;done
if ((cache_valid))&&{ [[ ! -s "$INPUT_STAMP" ]]||grep -qx "$INPUT_DIGEST" "$INPUT_STAMP";};then
 printf '%s\n' "$INPUT_DIGEST">"$INPUT_STAMP"
 echo "L5_ALL_HARDFLOAT_PRIMITIVES_CACHE_PASS input_sha256=$INPUT_DIGEST"
 exit 0
fi
CMD=";project chipyard;set Global / concurrentRestrictions := Seq(Tags.limitAll(8));set Compile / unmanagedSources ++= Seq(file(\"$S0\"),file(\"$S1\"),file(\"$S2\"),file(\"$S3\"),file(\"$S4\"),file(\"$S5\"));runMain gemmini.EmitHeteroAllPrimitives $OUT/HeteroAllPrimitives.sv"
pushd "$CHIP">/dev/null;MIN_AVAILABLE_KIB=10485760 MEMORY_HIGH=24G MEMORY_MAX=30G "$R" "$ROOT/work/toolchain/conda/bin/java" -Xmx8G -jar "$CHIP/scripts/sbt-launch.jar" -Dsbt.ivy.home="$CHIP/.ivy2" -Dsbt.global.base="$CHIP/.sbt" -Dsbt.boot.directory="$CHIP/.sbt/boot" -Dsbt.color=never -Dsbt.supershell=false "$CMD">"$OUT/generate.log" 2>&1;popd>/dev/null
test -s "$OUT/HeteroAllPrimitives.sv";for m in HeteroBF16FmaPre HeteroBF16FmaMul HeteroBF16FmaPost HeteroBF16FmaRound HeteroFP32MulPipeTag12 HeteroFP32AddPipeTag12 HeteroFP32MulPipeBit1 HeteroFP32AddPipeBit1;do grep -q "module $m" "$OUT/HeteroAllPrimitives.sv";done;sha256sum "$OUT/HeteroAllPrimitives.sv">"$OUT/HeteroAllPrimitives.sv.sha256";printf '%s\n' "$INPUT_DIGEST">"$INPUT_STAMP";git -C "$CHIP" status --porcelain>"$OUT/upstream.status";test ! -s "$OUT/upstream.status";echo L5_ALL_HARDFLOAT_PRIMITIVES_GENERATE_PASS
