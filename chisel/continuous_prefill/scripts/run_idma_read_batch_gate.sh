#!/usr/bin/env bash
# Real retained iDMA; 64-beat logical transfers, legalizer still emits <=16-beat AXI.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../.." && pwd);P="$ROOT/chisel/continuous_prefill"
OUT=${1:?absolute NEW output}
[[ "$OUT" = /* && ! -e "$OUT" && ! -L "$OUT" ]] || exit 2
[[ -n ${IDMA_EXPORT:-} && -f "$IDMA_EXPORT/idma.f.in" ]] || { echo BLOCKED_PINNED_IDMA;exit 77; }
mkdir -p "$(dirname "$OUT")";mkdir "$OUT"
trap 'code=$?;echo "$code" >"$OUT/gate.exit";exit "$code"' EXIT
source "$P/scripts/prepare_verilator_runtime.sh" "$OUT"
export MAKEFLAGS="${MAKEFLAGS:-} VK_PCH_I_FAST= VK_PCH_I_SLOW= OPT_FAST=-O3"
export HARDFLOAT_SOURCE=${HARDFLOAT_SOURCE:-$ROOT/work/upstream/hardfloat_continuous}
[[ -d "$HARDFLOAT_SOURCE/hardfloat/src/main/scala" ]] || bash "$P/scripts/prepare_hardfloat.sh" >"$OUT/prepare.log" 2>&1
python3 "$P/scripts/production_source_identity.py" record "$ROOT" "$OUT" "$HARDFLOAT_SOURCE"
if [[ -n ${OFFLINE_TOOLS:-} ]];then
 export CHISEL_FIRTOOL_PATH="$OFFLINE_TOOLS/bin"
 python3 "$P/scripts/production_source_identity.py" compile "$ROOT" "$OUT" "$HARDFLOAT_SOURCE" "$OFFLINE_TOOLS"
 CP=$(cat "$OUT/classpath.txt");mkdir "$OUT/testclasses"
 java -Xmx1500m -XX:ActiveProcessorCount=3 -cp "$CP" scala.tools.nsc.Main -classpath "$OUT/classes:$CP" -Xplugin:"$OFFLINE_TOOLS/jars/chisel-plugin_2.13.16-6.7.0.jar" -language:reflectiveCalls -d "$OUT/testclasses" "$P/src/test/scala/heteronpu/continuous/IdmaCommitTailProbe.scala" >"$OUT/test_compile.log" 2>&1
 java -Xmx2000m -XX:ActiveProcessorCount=3 -cp "$OUT/testclasses:$OUT/classes:$CP" heteronpu.continuous.EmitIdmaCommitTailProbe "$OUT/generated" 64 >"$OUT/emit.log" 2>&1
else
 (cd "$P";sbt -batch compile "Test / runMain heteronpu.continuous.EmitIdmaCommitTailProbe $OUT/generated 64") >"$OUT/compile_emit.log" 2>&1
fi
python3 "$P/scripts/prepare_idma_export.py" "$IDMA_EXPORT" "$OUT" >"$OUT/idma_verify.log"
verilator --cc --exe --build --assert -Wno-fatal --top-module IdmaCommitTailProbe -CFLAGS '-O3 -std=c++17' -j "${BUILD_JOBS:-2}" --Mdir "$OUT/obj" -f "$OUT/idma.f" "$OUT/generated/IdmaCommitTailProbe.sv" "$ROOT/rtl/integration/idma_backend_rw_axi_flat_wrap.sv" "$P/tests/idma_read_batch.cpp" >"$OUT/build.log" 2>&1
set +e
"$OUT/obj/VIdmaCommitTailProbe" >"$OUT/run.log" 2>&1
code=$?;set -e;echo "$code" >"$OUT/simulation.exit";cat "$OUT/run.log";((code==0))||exit "$code"
python3 "$P/scripts/production_source_identity.py" verify "$ROOT" "$OUT" "$HARDFLOAT_SOURCE"
