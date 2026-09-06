#!/usr/bin/env bash
# Reuse the already built, real HostResidualIdmaTop. Never patch generated files.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
P="$ROOT/chisel/continuous_prefill"
OUT=${1:?usage: run_host_partial_failure_gate.sh /absolute/new/output /absolute/passed/commands}
COMMANDS=${2:?passed command gate directory}
[[ "$OUT" = /* && ! -e "$OUT" && "$COMMANDS" = /* ]] || exit 2
for t in python3 g++ verilator; do
  if [[ "$t" = verilator && -n ${OFFLINE_TOOLS:-} ]]; then
    export VERILATOR_ROOT="$OFFLINE_TOOLS/share/verilator" PATH="$OFFLINE_TOOLS/bin:$PATH"
  fi
  command -v "$t" >/dev/null || { echo "BLOCKED_MISSING_TOOL: $t" >&2;exit 77; }
done
if [[ -z ${VERILATOR_ROOT:-} ]]; then
  VERILATOR_ROOT=$(verilator -V | awk '$1=="VERILATOR_ROOT" && $2=="=" && NF>=3 {print $3;exit}')
  export VERILATOR_ROOT
fi
[[ -f "$VERILATOR_ROOT/include/verilated.h" ]] || { echo BLOCKED_VERILATOR_HEADERS >&2;exit 77; }
mkdir -p "$OUT"
trap 'code=$?; printf "%s\n" "$code" >"$OUT/gate.exit";exit "$code"' EXIT
export HARDFLOAT_SOURCE=${HARDFLOAT_SOURCE:-$ROOT/work/upstream/hardfloat_continuous}
python3 "$P/scripts/production_source_identity.py" verify "$ROOT" "$COMMANDS" "$HARDFLOAT_SOURCE" >"$OUT/source_recheck.log"
python3 - "$COMMANDS" "$P" "$OUT" <<'PY'
import hashlib,json,sys
from pathlib import Path
commands,p,out=map(Path,sys.argv[1:])
def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()
for name in ('gate.exit','simulation.exit'):
    if (commands/name).read_text().strip()!='0':raise SystemExit('prerequisite gate did not pass')
r=json.loads((commands/'RESULT.json').read_text())
if r['status']!='PASS_SHARED_COMMAND_IDMA_SUITE':raise SystemExit('wrong prerequisite gate')
for name,digest in r['files'].items():
    if sha(commands/name)!=digest:raise SystemExit('changed prerequisite artifact: '+name)
files=[commands/'obj'/n for n in ('VHostResidualIdmaTop__ALL.a','verilated.o','verilated_threads.o','VHostResidualIdmaTop.h')]
files += [p/'tests/host_command_partial_failure.cpp',p/'tests/host_command_axi_service.h',p/'scripts/run_host_partial_failure_gate.sh']
(out/'inputs.sha256.json').write_text(json.dumps({str(f.resolve()):sha(f) for f in files},indent=2)+'\n')
PY
OBJ="$COMMANDS/obj"
g++ -O3 -std=c++17 -ffp-contract=off -fno-fast-math \
  -I"$OBJ" -I"$P/tests" -I"$VERILATOR_ROOT/include" -I"$VERILATOR_ROOT/include/vltstd" \
  "$P/tests/host_command_partial_failure.cpp" \
  "$OBJ/VHostResidualIdmaTop__ALL.a" "$OBJ/verilated.o" "$OBJ/verilated_threads.o" \
  -pthread -lpthread -latomic -o "$OUT/host_command_partial_failure" >"$OUT/build.log" 2>&1
set +e
"$OUT/host_command_partial_failure" >"$OUT/run.log" 2>&1
code=$?;set -e
printf '%s\n' "$code" >"$OUT/simulation.exit"
cat "$OUT/run.log"
((code==0)) || exit "$code"
python3 - "$OUT" <<'PY'
import hashlib,json,re,sys
from pathlib import Path
out=Path(sys.argv[1]);text=(out/'run.log').read_text()
def require(ok,msg):
    if not ok:raise SystemExit('PARTIAL_FAILURE_GATE_REJECTED: '+msg)
def rows(tag):
    result=[]
    for line in text.splitlines():
        if line.startswith(tag+' '):
            entries=re.findall(r'(\w+)=([^\s]+)',line)
            require(len(entries)==len(dict(entries)),'duplicate field')
            result.append(dict(entries))
    return result
require(not re.search('HOST_PARTIAL_FAILURE_FAIL|%Error|Fatal|Assertion failed',text),'failure in log')
failures=rows('HOST_PARTIAL_FAILURE_PASS');recoveries=rows('HOST_RESET_RECOVERY_PASS')
expected=[(pc,fault) for pc in range(3) for fault in range(4)]
for data in (failures,recoveries):
    require([(int(r['pc']),int(r['fault'])) for r in data]==expected,'missing/repeated/reordered case')
for r in failures:
    pc,fault=int(r['pc']),int(r['fault'])
    for key,value in dict(status=3,successful_commands=pc,current_visible_bytes=128 if fault==3 else 0,
                          dependent_commands=0,error_completions=1,original_idma=1).items():
        require(int(r[key])==value,'wrong fault counter: '+key)
for r in recoveries:
    require(int(r['commands'])==3 and int(r['checked_fp32'])==99,'wrong recovery size')
end=rows('HOST_PARTIAL_FAILURE_SUITE_PASS')
require(len(end)==1 and end[0]==dict(fault_cases='12',reset_recoveries='12',original_idma='1',arithmetic_stub='0'),'incomplete suite')
for file,digest in json.loads((out/'inputs.sha256.json').read_text()).items():
    require(hashlib.sha256(Path(file).read_bytes()).hexdigest()==digest,'changed execution input')
report=dict(status='PASS_REAL_IDMA_PARTIAL_FAILURE_AND_RESET_RECOVERY',fault_cases=12,reset_recoveries=12,
            full_recovery_checked_fp32=1188,failure_prefix_checked_fp32=396,
            failed_tensor_published=False,dependent_command_started=False,
            input_manifest_sha256=hashlib.sha256((out/'inputs.sha256.json').read_bytes()).hexdigest(),
            run_log_sha256=hashlib.sha256((out/'run.log').read_bytes()).hexdigest(),
            simulator_sha256=hashlib.sha256((out/'host_command_partial_failure').read_bytes()).hexdigest(),
            original_idma=True,arithmetic_stub=False,full_model=False)
(out/'RESULT.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
PY
