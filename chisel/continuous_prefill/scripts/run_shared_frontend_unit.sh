#!/usr/bin/env bash
# Actual Chisel DUT tests. Owner completion/memory stubs are CONTROL tests only.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../.." && pwd);P="$ROOT/chisel/continuous_prefill"
OUT=${1:?usage: run_shared_frontend_unit.sh /absolute/new/output}
[[ "$OUT" = /* && ! -e "$OUT" ]] || exit 2
for t in java g++ python3 git;do command -v "$t" >/dev/null || { echo "BLOCKED_MISSING_TOOL: $t";exit 77; };done
if [[ -n ${OFFLINE_TOOLS:-} ]];then
  export PATH="$OFFLINE_TOOLS/bin:$PATH" CHISEL_FIRTOOL_PATH="$OFFLINE_TOOLS/bin" VERILATOR_ROOT="$OFFLINE_TOOLS/share/verilator"
else
  command -v sbt >/dev/null || { echo BLOCKED_MISSING_SBT;exit 77; }
fi
command -v verilator >/dev/null || { echo BLOCKED_MISSING_VERILATOR;exit 77; }
mkdir -p "$OUT";trap 'c=$?; echo "$c" >"$OUT/gate.exit";exit "$c"' EXIT
export HARDFLOAT_SOURCE=${HARDFLOAT_SOURCE:-$ROOT/work/upstream/hardfloat_continuous}
[[ -d "$HARDFLOAT_SOURCE/hardfloat/src/main/scala" ]] || bash "$P/scripts/prepare_hardfloat.sh" >"$OUT/prepare.log" 2>&1
export MAKEFLAGS="${MAKEFLAGS:-} VK_PCH_I_FAST= VK_PCH_I_SLOW="
python3 "$P/scripts/production_source_identity.py" record "$ROOT" "$OUT" "$HARDFLOAT_SOURCE"
git -C "$ROOT" rev-parse HEAD >"$OUT/source_base_commit.txt"
if [[ -n ${OFFLINE_TOOLS:-} ]];then
  python3 "$P/scripts/production_source_identity.py" compile "$ROOT" "$OUT" "$HARDFLOAT_SOURCE" "$OFFLINE_TOOLS"
  CP=$(cat "$OUT/classpath.txt");mkdir "$OUT/testclasses"
  find "$P/src/test/scala" -name '*.scala' | sort >"$OUT/test_sources.txt"
  java -Xmx3G -XX:ActiveProcessorCount=3 -cp "$CP" scala.tools.nsc.Main -classpath "$OUT/classes:$CP" \
    -Xplugin:"$OFFLINE_TOOLS/jars/chisel-plugin_2.13.16-6.7.0.jar" -language:reflectiveCalls -d "$OUT/testclasses" @"$OUT/test_sources.txt" >"$OUT/test_compile.log" 2>&1
  (cd "$OUT";java -Xmx3G -XX:ActiveProcessorCount=3 -cp "$OUT/testclasses:$OUT/classes:$CP" org.scalatest.tools.Runner -R "$OUT/testclasses" -o \
    -s heteronpu.continuous.SharedMemoryArbiterSpec -s heteronpu.continuous.TypedTensorReaderSpec -s heteronpu.continuous.HostResidualCommandsSpec) >"$OUT/chisel_tests.log" 2>&1
else
  (cd "$P";sbt -batch compile Test/compile 'testOnly heteronpu.continuous.SharedMemoryArbiterSpec heteronpu.continuous.TypedTensorReaderSpec heteronpu.continuous.HostResidualCommandsSpec') >"$OUT/chisel_tests.log" 2>&1
fi
python3 "$P/tests/test_shared_command_evidence.py" >"$OUT/python_tests.log" 2>&1
python3 -O "$P/tests/test_shared_command_evidence.py" >"$OUT/python_optimized_tests.log" 2>&1
python3 "$P/scripts/production_source_identity.py" verify "$ROOT" "$OUT" "$HARDFLOAT_SOURCE"
cat "$OUT/chisel_tests.log";cat "$OUT/python_tests.log";cat "$OUT/python_optimized_tests.log"
