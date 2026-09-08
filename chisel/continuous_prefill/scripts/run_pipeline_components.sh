#!/usr/bin/env bash
# Real Chisel/Verilator arithmetic, streaming Dense + pinned iDMA, not a CPU model.
# Existing outputs and DUT sources are never overwritten or removed.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../.." && pwd); P="$ROOT/chisel/continuous_prefill"
OUT=${1:?absolute NEW output directory}
[[ "$OUT" = /* && ! -e "$OUT" && ! -L "$OUT" ]] || { echo OUTPUT_MUST_BE_NEW >&2;exit 2; }
for t in java python3 g++ git; do command -v "$t" >/dev/null || { echo "BLOCKED_MISSING_TOOL:$t";exit 77; };done
[[ -n ${OFFLINE_TOOLS:-} ]] || command -v sbt >/dev/null || { echo BLOCKED_MISSING_SBT;exit 77; }
[[ -n ${IDMA_EXPORT:-} && -f "$IDMA_EXPORT/idma.f.in" ]] || { echo BLOCKED_PINNED_IDMA;exit 77; }
python3 -c 'import numpy' || { echo BLOCKED_NUMPY;exit 77; }
mkdir -p "$(dirname "$OUT")";mkdir "$OUT"
trap 'code=$?;printf "%s\n" "$code" >"$OUT/gate.exit";exit "$code"' EXIT
source "$P/scripts/prepare_verilator_runtime.sh" "$OUT"
export MAKEFLAGS="${MAKEFLAGS:-} VK_PCH_I_FAST= VK_PCH_I_SLOW= OPT_FAST=-O3"
export HARDFLOAT_SOURCE=${HARDFLOAT_SOURCE:-$ROOT/work/upstream/hardfloat_continuous}
[[ -d "$HARDFLOAT_SOURCE/hardfloat/src/main/scala" ]] || bash "$P/scripts/prepare_hardfloat.sh" >"$OUT/hardfloat_prepare.log" 2>&1
python3 "$P/scripts/prepare_idma_export.py" "$IDMA_EXPORT" "$OUT" >"$OUT/idma_verify.log"
python3 "$P/scripts/production_source_identity.py" record "$ROOT" "$OUT" "$HARDFLOAT_SOURCE"
git -C "$ROOT" rev-parse HEAD >"$OUT/source_base_commit.txt"
if [[ -n ${OFFLINE_TOOLS:-} ]]; then
 export CHISEL_FIRTOOL_PATH="$OFFLINE_TOOLS/bin"
 python3 "$P/scripts/production_source_identity.py" compile "$ROOT" "$OUT" "$HARDFLOAT_SOURCE" "$OFFLINE_TOOLS"
 CP=$(cat "$OUT/classpath.txt");mkdir "$OUT/testclasses"
 java -Xmx1500m -XX:ActiveProcessorCount=2 -cp "$CP" scala.tools.nsc.Main -classpath "$OUT/classes:$CP" \
  -Xplugin:"$OFFLINE_TOOLS/jars/chisel-plugin_2.13.16-6.7.0.jar" -language:reflectiveCalls -d "$OUT/testclasses" \
  "$P/src/test/scala/heteronpu/continuous/MatrixPipelineProbe.scala" \
  "$P/src/test/scala/heteronpu/continuous/StreamingDenseProbe.scala" \
  "$P/src/test/scala/heteronpu/continuous/VectorSiluSpec.scala" >"$OUT/test_compile.log" 2>&1
 (cd "$OUT";java -Xmx2G -XX:ActiveProcessorCount=2 -cp "$OUT/testclasses:$OUT/classes:$CP" \
  org.scalatest.tools.Runner -R "$OUT/testclasses" -o -s heteronpu.continuous.VectorSiluSpec) >"$OUT/silu_tests.log" 2>&1
 for kind in MatrixPipeline StreamingDense;do
  java -Xmx2G -XX:ActiveProcessorCount=2 -cp "$OUT/testclasses:$OUT/classes:$CP" \
   "heteronpu.continuous.Emit${kind}Probe" "$OUT/$kind/generated" >"$OUT/${kind}_emit.log" 2>&1
 done
else
 (cd "$P";sbt -batch 'Test / compile' 'testOnly heteronpu.continuous.VectorSiluSpec' \
  "Test / runMain heteronpu.continuous.EmitMatrixPipelineProbe $OUT/MatrixPipeline/generated" \
  "Test / runMain heteronpu.continuous.EmitStreamingDenseProbe $OUT/StreamingDense/generated") >"$OUT/compile_emit_silu.log" 2>&1
fi
export RETAINED_SKIP_CLOCK=0;source "$P/scripts/retained_sources.sh"
for kind in MatrixPipeline StreamingDense;do
 d="$OUT/$kind";top="${kind}Probe"
 cpp=matrix_pipeline.cpp;[[ "$kind" != StreamingDense ]] || cpp=streaming_dense.cpp
 # Release the parent elaborator before compiling hierarchical children.
 verilator --cc --exe --assert -Wno-fatal --top-module "$top" \
  -CFLAGS '-O3 -std=c++17 -ffp-contract=off -fno-fast-math' -j "${BUILD_JOBS:-2}" --Mdir "$d/obj" \
  --hierarchical "$P/tests/matrix4096_hierarchy.vlt" "${RETAINED_SOURCES[@]}" -f "$OUT/idma.f" \
  "$ROOT/rtl/integration/idma_backend_rw_axi_flat_wrap.sv" "$d/generated/$top.sv" "$P/tests/$cpp" >"$d/build.log" 2>&1
 make -C "$d/obj" -f "V${top}_hier.mk" -j "${BUILD_JOBS:-2}" >>"$d/build.log" 2>&1
 set +e
 "$d/obj/V$top" "$d/outputs" >"$d/run.log" 2>&1;c=$?
 set -e;printf '%s\n' "$c" >"$d/simulation.exit";cat "$d/run.log";((c==0))||exit "$c"
done
# Same generated MatrixPipeline circuit; relink only the error-injection driver.
d="$OUT/MatrixPipeline";vr="$VERILATOR_ROOT";mkdir "$OUT/MatrixErrors"
g++ -O3 -std=c++17 -ffp-contract=off -fno-fast-math \
 -I"$d/obj" -I"$vr/include" -I"$vr/include/vltstd" -I"$P/tests" \
 "$P/tests/matrix_pipeline_errors.cpp" "$d/obj/VMatrixPipelineProbe__ALL.a" \
 "$d/obj/Vqwen2_matrix_command_endpoint/libqwen2_matrix_command_endpoint.a" \
 "$d/obj/Vbf16_context_lane_cluster16_rev8b_b_candidate/libbf16_context_lane_cluster16_rev8b_b_candidate.a" \
 "$d/obj/verilated.o" "$d/obj/verilated_dpi.o" "$d/obj/verilated_threads.o" -pthread -latomic \
 -o "$OUT/MatrixErrors/VMatrixErrors" >"$OUT/MatrixErrors/build.log" 2>&1
set +e
"$OUT/MatrixErrors/VMatrixErrors" "$OUT/MatrixErrors/outputs" >"$OUT/MatrixErrors/run.log" 2>&1;c=$?
set -e;echo "$c" >"$OUT/MatrixErrors/simulation.exit";cat "$OUT/MatrixErrors/run.log";((c==0))||exit "$c"
python3 "$P/scripts/production_source_identity.py" verify "$ROOT" "$OUT" "$HARDFLOAT_SOURCE"
python3 "$P/scripts/verify_pipeline_components.py" --evidence "$OUT" --output "$OUT/RESULT.json" >"$OUT/verification.log"
cat "$OUT/verification.log"
