#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd);OUT=$ROOT/reports/execution/l5_q1024_prefill_contract_result.json;PY=$ROOT/work/toolchain/cnn_py312/bin/python
taskset -c 8-23 "$PY" "$ROOT/scripts/verify_qwen_q1024_prefill_contract.py" --contract "$ROOT/config/qwen_q1024_prefill_contract.json" --result "$OUT"
