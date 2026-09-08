#!/usr/bin/env bash
# Actual 4096-MAC + pinned-iDMA component DUT. Memory timing is unchanged.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../.." && pwd);P="$ROOT/chisel/continuous_prefill"
OUT=${1:?absolute NEW output}
[[ "$OUT" = /* && ! -e "$OUT" && ! -L "$OUT" ]] || exit 2
[[ -n ${IDMA_EXPORT:-} && -f "$IDMA_EXPORT/idma.f.in" ]] || { echo BLOCKED_PINNED_IDMA;exit 77; }
for t in java python3 g++ git;do command -v "$t" >/dev/null || { echo "BLOCKED_MISSING_TOOL:$t";exit 77; };done
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
 java -Xmx1500m -XX:ActiveProcessorCount=3 -cp "$CP" scala.tools.nsc.Main -classpath "$OUT/classes:$CP" -Xplugin:"$OFFLINE_TOOLS/jars/chisel-plugin_2.13.16-6.7.0.jar" -language:reflectiveCalls -d "$OUT/testclasses" "$P/src/test/scala/heteronpu/continuous/StreamingDenseProbe.scala" >"$OUT/test_compile.log" 2>&1
 java -Xmx2500m -XX:ActiveProcessorCount=3 -cp "$OUT/testclasses:$OUT/classes:$CP" heteronpu.continuous.EmitStreamingDenseProbe "$OUT/generated" 1 1 >"$OUT/emit.log" 2>&1
else
 (cd "$P";sbt -batch compile "Test / runMain heteronpu.continuous.EmitStreamingDenseProbe $OUT/generated 1 1") >"$OUT/compile_emit.log" 2>&1
fi
python3 "$P/scripts/prepare_idma_export.py" "$IDMA_EXPORT" "$OUT" >"$OUT/idma_verify.log"
export RETAINED_SKIP_CLOCK=0;source "$P/scripts/retained_sources.sh"
verilator --cc --exe --assert -Wno-fatal --top-module StreamingDenseProbe -CFLAGS '-O3 -std=c++17 -ffp-contract=off -fno-fast-math' -j "${BUILD_JOBS:-2}" --Mdir "$OUT/obj" --hierarchical "$P/tests/matrix4096_hierarchy.vlt" "${RETAINED_SOURCES[@]}" -f "$OUT/idma.f" "$OUT/generated/StreamingDenseProbe.sv" "$ROOT/rtl/integration/idma_backend_rw_axi_flat_wrap.sv" "$P/tests/burst_write_dense.cpp" >"$OUT/build.log" 2>&1
make -C "$OUT/obj" -f VStreamingDenseProbe_hier.mk -j "${BUILD_JOBS:-2}" >"$OUT/make.log" 2>&1
set +e
"$OUT/obj/VStreamingDenseProbe" "$OUT/outputs" >"$OUT/run.log" 2>&1
code=$?;set -e;echo "$code" >"$OUT/simulation.exit";cat "$OUT/run.log";((code==0))||exit "$code"
python3 "$P/scripts/production_source_identity.py" verify "$ROOT" "$OUT" "$HARDFLOAT_SOURCE"
python3 "$P/scripts/verify_dense_burst_write.py" "$OUT" >"$OUT/verification.log"
cat "$OUT/verification.log"
