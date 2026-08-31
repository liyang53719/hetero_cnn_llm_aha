#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH=src
mkdir -p work/results/sandbox_v72
python3 -m compileall -q src scripts
python3 scripts/run_sandbox_v72.py --quant-cases 2000 --transactions 10000 --output work/results/sandbox_v72/result.json >/dev/null
python3 scripts/run_qwen_family_contracts.py --output work/results/sandbox_v72/qwen_family_contracts.json >/dev/null
pytest -q tests/test_v72.py tests/test_qwen_family_contracts.py
python3 - <<'PY'
from pathlib import Path
for path in (Path('rtl/quant/ggml_quant_frontend_top.sv'),Path('rtl/state/state_multislot_commit_arbiter.sv'),Path('rtl/state/state_refcount_cow_table.sv')):
 text=path.read_text();assert text.count('module ')==text.count('endmodule'),path
PY
for script in scripts/*.sh;do bash -n "$script";done
