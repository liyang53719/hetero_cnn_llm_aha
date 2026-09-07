#!/usr/bin/env bash
# Read stored outputs only. No simulator, source edits, or evidence rewrites.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
P="$ROOT/chisel/continuous_prefill/scripts"
OUT=${1:?absolute NEW audit output directory}
EVIDENCE=${2:-$ROOT/reports/execution/REAL16_TWO_LAYER_9f06249ca11f/numerical}
PEER=${3:-$ROOT/reports/execution/HOST_OWNER_21_6D39C76_CI/real16}
[[ "$OUT" = /* && ! -e "$OUT" && ! -L "$OUT" ]] || { echo OUTPUT_MUST_BE_NEW >&2; exit 2; }
command -v python3 >/dev/null || { echo BLOCKED_MISSING_PYTHON >&2; exit 77; }
python3 -c 'import numpy,yaml' || { echo BLOCKED_PYTHON_DEPENDENCIES >&2; exit 77; }
[[ -d "$EVIDENCE" && -d "$PEER" ]] || { echo BLOCKED_MISSING_PUBLISHED_EVIDENCE >&2; exit 77; }
mkdir -p "$(dirname "$OUT")"
mkdir "$OUT"
trap 'code=$?;echo "$code" > "$OUT/gate.exit";exit "$code"' EXIT
python3 "$P/verify_real_two_layer.py" --repo "$ROOT" --evidence "$EVIDENCE" \
  --output "$OUT/NUMERICAL_RECHECK.json" > "$OUT/numerical.log"
python3 "$P/audit_real2_boundary.py" --evidence "$EVIDENCE" --peer "$PEER" \
  --output "$OUT/BOUNDARY_RECHECK.json" > "$OUT/boundary.log"
python3 "$P/audit_real2_dense.py" --evidence "$EVIDENCE" \
  --output "$OUT/DENSE_RECHECK.json" > "$OUT/dense.log"
python3 - "$OUT" <<'PY'
from pathlib import Path
import hashlib,json,sys
out=Path(sys.argv[1])
a=json.loads((out/'NUMERICAL_RECHECK.json').read_text())
b=json.loads((out/'BOUNDARY_RECHECK.json').read_text())
c=json.loads((out/'DENSE_RECHECK.json').read_text())
if not (a['status']=='PASS_REAL16_TWO_LAYER_HOST_NUMERICAL' and a['checked_fp32']==1409024 and
        b['status']=='PASS_REAL2_FROZEN_PEER_AND_ACTUAL_BOUNDARY' and b['peer_compared_fp32']==704512 and
        b['boundary_norm_recomputed_fp32']==24576 and
        c['status']=='PASS_REAL2_ACTUAL_PREDECESSOR_GEMM_RECOMPUTE' and c['checked_fp32']==368640 and
        all(x['bit_differences']==0 for x in (a,b,c))):
    raise SystemExit('REAL2_RECHECK_INCOMPLETE')
result={'status':'PASS_REAL16_TWO_LAYER_DELIVERY_RECHECK','source_commit':a['source_commit'],
        'commands':42,'descriptor_records':430,'owner_jobs':38,'checked_fp32':1409024,
        'bit_differences':0,'rtl_rerun':False,'official_weights':False,'full_network_q1024':False,
        'reports_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.glob('*.json'))}}
with (out/'RESULT.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
print(json.dumps(result,indent=2))
PY
