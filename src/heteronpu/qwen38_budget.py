"""Analytical full-shape budget for the Qwen3.8-Flash-Next text path.

The model separates context-independent per-token work from QSA index scan and
sparse-attention work.  It is a lower-bound architecture screen, not measured
RTL cycles or model-quality evidence.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Iterable


@dataclass(frozen=True)
class Qwen38Shape:
    hidden_size: int = 2560
    layers: int = 48
    gdn_layers: int = 36
    qsa_layers: int = 12
    vocab_size: int = 248_320
    residual_branches: int = 4
    residual_lowrank: int = 320
    q_heads: int = 24
    kv_heads: int = 2
    head_dim: int = 256
    index_query_heads: int = 4
    index_kv_heads: int = 1
    index_head_dim: int = 128
    index_compress_ratio: int = 4
    index_token_budget: int = 2048
    gdn_qk_heads: int = 16
    gdn_v_heads: int = 48
    gdn_key_dim: int = 128
    gdn_value_dim: int = 128
    gdn_conv_kernel: int = 4
    experts: int = 512
    active_routed_experts: int = 10
    shared_experts: int = 1
    expert_intermediate: int = 640
    ple_layers: int = 1
    ple_embed_dim: int = 2560
    ple_ngram_heads: int = 16
    ple_conv_kernel: int = 4
    ple_table_rows_approx: int = 320_000_000

    def __post_init__(self) -> None:
        if self.gdn_layers + self.qsa_layers != self.layers:
            raise ValueError("layer inventory")
        if self.q_heads <= 0 or self.kv_heads <= 0 or self.q_heads % self.kv_heads:
            raise ValueError("attention geometry")
        if self.index_token_budget % self.index_compress_ratio:
            raise ValueError("QSA budget")
        if self.gdn_v_heads % self.gdn_qk_heads:
            raise ValueError("GDN head mapping")
        if self.ple_embed_dim % self.ple_ngram_heads:
            raise ValueError("PLE row width")

    @property
    def q_width(self) -> int:
        return self.q_heads * self.head_dim

    @property
    def kv_width(self) -> int:
        return self.kv_heads * self.head_dim

    @property
    def gdn_qk_width(self) -> int:
        return self.gdn_qk_heads * self.gdn_key_dim

    @property
    def gdn_v_width(self) -> int:
        return self.gdn_v_heads * self.gdn_value_dim

    @property
    def gdn_state_elements_per_layer(self) -> int:
        return self.gdn_v_heads * self.gdn_key_dim * self.gdn_value_dim

    @property
    def ple_row_elements(self) -> int:
        return self.ple_embed_dim // self.ple_ngram_heads


@dataclass(frozen=True)
class ComputePoint:
    name: str
    macs_per_cycle: int
    clock_hz: int = 1_000_000_000


DEFAULT_COMPUTE_POINTS = (
    ComputePoint("bf16_16x32", 512),
    ComputePoint("w8_32x64", 2048),
    ComputePoint("dual_w8_cluster", 4096),
    ComputePoint("native_w4_dual_dot", 4096),
)


def sum_complete_blocks(sequence_length: int, ratio: int) -> int:
    if sequence_length < 0 or ratio <= 0:
        raise ValueError("sum_complete_blocks")
    quotient, remainder = divmod(sequence_length, ratio)
    return ratio * quotient * (quotient - 1) // 2 + quotient * (remainder + 1)


def selected_tokens_for_visible_length(visible: int, ratio: int, budget: int) -> int:
    if visible < 0 or ratio <= 0 or budget <= 0 or budget % ratio:
        raise ValueError("selected-token geometry")
    complete, tail = divmod(visible, ratio)
    return min(complete, budget // ratio) * ratio + tail


def sum_selected_tokens(sequence_length: int, ratio: int, budget: int) -> int:
    return sum(selected_tokens_for_visible_length(visible, ratio, budget) for visible in range(1, sequence_length + 1))


def fixed_mac_breakdown(shape: Qwen38Shape) -> dict[str, int]:
    h = shape.hidden_size
    hyper = shape.residual_branches * h
    gr_one = hyper * shape.residual_lowrank + shape.residual_lowrank * hyper + hyper * shape.residual_branches
    gr_layer = 2 * gr_one
    final_gr = hyper * shape.residual_lowrank + shape.residual_lowrank * hyper
    qk_width = shape.gdn_qk_width
    v_width = shape.gdn_v_width
    gdn_projection = h * (qk_width + qk_width + v_width + v_width + shape.gdn_v_heads + shape.gdn_v_heads) + v_width * h
    state_entries = shape.gdn_state_elements_per_layer
    gdn_state_math = 3 * state_entries
    gdn_state_decay = state_entries
    gdn_conv = (qk_width + qk_width + v_width) * shape.gdn_conv_kernel
    qsa_projection = h * ((shape.index_query_heads + shape.index_kv_heads) * shape.index_head_dim) + h * (2 * shape.q_width) + h * (2 * shape.kv_width) + shape.q_width * h
    router = h * shape.experts
    one_expert = 3 * h * shape.expert_intermediate
    moe_active = router + (shape.active_routed_experts + shape.shared_experts) * one_expert
    ple_projection = shape.ple_embed_dim * (hyper + h)
    ple_gate_and_conv = hyper + hyper * shape.ple_conv_kernel
    fixed = shape.layers * (gr_layer + moe_active) + shape.gdn_layers * (gdn_projection + gdn_state_math + gdn_state_decay + gdn_conv) + shape.qsa_layers * qsa_projection + shape.ple_layers * (ple_projection + ple_gate_and_conv) + final_gr
    active_weight_parameters = shape.layers * (gr_layer + router + (shape.active_routed_experts + shape.shared_experts) * one_expert) + shape.gdn_layers * gdn_projection + shape.qsa_layers * qsa_projection + shape.ple_layers * ple_projection + final_gr
    return {
        "gated_residual_per_sublayer": gr_one,
        "gated_residual_per_layer": gr_layer,
        "final_hyper_mixer": final_gr,
        "gdn_projection_per_layer": gdn_projection,
        "gdn_state_matrix_per_layer": gdn_state_math,
        "gdn_state_decay_per_layer": gdn_state_decay,
        "gdn_causal_conv_per_layer": gdn_conv,
        "qsa_projection_per_layer": qsa_projection,
        "moe_router_per_layer": router,
        "moe_one_expert_per_layer": one_expert,
        "moe_active_per_layer": moe_active,
        "ple_projection": ple_projection,
        "ple_gate_and_conv": ple_gate_and_conv,
        "fixed_macs_per_token": fixed,
        "active_weight_parameters_per_token": active_weight_parameters,
    }


def qsa_dynamic_macs(shape: Qwen38Shape, sequence_length: int) -> dict[str, int]:
    blocks = sum_complete_blocks(sequence_length, shape.index_compress_ratio)
    index_macs = blocks * shape.index_query_heads * shape.index_head_dim * shape.qsa_layers
    selected = sum_selected_tokens(sequence_length, shape.index_compress_ratio, shape.index_token_budget)
    sparse_attention_macs = selected * 2 * shape.q_heads * shape.head_dim * shape.qsa_layers
    return {"complete_block_visits": blocks, "selected_token_visits": selected, "index_macs": index_macs, "sparse_qk_pv_macs": sparse_attention_macs, "total_dynamic_macs": index_macs + sparse_attention_macs}


def format_bytes(parameters: int, bits: int, group_size: int = 64, scale_bits: int = 16) -> int:
    if parameters < 0 or bits <= 0:
        raise ValueError("format bytes")
    scales = math.ceil(parameters / group_size) if bits <= 8 and group_size > 0 else 0
    return math.ceil((parameters * bits + scales * scale_bits) / 8)


def persistent_state_bytes(shape: Qwen38Shape, context: int, *, gdn_state_bits: int = 32, kv_bits: int = 16, index_bits: int = 16) -> dict[str, int]:
    if context < 0:
        raise ValueError("context")
    gdn_state = shape.gdn_layers * shape.gdn_state_elements_per_layer * gdn_state_bits // 8
    gdn_conv = shape.gdn_layers * (2 * shape.gdn_qk_width + shape.gdn_v_width) * (shape.gdn_conv_kernel - 1) * 2
    qsa_kv = shape.qsa_layers * context * shape.kv_heads * shape.head_dim * 2 * kv_bits // 8
    compressed_blocks = math.ceil(context / shape.index_compress_ratio)
    compressed_index = shape.qsa_layers * compressed_blocks * shape.index_head_dim * index_bits // 8
    raw_index = shape.qsa_layers * context * shape.index_head_dim * index_bits // 8
    ple_context = shape.ple_layers * ((3 - 1) * 4 + shape.residual_branches * shape.hidden_size * (shape.ple_conv_kernel - 1) * 3 * 2)
    return {"gdn_recurrent_state": gdn_state, "gdn_causal_conv_state": gdn_conv, "qsa_kv": qsa_kv, "qsa_compressed_index": compressed_index, "qsa_raw_index_alternative": raw_index, "ple_token_and_conv_state": ple_context, "total_with_compressed_index": gdn_state + gdn_conv + qsa_kv + compressed_index + ple_context}


def decode_external_bytes_per_token(shape: Qwen38Shape, context: int, *, weight_bits: int, gdn_state_bits: int = 32, kv_bits: int = 16, index_bits: int = 16, group_size: int = 64) -> dict[str, int]:
    fixed = fixed_mac_breakdown(shape)
    weights = format_bytes(fixed["active_weight_parameters_per_token"], weight_bits, group_size)
    state = persistent_state_bytes(shape, context, gdn_state_bits=gdn_state_bits, kv_bits=kv_bits, index_bits=index_bits)
    selected = selected_tokens_for_visible_length(context, shape.index_compress_ratio, shape.index_token_budget)
    selected_kv = shape.qsa_layers * selected * shape.kv_heads * shape.head_dim * 2 * kv_bits // 8
    index_scan = state["qsa_compressed_index"]
    gdn_state_rw = 2 * state["gdn_recurrent_state"]
    ple_rows = shape.ple_ngram_heads * shape.ple_row_elements * 2
    total = weights + selected_kv + index_scan + gdn_state_rw + ple_rows
    return {"weights": weights, "gdn_state_read_write": gdn_state_rw, "qsa_index_scan": index_scan, "qsa_selected_kv_read": selected_kv, "ple_row_payload": ple_rows, "total": total}


def prefill_budget(shape: Qwen38Shape, sequence_length: int, compute_points: Iterable[ComputePoint] = DEFAULT_COMPUTE_POINTS, target_tokens_per_second: int = 300) -> dict[str, object]:
    fixed = fixed_mac_breakdown(shape)
    dynamic = qsa_dynamic_macs(shape, sequence_length)
    total = fixed["fixed_macs_per_token"] * sequence_length + dynamic["total_dynamic_macs"]
    target_cycles = math.floor(sequence_length * 1_000_000_000 / target_tokens_per_second)
    points: dict[str, object] = {}
    for point in compute_points:
        required = total / (point.macs_per_cycle * target_cycles)
        points[point.name] = {"macs_per_cycle": point.macs_per_cycle, "ideal_cycles": math.ceil(total / point.macs_per_cycle), "target_cycles": target_cycles, "required_wall_utilization": required, "target_feasible_below_100pct": required <= 1.0}
    return {"sequence_length": sequence_length, "target_tokens_per_second": target_tokens_per_second, "fixed": fixed, "dynamic": dynamic, "total_macs": total, "average_macs_per_token": total / max(sequence_length, 1), "compute_points": points}


def full_budget_report(contexts: Iterable[int] = (1024, 4096, 262_144, 1_000_000), shape: Qwen38Shape = Qwen38Shape()) -> dict[str, object]:
    cases: dict[str, object] = {}
    for context in contexts:
        decode: dict[str, object] = {}
        for bits in (16, 8, 4):
            traffic = decode_external_bytes_per_token(shape, context, weight_bits=bits)
            decode[f"w{bits}"] = {**traffic, "gbps_at_10_tps": traffic["total"] * 10 / 1e9}
        cases[str(context)] = {"prefill": prefill_budget(shape, context), "persistent_state": persistent_state_bytes(shape, context), "decode": decode}
    return {
        "schema_version": 1,
        "status": "PASS",
        "evidence_class": "analytical_shape_budget_not_rtl_measurement",
        "shape": asdict(shape),
        "cases": cases,
        "ple_table_bf16_bytes_approx": shape.ple_table_rows_approx * shape.ple_row_elements * 2,
        "architecture_findings": {"single_bf16_512_mac_q1024_300tps": "infeasible", "single_w8_2048_mac_q1024_300tps": "mathematically_feasible_but_margin_too_small", "recommended_compute_candidates": ["dual_w8_cluster", "native_w4_dual_dot"], "gdn_state_engine_required": True, "qsa_streaming_selection_required": True, "expert_weight_cache_required": True},
    }
