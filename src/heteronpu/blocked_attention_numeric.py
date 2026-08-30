"""Numerical Golden for blocked causal GQA Attention.

The reference models the intended hardware order:

* BF16 Q/K/V containers (represented as float32 after BF16 RNE),
* QK in FP32,
* per-K/V-microtile online Softmax summaries,
* Block128 summary construction,
* hierarchical M/L/O merge in FP32,
* FP32 PV accumulation and final normalization.

It never materializes a score/probability tensor outside the function and can
validate selected query rows at long sequence lengths without allocating an
LxL matrix.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import math
from typing import Iterable, Sequence

import numpy as np


def _f32(value: np.ndarray | float) -> np.ndarray | np.float32:
    return np.asarray(value, dtype=np.float32)


def bf16_round(value: np.ndarray) -> np.ndarray:
    x = np.asarray(value, dtype=np.float32)
    bits = x.view(np.uint32).copy()
    lsb = (bits >> np.uint32(16)) & np.uint32(1)
    bits = (bits + np.uint32(0x7FFF) + lsb) & np.uint32(0xFFFF0000)
    return bits.view(np.float32)


@dataclass(frozen=True)
class AttentionGeometry:
    sequence: int
    q_heads: int = 12
    kv_heads: int = 2
    head_dim: int = 128
    query_tile: int = 16
    kv_tile: int = 32
    block_tokens: int = 128

    def __post_init__(self) -> None:
        if self.sequence <= 0 or self.head_dim <= 0:
            raise ValueError("positive geometry required")
        if self.q_heads <= 0 or self.kv_heads <= 0 or self.q_heads % self.kv_heads:
            raise ValueError("q_heads must be divisible by kv_heads")
        if min(self.query_tile, self.kv_tile, self.block_tokens) <= 0:
            raise ValueError("tile geometry")
        if self.block_tokens % self.kv_tile:
            raise ValueError("block_tokens must be divisible by kv_tile")

    @property
    def gqa_ratio(self) -> int:
        return self.q_heads // self.kv_heads

    @property
    def scale(self) -> np.float32:
        return np.float32(1.0 / math.sqrt(self.head_dim))

    @property
    def expected_summary_merges(self) -> int:
        return self.q_heads * sum(t // self.block_tokens for t in range(self.sequence))


@dataclass(frozen=True)
class MLOSummary:
    m: np.float32
    l: np.float32
    o: np.ndarray


def _empty_summary(head_dim: int) -> MLOSummary:
    return MLOSummary(np.float32(-np.inf), np.float32(0.0), np.zeros(head_dim, dtype=np.float32))


def _tile_summary(q: np.ndarray, keys: np.ndarray, values: np.ndarray, scale: np.float32) -> MLOSummary:
    if keys.shape[0] == 0:
        return _empty_summary(q.shape[0])
    scores = np.asarray(keys @ q, dtype=np.float32)
    scores = np.asarray(scores * scale, dtype=np.float32)
    m = np.float32(np.max(scores))
    weights = np.asarray(np.exp(np.asarray(scores - m, dtype=np.float32)), dtype=np.float32)
    l = np.float32(np.sum(weights, dtype=np.float32))
    o = np.asarray(weights @ values, dtype=np.float32)
    return MLOSummary(m, l, o)


def merge_summaries(lhs: MLOSummary, rhs: MLOSummary) -> MLOSummary:
    if lhs.l == 0:
        return MLOSummary(rhs.m, rhs.l, rhs.o.copy())
    if rhs.l == 0:
        return MLOSummary(lhs.m, lhs.l, lhs.o.copy())
    m = np.float32(max(float(lhs.m), float(rhs.m)))
    alpha = np.float32(math.exp(float(np.float32(lhs.m - m))))
    beta = np.float32(math.exp(float(np.float32(rhs.m - m))))
    l = np.float32(np.float32(lhs.l * alpha) + np.float32(rhs.l * beta))
    o = np.asarray(np.asarray(lhs.o * alpha, dtype=np.float32) + np.asarray(rhs.o * beta, dtype=np.float32), dtype=np.float32)
    return MLOSummary(m, l, o)


def _block_summary(
    q: np.ndarray,
    keys: np.ndarray,
    values: np.ndarray,
    *,
    scale: np.float32,
    kv_tile: int,
) -> MLOSummary:
    summary = _empty_summary(q.shape[0])
    for start in range(0, keys.shape[0], kv_tile):
        stop = min(keys.shape[0], start + kv_tile)
        summary = merge_summaries(summary, _tile_summary(q, keys[start:stop], values[start:stop], scale))
    return summary


def blocked_causal_gqa_rows(
    q: np.ndarray,
    k: np.ndarray,
    v: np.ndarray,
    *,
    rows: Sequence[int] | None = None,
    query_tile: int = 16,
    kv_tile: int = 32,
    block_tokens: int = 128,
) -> tuple[np.ndarray, dict[str, int]]:
    q = np.asarray(q, dtype=np.float32)
    k = np.asarray(k, dtype=np.float32)
    v = np.asarray(v, dtype=np.float32)
    if q.ndim != 3 or k.ndim != 3 or v.ndim != 3:
        raise ValueError("Q/K/V must have shape [sequence, heads, head_dim]")
    if k.shape != v.shape or q.shape[0] != k.shape[0] or q.shape[2] != k.shape[2]:
        raise ValueError("Q/K/V shapes are incompatible")
    sequence, q_heads, head_dim = q.shape
    kv_heads = k.shape[1]
    geometry = AttentionGeometry(sequence, q_heads, kv_heads, head_dim, query_tile, kv_tile, block_tokens)
    selected = tuple(range(sequence)) if rows is None else tuple(int(row) for row in rows)
    if any(row < 0 or row >= sequence for row in selected):
        raise ValueError("row out of range")

    result = np.empty((len(selected), q_heads, head_dim), dtype=np.float32)
    block_merges = 0
    tile_summaries = 0
    for out_row, token in enumerate(selected):
        key_limit = token + 1
        for q_head in range(q_heads):
            kv_head = q_head // geometry.gqa_ratio
            total = _empty_summary(head_dim)
            first_block = True
            for block_start in range(0, key_limit, block_tokens):
                block_stop = min(key_limit, block_start + block_tokens)
                block = _block_summary(
                    q[token, q_head],
                    k[block_start:block_stop, kv_head],
                    v[block_start:block_stop, kv_head],
                    scale=geometry.scale,
                    kv_tile=kv_tile,
                )
                tile_summaries += math.ceil((block_stop - block_start) / kv_tile)
                if first_block:
                    total = block
                    first_block = False
                else:
                    total = merge_summaries(total, block)
                    block_merges += 1
            result[out_row, q_head] = np.asarray(total.o / total.l, dtype=np.float32)
    return result, {
        "selected_rows": len(selected),
        "block_merges": block_merges,
        "tile_summaries": tile_summaries,
        "score_ddr_bytes": 0,
        "probability_ddr_bytes": 0,
    }


def dense_causal_gqa_rows(q: np.ndarray, k: np.ndarray, v: np.ndarray, rows: Sequence[int]) -> np.ndarray:
    q = np.asarray(q, dtype=np.float32)
    k = np.asarray(k, dtype=np.float32)
    v = np.asarray(v, dtype=np.float32)
    sequence, q_heads, head_dim = q.shape
    kv_heads = k.shape[1]
    if q_heads % kv_heads:
        raise ValueError("GQA ratio")
    ratio = q_heads // kv_heads
    scale = np.float32(1.0 / math.sqrt(head_dim))
    result = np.empty((len(rows), q_heads, head_dim), dtype=np.float32)
    for out_row, token in enumerate(rows):
        for q_head in range(q_heads):
            kv_head = q_head // ratio
            scores = np.asarray(k[: token + 1, kv_head] @ q[token, q_head], dtype=np.float32)
            scores = np.asarray(scores * scale, dtype=np.float32)
            m = np.float32(np.max(scores))
            weights = np.asarray(np.exp(np.asarray(scores - m, dtype=np.float32)), dtype=np.float32)
            weights = np.asarray(weights / np.float32(np.sum(weights, dtype=np.float32)), dtype=np.float32)
            result[out_row, q_head] = np.asarray(weights @ v[: token + 1, kv_head], dtype=np.float32)
    return result


def _metrics(actual: np.ndarray, expected: np.ndarray) -> dict[str, float]:
    error = np.asarray(actual - expected, dtype=np.float64)
    expected64 = np.asarray(expected, dtype=np.float64)
    return {
        "max_abs": float(np.max(np.abs(error))),
        "mean_abs": float(np.mean(np.abs(error))),
        "rmse": float(np.sqrt(np.mean(error * error))),
        "relative_l2": float(np.linalg.norm(error.ravel()) / max(np.linalg.norm(expected64.ravel()), 1e-30)),
    }


def _hash(array: np.ndarray) -> str:
    return hashlib.sha256(np.asarray(array, dtype="<f4").tobytes()).hexdigest()


def generate_inputs(geometry: AttentionGeometry, seed: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    q = bf16_round(rng.normal(0.0, 0.75, (geometry.sequence, geometry.q_heads, geometry.head_dim)).astype(np.float32))
    k = bf16_round(rng.normal(0.0, 0.75, (geometry.sequence, geometry.kv_heads, geometry.head_dim)).astype(np.float32))
    v = bf16_round(rng.normal(0.0, 0.50, (geometry.sequence, geometry.kv_heads, geometry.head_dim)).astype(np.float32))
    return q, k, v


def validation_case(geometry: AttentionGeometry, rows: Iterable[int], seed: int) -> dict[str, object]:
    selected = tuple(int(row) for row in rows)
    q, k, v = generate_inputs(geometry, seed)
    blocked, counters = blocked_causal_gqa_rows(
        q,
        k,
        v,
        rows=selected,
        query_tile=geometry.query_tile,
        kv_tile=geometry.kv_tile,
        block_tokens=geometry.block_tokens,
    )
    dense = dense_causal_gqa_rows(q, k, v, selected)
    return {
        "geometry": asdict(geometry),
        "rows": list(selected),
        "metrics": _metrics(blocked, dense),
        "blocked_sha256": _hash(blocked),
        "dense_sha256": _hash(dense),
        "counters": counters,
    }


def blocked_attention_numeric_report() -> dict[str, object]:
    cases = [
        validation_case(AttentionGeometry(128), range(128), 0xA771),
        validation_case(AttentionGeometry(384), (0, 15, 16, 127, 128, 255, 383), 0xA772),
        validation_case(AttentionGeometry(1024), (0, 31, 127, 128, 383, 511, 767, 1023), 0xA773),
    ]
    max_abs = max(float(case["metrics"]["max_abs"]) for case in cases)
    max_rel = max(float(case["metrics"]["relative_l2"]) for case in cases)
    return {
        "schema_version": 1,
        "status": "PASS" if max_abs <= 2.0e-4 and max_rel <= 2.0e-4 else "FAIL",
        "evidence_class": "blocked_attention_numerical_E0_not_RTL_E2",
        "input_format": "BF16_RNE_in_FP32_container",
        "state_format": "FP32_M_L_O",
        "cases": cases,
        "maximum_error": {"max_abs": max_abs, "relative_l2": max_rel},
        "analytic_q1024_summary_merges": AttentionGeometry(1024).expected_summary_merges,
        "frozen": {
            "score_DDR_bytes": 0,
            "probability_DDR_bytes": 0,
            "GQA_ratio": 6,
            "block_tokens": 128,
            "kv_tile": 32,
            "first_RTL_score_fifo_depth": 2,
            "first_RTL_probability_fifo_depth": 2,
        },
        "remaining_local_gates": [
            "real_QK_to_MLO_to_PV_ready_valid_E1",
            "RTL_vs_this_reference_q128_q384_q1024_E2",
            "Revision8B_B_measured_service_curve",
        ],
    }
