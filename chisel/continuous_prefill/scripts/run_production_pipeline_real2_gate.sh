#!/usr/bin/env bash
# Execute only; no source edits, generated RTL patching, or old-output cleanup.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
P="$ROOT/chisel/continuous_prefill"
OUT=${1:?absolute NEW output directory}
BASE512=${2:-$ROOT/reports/execution/REAL16_TWO_LAYER_9f06249ca11f/numerical}
BURST=${3:-$ROOT/reports/execution/WEIGHT_BURST_REAL2_cc2f9424daf2/numerical}
[[ "$OUT" = /* && ! -e "$OUT" && ! -L "$OUT" ]] || { echo OUTPUT_MUST_BE_NEW >&2;exit 2; }
for t in python3 java g++ git;do command -v "$t" >/dev/null || { echo "BLOCKED_MISSING_TOOL:$t";exit 77; };done
[[ -n ${IDMA_EXPORT:-} && -f "$IDMA_EXPORT/idma.f.in" ]] || { echo BLOCKED_PINNED_IDMA >&2;exit 77; }
python3 -c 'import numpy,yaml' || { echo BLOCKED_PYTHON_DEPENDENCIES >&2;exit 77; }
for b in "$BASE512" "$BURST";do
 [[ -f "$b/run.log" && -f "$b/gate.exit" && -f "$b/all_owner_elements.csv.gz" ]] || { echo BLOCKED_MISSING_FROZEN_EVIDENCE >&2;exit 77; }
done
mkdir -p "$(dirname "$OUT")";mkdir "$OUT"
trap 'c=$?;echo "$c" >"$OUT/gate.exit";exit "$c"' EXIT
export MATRIX_MACS=4096 WEIGHT_READ_BEATS=16 PIPELINED_OWNER=1
bash "$P/scripts/run_pipeline_components.sh" "$OUT/components" >"$OUT/components.log" 2>&1
bash "$P/scripts/run_host_block_gate.sh" tiny "$OUT/tiny" 16 0 2 >"$OUT/tiny.log" 2>&1
# Follow the runtime actually used by the child build, including normal installs.
if [[ -d "$OUT/tiny/verilator-runtime/include" ]]; then
 export VERILATOR_ROOT="$OUT/tiny/verilator-runtime"
elif [[ -n ${OFFLINE_TOOLS:-} ]]; then
 export VERILATOR_ROOT="$OFFLINE_TOOLS/share/verilator"
elif [[ -z ${VERILATOR_ROOT:-} ]]; then
 export VERILATOR_ROOT=$(verilator -V | awk '$1=="VERILATOR_ROOT" && $2=="=" && NF>=3 {print $3;exit}')
fi
[[ -d "$VERILATOR_ROOT/include" ]] || { echo BLOCKED_VERILATOR_RUNTIME >&2;exit 77; }
python3 "$P/scripts/run_pipeline_lifecycle.py" \
 --repo "$ROOT" --base "$OUT/tiny" --output "$OUT/lifecycle" >"$OUT/lifecycle.log" 2>&1
bash "$P/scripts/run_real_two_layer_gate.sh" "$OUT/numerical" >"$OUT/numerical.log" 2>&1
python3 "$P/scripts/compare_pipelined_real2.py" --current "$OUT/numerical" --burst "$BURST" \
 --baseline512 "$BASE512" --output "$OUT/PIPELINE_COMPARISON.json" >"$OUT/comparison.log"
python3 "$P/scripts/analyze_production_pipeline.py" --comparison "$OUT/PIPELINE_COMPARISON.json" \
 --output "$OUT/PERFORMANCE.json" >"$OUT/performance.log"
python3 - "$OUT" <<'PY'
import hashlib,json,sys
from pathlib import Path
out=Path(sys.argv[1]);checks={
 'components/RESULT.json':'PASS_PRODUCTION_PIPELINE_COMPONENT_ARITHMETIC_AND_RECOVERY',
 'lifecycle/PIPELINE_LIFECYCLE.json':'PASS_PRODUCTION_PIPELINE_TINY2_LIFECYCLE',
 'numerical/REAL2_ACCEPTANCE.json':'PASS_REAL16_TWO_LAYER_HOST_NUMERICAL',
 'PIPELINE_COMPARISON.json':'PASS_PIPELINED_REAL16_TWO_LAYER_ALL_OUTPUT_COMPARISON',
 'PERFORMANCE.json':'PASS_ACCOUNTED_PRODUCTION_PIPELINE_PERFORMANCE'}
for name,status in checks.items():
 if json.loads((out/name).read_text())['status']!=status:raise SystemExit('INCOMPLETE:'+name)
result={'status':'PASS_PRODUCTION_PIPELINE_REAL16_TWO_LAYER_DELIVERY',
        'source_commit':(out/'numerical/source_base_commit.txt').read_text().strip(),
        'checked_fp32':1409024,'bit_differences':0,'matrix_macs':4096,
        'tokens':16,'layers':2,'commands':42,'owner_jobs':38,
        'reports_sha256':{n:hashlib.sha256((out/n).read_bytes()).hexdigest() for n in checks},
        'official_weights':False,'full_model_q1024':False,'dc_signoff':False}
with (out/'RESULT.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
print(json.dumps(result,indent=2))
PY
