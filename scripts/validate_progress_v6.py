#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


control = load("config/control_plane.json")
ledger = load("reports/execution/MASTER_LEDGER.json")
next_action = load("reports/execution/NEXT_ACTION.json")
control_audit = load("reports/execution/control_plane_v6_audit.json")
archspec = load("reports/execution/archspec_v6_collateral_result.json")
program = load("reports/execution/qwen38_full_shape_program_v6_result.json")
sequence = load("reports/execution/sequence_memory_cycle_v6_result.json")
final = load("reports/final_validation.json")

assert control["schema_version"] == 6
assert control["current_state"] == "L5_2_HIER_DC_REV4_FROZEN_READY_CONTROL512"
assert control["local_checkpoint"]["l5_1"] == "PASS_E1_E4"
assert control["local_checkpoint"]["l5_2_e1"] == "PASS"
assert control["local_checkpoint"]["l5_2_full_top_e4"] == "INTERRUPTED_NO_FINAL_TIMING"
assert control["remote_audit"]["new_local_agent_commit_detected"] is False
assert ledger["accepted_local_evidence"]["L5.1"]["status"] == "PASS_WAIT_REMOTE_AUDIT"
assert ledger["accepted_local_evidence"]["L5.1"]["block128_wns_ns"] >= 0
assert ledger["accepted_local_evidence"]["L5.2"]["status"] == "E1_PASS_HIER_DC_REV4_READY_CONTROL512"
assert ledger["accepted_local_evidence"]["L5.2"]["full_top_e4"] == "INTERRUPTED_NO_FINAL_TIMING"
assert next_action["state"] == "READY_IMPLEMENT_CONTROL512_TIMING_BLOCK"
assert len(next_action["ordered_commands"]) == 3
assert (ROOT / "reports/L5_2_HIERARCHICAL_DC_EXECUTION_PLAN.md").is_file()
assert final["status"] == "PASS_SANDBOX_V6_LOCAL_L5_1_CLOSED_L5_2_E4_OPEN"

l51 = load("reports/execution/l5_block128_local_e1_e4_result.json")
l52 = load("reports/execution/l5_matrix_context_local_e1_e4_result.json")
assert l51["status"] == "PASS"
assert l51["e1"]["fp32_pipeline_vectors"] == 1024
assert l51["e1"]["block128_vectors"] == 132
assert l51["e4"]["block128_wns_ns"] >= 0
assert l51["e4"]["unmapped_cells"] == 0
assert l51["e4"]["unresolved_references"] == 0
assert l52["status"] == "E1_PASS_E4_FULL_TOP_INTERRUPTED_RUNTIME"
assert l52["e1"]["lanes"] == 512
assert l52["e1"]["dependent_steps"] == 1_000_000
assert l52["e1"]["issue_utilization_ppm"] == 1_000_000
assert l52["e4_stage_probe"]["status"] == "PASS_DIAGNOSTIC_NOT_FULL_TOP"
assert l52["e4_stage_probe"]["wns_ns"] >= 0
assert l52["e4_full_top"]["status"] == "INTERRUPTED_NO_FINAL_TIMING"
assert l52["e4_full_top"]["final_wns_ns"] is None
assert l52["closure"]["l5_2_pass"] is False
assert control_audit["status"] == "PASS"
assert archspec["status"] == "PASS" and archspec["total_sram_kib"] == 4096
assert program["status"] == "PASS"
assert program["prefill"]["operations"] == 500
assert program["decode"]["operations"] == 500
assert sequence["status"] == "PASS" and sequence["stale_generation_rejected"] is True
assert (ROOT / "configs/arch_v2_qwen38_candidate.yaml").is_file()
assert "candidate_sandbox_not_canonical" in (ROOT / "configs/arch_v2_qwen38_candidate.yaml").read_text()
assert not (ROOT / "scripts/validate_progress_v5.py").exists()

result = {
    "schema_version": 6,
    "status": "PASS_SANDBOX_V6_LOCAL_L5_1_CLOSED_L5_2_E4_OPEN",
    "remote_new_local_agent_commit": False,
    "local_L5_1": "PASS_E1_E4_WAIT_REMOTE_AUDIT",
    "local_L5_2_E1": "PASS_WAIT_REMOTE_AUDIT",
    "local_L5_2_full_E4": "INTERRUPTED_NO_FINAL_TIMING",
    "new_sandbox_gates": [
        "control_plane_audit",
        "Archspec_collateral",
        "Qwen38_full_shape_program",
        "Qwen38_mock_backend",
        "SequenceMemory_cycle_E0",
    ],
    "candidate_archspec": "not_canonical",
}
(ROOT / "reports" / "progress_v6_validation.json").write_text(
    json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
print(json.dumps(result, indent=2, sort_keys=True))
