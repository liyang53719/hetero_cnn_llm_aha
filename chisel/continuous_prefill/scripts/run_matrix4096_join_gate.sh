#!/usr/bin/env bash
# Real Chisel fanout/join protocol DUT, not floating-point arithmetic simulation.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../.." && pwd);P="$ROOT/chisel/continuous_prefill"
OUT=${1:?absolute NEW output}
[[ "$OUT" = /* && ! -e "$OUT" && ! -L "$OUT" ]] || { echo OUTPUT_MUST_BE_NEW >&2;exit 2; }
for tool in java python3 g++ git;do command -v "$tool" >/dev/null || { echo "BLOCKED_MISSING_TOOL:$tool";exit 77; };done
if [[ -z ${OFFLINE_TOOLS:-} ]];then command -v sbt >/dev/null || { echo BLOCKED_MISSING_SBT;exit 77; };fi
mkdir -p "$(dirname "$OUT")";mkdir "$OUT"
trap 'c=$?;echo "$c" >"$OUT/gate.exit";exit "$c"' EXIT
source "$P/scripts/prepare_verilator_runtime.sh" "$OUT"
export MAKEFLAGS="${MAKEFLAGS:-} VK_PCH_I_FAST= VK_PCH_I_SLOW= OPT_FAST=-O3"
export HARDFLOAT_SOURCE=${HARDFLOAT_SOURCE:-$ROOT/work/upstream/hardfloat_continuous}
[[ -d "$HARDFLOAT_SOURCE/hardfloat/src/main/scala" ]] || bash "$P/scripts/prepare_hardfloat.sh" >"$OUT/prepare.log" 2>&1
python3 "$P/scripts/production_source_identity.py" record "$ROOT" "$OUT" "$HARDFLOAT_SOURCE"
if [[ -n ${OFFLINE_TOOLS:-} ]];then
 export CHISEL_FIRTOOL_PATH="$OFFLINE_TOOLS/bin"
 python3 "$P/scripts/production_source_identity.py" compile "$ROOT" "$OUT" "$HARDFLOAT_SOURCE" "$OFFLINE_TOOLS"
 CP=$(cat "$OUT/classpath.txt");mkdir "$OUT/testclasses"
 java -Xmx1500m -XX:ActiveProcessorCount=2 -cp "$CP" scala.tools.nsc.Main -classpath "$OUT/classes:$CP" \
  -Xplugin:"$OFFLINE_TOOLS/jars/chisel-plugin_2.13.16-6.7.0.jar" -language:reflectiveCalls \
  -d "$OUT/testclasses" "$P/src/test/scala/heteronpu/continuous/MatrixSliceJoinSpec.scala" >"$OUT/test_compile.log" 2>&1
 (cd "$OUT";java -Xmx1500m -XX:ActiveProcessorCount=2 -cp "$OUT/testclasses:$OUT/classes:$CP" org.scalatest.tools.Runner -R "$OUT/testclasses" -o -s heteronpu.continuous.MatrixSliceJoinSpec) >"$OUT/chisel_tests.log" 2>&1
else
 (cd "$P";sbt -batch 'testOnly heteronpu.continuous.MatrixSliceJoinSpec') >"$OUT/chisel_tests.log" 2>&1
fi
python3 "$P/scripts/production_source_identity.py" verify "$ROOT" "$OUT" "$HARDFLOAT_SOURCE"
cat "$OUT/chisel_tests.log"
