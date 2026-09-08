#!/usr/bin/env bash
# Compare replay and cut-through using the same actual pinned iDMA and AXI service.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../.." && pwd);P="$ROOT/chisel/continuous_prefill"
OUT=${1:?absolute NEW output}
[[ "$OUT" = /* && ! -e "$OUT" && ! -L "$OUT" ]] || exit 2
[[ -n ${IDMA_EXPORT:-} && -f "$IDMA_EXPORT/idma.f.in" ]] || { echo BLOCKED_PINNED_IDMA;exit 77; }
for t in java python3 g++ git;do command -v "$t" >/dev/null || { echo "BLOCKED_MISSING_TOOL:$t";exit 77; };done
mkdir -p "$(dirname "$OUT")";mkdir "$OUT"
trap 'c=$?;echo "$c" >"$OUT/gate.exit";exit "$c"' EXIT
source "$P/scripts/prepare_verilator_runtime.sh" "$OUT"
export MAKEFLAGS="${MAKEFLAGS:-} VK_PCH_I_FAST= VK_PCH_I_SLOW= OPT_FAST=-O3"
export HARDFLOAT_SOURCE=${HARDFLOAT_SOURCE:-$ROOT/work/upstream/hardfloat_continuous}
[[ -d "$HARDFLOAT_SOURCE/hardfloat/src/main/scala" ]] || bash "$P/scripts/prepare_hardfloat.sh" >"$OUT/prepare.log" 2>&1
python3 "$P/scripts/production_source_identity.py" record "$ROOT" "$OUT" "$HARDFLOAT_SOURCE"
python3 "$P/scripts/prepare_idma_export.py" "$IDMA_EXPORT" "$OUT" >"$OUT/idma_verify.log"
if [[ -n ${OFFLINE_TOOLS:-} ]];then
 export CHISEL_FIRTOOL_PATH="$OFFLINE_TOOLS/bin"
 python3 "$P/scripts/production_source_identity.py" compile "$ROOT" "$OUT" "$HARDFLOAT_SOURCE" "$OFFLINE_TOOLS"
 CP=$(cat "$OUT/classpath.txt");mkdir "$OUT/testclasses"
 java -Xmx1200m -XX:ActiveProcessorCount=2 -cp "$CP" scala.tools.nsc.Main -classpath "$OUT/classes:$CP" -Xplugin:"$OFFLINE_TOOLS/jars/chisel-plugin_2.13.16-6.7.0.jar" -language:reflectiveCalls -d "$OUT/testclasses" "$P/src/test/scala/heteronpu/continuous/IdmaStreamReturnProbe.scala" >"$OUT/test_compile.log" 2>&1
else
 (cd "$P";sbt -batch compile 'Test / compile') >"$OUT/compile.log" 2>&1
fi
for mode in 0 1;do
 D="$OUT/mode$mode";mkdir "$D"
 if [[ -n ${OFFLINE_TOOLS:-} ]];then
  java -Xmx1200m -XX:ActiveProcessorCount=2 -cp "$OUT/testclasses:$OUT/classes:$CP" heteronpu.continuous.EmitIdmaStreamReturnProbe "$D/generated" "$mode" >"$D/emit.log" 2>&1
 else
  (cd "$P";sbt -batch "Test / runMain heteronpu.continuous.EmitIdmaStreamReturnProbe $D/generated $mode") >"$D/emit.log" 2>&1
 fi
 verilator --cc --exe --build --assert -Wno-fatal --top-module IdmaStreamReturnProbe --output-split 8000 -CFLAGS '-O2 -std=c++17' -j "${BUILD_JOBS:-1}" --Mdir "$D/obj" -f "$OUT/idma.f" "$D/generated/IdmaStreamReturnProbe.sv" "$ROOT/rtl/integration/idma_backend_rw_axi_flat_wrap.sv" "$P/tests/idma_stream_return.cpp" >"$D/build.log" 2>&1
 set +e
 "$D/obj/VIdmaStreamReturnProbe" "$mode" >"$D/run.log" 2>&1
 c=$?;set -e;echo "$c" >"$D/simulation.exit";cat "$D/run.log";((c==0))||exit "$c"
done
python3 "$P/scripts/production_source_identity.py" verify "$ROOT" "$OUT" "$HARDFLOAT_SOURCE"
python3 "$P/scripts/verify_idma_stream_return.py" "$OUT" >"$OUT/RESULT.json"
cat "$OUT/RESULT.json"
