#!/usr/bin/env bash
# Exercise the unchanged pinned iDMA, including actual payload and bus faults.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
P="$ROOT/chisel/continuous_prefill"
OUT=${1:?usage: run_pinned_idma_gate.sh /absolute/new/output}
[[ "$OUT" = /* && ! -e "$OUT" ]] || { echo 'output must be an absolute new directory' >&2; exit 2; }
: "${IDMA_EXPORT:?set IDMA_EXPORT to the verified idma_export directory}"
for t in java g++ python3 git; do command -v "$t" >/dev/null || { echo "BLOCKED_MISSING_TOOL: $t" >&2; exit 77; }; done
if [[ -n ${OFFLINE_TOOLS:-} ]]; then
  export CHISEL_FIRTOOL_PATH="$OFFLINE_TOOLS/bin" VERILATOR_ROOT="$OFFLINE_TOOLS/share/verilator" PATH="$OFFLINE_TOOLS/bin:$PATH"
else
  command -v sbt >/dev/null || { echo BLOCKED_MISSING_SBT >&2; exit 77; }
fi
command -v verilator >/dev/null || { echo BLOCKED_MISSING_VERILATOR >&2; exit 77; }
mkdir -p "$OUT"
trap 'code=$?; printf "%s\n" "$code" >"$OUT/gate.exit"; exit "$code"' EXIT
export HARDFLOAT_SOURCE=${HARDFLOAT_SOURCE:-$ROOT/work/upstream/hardfloat_continuous}
if [[ ! -d "$HARDFLOAT_SOURCE/hardfloat/src/main/scala" ]]; then bash "$P/scripts/prepare_hardfloat.sh" >"$OUT/prepare_hardfloat.log" 2>&1; fi
python3 "$P/scripts/prepare_idma_export.py" "$IDMA_EXPORT" "$OUT" >"$OUT/idma_verify.log"
python3 "$P/scripts/production_source_identity.py" record "$ROOT" "$OUT" "$HARDFLOAT_SOURCE"
git -C "$ROOT" rev-parse HEAD >"$OUT/source_base_commit.txt"
verilator --version >"$OUT/verilator.txt"
export MAKEFLAGS="${MAKEFLAGS:-} CFG_CXXFLAGS_PCH_I=-include OPT_FAST=-O3"
if [[ -n ${OFFLINE_TOOLS:-} ]]; then
  python3 "$P/scripts/production_source_identity.py" compile "$ROOT" "$OUT" "$HARDFLOAT_SOURCE" "$OFFLINE_TOOLS"
  java -Xmx3G -XX:ActiveProcessorCount=3 -cp "$OUT/classes:$(cat "$OUT/classpath.txt")" heteronpu.continuous.EmitProductionGate "$OUT/generated" transport >"$OUT/emit.log" 2>&1
else
  (cd "$P"; sbt -batch compile "runMain heteronpu.continuous.EmitProductionGate $OUT/generated transport") >"$OUT/compile_emit.log" 2>&1
fi
verilator --cc --exe --build --assert -Wno-fatal --top-module RetainedIdmaMemoryAdapter \
  -CFLAGS '-O3 -std=c++17' -j "${BUILD_JOBS:-3}" --Mdir "$OUT/obj" -f "$OUT/idma.f" \
  "$OUT/generated/RetainedIdmaMemoryAdapter.sv" "$ROOT/rtl/integration/idma_backend_rw_axi_flat_wrap.sv" \
  "$P/tests/pinned_idma_memory.cpp" >"$OUT/build.log" 2>&1
set +e
"$OUT/obj/VRetainedIdmaMemoryAdapter" >"$OUT/run.log" 2>&1
code=$?
set -e
printf '%s\n' "$code" >"$OUT/simulation.exit"; cat "$OUT/run.log"
((code==0)) || exit "$code"
python3 "$P/scripts/production_source_identity.py" verify "$ROOT" "$OUT" "$HARDFLOAT_SOURCE"
python3 - "$OUT" <<'PY'
from pathlib import Path
import hashlib,json,re,sys
out=Path(sys.argv[1]);text=(out/'run.log').read_text()
lines=[x for x in text.splitlines() if x.startswith('PINNED_IDMA_TRANSPORT_PASS ')]
if len(lines)!=1 or 'TRANSPORT_FAIL' in text:raise SystemExit('invalid transport test result')
f=dict(re.findall(r'(\w+)=(\d+)',lines[0]))
for key,value in [('cases',145),('original_backend',1),('response_after_axi_ack',1)]:
    if int(f[key])!=value:raise SystemExit('wrong '+key)
if int(f['request_stalls'])<=0 or int(f['response_delay_cycles'])<=0:raise SystemExit('no backpressure')
(out/'RESULT.json').write_text(json.dumps({'status':'PASS_ACTUAL_PINNED_IDMA_TRANSPORT','receipt':f,'source_manifest_sha256':hashlib.sha256((out/'sources.sha256.json').read_bytes()).hexdigest(),'log_sha256':hashlib.sha256((out/'run.log').read_bytes()).hexdigest(),'full_block':False},indent=2)+'\n')
PY
