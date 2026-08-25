#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
mkdir -p reports work/sandbox
HETERO_VERILATOR=""
if [[ -x "$ROOT/work/toolchain/conda/bin/verilator" ]]; then
  HETERO_VERILATOR="$ROOT/work/toolchain/conda/bin/verilator"
fi

python -m compileall -q src tests scripts
PYTHONPATH=src pytest -o addopts='' -q | tee reports/pytest.log
PYTHONPATH=src python -m heteronpu --config configs/arch_v0.yaml --output reports/functional_cycle_bf16kv.json \
  > work/sandbox/functional_cycle_bf16kv.stdout
PYTHONPATH=src python -m heteronpu --config configs/arch_v0.yaml --llm-kv-format int8 \
  --output reports/functional_cycle_int8kv.json > work/sandbox/functional_cycle_int8kv.stdout
PYTHONPATH=src python scripts/generate_reports.py | tee reports/generate_reports.log
PYTHONPATH=src python scripts/randomized_reference_sweep.py --output reports/randomized_reference_sweep.json \
  > work/sandbox/randomized_reference_sweep.stdout
python scripts/rtl_static_check.py rtl --output reports/rtl_static_check.json \
  > work/sandbox/rtl_static_check.stdout

HETERO_VERILATOR="$HETERO_VERILATOR" ./scripts/run_open_rtl.sh > work/sandbox/open_rtl.stdout
python scripts/l56_contract_validate.py --input work/results/open_rtl \
  --output reports/l56_contract_validation.json > work/sandbox/l56_contract_validation.stdout
PYTHONPATH=src python scripts/model_regression_l7_l11.py \
  --output reports/l7_l11_model_regression.json > work/sandbox/l7_l11_model_regression.stdout
PYTHONPATH=src python scripts/integrated_rtl_model_regression.py \
  --output reports/l11_integrated_rtl_model_regression.json > work/sandbox/l11_integrated_rtl_model_regression.stdout
python scripts/official_gemmini_micro_regression.py \
  --output reports/official_gemmini_micro_regression.json > work/sandbox/official_gemmini_micro_regression.stdout

 CXX=${CXX:-/usr/bin/g++}
"$CXX" -std=c++17 -O2 -Wall -Wextra -Werror cpp/reference_smoke.cpp \
  -o work/sandbox/reference_smoke
work/sandbox/reference_smoke | tee reports/cpp_reference_smoke.json
PATH="$ROOT/work/toolchain/conda/bin:$ROOT/work/toolchain/apt-yosys/usr/bin:$PATH" \
  ./scripts/toolchain_audit.sh > reports/sandbox_toolchain.txt

python - <<'PY'
from __future__ import annotations
import hashlib, json, re, subprocess
from pathlib import Path
import yaml
root=Path('.')
pytest_text=(root/'reports/pytest.log').read_text()
m=re.search(r'(\d+) passed',pytest_text)
if not m:
    raise SystemExit('pytest pass count not found')
passed=int(m.group(1))
arch=yaml.safe_load((root/'configs/arch_v0.yaml').read_text())
cmd=yaml.safe_load((root/'spec/command_isa.yaml').read_text())
result=json.loads((root/'reports/architecture_results.json').read_text())
rtl=json.loads((root/'reports/rtl_static_check.json').read_text())
cpp=json.loads((root/'reports/cpp_reference_smoke.json').read_text())
randomized=json.loads((root/'reports/randomized_reference_sweep.json').read_text())
open_rtl_text=(root/'work/sandbox/open_rtl.stdout').read_text()
l56=json.loads((root/'reports/l56_contract_validation.json').read_text())
model_reg=json.loads((root/'reports/l7_l11_model_regression.json').read_text())
integrated_reg=json.loads((root/'reports/l11_integrated_rtl_model_regression.json').read_text())
official_micro=json.loads((root/'reports/official_gemmini_micro_regression.json').read_text())
checks={
  'python_tests': passed >= 21,
  'cnn_exact': result['sandbox_evidence']['cnn_max_abs_error'] == 0,
  'llm_bf16_paged_exact': result['sandbox_evidence']['llm_bf16_paged_max_abs_error'] == 0,
  'llm_int8_kv_threshold': (
      result['sandbox_evidence']['llm_int8_kv_max_abs_error'] < 0.05 and
      result['sandbox_evidence']['llm_int8_kv_mean_abs_error'] < 0.01),
  'sram_budget': result['sram_budget']['consistent'],
  'command_bits': cmd['word_bits'] == 128,
  'clock_1GHz': arch['clock_hz'] == 1_000_000_000,
  'rtl_structural': rtl['status'] == 'PASS',
  'cpp_reference': cpp['cpp_reference_smoke'] == 'PASS',
  'randomized_reference_sweep': randomized['status'] == 'PASS',
  'rtl_open_gate': 'OPEN_RTL_GATE_PASS' in open_rtl_text,
  'l56_contract': l56['status'] == 'PASS',
  'model_regression_l7_l11': model_reg['status'] == 'PASS',
  'integrated_rtl_model_regression': integrated_reg['status'] == 'PASS',
  'official_gemmini_micro_regression': official_micro['status'] == 'PASS',
  'gemmini_rocc_adapter': 'GEMMINI_ROCC_ADAPTER_PASS' in open_rtl_text,
  'gemmini_rocc_integration': 'GEMMINI_ROCC_INTEGRATION_PASS' in open_rtl_text,
}
files=[]
excluded = {Path('reports/final_validation.json'), Path('MANIFEST.sha256')}
for path in sorted(root.rglob('*')):
    if (not path.is_file() or '.git' in path.parts or path.parts[0] == 'work'
            or path in excluded or '__pycache__' in path.parts or '.pytest_cache' in path.parts):
        continue
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    files.append({'path':str(path),'bytes':path.stat().st_size,'sha256':digest})
report={
  'overall_status':'PASS' if all(checks.values()) else 'FAIL',
  'checks':checks,
  'python_tests_passed':passed,
  'sandbox_executed':[
    'python compileall','pytest','CNN functional model','BF16 and INT8-KV LLM functional model',
    'analytical cycle model','randomized GEMM/Conv/Softmax/KV reference sweep',
    'C++17 independent smoke','RTL structural checker','RTL compile/lint and contract testbenches','L5/L6 contract integration evidence','L7-L11 model-level regression','L11 integrated clean-room RTL/model regression','official generated Gemmini MacUnit micro regression'],
  'not_executed_due_environment':[
    'upstream git clone/build','official Gemmini full-size/default/ResNet numerical regression',
    'AHA Docker/Garnet/map/PnR/test','Slang/Surelog lint',
    'Yosys synthesis','Synopsys DC 22nm synthesis/STA'],
  'files':files,
}
(root/'reports/final_validation.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
if report['overall_status'] != 'PASS':
    raise SystemExit(1)
print(json.dumps({'overall_status':'PASS','python_tests_passed':passed,'file_count':len(files)}))
PY

echo FINAL_SANDBOX_VALIDATION_PASS
