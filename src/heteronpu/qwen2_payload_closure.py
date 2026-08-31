"""Deterministic Qwen2 28-layer payload-closure sampling plan."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Iterable


@dataclass(frozen=True)
class Checkpoint:
    layer: int
    phase: str
    tensor: str
    sample_count: int
    continuity_group: int
    required: bool = True


PHASES = (
    ("input_norm", "norm_out", 64),
    ("qkv_projection", "qkv_out", 64),
    ("attention", "attention_out", 64),
    ("post_attention_norm", "post_norm_out", 64),
    ("mlp_gate_up", "gate_up_out", 64),
    ("mlp_down", "block_out", 64),
)


def build_plan(layers: int = 28) -> tuple[Checkpoint, ...]:
    if layers <= 0:
        raise ValueError("layers")
    checkpoints: list[Checkpoint] = []
    for layer in range(layers):
        group = layer // 4
        for phase, tensor, samples in PHASES:
            checkpoints.append(Checkpoint(layer, phase, tensor, samples, group))
    return tuple(checkpoints)


def plan_report(checkpoints: Iterable[Checkpoint] | None = None) -> dict[str, object]:
    items = tuple(checkpoints or build_plan())
    layer_set = sorted({item.layer for item in items})
    groups = sorted({item.continuity_group for item in items})
    per_phase: dict[str, int] = {}
    for item in items:
        per_phase[item.phase] = per_phase.get(item.phase, 0) + item.sample_count
    expected_layers = list(range(28))
    errors: list[str] = []
    if layer_set != expected_layers:
        errors.append("layer_coverage")
    if len(items) != 28 * len(PHASES):
        errors.append("checkpoint_count")
    if groups != list(range(7)):
        errors.append("continuity_groups")

    records = [asdict(item) for item in items]
    result: dict[str, object] = {
        "schema_version": 1,
        "status": "PASS_FULL_PAYLOAD_CLOSURE_PLAN" if not errors else "FAIL_PLAN",
        "errors": errors,
        "model": "Qwen/Qwen2-1.5B-Instruct",
        "sequence": 1024,
        "layers": 28,
        "checkpoint_count": len(items),
        "sample_values": sum(item.sample_count for item in items),
        "per_phase_sample_values": per_phase,
        "continuity_groups": groups,
        "checkpoints": records,
        "execution_phases": [
            {
                "id": "P1_all_layer_checkpoints",
                "acceptance": [
                    "all 28 layers and all six phases present",
                    "frozen tensor shape/dtype/stride metadata",
                    "BF16 bit-exact where the contract is BF16",
                    "FP32 error within the frozen per-operator tolerance",
                ],
            },
            {
                "id": "P2_seven_contiguous_four_layer_groups",
                "acceptance": [
                    "no reference hidden-state injection inside a four-layer group",
                    "random backpressure enabled",
                    "state and transaction counters close",
                    "group output matches official checkpoint",
                ],
            },
            {
                "id": "P3_full_28_layer_payload_or_real_backend",
                "acceptance": [
                    "no intermediate reference-state injection",
                    "all layer boundaries replayed continuously",
                    "final RMSNorm and sampled/full LM head close",
                    "payload trace hash is immutable and revision pinned",
                ],
            },
        ],
        "local_environment_requirements": [
            "exact-revision official weights",
            "PyTorch/Transformers reference capture",
            "Verilator/VCS or real llama.cpp backend",
            "large vector storage and bounded replay runtime",
        ],
        "non_claim": "This plan is source/test collateral, not full-payload numerical evidence.",
    }
    result["sha256"] = hashlib.sha256(
        json.dumps(result, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return result
