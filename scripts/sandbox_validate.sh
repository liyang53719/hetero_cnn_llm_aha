#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
./scripts/check_main_only_workflow.sh
export PYTHONPATH=src
python3 -m compileall -q src scripts
python3 scripts/run_qwen38_text_e0.py >/dev/null
python3 scripts/run_gdn_chunk_e0.py >/dev/null
python3 scripts/run_qwen38_architecture_e0.py >/dev/null
python3 scripts/generate_model_support_report.py >/dev/null
python3 scripts/run_planning_v6.py >/dev/null
python3 scripts/validate_l5_revision8a_contract.py --operations 100000 --output work/results/l5_revision8a/sandbox_smoke.json >/dev/null
mkdir -p work/results/sandbox_v610 work/results/sandbox_v70 work/results/sandbox_v72 work/results/sandbox_v75 work/results/sandbox_v78
python3 scripts/generate_ggml_quant_vectors.py --cases 128 --output work/results/sandbox_v610/ggml_quant_vectors.txt >/dev/null
python3 scripts/run_sandbox_v67.py --quant-cases 200 --transactions 100 --vectors work/results/sandbox_v610/ggml_quant_vectors.txt --output work/results/sandbox_v610/v67_result.json >/dev/null
python3 scripts/run_sandbox_v68.py --output work/results/sandbox_v610/v68_result.json >/dev/null
python3 scripts/run_l5_blocked_attention_controller_e0.py --output work/results/sandbox_v610/attention_controller.json >/dev/null
python3 scripts/run_l5_silu_lut_contract_e0.py --cases 20000 --output work/results/sandbox_v610/silu_contract.json >/dev/null
python3 scripts/generate_silu_lut_vectors.py --cases 256 --output work/results/sandbox_v610/silu_vectors.txt >/dev/null
python3 scripts/validate_v69_source_contracts.py --output work/results/sandbox_v610/source_contract.json >/dev/null
python3 scripts/run_sandbox_v70.py --quant-cases 2048 --transactions 5000 --output work/results/sandbox_v70/result.json >/dev/null
python3 scripts/validate_sandbox_v70.py --generated work/results/sandbox_v70/result.json --tracked-dir reports/execution >/dev/null
python3 scripts/run_sandbox_v72.py --quant-cases 2000 --transactions 10000 --output work/results/sandbox_v72/result.json >/dev/null
python3 scripts/run_qwen_family_contracts.py --output work/results/sandbox_v72/qwen_family_contracts.json >/dev/null
python3 scripts/run_l5_attention_sfu_balance_e0.py --output work/results/sandbox_v75/balanced_sfu.json >/dev/null
python3 scripts/run_qwen_model_resource_envelope.py --output work/results/sandbox_v75/qwen_resources.json >/dev/null
python3 scripts/run_sandbox_v75.py --output work/results/sandbox_v75/result.json >/dev/null
python3 scripts/run_sandbox_v78.py --output work/results/sandbox_v78/result.json --payload-plan work/results/sandbox_v78/payload_plan.json >/dev/null
python3 scripts/validate_sandbox_v78.py --result work/results/sandbox_v78/result.json >/dev/null
python3 scripts/audit_p3_backend_evidence.py >/dev/null
pytest -q
python3 scripts/generate_block128_vectors.py >/dev/null
python3 scripts/generate_fp32_pipeline_vectors.py >/dev/null
python3 scripts/validate_progress_v6.py
python3 scripts/rtl_source_check.py
for script in scripts/*.sh;do bash -n "$script";done
/usr/bin/g++ -std=c++20 -O2 -Wall -Wextra -Werror -ffp-contract=off cpp/mlo_merge_reference.cpp -o /tmp/heteronpu_mlo_ref
/tmp/heteronpu_mlo_ref tests/vectors/fp32_mlo_merge_vectors.txt | tee reports/execution/mlo_cpp_reference.json
