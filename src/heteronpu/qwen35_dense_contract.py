"""Offline, byte-pinned 0.8B text geometry contract. Never executes vendor code.

Names are checked against the official weight index. Shapes are derived from
config/source, NOT weight headers. A PASS here is compiler E0, never inference,
precision-policy closure, generated RTL or MAC utilization acceptance.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .model_geometry import BlockGeometry, load_json, load_profile, require, validate_profile
from .qwen_family_contracts import DENSE_FAMILY, layer_ops, summary

MODEL_REVISION = "2fc06364715b967f1860aea9cf38778875588b17"
FORWARD_REVISION = "14e738b5d0cc69aa27a95dde272aea41fde44f2f"
PROFILE_PATH = "config/model_profiles/qwen3_5_0p8b.json"
SOURCE_PATH = "config/upstream/qwen3_5_0p8b"
SOURCE_HASHES = {
    "config.json": "b90b86f35c8e6925ef74ee04d0e758f0a845c83a42089ad82bbaa948de9b4204",
    "model.safetensors.index.json": "d8a08838a613b025eb7952ed9db11696213e57e76a375661ef5c12f9dd5dcf4e",
    "configuration_qwen3_5.py": "2f26c4bb911772d42a5f16e82bdea4b9ba1ac07872df527ec228622d35f3c30e",
    "modeling_qwen3_5.py": "aac2a1bcca88829afc6dbdf83f97155ebf64d800ee9d703af3802a9aebcfcd18",
    "modular_qwen3_5.py": "ba423e1400fc253dce1cdbb215463675ea09c96df5a379b43e985d36c9e675c7",
}


def tensor_shapes(p: dict) -> dict[str, list[int]]:
    """PyTorch weight order [out,in]; depthwise Conv1d [channels,1,kernel]."""
    validate_profile(p)
    require(p["architecture_family"] == DENSE_FAMILY, "expected 0.8B dense family")
    g = BlockGeometry.from_profile(p)
    out = {
        "model.language_model.embed_tokens.weight": [p["vocab_size"], g.hidden],
        "model.language_model.norm.weight": [g.hidden],
    }
    for layer, kind in enumerate(p["layer_pattern"]):
        shapes = {
            "input_layernorm.weight": [g.hidden],
            "post_attention_layernorm.weight": [g.hidden],
            "mlp.gate_proj.weight": [g.dense_ffn, g.hidden],
            "mlp.up_proj.weight": [g.dense_ffn, g.hidden],
            "mlp.down_proj.weight": [g.hidden, g.dense_ffn],
        }
        if kind == "full_attention":
            shapes.update({
                "self_attn.q_proj.weight": [2 * g.q_width, g.hidden],
                "self_attn.k_proj.weight": [g.kv_width, g.hidden],
                "self_attn.v_proj.weight": [g.kv_width, g.hidden],
                "self_attn.o_proj.weight": [g.hidden, g.q_width],
                "self_attn.q_norm.weight": [g.head_dim],
                "self_attn.k_norm.weight": [g.head_dim],
            })
        else:
            shapes.update({
                "linear_attn.in_proj_qkv.weight": [g.gdn_conv_channels, g.hidden],
                "linear_attn.in_proj_z.weight": [g.gdn_value_width, g.hidden],
                "linear_attn.in_proj_b.weight": [g.value_heads, g.hidden],
                "linear_attn.in_proj_a.weight": [g.value_heads, g.hidden],
                "linear_attn.conv1d.weight": [g.gdn_conv_channels, 1, p["gated_deltanet"]["conv_kernel"]],
                "linear_attn.dt_bias": [g.value_heads],
                "linear_attn.A_log": [g.value_heads],
                "linear_attn.norm.weight": [g.value_dim],
                "linear_attn.out_proj.weight": [g.hidden, g.gdn_value_width],
            })
        out.update({f"model.language_model.layers.{layer}.{name}": shape for name, shape in shapes.items()})
    return out


def source_bundle(root: str | Path) -> tuple[dict, dict, dict]:
    root = Path(root)
    directory = root / SOURCE_PATH
    manifest = load_json(directory / "manifest.json")
    require(isinstance(manifest, dict), "source manifest must be a mapping")
    require(manifest.get("model_id") == "Qwen/Qwen3.5-0.8B" and manifest.get("model_revision") == MODEL_REVISION,
            "wrong source model identity")
    require(manifest.get("modeling_repository") == "huggingface/transformers" and
            manifest.get("modeling_revision") == FORWARD_REVISION, "wrong forward identity")
    files = manifest.get("files")
    require(isinstance(files, list) and len(files) == len(SOURCE_HASHES), "source inventory mismatch")
    require(all(isinstance(x, dict) and isinstance(x.get("file"), str) for x in files), "invalid source record")
    require({x["file"] for x in files} == set(SOURCE_HASHES), "source filenames mismatch")
    for item in files:
        name = item["file"]
        rev = FORWARD_REVISION if name.endswith(".py") else MODEL_REVISION
        url = (f"https://raw.githubusercontent.com/huggingface/transformers/{rev}/src/transformers/models/qwen3_5/{name}"
               if name.endswith(".py") else f"https://huggingface.co/Qwen/Qwen3.5-0.8B/resolve/{rev}/{name}")
        raw = (directory / name).read_bytes()
        require(item.get("revision") == rev and item.get("url") == url, "source URL/revision mismatch: " + name)
        require(item.get("sha256") == SOURCE_HASHES[name] == hashlib.sha256(raw).hexdigest(),
                "source SHA256 mismatch: " + name)
        require(type(item.get("bytes")) is int and item["bytes"] == len(raw), "source length mismatch: " + name)
    return manifest, load_json(directory / "config.json"), load_json(directory / "model.safetensors.index.json")


def contract_report(root: str | Path) -> dict[str, Any]:
    root = Path(root)
    p = load_profile(root / PROFILE_PATH)
    manifest, config, index = source_bundle(root)
    c = config["text_config"]
    # Explicit bridge between upstream layer naming and compiler naming.
    require(p["layer_pattern"] == ["gated_deltanet" if x == "linear_attention" else x for x in c["layer_types"]],
            "upstream/compiler layer pattern mismatch")
    require(p["hidden_size"] == c["hidden_size"] and p["dense_ffn"]["intermediate_size"] == c["intermediate_size"],
            "upstream/compiler FFN geometry mismatch")
    shapes = tensor_shapes(p)
    weights = index["weight_map"]
    text_keys = {key for key in weights if key.startswith("model.language_model.")}
    require(set(shapes) == text_keys, "official main-text index names mismatch")
    g = BlockGeometry.from_profile(p)
    return {
        "schema_version": 1,
        "status": "PASS_PINNED_GEOMETRY_E0_ONLY",
        "model_id": p["model_id"], "model_revision": MODEL_REVISION,
        "profile_sha256": hashlib.sha256((root / PROFILE_PATH).read_bytes()).hexdigest(),
        "source_manifest": manifest,
        "family": summary(p), "geometry_M128": g.report(128),
        "index_names_verified": True, "main_text_tensor_count": len(shapes),
        "index_total_tensor_count": len(weights),
        "tensor_shapes_derived_not_weight_header_verified": dict(sorted(shapes.items())),
        "query_gate_packing": {"projected_shape": [128, g.q_heads, 2 * g.head_dim],
                               "query_slice_per_head": [0, g.head_dim],
                               "gate_slice_per_head": [g.head_dim, 2 * g.head_dim],
                               "gate_activation_before_output_projection": "sigmoid"},
        "typical_block_geometry": [
            {"block_type": "B35_08_GDN_DENSE", "layer_id_zero_based": 0, "operators": layer_ops(p, 0)},
            {"block_type": "B35_08_ATTN_DENSE", "layer_id_zero_based": 3, "operators": layer_ops(p, 3)},
        ],
        "weights_loaded": False, "numerical_execution": False, "rtl_execution": False,
        "mac_utilization_measured": False, "full_U00_complete": False,
        "unresolved_gates": ["checkpoint weight bytes/shape headers", "three-model precision and dual references",
                             "required batch/query/KV workload set and initial state/cache policy",
                             "actual MoE route histogram and fixed Matrix/Vector resource counters",
                             "generated RTL numerical replay and whole-block useful MAC >=90%"],
        "scope": "Pinned raw-source integrity, tensor names, derived geometry and E0 inventory only; not official-weight, RTL or performance acceptance.",
    }
