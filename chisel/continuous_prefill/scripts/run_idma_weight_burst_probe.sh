#!/usr/bin/env bash
# Actual pinned-iDMA protocol/data regression, not a mocked transport.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../.." && pwd); P="$ROOT/chisel/continuous_prefill"
OUT=${1:?absolute NEW directory}
[[ "$OUT" = /* && ! -e "$OUT" && ! -L "$OUT" ]] || exit 2
for t in java g++ python3; do command -v "$t" >/dev/null || { echo "BLOCKED_MISSING_TOOL:$t"; exit 77; }; done
[[ -n ${IDMA_EXPORT:-} && -f "$IDMA_EXPORT/idma.f.in" ]] || { echo BLOCKED_PINNED_IDMA; exit 77; }
mkdir -p "$(dirname "$OUT")"; mkdir "$OUT"
trap 'c=$?;echo "$c" >"$OUT/gate.exit";exit "$c"' EXIT
source "$P/scripts/prepare_verilator_runtime.sh" "$OUT"
export MAKEFLAGS="${MAKEFLAGS:-} VK_PCH_I_FAST= VK_PCH_I_SLOW= OPT_FAST=-O3"
export HARDFLOAT_SOURCE=${HARDFLOAT_SOURCE:-$ROOT/work/upstream/hardfloat_continuous}
[[ -d "$HARDFLOAT_SOURCE/hardfloat/src/main/scala" ]] || bash "$P/scripts/prepare_hardfloat.sh" >"$OUT/prepare.log" 2>&1
python3 "$P/scripts/production_source_identity.py" record "$ROOT" "$OUT" "$HARDFLOAT_SOURCE"
python3 "$P/scripts/prepare_idma_export.py" "$IDMA_EXPORT" "$OUT" >"$OUT/idma_verify.log"
if [[ -n ${OFFLINE_TOOLS:-} ]]; then
  export CHISEL_FIRTOOL_PATH="$OFFLINE_TOOLS/bin"
  python3 "$P/scripts/production_source_identity.py" compile "$ROOT" "$OUT" "$HARDFLOAT_SOURCE" "$OFFLINE_TOOLS"
  CP=$(cat "$OUT/classpath.txt"); mkdir "$OUT/testclasses"
  java -Xmx1500m -XX:ActiveProcessorCount=2 -cp "$CP" scala.tools.nsc.Main -classpath "$OUT/classes:$CP" \
    -Xplugin:"$OFFLINE_TOOLS/jars/chisel-plugin_2.13.16-6.7.0.jar" -language:reflectiveCalls \
    -d "$OUT/testclasses" "$P/src/test/scala/heteronpu/continuous/IdmaWeightBurstProbe.scala" >"$OUT/probe_compile.log" 2>&1
  java -Xmx2G -XX:ActiveProcessorCount=2 -cp "$OUT/testclasses:$OUT/classes:$CP" \
    heteronpu.continuous.EmitIdmaWeightBurstProbe "$OUT/generated" >"$OUT/emit.log" 2>&1
else
  (cd "$P";sbt -batch "Test / runMain heteronpu.continuous.EmitIdmaWeightBurstProbe $OUT/generated") >"$OUT/compile_emit.log" 2>&1
fi
verilator --cc --exe --build --assert -Wno-fatal --top-module IdmaWeightBurstProbe \
  -CFLAGS '-O3 -std=c++17' -j "${BUILD_JOBS:-3}" --Mdir "$OUT/obj" \
  -f "$OUT/idma.f" "$OUT/generated/IdmaWeightBurstProbe.sv" \
  "$ROOT/rtl/integration/idma_backend_rw_axi_flat_wrap.sv" "$P/tests/idma_weight_burst.cpp" >"$OUT/build.log" 2>&1
set +e
"$OUT/obj/VIdmaWeightBurstProbe" >"$OUT/run.log" 2>&1
c=$?;set -e;echo "$c" >"$OUT/simulation.exit";cat "$OUT/run.log";((c==0)) || exit "$c"
python3 "$P/scripts/production_source_identity.py" verify "$ROOT" "$OUT" "$HARDFLOAT_SOURCE"
python3 - "$OUT" <<'PY'
import hashlib,json,re,sys
from pathlib import Path
p=Path(sys.argv[1]);text=(p/'run.log').read_text()
lines=[s for s in text.splitlines() if s.startswith('IDMA_WEIGHT_BURST_PASS ')]
if len(lines)!=1 or 'FAIL' in text:raise SystemExit('INCOMPLETE_BURST_PROBE')
v=dict(re.findall(r'(\w+)=(\d+)',lines[0]))
if any(int(v[k])!=n for k,n in {'cases':24,'real_pinned_idma':1,'max_beats':16,'mailbox_bytes':1024,'data_mismatches':0}.items()):raise SystemExit('BAD_PROBE_COUNTERS')
if not 0<int(v['supply_cycles_burst'])<int(v['supply_cycles_single']):raise SystemExit('NO_SUPPLY_IMPROVEMENT')
r={'status':'PASS_REAL_IDMA_WEIGHT_BURST_PROBE','counters':v,'full_model':False,'dc':False,
   'log_sha256':hashlib.sha256((p/'run.log').read_bytes()).hexdigest(),
   'generated_sha256':hashlib.sha256((p/'generated/IdmaWeightBurstProbe.sv').read_bytes()).hexdigest()}
with (p/'RESULT.json').open('x') as f:json.dump(r,f,indent=2);f.write('\n')
PY
