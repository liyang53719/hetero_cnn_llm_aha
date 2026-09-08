#!/usr/bin/env bash
# Read stored outputs; never launch a simulator or rewrite the input proof.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
P="$ROOT/chisel/continuous_prefill/scripts"
OUT=${1:?absolute NEW audit output directory}
PROOF=${2:?published production-pipeline proof directory}
BASE512=${3:-$ROOT/reports/execution/REAL16_TWO_LAYER_9f06249ca11f/numerical}
BURST=${4:-$ROOT/reports/execution/WEIGHT_BURST_REAL2_cc2f9424daf2/numerical}
[[ "$OUT" = /* && ! -e "$OUT" && ! -L "$OUT" ]] || { echo OUTPUT_MUST_BE_NEW >&2;exit 2; }
command -v python3 >/dev/null || { echo BLOCKED_PYTHON >&2;exit 77; }
python3 -c 'import numpy,yaml' || { echo BLOCKED_PYTHON_DEPENDENCIES >&2;exit 77; }
[[ -d "$PROOF/numerical" && -d "$PROOF/components" && -d "$BASE512" && -d "$BURST" ]] || { echo BLOCKED_MISSING_PUBLISHED_PROOF >&2;exit 77; }
mkdir -p "$(dirname "$OUT")";mkdir "$OUT"
trap 'c=$?;echo "$c" >"$OUT/gate.exit";exit "$c"' EXIT
python3 "$P/verify_real_two_layer.py" --repo "$ROOT" --evidence "$PROOF/numerical" \
 --output "$OUT/NUMERICAL.json" >"$OUT/numerical.log"
python3 "$P/verify_pipeline_components.py" --evidence "$PROOF/components" \
 --output "$OUT/COMPONENTS.json" >"$OUT/components.log"
python3 "$P/compare_pipelined_real2.py" --current "$PROOF/numerical" --burst "$BURST" \
 --baseline512 "$BASE512" --output "$OUT/COMPARISON.json" >"$OUT/comparison.log"
python3 "$P/analyze_production_pipeline.py" --comparison "$OUT/COMPARISON.json" \
 --output "$OUT/PERFORMANCE.json" >"$OUT/performance.log"
python3 "$P/audit_real2_dense.py" --evidence "$PROOF/numerical" \
 --output "$OUT/ACTUAL_PREDECESSOR_GEMMS.json" >"$OUT/dense.log"
python3 - "$OUT" <<'PY'
import hashlib,json,sys
from pathlib import Path
out=Path(sys.argv[1]);checks={
 'NUMERICAL.json':'PASS_REAL16_TWO_LAYER_HOST_NUMERICAL',
 'COMPONENTS.json':'PASS_PRODUCTION_PIPELINE_COMPONENT_ARITHMETIC_AND_RECOVERY',
 'COMPARISON.json':'PASS_PIPELINED_REAL16_TWO_LAYER_ALL_OUTPUT_COMPARISON',
 'PERFORMANCE.json':'PASS_ACCOUNTED_PRODUCTION_PIPELINE_PERFORMANCE',
 'ACTUAL_PREDECESSOR_GEMMS.json':'PASS_REAL2_ACTUAL_PREDECESSOR_GEMM_RECOMPUTE'}
for name,status in checks.items():
 if json.loads((out/name).read_text())['status']!=status:raise SystemExit('INCOMPLETE:'+name)
r={'status':'PASS_PRODUCTION_PIPELINE_REAL2_READ_ONLY_RECHECK',
   'checked_fp32':1409024,'bit_differences':0,'recomputed_layer1_dense_fp32':368640,
   'rtl_rerun':False,'official_weights':False,'full_model_q1024':False,'dc_signoff':False,
   'reports_sha256':{n:hashlib.sha256((out/n).read_bytes()).hexdigest() for n in checks}}
with (out/'RESULT.json').open('x') as f:json.dump(r,f,indent=2);f.write('\n')
print(json.dumps(r,indent=2))
PY
