#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(path: str) -> dict:
    return json.loads((ROOT / path).read_text())


control = load("config/control_plane.json")
ledger = load("reports/execution/MASTER_LEDGER.json")
next_action = load("reports/execution/NEXT_ACTION.json")
final = load("reports/final_validation.json")

assert control["schema_version"] == 5
assert control["current_state"] == "E1_PASS_E4_FAIL_TIMING_CANDIDATE_SOURCE_READY"
assert control["retained_local_evidence"]["block128_e1"] == "PASS"
assert control["retained_local_evidence"]["block128_e4"] == "FAIL_TIMING"
assert control["retained_local_evidence"]["block128_wns_ns"] < 0
assert ledger["retained_local"]["block128"]["e1"] == "PASS"
assert ledger["retained_local"]["block128"]["e4"] == "FAIL_TIMING"
assert next_action["acceptance"]["setup_wns_ns_min"] == 0.0
assert final["status"] == "PASS_WITH_LOCAL_E4_BLOCKER"

for path in (
    "reports/execution/qwen38_architecture_e0_result.json",
    "reports/execution/qwen38_qsa_streaming_result.json",
    "reports/execution/qwen38_state_transaction_result.json",
    "reports/execution/qwen38_full_shape_budget.json",
    "reports/execution/qwen38_memory_dse.json",
    "reports/execution/qwen38_quantization_screen.json",
    "reports/execution/qwen38_liveness_result.json",
    "reports/execution/matrix_context_source_model_result.json",
):
    assert load(path).get("status") == "PASS", path

for path in (
    "integration/gemmini/EmitHeteroFP32Pipelines.scala",
    "rtl/sfu/fp32_mlo_merge_coeff_rawpipe.sv",
    "rtl/sfu/fp32_mlo_merge_beat_rawpipe.sv",
    "rtl/sfu/fp32_mlo_summary_merge_stream_rawpipe.sv",
    "rtl/matrix/bf16_outer_product_context_array.sv",
    "tb/tb_fp32_pipelines.sv",
    "configs/arch_v2_qwen38_candidate.yaml",
):
    assert (ROOT / path).is_file(), path

candidate = (ROOT / "configs/arch_v2_qwen38_candidate.yaml").read_text()
assert "candidate_sandbox_not_canonical" in candidate
assert "total_sram_kib: 4096" in candidate
assert not (ROOT / "scripts/validate_progress_v4.py").exists()

result = {
    "schema_version": 5,
    "status": "PASS",
    "retained_local_block128_E1": "PASS",
    "retained_local_block128_E4": "FAIL_TIMING",
    "architecture_reports": 8,
    "candidate_archspec": "not_canonical",
}
(ROOT / "reports" / "progress_v5_validation.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print(json.dumps(result, indent=2, sort_keys=True))
