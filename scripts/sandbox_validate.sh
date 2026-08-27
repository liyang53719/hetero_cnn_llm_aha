#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH=src
python3 -m compileall -q src scripts
python3 scripts/run_qwen38_text_e0.py >/dev/null
python3 scripts/run_gdn_chunk_e0.py >/dev/null
python3 scripts/run_qwen38_architecture_e0.py >/dev/null
python3 scripts/generate_model_support_report.py >/dev/null
python3 scripts/run_planning_v6.py >/dev/null
pytest -q
python3 scripts/generate_block128_vectors.py >/dev/null
python3 scripts/generate_fp32_pipeline_vectors.py >/dev/null
python3 scripts/validate_progress_v6.py
python3 scripts/rtl_source_check.py
for script in scripts/*.sh; do bash -n "$script"; done
/usr/bin/g++ -std=c++20 -O2 -Wall -Wextra -Werror -ffp-contract=off cpp/mlo_merge_reference.cpp -o /tmp/heteronpu_mlo_ref
/tmp/heteronpu_mlo_ref tests/vectors/fp32_mlo_merge_vectors.txt | tee reports/execution/mlo_cpp_reference.json
