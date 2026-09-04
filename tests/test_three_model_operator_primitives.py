from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "audit_three_model_operator_primitives.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("operator_audit", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_complete_three_model_chisel_operator_source_gate():
    result = _load_module().audit()
    assert result["status"] == "PASS_COMPLETE_THREE_MODEL_CHISEL_OPERATOR_PRIMITIVE_SOURCE_GATE"
    assert result["root_count"] == 18
    assert result["operator_counts"] == {
        "qwen2_1p5b": 30,
        "qwen3_5_35b_a3b": 93,
        "qwen3_8_flash_next": 150,
    }
    assert all(not missing for missing in result["missing_operators"].values())
    assert result["target_clock_hz"] == 800_000_000
    assert result["target_period_ns"] == 1.25


def test_inventory_has_no_coarse_vision_placeholder():
    module = _load_module()
    inventory = module.json.loads(module.INVENTORY_PATH.read_text(encoding="utf-8"))
    operators = []
    for entry in inventory["models"].values():
        operators.extend(module._flatten_model(entry))
    assert "vision_encoder" not in operators
    assert "vision_patch_projection" in operators
    assert "vision_noncausal_qk" in operators
    assert "vision_spatial_merge" in operators
    assert "multimodal_token_scatter" in operators


def test_qwen38_unique_operator_surface_is_explicit():
    module = _load_module()
    inventory = module.json.loads(module.INVENTORY_PATH.read_text(encoding="utf-8"))
    q38 = set(module._flatten_model(inventory["models"]["qwen3_8_flash_next"]))
    required = {
        "attention_hyper_lowrank_down",
        "attention_hyper_state_write",
        "ple_ngram_hash",
        "ple_dilated_depthwise_conv",
        "qsa_stable_top512",
        "qsa_run_coalesce",
        "qsa_sparse_kv_gather",
        "final_hyper_weighted_reduce",
        "moe_stable_top10",
        "mtp_state_commit_rollback",
    }
    assert required <= q38


def test_qwen35_gdn_moe_and_dense_attention_are_explicit():
    module = _load_module()
    inventory = module.json.loads(module.INVENTORY_PATH.read_text(encoding="utf-8"))
    q35 = set(module._flatten_model(inventory["models"]["qwen3_5_35b_a3b"]))
    required = {
        "gdn_decay_exp",
        "gdn_outer_product_update",
        "attention_output_sigmoid_gate",
        "dense_online_softmax",
        "moe_stable_top8",
        "routed_expert_weighted_reduce",
        "shared_expert_router_gate",
        "multimodal_token_scatter",
    }
    assert required <= q35
