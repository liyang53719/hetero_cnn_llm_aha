"""Static contract audit for the Qwen2 layer-0 Command128 transport canary.

Passing this audit proves that the 21-command manifest is well-formed and
matches the frozen layer-0 schedule.  It does not prove that any command was
executed by RTL or that tensor payloads traversed DMA/Shared-L2.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .command import Command128, Engine, NULL_INDEX, Opcode


@dataclass(frozen=True)
class CommandSpec:
    operation: str
    engine: str
    opcode: str
    phase: str


EXPECTED_LAYER0: tuple[CommandSpec, ...] = (
    CommandSpec("l0.input_norm", "sfu", "sfu_rmsnorm", "input_norm"),
    CommandSpec("l0.q", "matrix", "matrix_gemm", "qkv_projection_rope"),
    CommandSpec("l0.q_bias", "sfu", "sfu_vector", "qkv_projection_rope"),
    CommandSpec("l0.q_rope", "sfu", "sfu_rope", "qkv_projection_rope"),
    CommandSpec("l0.k", "matrix", "matrix_gemm", "qkv_projection_rope"),
    CommandSpec("l0.k_bias", "sfu", "sfu_vector", "qkv_projection_rope"),
    CommandSpec("l0.k_rope", "sfu", "sfu_rope", "qkv_projection_rope"),
    CommandSpec("l0.v", "matrix", "matrix_gemm", "qkv_projection_rope"),
    CommandSpec("l0.v_bias", "sfu", "sfu_vector", "qkv_projection_rope"),
    CommandSpec("l0.kv_append", "kv", "kv_append", "kv_state"),
    CommandSpec("l0.qk", "matrix", "matrix_qk", "attention"),
    CommandSpec("l0.softmax", "sfu", "sfu_softmax", "attention"),
    CommandSpec("l0.pv", "matrix", "matrix_pv", "attention"),
    CommandSpec("l0.oproj", "matrix", "matrix_gemm", "attention"),
    CommandSpec("l0.attn_residual", "sfu", "sfu_vector", "attention"),
    CommandSpec("l0.post_norm", "sfu", "sfu_rmsnorm", "post_norm_mlp"),
    CommandSpec("l0.gate", "matrix", "matrix_gemm", "post_norm_mlp"),
    CommandSpec("l0.up", "matrix", "matrix_gemm", "post_norm_mlp"),
    CommandSpec("l0.silu_mul", "sfu", "sfu_activation", "post_norm_mlp"),
    CommandSpec("l0.down", "matrix", "matrix_gemm", "post_norm_mlp"),
    CommandSpec("l0.residual", "sfu", "sfu_vector", "residual_writeback"),
)

_ENGINE_BY_RECORD = {
    "control": Engine.CONTROL,
    "dma": Engine.DMA,
    "matrix": Engine.MATRIX,
    "sfu": Engine.SFU_CGRA,
    "sfu_cgra": Engine.SFU_CGRA,
    "kv": Engine.KV,
    "collective": Engine.COLLECTIVE,
}
_OPCODE_BY_RECORD = {opcode.name.lower(): opcode for opcode in Opcode}
_REQUIRED_PHASES = (
    "input_norm",
    "qkv_projection_rope",
    "kv_state",
    "attention",
    "post_norm_mlp",
    "residual_writeback",
)


def _record_roots(record: Mapping[str, Any]) -> dict[str, int]:
    roots = record.get("roots", {})
    return {
        "src0": int(roots.get("src0", NULL_INDEX)),
        "src1": int(roots.get("src1", NULL_INDEX)),
        "dst": int(roots.get("dst", NULL_INDEX)),
    }


def _binding_keys(record: Mapping[str, Any]) -> set[int]:
    result: set[int] = set()
    for key in record.get("root_bindings", {}):
        result.add(int(key))
    return result


def _select_layer(records: Sequence[Mapping[str, Any]], layer: int) -> list[tuple[int, Mapping[str, Any]]]:
    prefix = f"l{layer}."
    return [(index, record) for index, record in enumerate(records) if str(record.get("operation", "")).startswith(prefix)]


def audit_layer_manifest(
    records: Sequence[Mapping[str, Any]],
    *,
    layer: int = 0,
) -> dict[str, Any]:
    expected = tuple(
        CommandSpec(
            operation=spec.operation.replace("l0.", f"l{layer}.", 1),
            engine=spec.engine,
            opcode=spec.opcode,
            phase=spec.phase,
        )
        for spec in EXPECTED_LAYER0
    )
    selected = _select_layer(records, layer)
    errors: list[dict[str, Any]] = []
    decoded: list[Command128 | None] = []

    if len(selected) != len(expected):
        errors.append({"kind": "command_count", "expected": len(expected), "actual": len(selected)})

    for ordinal, spec in enumerate(expected):
        if ordinal >= len(selected):
            break
        manifest_index, record = selected[ordinal]
        context = {"ordinal": ordinal, "manifest_index": manifest_index, "operation": spec.operation}
        for field, expected_value in (
            ("operation", spec.operation),
            ("engine", spec.engine),
            ("opcode", spec.opcode),
        ):
            actual_value = str(record.get(field, ""))
            if actual_value != expected_value:
                errors.append({"kind": f"{field}_mismatch", "expected": expected_value,
                               "actual": actual_value, **context})

        command: Command128 | None = None
        try:
            command = Command128.unpack(int(str(record["word"]), 16))
        except (KeyError, TypeError, ValueError) as exc:
            errors.append({"kind": "command_word_decode", "detail": str(exc), **context})
        decoded.append(command)
        if command is None:
            continue

        record_engine = _ENGINE_BY_RECORD.get(str(record.get("engine", "")))
        record_opcode = _OPCODE_BY_RECORD.get(str(record.get("opcode", "")))
        if command.engine != record_engine:
            errors.append({"kind": "word_engine_mismatch", "word": command.engine.name,
                           "record": str(record.get("engine", "")), **context})
        if command.opcode != record_opcode:
            errors.append({"kind": "word_opcode_mismatch", "word": command.opcode.name,
                           "record": str(record.get("opcode", "")), **context})

        roots = _record_roots(record)
        for root_name, root_value in roots.items():
            if getattr(command, root_name) != root_value:
                errors.append({"kind": "word_root_mismatch", "root": root_name,
                               "word": getattr(command, root_name), "record": root_value, **context})
        binding_keys = _binding_keys(record)
        for root_name, root_value in roots.items():
            if root_value != NULL_INDEX and root_value not in binding_keys:
                errors.append({"kind": "missing_root_binding", "root": root_name,
                               "descriptor": root_value, **context})

    signals: list[int] = []
    for ordinal, command in enumerate(decoded):
        if command is None:
            continue
        expected_wait = 0 if ordinal == 0 else ordinal
        expected_signal = ordinal + 1
        if command.event_wait != expected_wait:
            errors.append({"kind": "event_wait_chain", "ordinal": ordinal,
                           "expected": expected_wait, "actual": command.event_wait})
        if command.event_signal != expected_signal:
            errors.append({"kind": "event_signal_chain", "ordinal": ordinal,
                           "expected": expected_signal, "actual": command.event_signal})
        signals.append(command.event_signal)
    duplicate_signals = sorted(signal for signal, count in Counter(signals).items() if signal and count > 1)
    if duplicate_signals:
        errors.append({"kind": "duplicate_signal_events", "events": duplicate_signals})

    actual_engine_counts = Counter(str(record.get("engine", "")) for _, record in selected)
    expected_engine_counts = Counter(spec.engine for spec in expected)
    if actual_engine_counts != expected_engine_counts:
        errors.append({"kind": "engine_counts", "expected": dict(expected_engine_counts),
                       "actual": dict(actual_engine_counts)})

    phase_by_operation = {spec.operation: spec.phase for spec in expected}
    phase_counts = Counter(
        phase_by_operation.get(str(record.get("operation", "")), "unknown")
        for _, record in selected
    )
    phase_coverage = {phase: phase_counts[phase] > 0 for phase in _REQUIRED_PHASES}
    selected_indices = [index for index, _ in selected]
    contiguous_indices = (
        len(selected_indices) == 21
        and selected_indices == list(range(selected_indices[0], selected_indices[0] + 21))
    )
    checks = {
        "command_count_21": len(selected) == 21,
        "engine_counts_9_11_1": actual_engine_counts == Counter({"matrix": 9, "sfu": 11, "kv": 1}),
        "contiguous_layer_records": contiguous_indices,
        "ordered_operations": all(
            ordinal < len(selected) and selected[ordinal][1].get("operation") == spec.operation
            for ordinal, spec in enumerate(expected)
        ),
        "command_words_decode": len(decoded) == 21 and all(command is not None for command in decoded),
        "event_chain_0_to_21": (
            len(decoded) == 21
            and all(
                command is not None
                and command.event_wait == ordinal
                and command.event_signal == ordinal + 1
                for ordinal, command in enumerate(decoded)
            )
        ),
        "six_phase_static_coverage": all(phase_coverage.values()),
        "no_contract_errors": not errors,
    }
    return {
        "schema_version": 1,
        "status": "PASS_L9_4_LAYER_MANIFEST_STATIC_CONTRACT" if all(checks.values()) else "FAIL_L9_4_LAYER_MANIFEST_STATIC_CONTRACT",
        "layer": layer,
        "manifest_records_total": len(records),
        "layer_record_indices": selected_indices,
        "layer_commands": len(selected),
        "expected_commands": [asdict(spec) for spec in expected],
        "engine_counts": dict(actual_engine_counts),
        "phase_counts": dict(phase_counts),
        "checks": checks,
        "errors": errors,
        "evidence_scope": "static_manifest_and_Command128_encoding_only",
        "not_accepted_as": [
            "RTL_command_acceptance",
            "descriptor_fetch",
            "DMA_or_Shared_L2_tensor_transport",
            "Matrix_SFU_KV_payload_execution",
            "numerical_checkpoint_parity",
        ],
    }


def load_manifest_jsonl(path: str | Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL at line {line_number}: {exc}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"manifest line {line_number} is not an object")
            records.append(record)
    if not records:
        raise ValueError("manifest is empty")
    return records


def audit_manifest_file(
    path: str | Path,
    *,
    layer: int = 0,
    expected_total_commands: int | None = None,
) -> dict[str, Any]:
    manifest_path = Path(path)
    records = load_manifest_jsonl(manifest_path)
    report = audit_layer_manifest(records, layer=layer)
    data = manifest_path.read_bytes()
    report["input"] = {
        "path": str(manifest_path),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    total_ok = expected_total_commands is None or len(records) == expected_total_commands
    report["expected_manifest_records_total"] = expected_total_commands
    report["checks"]["manifest_total"] = total_ok
    if not total_ok:
        report["errors"].append({
            "kind": "manifest_total",
            "expected": expected_total_commands,
            "actual": len(records),
        })
    report["status"] = (
        "PASS_L9_4_LAYER_MANIFEST_STATIC_CONTRACT"
        if all(report["checks"].values())
        else "FAIL_L9_4_LAYER_MANIFEST_STATIC_CONTRACT"
    )
    return report
