"""Source-derived payload coverage for the 21-command Qwen2 layer canary."""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import re
from typing import Any, Iterable

from .command import Opcode
from .l9_transport_contract import EXPECTED_LAYER0

_HEX_OPCODE = re.compile(r"8'h([0-9a-fA-F]{2})")


@dataclass(frozen=True)
class PayloadCoverage:
    ordinal: int
    operation: str
    engine: str
    opcode: str
    opcode_value: int
    state: str
    next_requirement: str


def _supported_opcodes(source: str) -> set[int]:
    return {int(value, 16) for value in _HEX_OPCODE.findall(source)}


def classify_layer0_payload_coverage(
    *,
    sfu_endpoint_source: str,
    matrix_endpoint_source: str,
    kv_endpoint_source: str,
    numerically_tested_ordinals: Iterable[int] = (1, 2),
) -> dict[str, Any]:
    tested = set(int(value) for value in numerically_tested_ordinals)
    if any(value < 1 or value > 21 for value in tested):
        raise ValueError("tested ordinals must be in [1, 21]")

    sfu_supported = _supported_opcodes(sfu_endpoint_source)
    matrix_supported = _supported_opcodes(matrix_endpoint_source)
    kv_supported = _supported_opcodes(kv_endpoint_source)
    kv_command_adapter = "cmd_valid_i" in kv_endpoint_source and int(Opcode.KV_APPEND) in kv_supported

    rows: list[PayloadCoverage] = []
    for ordinal, spec in enumerate(EXPECTED_LAYER0, start=1):
        opcode = Opcode[spec.opcode.upper()]
        if ordinal in tested:
            state = "real_payload_numerically_tested"
            requirement = "retain as regression anchor"
        elif spec.engine == "matrix" and int(opcode) in matrix_supported:
            state = "endpoint_opcode_supported_payload_feeder_open"
            requirement = "bind descriptors, fetch Shared-L2 tiles, drive steps, store result and checkpoint"
        elif spec.engine == "sfu" and int(opcode) in sfu_supported:
            state = "endpoint_opcode_supported_not_numerically_tested"
            requirement = "reuse endpoint with descriptor-backed payload and add checkpoint"
        elif spec.engine == "kv" and kv_command_adapter:
            state = "kv_command128_adapter_present_payload_not_tested"
            requirement = "drive descriptor-backed KV payload and add storage-image checkpoint"
        elif spec.engine == "kv":
            state = "kv_stream_primitive_present_command128_adapter_open"
            requirement = "translate KV_APPEND command/descriptors into cfg/stream/memory handshake"
        else:
            state = "command_endpoint_opcode_unsupported"
            requirement = "implement opcode-specific numerical endpoint and descriptor-backed payload path"
        rows.append(
            PayloadCoverage(
                ordinal=ordinal,
                operation=spec.operation,
                engine=spec.engine,
                opcode=spec.opcode,
                opcode_value=int(opcode),
                state=state,
                next_requirement=requirement,
            )
        )

    state_counts = Counter(row.state for row in rows)
    tested_count = state_counts["real_payload_numerically_tested"]
    remaining = len(rows) - tested_count
    return {
        "schema_version": 1,
        "status": "PASS_LAYER0_PAYLOAD_COVERAGE_CLASSIFIED",
        "layer_commands": len(rows),
        "real_payload_numerically_tested": tested_count,
        "remaining_real_payload_commands": remaining,
        "endpoint_opcode_sets": {
            "matrix": sorted(matrix_supported),
            "sfu": sorted(sfu_supported),
            "kv": sorted(kv_supported),
            "kv_command128_adapter_detected": kv_command_adapter,
        },
        "state_counts": dict(state_counts),
        "commands": [asdict(row) for row in rows],
        "implementation_buckets": {
            "A_common_descriptor_and_Shared_L2_payload_shell": [row.ordinal for row in rows if row.ordinal not in tested],
            "B_reuse_existing_RMSNorm_endpoint": [16],
            "C_matrix_feeders_and_writeback": [5, 8, 11, 13, 14, 17, 18, 20],
            "D_SFU_vector_bias_residual": [3, 6, 9, 15, 21],
            "E_RoPE": [4, 7],
            "F_Softmax": [12],
            "G_SiLU_multiply": [19],
            "H_KV_APPEND_adapter": [10],
        },
        "non_claims": [
            "opcode acceptance is not descriptor-backed tensor execution",
            "the outer-product step interface is not a complete GEMM/QK/PV command implementation",
            "the KV stream primitive is not a Command128 KV endpoint",
        ],
    }
