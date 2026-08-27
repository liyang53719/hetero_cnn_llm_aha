"""Tiny Qwen3.8 E0 math, configuration and trace contracts."""
from __future__ import annotations

from dataclasses import dataclass
import math
import random
from typing import Iterable, Sequence

from .gated_deltanet import f32, sigmoid, silu

Vector = tuple[float, ...]
Matrix = tuple[Vector, ...]

def _fvec(values: Iterable[float]) -> Vector:
    return tuple(f32(v) for v in values)


def _check_width(values: Sequence[float], width: int, name: str) -> None:
    if len(values) != width:
        raise ValueError(f"{name}: expected width {width}, got {len(values)}")


def dot(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) != len(b):
        raise ValueError("dot width")
    acc = 0.0
    for x, y in zip(a, b, strict=True):
        acc = f32(acc + f32(f32(x) * f32(y)))
    return acc


def add(a: Sequence[float], b: Sequence[float]) -> Vector:
    if len(a) != len(b):
        raise ValueError("add width")
    return tuple(f32(x + y) for x, y in zip(a, b, strict=True))


def scale(a: Sequence[float], s: float) -> Vector:
    s = f32(s)
    return tuple(f32(f32(x) * s) for x in a)


def matvec(matrix: Matrix, vector: Sequence[float]) -> Vector:
    if matrix and len(matrix[0]) != len(vector):
        raise ValueError("matvec width")
    return tuple(dot(row, vector) for row in matrix)


def rmsnorm(vector: Sequence[float], eps: float = 1e-6) -> Vector:
    if not vector:
        return ()
    acc = 0.0
    for x in vector:
        acc = f32(acc + f32(f32(x) * f32(x)))
    mean = f32(acc / len(vector))
    inv = f32(1.0 / math.sqrt(f32(mean + eps)))
    return tuple(f32(f32(x) * inv) for x in vector)


def group_rmsnorm(vector: Sequence[float], branches: int, hidden: int, eps: float = 1e-6) -> Vector:
    _check_width(vector, branches * hidden, "group_rmsnorm")
    out: list[float] = []
    for branch in range(branches):
        start = branch * hidden
        out.extend(rmsnorm(vector[start : start + hidden], eps))
    return tuple(out)


def stable_softmax(logits: Sequence[float]) -> Vector:
    if not logits:
        raise ValueError("softmax empty")
    peak = max(logits)
    values = [math.exp(float(x) - float(peak)) for x in logits]
    den = sum(values)
    return tuple(f32(x / den) for x in values)


def rotate_half(vector: Sequence[float]) -> Vector:
    if len(vector) % 2:
        raise ValueError("rotate_half requires even width")
    half = len(vector) // 2
    return tuple(-f32(x) for x in vector[half:]) + tuple(f32(x) for x in vector[:half])


def rope(vector: Sequence[float], position: int, rotary_dim: int, theta: float = 1_000_000.0) -> Vector:
    if rotary_dim < 0 or rotary_dim > len(vector) or rotary_dim % 2:
        raise ValueError("invalid rotary_dim")
    if rotary_dim == 0:
        return _fvec(vector)
    head = _fvec(vector[:rotary_dim])
    rotated = rotate_half(head)
    half = rotary_dim // 2
    cos: list[float] = []
    sin: list[float] = []
    for idx in range(half):
        freq = 1.0 / (theta ** (2.0 * idx / rotary_dim))
        angle = float(position) * freq
        cos.append(f32(math.cos(angle)))
        sin.append(f32(math.sin(angle)))
    cos = cos + cos
    sin = sin + sin
    out = [f32(f32(x) * c + f32(y) * s) for x, y, c, s in zip(head, rotated, cos, sin, strict=True)]
    out.extend(f32(x) for x in vector[rotary_dim:])
    return tuple(out)


def _matrix(rng: random.Random, rows: int, cols: int, scale_value: float = 0.20) -> Matrix:
    return tuple(tuple(f32(rng.uniform(-scale_value, scale_value)) for _ in range(cols)) for _ in range(rows))


def _vector(rng: random.Random, width: int, scale_value: float = 0.20) -> Vector:
    return tuple(f32(rng.uniform(-scale_value, scale_value)) for _ in range(width))


@dataclass(frozen=True)
class TinyQwen38Config:
    """Small but structurally faithful text configuration used for E0 regression."""

    vocab_size: int = 32
    hidden_size: int = 8
    branches: int = 4
    hc_lowrank: int = 3
    layer_pattern: tuple[str, ...] = (
        "linear_attention",
        "linear_attention",
        "linear_attention",
        "qwen_sparse_attention",
    )
    ple_layer_ids: tuple[int, ...] = (1,)  # zero-based layer 2

    gdn_qk_heads: int = 1
    gdn_v_heads: int = 2
    gdn_key_dim: int = 2
    gdn_value_dim: int = 2
    gdn_conv_kernel: int = 4

    q_heads: int = 2
    kv_heads: int = 1
    head_dim: int = 4
    rotary_dim: int = 2

    qsa_index_q_heads: int = 2
    qsa_index_head_dim: int = 2
    qsa_token_budget: int = 4
    qsa_compress_ratio: int = 2

    num_experts: int = 4
    top_k: int = 2
    expert_intermediate: int = 3
    shared_intermediate: int = 3

    ple_ngram_size: int = 3
    ple_heads_per_ngram: int = 2
    ple_embed_dim: int = 8
    ple_conv_kernel: int = 3
    ple_conv_dilation: int = 2

    def __post_init__(self) -> None:
        if self.hidden_size != self.q_heads * self.head_dim:
            raise ValueError("hidden_size must equal q_heads * head_dim in the tiny reference")
        if self.q_heads % self.kv_heads:
            raise ValueError("q_heads must be divisible by kv_heads")
        if self.gdn_v_heads % self.gdn_qk_heads:
            raise ValueError("GDN v heads must be divisible by qk heads")
        if self.ple_embed_dim % ((self.ple_ngram_size - 1) * self.ple_heads_per_ngram):
            raise ValueError("PLE embed dimension must divide evenly across n-gram heads")
        if not 0 < self.qsa_token_budget:
            raise ValueError("qsa token budget")
        if self.qsa_token_budget % self.qsa_compress_ratio:
            raise ValueError("qsa token budget must be divisible by compression ratio")
        unknown = set(self.layer_pattern) - {"linear_attention", "qwen_sparse_attention"}
        if unknown:
            raise ValueError(f"unknown layer types: {sorted(unknown)}")


@dataclass(frozen=True)
class TraceEvent:
    token_index: int
    layer_index: int
    op: str
    engine: str
    detail: tuple[tuple[str, int | float | str], ...] = ()

    @classmethod
    def make(cls, token: int, layer: int, op: str, engine: str, **detail: int | float | str) -> "TraceEvent":
        return cls(token, layer, op, engine, tuple(sorted(detail.items())))
