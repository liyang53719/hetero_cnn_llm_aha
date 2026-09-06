#!/usr/bin/env bash
# Actual Chisel DUT and unchanged upstream iDMA; no generated-SV editing.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
P="$ROOT/chisel/continuous_prefill"
OUT=${1:?usage: run_record128_gate.sh /absolute/new/output}
[[ "$OUT" = /* && ! -e "$OUT" ]] || { echo 'new absolute output directory required' >&2; exit 2; }
: "${IDMA_EXPORT:?set IDMA_EXPORT to the verified pinned idma_export directory}"
for t in java g++ python3 git; do command -v "$t" >/dev/null || { echo "BLOCKED_MISSING_TOOL: $t" >&2; exit 77; }; done
if [[ -n ${OFFLINE_TOOLS:-} ]]; then
  export CHISEL_FIRTOOL_PATH="$OFFLINE_TOOLS/bin" VERILATOR_ROOT="$OFFLINE_TOOLS/share/verilator"
  export PATH="$OFFLINE_TOOLS/bin:$PATH"
else
  command -v sbt >/dev/null || { echo BLOCKED_MISSING_SBT >&2; exit 77; }
fi
command -v verilator >/dev/null || { echo BLOCKED_MISSING_VERILATOR >&2; exit 77; }
mkdir -p "$OUT"
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'code=$?; printf "%s\n" "$code" >"$OUT/gate.exit"' EXIT
export HARDFLOAT_SOURCE=${HARDFLOAT_SOURCE:-$ROOT/work/upstream/hardfloat_continuous}
if [[ ! -d "$HARDFLOAT_SOURCE/hardfloat/src/main/scala" ]]; then bash "$P/scripts/prepare_hardfloat.sh" >"$OUT/prepare_hardfloat.log" 2>&1; fi
python3 "$P/scripts/prepare_idma_export.py" "$IDMA_EXPORT" "$OUT" >"$OUT/prepare_idma.log"
python3 "$P/scripts/production_source_identity.py" record "$ROOT" "$OUT" "$HARDFLOAT_SOURCE"
git -C "$ROOT" rev-parse HEAD >"$OUT/source_base_commit.txt"
export MAKEFLAGS="${MAKEFLAGS:-} CFG_CXXFLAGS_PCH_I=-include OPT_FAST=-O3"
if [[ -n ${OFFLINE_TOOLS:-} ]]; then
  python3 "$P/scripts/production_source_identity.py" compile "$ROOT" "$OUT" "$HARDFLOAT_SOURCE" "$OFFLINE_TOOLS"
  CP=$(cat "$OUT/classpath.txt"); mkdir -p "$OUT/test_classes" "$OUT/test_reports"
  java -Xmx2G -XX:ActiveProcessorCount=2 -cp "$CP" scala.tools.nsc.Main -classpath "$OUT/classes:$CP" \
    -Xplugin:"$OFFLINE_TOOLS/jars/chisel-plugin_2.13.16-6.7.0.jar" -language:reflectiveCalls \
    -d "$OUT/test_classes" "$P/src/test/scala/heteronpu/continuous/Record128ReaderSpec.scala" >"$OUT/test_compile.log" 2>&1
  (cd "$OUT"; java -Xmx2G -XX:ActiveProcessorCount=2 -cp "$OUT/test_classes:$OUT/classes:$CP" org.scalatest.tools.Runner \
    -R "$OUT/test_classes" -s heteronpu.continuous.Record128ReaderSpec -o -u "$OUT/test_reports") >"$OUT/chisel_tests.log" 2>&1
  java -Xmx2G -XX:ActiveProcessorCount=2 -cp "$OUT/classes:$CP" heteronpu.continuous.EmitRecord128Reader "$OUT/generated" >"$OUT/emit.log" 2>&1
else
  (cd "$P"; sbt -batch compile 'testOnly heteronpu.continuous.Record128ReaderSpec' \
    "runMain heteronpu.continuous.EmitRecord128Reader $OUT/generated") >"$OUT/chisel_tests.log" 2>&1
fi
verilator --cc --exe --build --assert -Wno-fatal --top-module Record128IdmaTop \
  -CFLAGS '-O3 -std=c++17' -j "${BUILD_JOBS:-2}" --Mdir "$OUT/obj" -f "$OUT/idma.f" \
  "$OUT/generated/Record128IdmaTop.sv" "$ROOT/rtl/integration/idma_backend_rw_axi_flat_wrap.sv" \
  "$P/tests/record128_idma.cpp" >"$OUT/build.log" 2>&1
set +e
"$OUT/obj/VRecord128IdmaTop" >"$OUT/run.log" 2>&1
code=$?
set -e
printf '%s\n' "$code" >"$OUT/simulation.exit"; cat "$OUT/run.log"
((code==0)) || exit "$code"
python3 "$P/scripts/production_source_identity.py" verify "$ROOT" "$OUT" "$HARDFLOAT_SOURCE"
python3 - "$OUT" <<'PY'
from pathlib import Path
import hashlib,json,re,sys
p=Path(sys.argv[1]);lines=(p/'run.log').read_text().splitlines()
if len(lines)!=1 or not re.fullmatch(r'RECORD128_IDMA_PASS cases=23 external_read_acks=18 request_stalls=[1-9][0-9]* response_delay_cycles=[1-9][0-9]* original_idma=1 descriptor_execution=0',lines[0]):
    raise SystemExit('Incomplete record/iDMA proof')
if 'All tests passed.' not in (p/'chisel_tests.log').read_text():raise SystemExit('Missing Chisel unit test success')
files=['run.log','chisel_tests.log','sources.sha256.json','generated/Record128IdmaTop.sv','idma_identity.json']
report={'status':'PASS_RECORD128_READ_THROUGH_PINNED_IDMA','unit_tests':10,'integration_cases':23,
        'descriptor_decode':False,'host_graph_execution':False,
        'sha256':{n:hashlib.sha256((p/n).read_bytes()).hexdigest() for n in files}}
(p/'RESULT.json').write_text(json.dumps(report,indent=2)+'\n')
PY
