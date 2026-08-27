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

assert control["schema_version"] == 6
assert control["current_state"] == "E1_PASS_E4_FAIL_TIMING_WAIT_LOCAL_RAWPIPE_RESULTS"
assert control["retained_local_evidence"]["block128_e1"] == "PASS"
assert control["retained_local_evidence"]["block128_e4"] == "FAIL_TIMING"
assert control["retained_local_evidence"]["block128_wns_ns"] < 0
assert control["remote_audit"]["new_local_agent_commit_detected"] is False
assert ledger["accepted_local_evidence"]["block128"]["e1"] == "PASS"
assert ledger["accepted_local_evidence"]["block128"]["e4"] == "FAIL_TIMING"
assert next_action["acceptance"]["setup_wns_ns_min"] == 0.0
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
    "status": "PASS_WITH_RETAINED_LOCAL_E4_BLOCKER",
    "remote_new_local_agent_commit": False,
    "retained_block128_E1": "PASS",
    "retained_block128_E4": "FAIL_TIMING",
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
