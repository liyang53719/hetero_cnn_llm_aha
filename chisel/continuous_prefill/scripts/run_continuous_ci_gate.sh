#!/usr/bin/env bash
# All control suites get their required fixture; actual elementwise DUT follows.
# This is a regression entrypoint, NOT a Matrix4096 full-model result.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../.." && pwd);P="$ROOT/chisel/continuous_prefill"
OUT=${1:?absolute NEW evidence directory}
[[ "$OUT" = /* && ! -e "$OUT" && ! -L "$OUT" ]] || { echo OUTPUT_MUST_BE_NEW >&2;exit 2; }
for t in java g++ python3; do command -v "$t" >/dev/null || { echo "BLOCKED_MISSING_TOOL:$t" >&2;exit 77; };done
python3 -c 'import numpy,yaml' || { echo BLOCKED_PYTHON_DEPENDENCIES >&2;exit 77; }
mkdir -p "$(dirname "$OUT")";mkdir "$OUT"
trap 'c=$?;echo "$c" >"$OUT/gate.exit";exit "$c"' EXIT
source "$P/scripts/prepare_verilator_runtime.sh" "$OUT"
export MAKEFLAGS="${MAKEFLAGS:-} VK_PCH_I_FAST= VK_PCH_I_SLOW="
export HARDFLOAT_SOURCE=${HARDFLOAT_SOURCE:-$ROOT/work/upstream/hardfloat_continuous}
[[ -d "$HARDFLOAT_SOURCE/hardfloat/src/main/scala" ]] || bash "$P/scripts/prepare_hardfloat.sh" >"$OUT/hardfloat_prepare.log" 2>&1
python3 "$P/scripts/production_source_identity.py" record "$ROOT" "$OUT" "$HARDFLOAT_SOURCE"
printf 'H=64 F=128 HEADS=2 KVHEADS=1 HD=32 MAX_TOKENS=1024\n' > "$OUT/tiny_shape.h"
printf 'H=1536 F=8960 HEADS=12 KVHEADS=2 HD=128 MAX_TOKENS=1024\n' > "$OUT/real_shape.h"
python3 "$P/scripts/pack_owner_block_fixture.py" "$OUT/tiny_shape.h" "$OUT/tiny_fixture" >"$OUT/tiny_packing.log"
python3 "$P/scripts/pack_owner_multilayer_fixture.py" "$OUT/real_shape.h" "$OUT/real_fixture" --tokens 16 --layers 2 --relocate 9467985920 >"$OUT/real_packing.log"
# Explicit enumeration avoids constructing the real suite with tiny metadata.
# Discover every *Spec source, then execute both fixture-dependent suites alone.
python3 - "$P" "$OUT" <<'PY'
from pathlib import Path
import json,sys
p,out=map(Path,sys.argv[1:]); names=sorted('heteronpu.continuous.'+f.stem for f in (p/'src/test/scala/heteronpu/continuous').glob('*Spec.scala'))
required=['heteronpu.continuous.HostBlockCommandsSpec','heteronpu.continuous.HostBlockCommandsRealLayersSpec']
if not all(x in names for x in required):raise SystemExit('MISSING_FIXTURE_SUITE')
(out/'suite_plan.json').write_text(json.dumps({'general':[n for n in names if n not in required], 'tiny':[required[0]],'real':[required[1]]},indent=2)+'\n')
PY
if [[ -n ${OFFLINE_TOOLS:-} ]];then
 export CHISEL_FIRTOOL_PATH="$OFFLINE_TOOLS/bin"
 python3 "$P/scripts/production_source_identity.py" compile "$ROOT" "$OUT" "$HARDFLOAT_SOURCE" "$OFFLINE_TOOLS"
 CP=$(cat "$OUT/classpath.txt");mkdir "$OUT/testclasses"
 find "$P/src/test/scala" -name '*.scala' | sort >"$OUT/test_sources.txt"
 java -Xmx3G -XX:ActiveProcessorCount=3 -cp "$CP" scala.tools.nsc.Main -classpath "$OUT/classes:$CP" \
  -Xplugin:"$OFFLINE_TOOLS/jars/chisel-plugin_2.13.16-6.7.0.jar" -language:reflectiveCalls \
  -d "$OUT/testclasses" @"$OUT/test_sources.txt" >"$OUT/test_compile.log" 2>&1
else
 (cd "$P";sbt -batch compile Test/compile) >"$OUT/compile.log" 2>&1
fi
for group in general tiny real;do
 mapfile -t SUITES < <(python3 -c 'import json,sys;print("\n".join(json.load(open(sys.argv[1]))[sys.argv[2]]))' "$OUT/suite_plan.json" "$group")
 [[ ${#SUITES[@]} -gt 0 ]] || { echo EMPTY_SUITE_GROUP >&2;exit 2; }
 export OWNER_FIXTURE="$OUT/tiny_fixture"
 [[ "$group" != real ]] || export OWNER_FIXTURE="$OUT/real_fixture"
 mkdir "$OUT/$group"
 if [[ -n ${OFFLINE_TOOLS:-} ]];then
  ARGS=();for suite in "${SUITES[@]}";do ARGS+=(-s "$suite");done
  (cd "$OUT/$group";java -Xmx3G -XX:ActiveProcessorCount=3 -cp "$OUT/testclasses:$OUT/classes:$CP" org.scalatest.tools.Runner -R "$OUT/testclasses" -o "${ARGS[@]}") >"$OUT/$group/chisel_tests.log" 2>&1
 else
  (cd "$P";sbt -batch "testOnly ${SUITES[*]}") >"$OUT/$group/chisel_tests.log" 2>&1
 fi
 cat "$OUT/$group/chisel_tests.log"
done
if [[ -n ${OFFLINE_TOOLS:-} ]];then
 java -Xmx3G -XX:ActiveProcessorCount=3 -cp "$OUT/classes:$CP" heteronpu.continuous.EmitContinuous "$OUT/generated_ci" --small-fabric >"$OUT/emit.log" 2>&1
else
 (cd "$P";sbt -batch "runMain heteronpu.continuous.EmitContinuous $OUT/generated_ci --small-fabric") >"$OUT/emit.log" 2>&1
fi
verilator --cc --exe --build --assert -Wno-fatal --top-module ContinuousElementwiseTop \
 -CFLAGS '-O2 -std=c++17 -ffp-contract=off -fno-fast-math' -j "${BUILD_JOBS:-2}" --Mdir "$OUT/obj" \
 "$OUT/generated_ci/ContinuousElementwiseTop.sv" "$P/tests/continuous_memory.cpp" >"$OUT/verilator_build.log" 2>&1
for count in 1 17 33 1025 32768 1572864 2097152 2621440;do
 "$OUT/obj/VContinuousElementwiseTop" "$count" >"$OUT/n${count}.log" 2>&1
 cat "$OUT/n${count}.log"
done
"$OUT/obj/VContinuousElementwiseTop" 1025 fail >"$OUT/memory_failure.log" 2>&1
python3 "$P/scripts/production_source_identity.py" verify "$ROOT" "$OUT" "$HARDFLOAT_SOURCE" >"$OUT/source_verify.log"
python3 - "$OUT" <<'PY'
import hashlib,json,re,sys
from pathlib import Path
out=Path(sys.argv[1]);plan=json.loads((out/'suite_plan.json').read_text());groups={}
for name,suites in plan.items():
 text=re.sub(r'\x1b\[[0-9;]*m','',(out/name/'chisel_tests.log').read_text())
 counts=re.findall(r'Tests: succeeded (\d+), failed 0, canceled 0, ignored 0, pending 0',text)
 if len(counts)!=1 or 'All tests passed.' not in text or '***' in text:raise SystemExit('INCOMPLETE_CONTROL_SUITE:'+name)
 if any(s.split('.')[-1]+':' not in text for s in suites):raise SystemExit('MISSING_SUITE:'+name)
 groups[name]={'tests':int(counts[0]),'suites':suites}
if groups['tiny']['tests']!=7 or groups['real']['tests']!=9:raise SystemExit('INCOMPLETE_FIXTURE_TESTS')
if 'SOURCE_IMMUTABILITY_PASS' not in (out/'source_verify.log').read_text():raise SystemExit('SOURCE_DRIFT')
report={'status':'PASS_CONTINUOUS_CONTROL_AND_ELEMENTWISE_REGRESSION','groups':groups,
 'total_tests':sum(x['tests'] for x in groups.values()),'elementwise_sizes':[1,17,33,1025,32768,1572864,2097152,2621440],
 'scope':{'matrix4096_full_numerical':False,'official_model':False,'dc':False},
 'logs_sha256':{str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*.log'))}}
with (out/'RESULT.json').open('x') as f:json.dump(report,f,indent=2);f.write('\n')
print(json.dumps(report,indent=2))
PY
