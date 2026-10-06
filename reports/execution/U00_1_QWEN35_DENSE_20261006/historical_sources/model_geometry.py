"""Fail-closed geometry of the two repository-pinned hybrid Qwen profiles.

This validates repository configuration, NOT upstream authenticity or RTL
support. Derived widths deliberately do not equate hidden size to Q width.
No weights are loaded and no arithmetic/RTL precision policy is changed.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any, Mapping


class ModelContractError(ValueError):
    """A configuration cannot be used by the frozen model-family compiler."""


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ModelContractError(message)


def positive(value: Any, name: str, maximum: int = 2**31 - 1) -> int:
    require(type(value) is int and 0 < value <= maximum, f"invalid integer: {name}")
    return value


# These are identities of already-committed inputs, not newly verified releases.
PINNED = {
    "qwen3_5_hybrid_gdn_full_attention_moe": {
        "model_id": "Qwen/Qwen3.5-35B-A3B",
        "revision": "62704185bd97ad488cfc404e7caea797396b74dc",
        "hf_model_type": "qwen3_5_moe", "text_model_type": "qwen3_5_moe_text",
        "num_hidden_layers": 40, "hidden_size": 2048,
        "residual_architecture": "single_stream_standard_residual",
        "normal": "gated_deltanet", "special": "full_attention",
        "q_heads": 16, "v_heads": 32, "experts": 256, "top_k": 8, "ffn": 512,
    },
    "qwen4_exp_flash_next": {
        "model_id": "Qwen/Qwen3.8-Flash-Next",
        "revision": "34567a4712bc9766c4449e2e98e4468bfa24d915",
        "hf_model_type": "qwen4_exp", "text_model_type": "qwen4_exp_text",
        "num_hidden_layers": 48, "hidden_size": 2560,
        "residual_architecture": "four_branch_gated_residual",
        "normal": "linear_attention", "special": "qwen_sparse_attention",
        "q_heads": 24, "v_heads": 48, "experts": 512, "top_k": 10, "ffn": 640,
    },
}


def _section(p: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = p.get(key)
    require(isinstance(value, dict), f"missing/invalid section: {key}")
    return value


def _exact_ints(section: Mapping[str, Any], values: Mapping[str, int], prefix: str) -> None:
    for key, expected in values.items():
        require(positive(section.get(key), prefix + key) == expected, f"frozen geometry mismatch: {prefix}{key}")


def validate_profile(p: Any) -> None:
    require(isinstance(p, dict), "profile must be a mapping")
    family = p.get("architecture_family")
    require(isinstance(family, str) and family in PINNED, "unknown architecture_family")
    expected = PINNED[family]
    for key in ("model_id", "revision", "hf_model_type", "text_model_type", "residual_architecture"):
        require(p.get(key) == expected[key], f"frozen identity mismatch: {key}")
    _exact_ints(p, {k: expected[k] for k in ("num_hidden_layers", "hidden_size")}, "")
    require(p.get("is_qwen3_dense_architecture") is False, "hybrid profile misclassified as dense")
    layers = expected["num_hidden_layers"]
    pattern = p.get("layer_pattern")
    require(isinstance(pattern, list) and pattern == [expected["special"] if i % 4 == 3 else expected["normal"]
                                                    for i in range(layers)], "invalid complete layer pattern")
    a, g, m = (_section(p, key) for key in ("full_attention", "gated_deltanet", "moe"))
    _exact_ints(a, {"q_heads": expected["q_heads"], "kv_heads": 2, "head_dim": 256, "rotary_dim": 64}, "attention.")
    _exact_ints(g, {"qk_heads": 16, "v_heads": expected["v_heads"], "key_dim": 128,
                    "value_dim": 128, "conv_kernel": 4, "chunk_size": 64}, "gdn.")
    _exact_ints(m, {"num_experts": expected["experts"], "top_k": expected["top_k"],
                    "intermediate_size": expected["ffn"], "shared_experts": 1}, "moe.")
    require(a["q_heads"] % a["kv_heads"] == 0 and g["v_heads"] % g["qk_heads"] == 0, "invalid head grouping")
    require(m.get("norm_topk_prob") is True and p.get("attention_output_gate") is True, "missing normalization/gate")
    if family == "qwen3_5_hybrid_gdn_full_attention_moe":
        require(not any(p.get(k) for k in ("qsa", "gated_residual", "ple")), "Qwen35 cannot acquire Qwen38 operators")
    else:
        qsa, hyper, ple = (_section(p, k) for k in ("qsa", "gated_residual", "ple"))
        _exact_ints(qsa, {"index_q_heads": 4, "index_kv_heads": 1, "index_head_dim": 128,
                         "token_budget": 2048, "block_budget": 512, "compress_ratio": 4}, "qsa.")
        _exact_ints(hyper, {"branches": 4, "lowrank": 320, "group_norm_size": 2560}, "hyper.")
        _exact_ints(ple, {"ngram_size": 3, "total_ngram_heads": 16, "row_width_per_head": 160,
                         "conv_kernel": 4, "conv_dilation": 3}, "ple.")
        require(ple.get("layer_ids") == [2] and all(type(i) is int for i in ple["layer_ids"]), "frozen PLE layer_ids mismatch")
        # Preserve the existing scheduler's i+1 convention; official forward
        # re-verification remains a different checklist item, C01.2.


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _nonfinite(value: str) -> None:
    raise ModelContractError(f"non-finite JSON constant: {value}")


def load_profile(path: str | Path) -> dict:
    p = json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=_unique_pairs, parse_constant=_nonfinite)
    validate_profile(p)
    return p


@dataclass(frozen=True)
class BlockGeometry:
    hidden: int
    q_heads: int
    kv_heads: int
    head_dim: int
    key_heads: int
    value_heads: int
    key_dim: int
    value_dim: int
    expert_ffn: int
    experts: int
    top_k: int
    branches: int

    @classmethod
    def from_profile(cls, p: Mapping[str, Any]) -> "BlockGeometry":
        validate_profile(p)
        a, g, m = p["full_attention"], p["gated_deltanet"], p["moe"]
        return cls(p["hidden_size"], a["q_heads"], a["kv_heads"], a["head_dim"],
                   g["qk_heads"], g["v_heads"], g["key_dim"], g["value_dim"],
                   m["intermediate_size"], m["num_experts"], m["top_k"],
                   p.get("gated_residual", {}).get("branches", 1))

    def __post_init__(self) -> None:
        for key, value in asdict(self).items():
            positive(value, key, 65535)
        require(self.q_heads % self.kv_heads == 0, "non-integral GQA grouping")
        require(self.value_heads % self.key_heads == 0, "non-integral GDN grouping")
        require(self.top_k <= self.experts, "top_k exceeds expert count")
        # Widths are not automatically truncated to the current 16-bit owner ABI.
        require(max(self.q_width, self.kv_width, self.gdn_value_width, self.gdn_conv_channels) <= 65535,
                "derived dimension exceeds 16-bit owner contract")

    @property
    def q_width(self) -> int:
        return self.q_heads * self.head_dim

    @property
    def kv_width(self) -> int:
        return self.kv_heads * self.head_dim

    @property
    def gdn_value_width(self) -> int:
        return self.value_heads * self.value_dim

    @property
    def gdn_conv_channels(self) -> int:
        return 2 * self.key_heads * self.key_dim + self.gdn_value_width

    def report(self, tokens: int = 128, kv_tokens: int | None = None) -> dict:
        positive(tokens, "query_tokens", 1024)
        kv_tokens = tokens if kv_tokens is None else positive(kv_tokens, "kv_tokens", 2**32 - 1)
        require(kv_tokens >= tokens, "KV length cannot be shorter than this prefill chunk")
        return {
            "evidence_class": "repository_profile_geometry_E0", "rtl_execution": False,
            "official_source_reverified": False,
            **asdict(self), "q_width": self.q_width, "kv_width": self.kv_width,
            "gdn_value_width": self.gdn_value_width, "gdn_conv_channels": self.gdn_conv_channels,
            "gdn_state_fp32_bytes": self.value_heads * self.key_dim * self.value_dim * 4,
            "routed_expert_three_matrices_bf16_bytes": 3 * self.hidden * self.expert_ffn * self.experts * 2,
            "residual_fp32_bytes_assuming_materialization": tokens * self.branches * self.hidden * 4,
            "query_tokens": tokens, "kv_tokens": kv_tokens,
            "kv_bf16_bytes": 2 * kv_tokens * self.kv_width * 2,
            "dense_shapes_MNK": {
                "attention_q": [tokens, self.q_width, self.hidden],
                "attention_kv_each": [tokens, self.kv_width, self.hidden],
                "attention_output": [tokens, self.hidden, self.q_width],
                "gdn_output": [tokens, self.hidden, self.gdn_value_width],
                "router": [tokens, self.experts, self.hidden],
                "one_expert_gate_up_each": [tokens, self.expert_ffn, self.hidden],
                "one_expert_down": [tokens, self.hidden, self.expert_ffn],
            },
            "scope": "Shapes/budgets only; gate projection packing, RoPE semantics, SRAM mapping and actual routing remain separate gates.",
        }
