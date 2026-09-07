#!/usr/bin/env bash
# Execute actual eight-slice arithmetic. No handwritten or generated RTL edits.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../.." && pwd);P="$ROOT/chisel/continuous_prefill"
OUT=${1:?absolute NEW output directory}
[[ "$OUT" = /* && ! -e "$OUT" && ! -L "$OUT" ]] || { echo OUTPUT_MUST_BE_NEW >&2;exit 2; }
for t in java python3 g++ git;do command -v "$t" >/dev/null || { echo "BLOCKED_MISSING_TOOL:$t";exit 77; };done
[[ -n ${IDMA_EXPORT:-} && -f "$IDMA_EXPORT/idma.f.in" ]] || { echo BLOCKED_PINNED_TECH_CELL_DEPENDENCY;exit 77; }
[[ -n ${OFFLINE_TOOLS:-} ]] || command -v sbt >/dev/null || { echo BLOCKED_MISSING_SBT;exit 77; }
mkdir -p "$(dirname "$OUT")";mkdir "$OUT";trap 'c=$?;echo "$c" >"$OUT/gate.exit";exit "$c"' EXIT
source "$P/scripts/prepare_verilator_runtime.sh" "$OUT"
export MAKEFLAGS="${MAKEFLAGS:-} VK_PCH_I_FAST= VK_PCH_I_SLOW= OPT_FAST=-O3"
export HARDFLOAT_SOURCE=${HARDFLOAT_SOURCE:-$ROOT/work/upstream/hardfloat_continuous}
[[ -d "$HARDFLOAT_SOURCE/hardfloat/src/main/scala" ]] || bash "$P/scripts/prepare_hardfloat.sh" >"$OUT/hardfloat_prepare.log" 2>&1
python3 "$P/scripts/prepare_idma_export.py" "$IDMA_EXPORT" "$OUT" >"$OUT/dependency_verify.log"
python3 "$P/scripts/production_source_identity.py" record "$ROOT" "$OUT" "$HARDFLOAT_SOURCE"
if [[ -n ${OFFLINE_TOOLS:-} ]];then
 export CHISEL_FIRTOOL_PATH="$OFFLINE_TOOLS/bin"
 python3 "$P/scripts/production_source_identity.py" compile "$ROOT" "$OUT" "$HARDFLOAT_SOURCE" "$OFFLINE_TOOLS"
 CP=$(cat "$OUT/classpath.txt");mkdir "$OUT/probeclasses"
 java -Xmx1500m -XX:ActiveProcessorCount=2 -cp "$CP" scala.tools.nsc.Main -classpath "$OUT/classes:$CP" -Xplugin:"$OFFLINE_TOOLS/jars/chisel-plugin_2.13.16-6.7.0.jar" -language:reflectiveCalls -d "$OUT/probeclasses" "$P/src/test/scala/heteronpu/continuous/Matrix4096ArithmeticProbe.scala" >"$OUT/probe_compile.log" 2>&1
 java -Xmx1500m -XX:ActiveProcessorCount=2 -cp "$OUT/probeclasses:$OUT/classes:$CP" heteronpu.continuous.EmitMatrix4096ArithmeticProbe "$OUT/generated" >"$OUT/emit.log" 2>&1
else
 (cd "$P";sbt -batch 'Test / compile' "Test / runMain heteronpu.continuous.EmitMatrix4096ArithmeticProbe $OUT/generated") >"$OUT/compile_emit.log" 2>&1
fi
export RETAINED_SKIP_CLOCK=0;source "$P/scripts/retained_sources.sh"
verilator --cc --exe --build --assert -Wno-fatal --top-module Matrix4096ArithmeticProbe \
 -CFLAGS '-O3 -std=c++17 -ffp-contract=off -fno-fast-math' -j "${BUILD_JOBS:-2}" --Mdir "$OUT/obj" \
 --hierarchical "$P/tests/matrix4096_hierarchy.vlt" "${RETAINED_SOURCES[@]}" \
 "$OUT/generated/Matrix4096ArithmeticProbe.sv" "$P/tests/matrix4096_arithmetic.cpp" >"$OUT/build.log" 2>&1
set +e
"$OUT/obj/VMatrix4096ArithmeticProbe" "$OUT/outputs" >"$OUT/run.log" 2>&1
c=$?;set -e;echo "$c" >"$OUT/simulation.exit";cat "$OUT/run.log";((c==0))||exit "$c"
python3 "$P/scripts/production_source_identity.py" verify "$ROOT" "$OUT" "$HARDFLOAT_SOURCE"
python3 "$P/scripts/verify_matrix4096_arithmetic.py" "$OUT" --output "$OUT/RESULT.json" >"$OUT/verification.log"
cat "$OUT/verification.log"
