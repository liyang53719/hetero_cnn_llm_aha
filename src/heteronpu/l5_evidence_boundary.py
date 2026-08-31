"""Normalize L5.6 evidence without overstating reduced-payload replay."""
from __future__ import annotations

import hashlib
import json
from typing import Mapping


EXPECTED_CROSS_NON_CLAIM = "not a full q1024 payload RTL simulation"


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def audit_l5_boundary(
    full_trace: Mapping[str, object],
    cross_replay: Mapping[str, object],
    final_validation: Mapping[str, object],
) -> dict[str, object]:
    errors: list[str] = []

    if full_trace.get("status") != "PASS_CYCLE_E3":
        errors.append("full_trace_status")
    if full_trace.get("layers") != 28 or full_trace.get("sequence") != 1024:
        errors.append("full_trace_geometry")
    full_non_claims = tuple(str(v) for v in full_trace.get("non_claims", []))
    if not any("not a 28-layer payload numerical simulation" in item for item in full_non_claims):
        errors.append("missing_full_trace_non_claim")

    if cross_replay.get("status") != "PASS" or cross_replay.get("layers") != 4:
        errors.append("cross_replay_status_or_layers")
    cross_non_claims = tuple(str(v) for v in cross_replay.get("non_claims", []))
    if not any(EXPECTED_CROSS_NON_CLAIM in item for item in cross_non_claims):
        errors.append("missing_cross_replay_non_claim")
    rtl = cross_replay.get("rtl", {})
    if not isinstance(rtl, Mapping) or int(rtl.get("bf16_bit_exact", 0)) != 7_840:
        errors.append("cross_replay_exact_count")

    remaining = set(str(v) for v in final_validation.get("remaining_local_gates", []))
    full_payload_open = "L5.6_full_model" in remaining or "L5.6_full_payload_RTL" in remaining

    subgates = {
        "L5.6a_cycle_count_trace_E3": "PASS",
        "L5.6b_official_reference_and_sampled_lm_head": "PASS",
        "L5.6c_reduced_four_layer_cross_RTL": "PASS",
        "L5.6d_full_28_layer_payload_numerical_RTL": "OPEN",
    }
    if not full_payload_open:
        errors.append("final_validation_does_not_keep_full_payload_open")

    result: dict[str, object] = {
        "schema_version": 1,
        "status": "PASS_BOUNDARY_NORMALIZED" if not errors else "FAIL_BOUNDARY_INCONSISTENT",
        "errors": errors,
        "subgates": subgates,
        "current_parallel_stage": "L10_EARLY_PPA",
        "accepted_claim": (
            "Qwen2 q1024 cycle/count E3, official-reference checkpoints, sampled LM-head RTL, "
            "and a reduced four-layer cross-RTL replay pass."
        ),
        "forbidden_claim": "Full 28-layer q1024 payload numerical RTL is closed.",
        "rationale": (
            "The trace and cross-replay reports explicitly retain reduced-payload boundaries; "
            "early PPA may proceed in parallel without erasing the open full-payload gate."
        ),
    }
    result["sha256"] = _digest(result)
    return result
