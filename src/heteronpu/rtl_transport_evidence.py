"""Classify existing Command128 RTL evidence without over-claiming payload execution.

The repository contains two useful but different tests:

* a 588-command command/event-fabric test whose engine endpoints return delayed
  completions without executing descriptor-backed tensor arithmetic; and
* a two-command numerical endpoint test that executes RMSNorm and Matrix RTL.

This module keeps those evidence classes separate from a complete 21-command
layer canary and from the 588-command end-to-end device path.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any

_SUBMISSION_RE = re.compile(
    r"QWEN2_REAL_COMMAND_SUBMISSION_PASS commands=(?P<commands>\d+) "
    r"completions=(?P<completions>\d+) matrix=(?P<matrix>\d+) "
    r"sfu=(?P<sfu>\d+) kv=(?P<kv>\d+)"
)
_PAYLOAD_RE = re.compile(
    r"QWEN2_REAL_PAYLOAD_ENDPOINT_PASS commands=(?P<commands>\d+) "
    r"completions=(?P<completions>\d+) rms_values=(?P<rms_values>\d+) "
    r"matrix_steps=(?P<matrix_steps>\d+) matrix_outputs=(?P<matrix_outputs>\d+) "
    r"bf16_bit_exact=(?P<bf16_bit_exact>\d+)"
)


@dataclass(frozen=True)
class ExistingRtlEvidence:
    command_fabric_present: bool
    standalone_frontend_commands: int
    standalone_frontend_completions: int
    standalone_matrix_commands: int
    standalone_sfu_commands: int
    standalone_kv_commands: int
    completion_endpoint_model: str
    command_port_random_backpressure: bool
    descriptor_l2_activity_tied_off: bool
    real_payload_modules_in_submission: bool
    real_payload_endpoint_commands: int
    real_payload_endpoint_completions: int
    real_payload_bf16_values: int
    real_payload_uses_host_generated_vectors: bool
    real_payload_descriptor_l2_activity_tied_off: bool
    real_payload_output_backpressure_proven: bool
    real_payload_kv_endpoint_present: bool
    full_layer_real_payload_commands: int
    full_matrix_sfu_kv_internal_backpressure_proven: bool


def _parse_required(pattern: re.Pattern[str], text: str, label: str) -> dict[str, int]:
    match = pattern.search(text)
    if match is None:
        raise ValueError(f"{label} PASS signature not found")
    return {name: int(value) for name, value in match.groupdict().items()}


def inspect_existing_rtl_evidence(
    *,
    submission_script: str,
    submission_tb: str,
    payload_script: str,
    payload_tb: str = "",
) -> ExistingRtlEvidence:
    submission = _parse_required(_SUBMISSION_RE, submission_script + "\n" + submission_tb, "submission")
    payload = _parse_required(_PAYLOAD_RE, payload_script, "payload endpoint")

    command_fabric_present = "hetero_l3_command_fabric" in submission_tb
    delayed_echo_markers = (
        "held[0:5]" in submission_tb
        and "delay[0:5]" in submission_tb
        and "cd[e*56+:56]={held[e][55:40]" in submission_tb
        and "completed<=completed+1" in submission_tb
    )
    completion_endpoint_model = "delayed_completion_echo_stub" if delayed_echo_markers else "unknown"
    command_port_random_backpressure = (
        "lfsr" in submission_tb
        and "er[e]=!busy[e]" in submission_tb
        and "random_backpressure=1" in submission_tb
    )
    descriptor_l2_activity_tied_off = all(
        marker in submission_tb
        for marker in ("assign rv=0", "assign wv=0", "assign prspv=0")
    )
    real_payload_modules_in_submission = any(
        marker in submission_script or marker in submission_tb
        for marker in (
            "qwen2_sfu_command_endpoint",
            "qwen2_matrix_command_endpoint",
            "kv_tensor_stream_endpoint",
        )
    )
    payload_has_real_modules = all(
        marker in payload_script
        for marker in ("qwen2_sfu_command_endpoint.sv", "qwen2_matrix_command_endpoint.sv")
    )
    if not payload_has_real_modules:
        raise ValueError("payload endpoint script does not instantiate both real numerical endpoints")
    real_payload_uses_host_generated_vectors = all(
        marker in payload_script or marker in payload_tb
        for marker in ("rms_expected.memh", "matrix_expected.memh")
    )
    real_payload_descriptor_l2_activity_tied_off = all(
        marker in payload_tb for marker in ("assign rv=0", "assign wv=0", "assign prspv=0")
    )
    real_payload_output_backpressure_proven = (
        "assign sor=lfsr" in payload_tb
        and "assign mor=lfsr" in payload_tb
        and "random_backpressure=1" in payload_tb
    )
    real_payload_kv_endpoint_present = "kv_tensor_stream_endpoint" in payload_script or "kv_tensor_stream_endpoint" in payload_tb

    real_payload_commands = payload["commands"]
    return ExistingRtlEvidence(
        command_fabric_present=command_fabric_present,
        standalone_frontend_commands=submission["commands"],
        standalone_frontend_completions=submission["completions"],
        standalone_matrix_commands=submission["matrix"],
        standalone_sfu_commands=submission["sfu"],
        standalone_kv_commands=submission["kv"],
        completion_endpoint_model=completion_endpoint_model,
        command_port_random_backpressure=command_port_random_backpressure,
        descriptor_l2_activity_tied_off=descriptor_l2_activity_tied_off,
        real_payload_modules_in_submission=real_payload_modules_in_submission,
        real_payload_endpoint_commands=real_payload_commands,
        real_payload_endpoint_completions=payload["completions"],
        real_payload_bf16_values=payload["bf16_bit_exact"],
        real_payload_uses_host_generated_vectors=real_payload_uses_host_generated_vectors,
        real_payload_descriptor_l2_activity_tied_off=real_payload_descriptor_l2_activity_tied_off,
        real_payload_output_backpressure_proven=real_payload_output_backpressure_proven,
        real_payload_kv_endpoint_present=real_payload_kv_endpoint_present,
        full_layer_real_payload_commands=real_payload_commands if real_payload_commands == 21 else 0,
        full_matrix_sfu_kv_internal_backpressure_proven=False,
    )


def classify_existing_rtl_evidence(
    *,
    submission_script: str,
    submission_tb: str,
    payload_script: str,
    payload_tb: str = "",
) -> dict[str, Any]:
    evidence = inspect_existing_rtl_evidence(
        submission_script=submission_script,
        submission_tb=submission_tb,
        payload_script=payload_script,
        payload_tb=payload_tb,
    )
    checks = {
        "588_command_frontend_dispatch": (
            evidence.command_fabric_present
            and evidence.standalone_frontend_commands == 588
            and evidence.standalone_frontend_completions == 588
            and evidence.standalone_matrix_commands == 252
            and evidence.standalone_sfu_commands == 308
            and evidence.standalone_kv_commands == 28
        ),
        "submission_is_stub_endpoint_smoke": (
            evidence.completion_endpoint_model == "delayed_completion_echo_stub"
            and evidence.descriptor_l2_activity_tied_off
            and not evidence.real_payload_modules_in_submission
        ),
        "two_command_real_payload_endpoint": (
            evidence.real_payload_endpoint_commands == 2
            and evidence.real_payload_endpoint_completions == 2
            and evidence.real_payload_bf16_values == 1568
        ),
        "complete_21_command_layer_payload": evidence.full_layer_real_payload_commands == 21,
        "two_command_endpoint_output_backpressure": evidence.real_payload_output_backpressure_proven,
        "full_matrix_sfu_kv_internal_backpressure": evidence.full_matrix_sfu_kv_internal_backpressure_proven,
    }
    required_for_classification = (
        checks["588_command_frontend_dispatch"]
        and checks["submission_is_stub_endpoint_smoke"]
        and checks["two_command_real_payload_endpoint"]
    )
    return {
        "schema_version": 1,
        "status": (
            "PASS_EXISTING_RTL_EVIDENCE_CLASSIFIED"
            if required_for_classification
            else "FAIL_EXISTING_RTL_EVIDENCE_CLASSIFICATION"
        ),
        "evidence": asdict(evidence),
        "checks": checks,
        "accepted_as": [
            "standalone_588_command_event_frontend_dispatch_with_stub_engine_completions",
            "standalone_two_command_RMSNorm_then_Matrix_real_RTL_numeric_endpoint",
        ],
        "not_accepted_as": [
            "llama_backend_to_RTL_transport",
            "descriptor_backed_21_command_complete_layer_payload",
            "full_21_command_Matrix_SFU_KV_ready_valid_backpressure",
            "588_command_real_payload_execution",
            "non_host_device_buffer_execution",
        ],
        "next_gate": {
            "name": "L9.4_21_command_layer0_real_payload_canary",
            "commands": 21,
            "remaining_real_payload_commands_after_existing_endpoint": 19,
            "required_engine_counts": {"matrix": 9, "sfu": 11, "kv": 1},
        },
    }
