"""Evidence classification for the Qwen2 llama.cpp HETERO P3 backend.

The audit deliberately separates four things that can otherwise be conflated:

* an original GGML graph being assigned to a backend;
* a monolithic software implementation running behind that backend;
* a Command128 manifest being validated;
* Command128/device RTL actually executing the payload.

It also separates unchanged GGUF storage bytes from canonical payload bytes
created by an explicit dtype conversion (for example F32 Norm -> BF16 RNE).
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import json
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class SourceSemantics:
    original_graph_guard: bool
    monolithic_submission: bool
    host_cpu_buffer_type: bool
    software_stage_backend: bool
    command_manifest_validation: bool
    command_rtl_interpreter: bool
    layer_completion_callback_backpressure: bool


@dataclass(frozen=True)
class BindingSemantics:
    total_bindings: int
    raw_storage_byte_parity: int
    canonical_converted_parity: int
    conversion: str


def inspect_sources(backend_cpp: str, device_api_cpp: str, generic_backend_cpp: str) -> SourceSemantics:
    original_graph_guard = "graph->n_nodes==958" in backend_cpp
    monolithic_submission = "hetero_qwen2_submit_588" in backend_cpp
    host_cpu_buffer_type = (
        "ggml_backend_cpu_buffer_type" in backend_cpp
        or "ggml_backend_cpu_buffer_from_ptr" in backend_cpp
    )
    software_stage_backend = (
        'include "qwen2_q1024_generic_layer_backend.cpp"' in device_api_cpp
        and "qwen2_generic_layer_embedded_main" in device_api_cpp
        and "#pragma omp parallel for" in generic_backend_cpp
    )
    command_manifest_validation = (
        "validate_commands" in generic_backend_cpp
        and "commands[index * 16]" in generic_backend_cpp
        and "opcodes[21]" in generic_backend_cpp
    )
    command_rtl_interpreter = any(
        marker in device_api_cpp or marker in generic_backend_cpp
        for marker in (
            "command_dispatch_submit",
            "command128_frontend_submit",
            "rtl_command_submit",
        )
    )
    layer_completion_callback_backpressure = (
        "completion_ready_cb" in device_api_cpp
        and "max_completion_waits" in device_api_cpp
    )
    return SourceSemantics(
        original_graph_guard=original_graph_guard,
        monolithic_submission=monolithic_submission,
        host_cpu_buffer_type=host_cpu_buffer_type,
        software_stage_backend=software_stage_backend,
        command_manifest_validation=command_manifest_validation,
        command_rtl_interpreter=command_rtl_interpreter,
        layer_completion_callback_backpressure=layer_completion_callback_backpressure,
    )


def classify_bindings(direct_report: Mapping[str, Any]) -> BindingSemantics:
    gguf = direct_report["gguf"]
    total = int(gguf["direct_buffer_bindings"])
    converted = int(gguf.get("norm_f32_to_bf16_RNE", 0))
    if converted < 0 or converted > total:
        raise ValueError("invalid conversion count")
    return BindingSemantics(
        total_bindings=total,
        raw_storage_byte_parity=total - converted,
        canonical_converted_parity=converted,
        conversion="F32_to_BF16_RNE",
    )


def audit_p3(
    *,
    backend_cpp: str,
    device_api_cpp: str,
    generic_backend_cpp: str,
    direct_report: Mapping[str, Any],
    backpressure_report: Mapping[str, Any],
    final_report: Mapping[str, Any],
) -> dict[str, Any]:
    sources = inspect_sources(backend_cpp, device_api_cpp, generic_backend_cpp)
    bindings = classify_bindings(direct_report)
    graph = direct_report["graph"]
    output = direct_report["output"]
    requirements = final_report["requirements"]

    closed = {
        "original_llama_graph_received": sources.original_graph_guard and int(graph["nodes"]) == 958,
        "single_backend_split": int(graph["splits"]) == 1,
        "scheduler_cpu_fallback_zero": int(graph["cpu_fallback"]) == 0,
        "continuous_28_layer_backend_function": int(graph["layers"]) == 28 and int(graph["groups"]) == 7,
        "canonical_GGUF_payload_bindings": bindings.total_bindings == 338,
        "final_argmax_match": int(output["argmax"]) == int(requirements["argmax"]),
        "final_top10_overlap": int(output["top10_overlap"]) == 10,
        "layer_completion_backpressure": (
            sources.layer_completion_callback_backpressure
            and int(backpressure_report["completions"]) == 28
            and int(backpressure_report["stalls"]) > 0
        ),
    }
    open_gates = {
        "Command128_RTL_execution": not sources.command_rtl_interpreter,
        "non_host_device_buffer": sources.host_cpu_buffer_type,
        "internal_engine_backpressure": sources.layer_completion_callback_backpressure,
        "all_row_integrated_RTL": True,
        "full_logits_metric_report": True,
        "post_route_PVT_OCV_SAIF": True,
    }
    errors: list[str] = []
    if not all(closed.values()):
        errors.extend(name for name, ok in closed.items() if not ok)
    if not sources.monolithic_submission:
        errors.append("missing_monolithic_submission")
    if not sources.software_stage_backend:
        errors.append("software_stage_backend_not_detected")
    if not sources.command_manifest_validation:
        errors.append("command_manifest_validation_not_detected")

    status = "PASS_LLAMA_BACKEND_FUNCTIONAL_SOFTWARE_EMULATION" if not errors else "FAIL_P3_EVIDENCE"
    return {
        "schema_version": 1,
        "status": status,
        "accepted_gate": "L5.6d.P3_real_llama_backend_equivalent",
        "not_accepted_as": [
            "hardware_device_payload_execution",
            "Command128_RTL_execution",
            "all_row_integrated_RTL",
            "post_route_signoff",
        ],
        "source_semantics": asdict(sources),
        "binding_semantics": asdict(bindings),
        "graph": {
            "nodes_received": int(graph["nodes"]),
            "splits": int(graph["splits"]),
            "manifest_commands": int(graph["commands"]),
            "commands_executed_by_RTL_frontend": 0 if not sources.command_rtl_interpreter else int(graph["commands"]),
        },
        "backpressure_scope": {
            "scope": "layer_completion_callback",
            "completions": int(backpressure_report["completions"]),
            "stalls": int(backpressure_report["stalls"]),
            "not_internal_matrix_sfu_kv_ready_valid": True,
        },
        "output_scope": {
            "vocab": int(output["vocab"]),
            "argmax": int(output["argmax"]),
            "top10_overlap": int(output["top10_overlap"]),
            "full_logits_metrics_present": False,
        },
        "closed_checks": closed,
        "open_gates": open_gates,
        "errors": errors,
    }


def audit_repository(root: str | Path) -> dict[str, Any]:
    root = Path(root)
    load_json = lambda rel: json.loads((root / rel).read_text(encoding="utf-8"))
    direct = load_json("reports/execution/llama_hetero_direct_gguf_result.json")
    backpressure = load_json("reports/execution/qwen2_device_backpressure_result.json")
    final = load_json("reports/execution/l5_6d_p3_device_final_audit.json")
    report = audit_p3(
        backend_cpp=(root / "src/ggml_hetero_backend.cpp").read_text(encoding="utf-8"),
        device_api_cpp=(root / "src/hetero_qwen2_device_api.cpp").read_text(encoding="utf-8"),
        generic_backend_cpp=(root / "src/qwen2_q1024_layer0_tail_backend.cpp").read_text(encoding="utf-8"),
        direct_report=direct,
        backpressure_report=backpressure,
        final_report=final,
    )
    report["audit_decision"] = "ACCEPT_L5_6D_P3_REAL_LLAMA_BACKEND_EQUIVALENT_RECLASSIFY_NOT_HARDWARE_DEVICE"
    report["numerical_context"] = {
        "continuous_layers": int(final["requirements"]["continuous_layers"]),
        "four_layer_groups": int(final["requirements"]["four_layer_groups"]),
        "maximum_attention_error": float(final["numerical"]["maximum_attention_error"]),
        "layer27_sha256": final["numerical"]["layer27_sha256"],
        "argmax": int(final["requirements"]["argmax"]),
        "top10_overlap": int(final["requirements"]["top10_overlap"]),
        "full_logits_metrics": "OPEN",
    }
    report["provenance"] = {
        "final_audit": "reports/execution/l5_6d_p3_device_final_audit.json",
        "direct_gguf": "reports/execution/llama_hetero_direct_gguf_result.json",
        "backpressure": "reports/execution/qwen2_device_backpressure_result.json",
        "backend_source": "src/ggml_hetero_backend.cpp",
        "device_api_source": "src/hetero_qwen2_device_api.cpp",
        "software_payload_source": "src/qwen2_q1024_generic_layer_backend.cpp",
    }
    return report
