"""Three-model M128 preparation manifest, deliberately not a replay admission.

This first-stage schema can bind authenticated metadata and known workload
constraints only. It cannot promote arbitrary filenames, hashes or booleans to
numerical/DUT proof. Missing replay contracts remain explicit and fail closed.
"""
from __future__ import annotations

from pathlib import Path

from .model_geometry import load_json, require
from .weight_header_contract import PINS, read_record, sha256, verify_bundle

MANIFEST_PATH = "config/workloads/three_model_m128_open.json"
BLOCKS = {
    "qwen2_1p5b": {"B2_DENSE": 0},
    "qwen3_5_0p8b": {"B35_08_GDN_DENSE": 0, "B35_08_ATTN_DENSE": 3},
    "qwen3_5_35b_a3b": {"B35_GDN_MOE": 0, "B35_ATTN_MOE": 3},
}
OPEN_FIELDS = {
    "kv_tokens", "weights_payload_sha256", "input_sha256", "initial_state_sha256",
    "position_ids_attention_mask_sha256", "precision_policy_sha256", "official_reference_sha256",
    "fixed_arithmetic_reference_sha256", "memory_cache_policy_sha256", "generated_rtl_sha256",
    "rtl_source_git_sha", "tool_versions_sha256", "configured_matrix_macs_per_cycle",
    "configured_vector_units", "vector_counting_policy_sha256", "matrix_tile_mapping_sha256",
}
PERFORMANCE_CONTRACT = {
    "minimum_matrix_useful_wall_utilization": 0.9,
    "denominator": "configured_matrix_macs_per_cycle * block_wall_cycles",
    "numerator": "matrix_useful_macs_excluding_padding",
    "start_event": "block_launch_handshake_accepted",
    "end_event": "all_final_output_and_required_state_write_acks_completed",
    "include": ["descriptor", "DMA", "internal_stall", "phase_gaps", "padding", "drain"],
    "matrix_vector_report_separately": True,
    "fixed_resources_from_same_generated_rtl": True,
}


def validate_preparation(root: str | Path, manifest: dict | None = None, *, require_complete: bool = False) -> dict:
    root = Path(root)
    if manifest is None:
        manifest = load_json(root / MANIFEST_PATH)
    require(isinstance(manifest, dict), "manifest must be a mapping")
    require(set(manifest) == {"schema_version", "status", "scope", "models", "workloads", "performance_contract",
                              "required_performance_suite_frozen", "required_performance_suite_sha256"}, "unknown/missing manifest fields")
    require(type(manifest["schema_version"]) is int and manifest["schema_version"] == 1, "unknown preparation schema")
    require(manifest["status"] == "OPEN_PINNED_HEADERS_ONLY", "header evidence cannot close a replay gate")
    require(manifest["scope"] == "typical_text_blocks_M128_preparation", "unknown workload scope")
    require(manifest["required_performance_suite_frozen"] is False and manifest["required_performance_suite_sha256"] is None,
            "M128 preparation is not a frozen required performance suite")
    require(manifest["performance_contract"] == PERFORMANCE_CONTRACT, "whole-block useful-MAC contract drift")
    require(type(manifest["performance_contract"]["minimum_matrix_useful_wall_utilization"]) is float,
            "invalid utilization threshold")
    for key in ("matrix_vector_report_separately", "fixed_resources_from_same_generated_rtl"):
        require(manifest["performance_contract"][key] is True, "invalid resource/counting flag")
    models = manifest["models"]
    require(isinstance(models, dict) and set(models) == set(PINS), "must retain all three exact models")
    header_reports = {}
    for key, model in models.items():
        require(isinstance(model, dict) and set(model) == {"model_id", "model_revision", "header_bundle_sha256",
                    "config", "forward", "forward_revision", "forward_repository"}, "invalid model binding")
        require((model["model_id"], model["model_revision"]) == PINS[key], "workload/checkpoint identity drift")
        header_reports[key] = verify_bundle(root, key)
        require(model["header_bundle_sha256"] == header_reports[key]["bundle_sha256"], "workload/header source drift")
        bundle = load_json(root / "config/upstream/weight_headers" / key / "manifest.json")
        require(model["config"] == bundle["config"] and model["forward"] == bundle["forward"], "workload/config/forward bytes drift")
        require(model["forward_revision"] == bundle["forward_revision"] and
                model["forward_repository"] == "huggingface/transformers", "unbound forward identity")
        read_record(root, model["config"])
        read_record(root, model["forward"])
    rows = manifest["workloads"]
    require(isinstance(rows, list) and len(rows) == 5, "five representative block entries required")
    expected = {(key, block, layer) for key, blocks in BLOCKS.items() for block, layer in blocks.items()}
    seen = set()
    gates = []
    for row in rows:
        require(isinstance(row, dict) and set(row) == {"model_key", "block_type", "layer_id", "batch", "query_tokens",
                    "shape_origin", "replay", "missing_evidence"}, "invalid workload row")
        require(type(row["layer_id"]) is int, "layer id must be an integer")
        identity = (row["model_key"], row["block_type"], row["layer_id"])
        require(identity in expected and identity not in seen, "unknown/duplicate representative block")
        seen.add(identity)
        require(type(row["batch"]) is int and row["batch"] == 1, "inherited batch=1 changed")
        require(type(row["query_tokens"]) is int and row["query_tokens"] == 128, "inherited M128 changed")
        require(row["shape_origin"] == "existing_plan_batch1_and_inherited_M128_not_complete_performance_suite",
                "workload origin must retain the unfrozen-suite caveat")
        replay = row["replay"]
        require(isinstance(replay, dict) and set(replay) == OPEN_FIELDS | {"expert_route_histogram_sha256"}, "missing replay gate fields")
        # Later proof types need semantic validators, not acceptance of arbitrary
        # digest strings. This metadata-only schema deliberately admits none.
        require(all(replay[k] is None for k in OPEN_FIELDS), "unvalidated replay evidence cannot be promoted by this schema")
        moe = row["model_key"] == "qwen3_5_35b_a3b"
        require(replay["expert_route_histogram_sha256"] == (None if moe else "not_applicable_dense_ffn"),
                "MoE routes cannot be invented or omitted")
        missing = OPEN_FIELDS | ({"expert_route_histogram_sha256"} if moe else set())
        reasons = row["missing_evidence"]
        require(isinstance(reasons, dict) and set(reasons) == missing, "all unresolved fields need explicit reasons")
        require(all(isinstance(v, str) and v.strip() for v in reasons.values()), "blank gate reason")
        gates.append({"model_key": identity[0], "block_type": identity[1], "layer_id": identity[2],
                      "status": "OPEN", "unresolved_fields": sorted(missing)})
    require(seen == expected, "required block omitted")
    require(not require_complete, "U00.2 OPEN: actual payload/input/state/precision/routes/cache/resources and performance suite are not frozen")
    return {"schema_version": 1, "status": "PASS_METADATA_PREPARATION_WITH_OPEN_REPLAY_GATES",
            "manifest_sha256": sha256((root / MANIFEST_PATH).read_bytes()) if manifest == load_json(root / MANIFEST_PATH) else None,
            "header_evidence": header_reports, "workloads": gates,
            "required_performance_suite_frozen": False, "full_U00_complete": False,
            "official_numerical_execution": False, "actual_rtl_execution": False, "mac_utilization_measured": False,
            "minimum_matrix_useful_wall_utilization": 0.9}
