#!/usr/bin/env bash
# One persistent sequential service. Subprocess completion, no status polling.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.."&&pwd)
cd "$ROOT"
/usr/bin/python3 scripts/run_q1024_captured_attention.py
/usr/bin/python3 scripts/assemble_q1024_attention_payload.py
/usr/bin/python3 scripts/run_captured_attention_tail_reference.py
MIN_AVAILABLE_KIB=10485760 bash scripts/run_memory_capped.sh timeout 600 \
 /home/yang/anaconda3/bin/python3 scripts/prepare_captured_oproj_fixtures.py
echo 'Q1024_ATTENTION_AND_OPROJ_PREPARATION_COMPLETE full_model_pass=false'
