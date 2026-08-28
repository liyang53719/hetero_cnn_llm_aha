"""Static and cycle-semantic gates for the L5.2 Revision-7 synthesis decision.

Revision 7 is deliberately a synthesis-boundary change, not an RTL change.
The validator pins all source blobs, proves the explicit four-context/four-stage
contract is still present, rejects timing exceptions/retiming in the Tcl flow,
and runs an independent recurrence model for same-cycle completion bypass.
It does not replace Verilator E1, Formality/gate equivalence, or CLN22UL E4.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import random
import re
from typing import Any


def git_blob_sha1(payload: bytes) -> str:
    return hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest()


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _require(text: str, needle: str, errors: list[str], label: str) -> None:
    if needle not in text:
        errors.append(f"missing:{label}")


def _forbid(text: str, pattern: str, errors: list[str], label: str) -> None:
    if re.search(pattern, text, re.IGNORECASE | re.MULTILINE):
        errors.append(f"forbidden:{label}")


def validate_sources(root: str | Path, policy_path: str | Path) -> dict[str, Any]:
    root = Path(root)
    policy = json.loads(Path(policy_path).read_text(encoding="utf-8"))
    errors: list[str] = []
    observed: dict[str, dict[str, str | int]] = {}
    if policy.get("revision") != 7 or policy.get("decision") != "APPROVE_WITH_GATES":
        errors.append("policy_identity")
    for relative, expected_blob in policy["pinned_sources"].items():
        path = root / relative
        if not path.is_file():
            errors.append(f"missing_file:{relative}")
            continue
        payload = path.read_bytes()
        blob = git_blob_sha1(payload)
        observed[relative] = {"bytes": len(payload), "git_blob_sha1": blob, "sha256": sha256(payload)}
        if blob != expected_blob:
            errors.append(f"blob_mismatch:{relative}:{blob}")
    context = (root / "rtl/matrix/bf16_context_fma_pipeline_lane4.sv").read_text()
    base = (root / "rtl/matrix/bf16_fma_pipeline_lane.sv").read_text()
    emitter = (root / "integration/gemmini/EmitHeteroBF16Fma.scala").read_text()
    all_emitter = (root / "integration/gemmini/EmitHeteroAllPrimitives.scala").read_text()
    for needle, label in (("logic [31:0] accumulator_bank [0:3]", "four_accumulator_banks"), ("else if (issue_bypass_i)", "same_cycle_bypass"), ("else if (issue_use_bank_i)", "bank_select"), ("accumulator_bank[completion_context_i] <= fma_out", "completion_commit"), ("bf16_fma_pipeline_lane fma", "single_base_lane")):
        _require(context, needle, errors, label)
    order = [context.find("if (issue_clear_i)"), context.find("else if (issue_bypass_i)"), context.find("else if (issue_use_bank_i)")]
    if any(index < 0 for index in order) or order != sorted(order):
        errors.append("context_mux_priority")
    if context.count("bf16_fma_pipeline_lane fma") != 1:
        errors.append("base_lane_instance_count")
    stages = ("HeteroBF16FmaPre", "HeteroBF16FmaMul", "HeteroBF16FmaPost", "HeteroBF16FmaRound")
    for stage in stages:
        if base.count(stage) != 1:
            errors.append(f"base_stage_count:{stage}")
        if f"class {stage}" not in emitter:
            errors.append(f"emitter_stage_missing:{stage}")
        if f"new {stage}" not in all_emitter:
            errors.append(f"all_emitter_stage_missing:{stage}")
    for enable in ("pre_write_i", "mul_write_i", "post_write_i", "output_write_i"):
        _require(base, f"if ({enable})", errors, f"stage_enable:{enable}")
    _require(emitter, "round_near_even", errors, "RNE")
    _require(emitter, "tininess_afterRounding", errors, "tininess_after_rounding")
    _require(emitter, "MulAddRecFNToRaw_preMul", errors, "HardFloat_Pre")
    _require(emitter, "MulAddRecFNToRaw_postMul", errors, "HardFloat_Post")
    return {"schema_version": 1, "status": "PASS" if not errors else "FAIL", "revision": 7, "observed_sources": observed, "errors": errors, "contract": {"contexts": 4, "feedback_latency_cycles": 4, "same_cycle_bypass": True, "generated_rtl_hand_edit_authorized": False}}


def validate_tcl(tcl_path: str | Path) -> dict[str, Any]:
    text = Path(tcl_path).read_text(encoding="utf-8")
    errors: list[str] = []
    required = (("GENERATED_SV", "generated_sv_input"), ("BASE_LANE_RTL", "base_lane_input"), ("CONTEXT_RTL", "context_lane_input"), ("set_svf", "svf"), ("analyze -format sverilog", "source_analysis"), ("elaborate bf16_context_fma_pipeline_lane4", "top_elaboration"), ("create_clock -name core_clk -period $CLK_PERIOD", "clock"), ("set_clock_uncertainty 0.08", "uncertainty"), ("set_input_delay 0.10", "input_budget"), ("set_output_delay 0.10", "output_budget"), ("set_load 0.02", "output_load"), ("compile_ultra -no_autoungroup", "compile"), ("REVISION=7", "status_revision"), ("SOURCE_REMAP=1", "status_source_remap"), ("LEAF_DDCS_READ=0", "status_no_ddc"), ("RETIMING_AUTHORIZED=0", "status_no_retiming"))
    for needle, label in required:
        _require(text, needle, errors, label)
    for pattern, label in ((r"\bread_ddc\b", "read_ddc"), (r"set_multicycle_path", "multicycle"), (r"compile_ultra[^\n]*-retime", "retime"), (r"optimize_registers", "register_retime"), (r"set_false_path(?![^\n]*rst_ni)", "non_reset_false_path"), (r"CLOCK_PERIOD_NS[^\n]*[2-9]\.", "lower_frequency")):
        _forbid(text, pattern, errors, label)
    false_paths = [line.strip() for line in text.splitlines() if "set_false_path" in line]
    if false_paths != ["set_false_path -from [get_ports rst_ni]"]:
        errors.append(f"false_path_contract:{false_paths}")
    return {"schema_version": 1, "status": "PASS" if not errors else "FAIL", "errors": errors, "false_paths": false_paths}


@dataclass(frozen=True)
class PipelineItem:
    context: int
    value: int


def recurrence_stress(operations: int = 100_000, *, contexts: int = 4, latency: int = 4, seed: int = 7007, stall_probability: float = 0.20) -> dict[str, Any]:
    if contexts <= 0 or latency <= 0 or operations <= 0:
        raise ValueError("geometry")
    rng = random.Random(seed)
    banks = [0] * contexts
    expected = [0] * contexts
    pipeline: list[PipelineItem | None] = [None] * latency
    issued = completed = cycles = bypasses = 0
    next_context = 0
    while completed < operations:
        cycles += 1
        stalled = rng.random() < stall_probability
        completion = pipeline[-1] if not stalled else None
        if not stalled:
            for stage in range(latency - 1, 0, -1):
                pipeline[stage] = pipeline[stage - 1]
            pipeline[0] = None
        context = next_context
        context_still_in_flight = any(item is not None and item.context == context for item in pipeline)
        same_context = completion is not None and completion.context == context
        can_issue = (not stalled) and issued < operations and (same_context or not context_still_in_flight)
        if can_issue:
            next_context = (next_context + 1) % contexts
            base = completion.value if same_context else banks[context]
            if same_context:
                bypasses += 1
            delta = ((issued * 17 + context * 13) & 0xFFFF) + 1
            value = (base + delta) & 0xFFFFFFFF
            pipeline[0] = PipelineItem(context, value)
            expected[context] = (expected[context] + delta) & 0xFFFFFFFF
            issued += 1
        if completion is not None:
            banks[completion.context] = completion.value
            completed += 1
    if banks != expected:
        raise AssertionError((banks, expected))
    return {"schema_version": 1, "status": "PASS", "operations": operations, "contexts": contexts, "latency": latency, "cycles": cycles, "issued": issued, "completed": completed, "same_cycle_bypasses": bypasses, "issue_per_cycle": issued / cycles, "no_stall_ideal_issue_per_cycle": min(1.0, contexts / latency), "final_banks_sha256": hashlib.sha256(b"".join(value.to_bytes(4, "little") for value in banks)).hexdigest()}


def approval_report(root: str | Path, policy_path: str | Path, tcl_path: str | Path, *, operations: int = 100_000) -> dict[str, Any]:
    source = validate_sources(root, policy_path)
    tcl = validate_tcl(tcl_path)
    recurrence = recurrence_stress(operations=operations)
    errors: list[str] = []
    if source["status"] != "PASS": errors.extend(source["errors"])
    if tcl["status"] != "PASS": errors.extend(tcl["errors"])
    return {"schema_version": 1, "status": "PASS" if not errors else "FAIL", "decision": "APPROVE_WITH_GATES" if not errors else "REJECT_SOURCE_CONTRACT", "revision": 7, "source_contract": source, "tcl_contract": tcl, "recurrence_stress": recurrence, "remaining_local_gates": ["single_context_lane_CLN22UL_1GHz_E4", "Formality_or_post_synthesis_equivalence", "real_512_lane_E1_rerun", "structural_512_lane_four_context_H3_E4"], "errors": errors}
