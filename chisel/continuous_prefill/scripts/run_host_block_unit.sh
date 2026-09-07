#!/usr/bin/env bash
# New Host owner decoder tests plus retained shared-frontend regression.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../.." && pwd);P="$ROOT/chisel/continuous_prefill"
OUT=${1:?absolute NEW output};[[ "$OUT" = /* && ! -e "$OUT" ]] || exit 2
mkdir -p "$OUT";trap 'c=$?;echo "$c" >"$OUT/gate.exit";exit "$c"' EXIT
source "$P/scripts/prepare_verilator_runtime.sh" "$OUT"
export MAKEFLAGS="${MAKEFLAGS:-} VK_PCH_I_FAST= VK_PCH_I_SLOW="
export HARDFLOAT_SOURCE=${HARDFLOAT_SOURCE:-$ROOT/work/upstream/hardfloat_continuous}
[[ -d "$HARDFLOAT_SOURCE/hardfloat/src/main/scala" ]] || bash "$P/scripts/prepare_hardfloat.sh" >"$OUT/prepare.log" 2>&1
printf 'H=64 F=128 HEADS=2 KVHEADS=1 HD=32 MAX_TOKENS=1024\n' >"$OUT/shape.h"
python3 "$P/scripts/pack_owner_block_fixture.py" "$OUT/shape.h" "$OUT/fixture" >"$OUT/fixture.log"
export OWNER_FIXTURE="$OUT/fixture" OWNER_TEST_ARTIFACTS="$OUT/fixture_unit_artifacts"
python3 "$P/scripts/production_source_identity.py" record "$ROOT" "$OUT" "$HARDFLOAT_SOURCE"
SUITES='heteronpu.continuous.HostBlockCommandsSpec heteronpu.continuous.SharedMemoryArbiterSpec heteronpu.continuous.TypedTensorReaderSpec heteronpu.continuous.HostResidualCommandsSpec heteronpu.continuous.BlockWritebackFenceSpec heteronpu.continuous.DenseTileCursorSpec'
if [[ -n ${OFFLINE_TOOLS:-} ]];then
 python3 "$P/scripts/production_source_identity.py" compile "$ROOT" "$OUT" "$HARDFLOAT_SOURCE" "$OFFLINE_TOOLS"
 CP=$(cat "$OUT/classpath.txt");mkdir "$OUT/testclasses"
 find "$P/src/test/scala" -name '*.scala' | sort >"$OUT/test_sources.txt"
 java -Xmx3G -XX:ActiveProcessorCount=3 -cp "$CP" scala.tools.nsc.Main -classpath "$OUT/classes:$CP" \
  -Xplugin:"$OFFLINE_TOOLS/jars/chisel-plugin_2.13.16-6.7.0.jar" -language:reflectiveCalls -d "$OUT/testclasses" @"$OUT/test_sources.txt" >"$OUT/test_compile.log" 2>&1
 ARGS=();for suite in $SUITES;do ARGS+=(-s "$suite");done
 (cd "$OUT";java -Xmx3G -XX:ActiveProcessorCount=3 -cp "$OUT/testclasses:$OUT/classes:$CP" org.scalatest.tools.Runner -R "$OUT/testclasses" -o "${ARGS[@]}") >"$OUT/chisel_tests.log" 2>&1
else
 (cd "$P";sbt -batch compile Test/compile "testOnly $SUITES") >"$OUT/chisel_tests.log" 2>&1
fi
python3 "$P/tests/test_owner_block_fixture.py" >"$OUT/python_tests.log" 2>&1
python3 -O "$P/tests/test_owner_block_fixture.py" >"$OUT/python_optimized_tests.log" 2>&1
python3 "$P/scripts/production_source_identity.py" verify "$ROOT" "$OUT" "$HARDFLOAT_SOURCE"
cat "$OUT/chisel_tests.log" "$OUT/python_tests.log" "$OUT/python_optimized_tests.log"
