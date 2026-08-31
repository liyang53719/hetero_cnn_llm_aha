"""Resource envelopes for Qwen3.5-35B-A3B and Qwen3.8-Flash-Next.

The two models are distinct architecture families. This module derives state,
KV/index, activation-tile, PLE and active-MoE traffic from frozen official
configuration profiles. It is architecture/compiler E0, not official-weight,
RTL, performance or PPA evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Mapping


MIB = 1024 * 1024
GIB = 1024 * MIB


@dataclass(frozen=True)
class WeightTraffic:
    format: str
    bits: int
    one_expert_bytes: int
    active_experts_per_layer: int
    active_bytes_per_layer: int
    active_bytes_all_layers: int


def load_profile(path: str | Path) -> dict[str, object]:
    return json.loads(Path(path).read_text())


def validate_profiles(q35: Mapping[str, object], q38: Mapping[str, object]) -> None:
    if q35.get("hf_model_type") != "qwen3_5_moe":
        raise ValueError("Qwen3.5 profile is not qwen3_5_moe")
    if q38.get("hf_model_type") != "qwen4_exp":
        raise ValueError("Flash-Next profile is not qwen4_exp")
    if q35.get("architecture_family") == q38.get("architecture_family"):
        raise ValueError("model family conflation")
    if any(key in q35 for key in ("qsa", "ple", "gated_residual")):
        raise ValueError("Qwen3.5 must not inherit Flash-Next-only operators")
    for key in ("qsa", "ple", "gated_residual"):
        if key not in q38:
            raise ValueError(f"Flash-Next missing {key}")
    if len(q35["layer_pattern"]) != int(q35["num_hidden_layers"]):
        raise ValueError("Qwen3.5 layer count")
    if len(q38["layer_pattern"]) != int(q38["num_hidden_layers"]):
        raise ValueError("Flash-Next layer count")


def _layer_counts(profile: Mapping[str, object]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in profile["layer_pattern"]:
        counts[str(item)] = counts.get(str(item), 0) + 1
    return counts


def _moe_traffic(profile: Mapping[str, object], *, group_size: int = 64, scale_bytes: int = 2) -> tuple[WeightTraffic, ...]:
    hidden = int(profile["hidden_size"])
    layers = int(profile["num_hidden_layers"])
    moe = profile["moe"]
    intermediate = int(moe["intermediate_size"])
    active = int(moe["top_k"]) + int(moe["shared_experts"])
    parameters = 3 * hidden * intermediate
    out: list[WeightTraffic] = []
    for name, bits in (("bf16", 16), ("w8", 8), ("w4", 4)):
        payload = math.ceil(parameters * bits / 8)
        scale = 0 if bits == 16 else math.ceil(parameters / group_size) * scale_bytes
        one = payload + scale
        per_layer = one * active
        out.append(WeightTraffic(name, bits, one, active, per_layer, per_layer * layers))
    return tuple(out)


def _gdn_state(profile: Mapping[str, object]) -> dict[str, int]:
    counts = _layer_counts(profile)
    gdn_layers = counts.get("gated_deltanet", 0) + counts.get("linear_attention", 0)
    gdn = profile["gated_deltanet"]
    v_heads = int(gdn["v_heads"])
    key_dim = int(gdn["key_dim"])
    value_dim = int(gdn["value_dim"])
    qk_heads = int(gdn["qk_heads"])
    kernel = int(gdn["conv_kernel"])
    state_per_layer = v_heads * key_dim * value_dim * 4
    conv_channels = 2 * qk_heads * key_dim + v_heads * value_dim
    conv_per_layer_bf16 = conv_channels * max(0, kernel - 1) * 2
    tile_heads = 4
    tile_bytes = tile_heads * key_dim * value_dim * 4
    return {
        "layers": gdn_layers,
        "state_bytes_per_layer_fp32": state_per_layer,
        "state_bytes_all_layers_fp32": state_per_layer * gdn_layers,
        "conv_history_bytes_per_layer_bf16": conv_per_layer_bf16,
        "conv_history_bytes_all_layers_bf16": conv_per_layer_bf16 * gdn_layers,
        "four_head_state_tile_bytes": tile_bytes,
        "four_head_pingpong_bytes": 2 * tile_bytes,
    }


def _kv(profile: Mapping[str, object]) -> dict[str, int]:
    counts = _layer_counts(profile)
    attention_layers = counts.get("full_attention", 0) + counts.get("qwen_sparse_attention", 0)
    attn = profile["full_attention"]
    context = int(profile["context_length"])
    kv_heads = int(attn["kv_heads"])
    head_dim = int(attn["head_dim"])
    per_token_per_layer = kv_heads * head_dim * 2 * 2
    result = {
        "attention_layers": attention_layers,
        "bf16_bytes_per_token_per_layer": per_token_per_layer,
        "bf16_bytes_full_context_all_layers": attention_layers * context * per_token_per_layer,
    }
    if profile.get("hf_model_type") == "qwen4_exp":
        qsa = profile["qsa"]
        blocks = math.ceil(context / int(qsa["compress_ratio"]))
        index_per_block = int(qsa["index_kv_heads"]) * int(qsa["index_head_dim"]) * 2
        result.update({
            "qsa_compressed_blocks": blocks,
            "qsa_index_bytes_per_layer_bf16": blocks * index_per_block,
            "qsa_index_bytes_all_layers_bf16": attention_layers * blocks * index_per_block,
            "qsa_selected_token_budget": int(qsa["token_budget"]),
            "qsa_selected_block_budget": int(qsa["block_budget"]),
        })
    return result


def _activation_and_ple(profile: Mapping[str, object], tile_tokens: int = 16) -> dict[str, int | str]:
    hidden = int(profile["hidden_size"])
    if profile.get("hf_model_type") == "qwen4_exp":
        branches = int(profile["gated_residual"]["branches"])
        hyper_tile = branches * hidden * tile_tokens * 2
        ple = profile["ple"]
        return {
            "layout": "four_branch_hyper_stream",
            "tile_tokens": tile_tokens,
            "single_tile_bytes_bf16": hyper_tile,
            "pingpong_bytes_bf16": 2 * hyper_tile,
            "ple_rows_per_token": int(ple["total_ngram_heads"]),
            "ple_row_width": int(ple["row_width_per_head"]),
            "ple_row_payload_bytes_per_token_bf16": int(ple["total_ngram_heads"]) * int(ple["row_width_per_head"]) * 2,
            "ple_conv_history_bytes_bf16": int(ple["embed_dim"]) * max(0, int(ple["conv_kernel"]) - 1) * 2,
        }
    tile = hidden * tile_tokens * 2
    return {
        "layout": "single_residual_stream",
        "tile_tokens": tile_tokens,
        "single_tile_bytes_bf16": tile,
        "pingpong_bytes_bf16": 2 * tile,
        "ple_rows_per_token": 0,
        "ple_row_payload_bytes_per_token_bf16": 0,
        "ple_conv_history_bytes_bf16": 0,
    }


def model_envelope(profile: Mapping[str, object]) -> dict[str, object]:
    counts = _layer_counts(profile)
    gdn = _gdn_state(profile)
    kv = _kv(profile)
    activations = _activation_and_ple(profile)
    moe = _moe_traffic(profile)
    if profile["hf_model_type"] == "qwen3_5_moe":
        exclusive = ["dense_causal_GQA", "single_residual_stream", "256_expert_top8_scheduler"]
        required_engines = ["matrix", "norm_rope_gate_sfu", "gdn_state", "dense_attention", "expert_weight_cache", "mtp_transaction"]
    else:
        exclusive = ["QSA_selection_top512_sparse_gather", "four_branch_gated_residual", "PLE_row_fetch_conv", "512_expert_top10_scheduler"]
        required_engines = ["matrix", "norm_rope_gate_sfu", "gdn_state", "qsa_selection", "sparse_kv_gather", "ple_row_fetch", "expert_weight_cache", "mtp_transaction"]
    minimum_staging = int(gdn["four_head_pingpong_bytes"]) + int(activations["pingpong_bytes_bf16"])
    if profile["hf_model_type"] == "qwen4_exp":
        minimum_staging += 288 * 1024
    else:
        minimum_staging += 256 * 1024
    return {
        "model_id": profile["model_id"],
        "architecture_family": profile["architecture_family"],
        "hf_model_type": profile["hf_model_type"],
        "layers": int(profile["num_hidden_layers"]),
        "layer_counts": counts,
        "gdn": gdn,
        "kv_and_index": kv,
        "activation_and_ple": activations,
        "moe_active_weight_traffic": [traffic.__dict__ for traffic in moe],
        "minimum_onchip_staging_bytes": minimum_staging,
        "minimum_onchip_staging_mib": minimum_staging / MIB,
        "fits_within_4MiB_before_matrix_scratch": minimum_staging <= 4 * MIB,
        "required_engines": required_engines,
        "family_exclusive_contracts": exclusive,
    }


def resource_envelope_report(q35_path: str | Path, q38_path: str | Path) -> dict[str, object]:
    q35 = load_profile(q35_path); q38 = load_profile(q38_path); validate_profiles(q35, q38)
    a = model_envelope(q35); b = model_envelope(q38)
    if a["gdn"]["state_bytes_all_layers_fp32"] != 60 * MIB: raise AssertionError("Qwen3.5 GDN state")
    if b["gdn"]["state_bytes_all_layers_fp32"] != 108 * MIB: raise AssertionError("Flash-Next GDN state")
    if a["kv_and_index"]["bf16_bytes_full_context_all_layers"] != 5 * GIB: raise AssertionError("Qwen3.5 KV")
    if b["kv_and_index"]["bf16_bytes_full_context_all_layers"] != 6 * GIB: raise AssertionError("Flash-Next KV")
    if b["kv_and_index"]["qsa_index_bytes_all_layers_bf16"] != 192 * MIB: raise AssertionError("Flash-Next index")
    if b["activation_and_ple"]["pingpong_bytes_bf16"] != 640 * 1024: raise AssertionError("Flash-Next hyper tile")
    payload = {
        "schema_version": 1,
        "status": "PASS_DISTINCT_QWEN_MODEL_RESOURCE_ENVELOPES",
        "evidence_class": "official_config_resource_envelope_E0_not_official_weight_RTL_or_E3",
        "qwen3_5_35b_a3b": a,
        "qwen3_8_flash_next": b,
        "shared_hardware": ["matrix_and_grouped_expert_datapath", "norm_rope_gate_sfu", "gdn_recurrent_state_engine", "quant_operand_frontend", "expert_weight_cache_base", "mtp_transaction_manager"],
        "forbidden_conflation": [
            "Do not lower Qwen3.5 dense full-attention layers through QSA selection/gather.",
            "Do not add PLE or four-branch hyper residual state to Qwen3.5.",
            "Do not use Qwen3.5 dense-attention service curves for Flash-Next QSA index scan and sparse gather.",
            "Do not infer ordinary Qwen3.8 support from the Flash-Next qwen4_exp profile.",
        ],
        "sandbox_next": {
            "qwen3_5": ["tiny 3xGDN+1xdense-attention+MoE executable group", "official-shape GDN recurrent/chunk sampled parity", "dense-attention output-gate adversarial vectors", "40-layer Command128/liveness validation", "256-expert top8 route/cache DSE"],
            "qwen3_8_flash_next": ["QSA index-key quantization and Top-k Jaccard vectors", "PLE random-row cache/outstanding DSE", "four-branch residual quantization/liveness", "48-layer state transaction trace", "512-expert top10 route/cache DSE"],
        },
    }
    payload["sha256"] = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return payload
