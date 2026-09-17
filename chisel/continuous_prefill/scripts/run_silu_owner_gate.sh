#!/usr/bin/env bash
# Actual scalar/vector/owner arithmetic and transport regression, not full-model timing.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../.." && pwd);P="$ROOT/chisel/continuous_prefill"
OUT=${1:?absolute NEW evidence directory}
[[ "$OUT" = /* && ! -e "$OUT" && ! -L "$OUT" ]] || { echo OUTPUT_MUST_BE_NEW >&2;exit 2; }
for t in java g++ python3;do command -v "$t" >/dev/null || { echo "BLOCKED_MISSING_TOOL:$t" >&2;exit 77; };done
mkdir -p "$(dirname "$OUT")";mkdir "$OUT"
trap 'code=$?;echo "$code" >"$OUT/gate.exit";exit "$code"' EXIT
source "$P/scripts/prepare_verilator_runtime.sh" "$OUT"
export MAKEFLAGS="${MAKEFLAGS:-} VK_PCH_I_FAST= VK_PCH_I_SLOW="
export HARDFLOAT_SOURCE=${HARDFLOAT_SOURCE:-$ROOT/work/upstream/hardfloat_continuous}
[[ -d "$HARDFLOAT_SOURCE/hardfloat/src/main/scala" ]] || bash "$P/scripts/prepare_hardfloat.sh" >"$OUT/hardfloat_prepare.log" 2>&1
python3 "$P/scripts/production_source_identity.py" record "$ROOT" "$OUT" "$HARDFLOAT_SOURCE"
SUITES='heteronpu.continuous.ScheduledSiluOwnerSpec heteronpu.continuous.VectorSiluSpec'
if [[ -n ${OFFLINE_TOOLS:-} ]];then
 export CHISEL_FIRTOOL_PATH="$OFFLINE_TOOLS/bin"
 python3 "$P/scripts/production_source_identity.py" compile "$ROOT" "$OUT" "$HARDFLOAT_SOURCE" "$OFFLINE_TOOLS"
 CP=$(cat "$OUT/classpath.txt");mkdir "$OUT/testclasses"
 java -Xmx3G -XX:ActiveProcessorCount=3 -cp "$CP" scala.tools.nsc.Main -classpath "$OUT/classes:$CP" \
  -Xplugin:"$OFFLINE_TOOLS/jars/chisel-plugin_2.13.16-6.7.0.jar" -language:reflectiveCalls -d "$OUT/testclasses" \
  "$P/src/test/scala/heteronpu/continuous/ScheduledSiluOwnerSpec.scala" \
  "$P/src/test/scala/heteronpu/continuous/VectorSiluSpec.scala" >"$OUT/test_compile.log" 2>&1
 (cd "$OUT";java -Xmx3G -XX:ActiveProcessorCount=3 -cp "$OUT/testclasses:$OUT/classes:$CP" org.scalatest.tools.Runner \
  -R "$OUT/testclasses" -oW -s heteronpu.continuous.ScheduledSiluOwnerSpec -s heteronpu.continuous.VectorSiluSpec) >"$OUT/tests.log" 2>&1
else
 (cd "$P";sbt -batch "testOnly $SUITES") >"$OUT/tests.log" 2>&1
fi
cat "$OUT/tests.log"
python3 "$P/scripts/production_source_identity.py" verify "$ROOT" "$OUT" "$HARDFLOAT_SOURCE" >"$OUT/source_verify.log"
python3 "$P/scripts/verify_silu_owner_gate.py" "$OUT"
