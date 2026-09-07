#!/usr/bin/env bash
# CONTROL-ONLY: real H1536/F8960, 16 tokens, two layers, 42 Host commands.
# Metadata responses and owner completions are test services, NOT arithmetic.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
P="$ROOT/chisel/continuous_prefill"
OUT=${1:?absolute NEW output directory}
[[ "$OUT" = /* && ! -e "$OUT" ]] || { echo OUTPUT_MUST_BE_NEW >&2; exit 2; }
for tool in python3 java g++; do
  command -v "$tool" >/dev/null || { echo "BLOCKED_MISSING_TOOL:$tool" >&2; exit 77; }
done
python3 -c 'import numpy, yaml' || { echo BLOCKED_PYTHON_DEPENDENCIES >&2; exit 77; }
mkdir -p "$OUT"
trap 'code=$?;echo "$code" > "$OUT/gate.exit";exit "$code"' EXIT
source "$P/scripts/prepare_verilator_runtime.sh" "$OUT"
export MAKEFLAGS="${MAKEFLAGS:-} VK_PCH_I_FAST= VK_PCH_I_SLOW="
export HARDFLOAT_SOURCE=${HARDFLOAT_SOURCE:-$ROOT/work/upstream/hardfloat_continuous}
[[ -d "$HARDFLOAT_SOURCE/hardfloat/src/main/scala" ]] || bash "$P/scripts/prepare_hardfloat.sh" > "$OUT/prepare.log" 2>&1
printf 'H=1536 F=8960 HEADS=12 KVHEADS=2 HD=128 MAX_TOKENS=1024\n' > "$OUT/shape.h"
python3 "$P/scripts/pack_owner_multilayer_fixture.py" "$OUT/shape.h" "$OUT/fixture" \
  --tokens 16 --layers 2 --relocate 9467985920 > "$OUT/packing.log"
export OWNER_FIXTURE="$OUT/fixture"
python3 "$P/scripts/production_source_identity.py" record "$ROOT" "$OUT" "$HARDFLOAT_SOURCE"
if [[ -n ${OFFLINE_TOOLS:-} ]]; then
  export CHISEL_FIRTOOL_PATH="$OFFLINE_TOOLS/bin"
  python3 "$P/scripts/production_source_identity.py" compile "$ROOT" "$OUT" "$HARDFLOAT_SOURCE" "$OFFLINE_TOOLS"
  CP=$(cat "$OUT/classpath.txt")
  mkdir "$OUT/testclasses"
  printf '%s\n' \
    "$P/src/test/scala/heteronpu/continuous/HostBlockCommandsSpec.scala" \
    "$P/src/test/scala/heteronpu/continuous/HostBlockCommandsRealLayersSpec.scala" > "$OUT/test_sources.txt"
  java -Xmx2G -XX:ActiveProcessorCount=2 -cp "$CP" scala.tools.nsc.Main \
    -classpath "$OUT/classes:$CP" -Xplugin:"$OFFLINE_TOOLS/jars/chisel-plugin_2.13.16-6.7.0.jar" \
    -language:reflectiveCalls -d "$OUT/testclasses" @"$OUT/test_sources.txt" > "$OUT/test_compile.log" 2>&1
  (cd "$OUT"; java -Xmx2G -XX:ActiveProcessorCount=2 -cp "$OUT/testclasses:$OUT/classes:$CP" \
    org.scalatest.tools.Runner -R "$OUT/testclasses" -o -s heteronpu.continuous.HostBlockCommandsRealLayersSpec) \
    > "$OUT/chisel_tests.log" 2>&1
else
  (cd "$P"; sbt -batch compile Test/compile 'testOnly heteronpu.continuous.HostBlockCommandsRealLayersSpec') \
    > "$OUT/chisel_tests.log" 2>&1
fi
python3 "$P/scripts/production_source_identity.py" verify "$ROOT" "$OUT" "$HARDFLOAT_SOURCE" > "$OUT/source_verify.log"
python3 - "$OUT" <<'PY'
from pathlib import Path
import hashlib, json, re, sys
out = Path(sys.argv[1]); text = (out / 'chisel_tests.log').read_text()
plain = re.sub(r'\x1b\[[0-9;]*m', '', text)
if not (re.search(r'Total number of tests run: 9\b', plain) and
        'Tests: succeeded 9, failed 0, canceled 0, ignored 0, pending 0' in plain and
        'All tests passed.' in plain):
    raise SystemExit('INCOMPLETE_REAL_TWO_LAYER_FRONTEND_TESTS')
if 'SOURCE_IMMUTABILITY_PASS' not in (out / 'source_verify.log').read_text():
    raise SystemExit('SOURCE_IDENTITY_FAILED')
m = json.loads((out / 'fixture/manifest.json').read_text())
if (m['shape']['H'], m['shape']['F'], m['tokens'], m['layers'], m['commands'], m['descriptors']) != (1536,8960,16,2,42,430):
    raise SystemExit('WRONG_FIXED_GEOMETRY')
if m['tensors']['l1_x']['address'] != m['tensors']['l0_y']['address']:
    raise SystemExit('BROKEN_LAYER_DESCRIPTOR_ALIAS')
result = {'status':'PASS_REAL16_TWO_LAYER_HOST_FRONTEND_CONTROL_ONLY',
          'tests_passed':9, 'tokens':16, 'layers':2, 'hidden':1536, 'ffn':8960,
          'commands':42, 'descriptors':430, 'successful_path_owner_jobs':38,
          'chisel_decoder_dut':True, 'metadata_service':'controlled_test_responses',
          'owner_completions':'controlled_test_responses', 'actual_idma':False,
          'matrix_arithmetic':False, 'numerical_multilayer_pass':False,
          'source_identity_verified':True,
          'log_sha256':hashlib.sha256((out/'chisel_tests.log').read_bytes()).hexdigest()}
with (out / 'RESULT.json').open('x') as stream:
    json.dump(result,stream,indent=2);stream.write('\n')
print(json.dumps(result,indent=2))
PY
cat "$OUT/chisel_tests.log"
