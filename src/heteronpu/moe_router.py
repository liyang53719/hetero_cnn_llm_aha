"""Deterministic MoE routing, batching and executable tiny expert reference."""
from __future__ import annotations
from dataclasses import dataclass
import math
import random
import struct
from typing import Sequence


def _f32(x: float) -> float:
    return struct.unpack('<f', struct.pack('<f', float(x)))[0]


def _sigmoid(x: float) -> float:
    x = _f32(x)
    z = _f32(math.exp(-abs(x)))
    return _f32(1 / (1 + z)) if x >= 0 else _f32(z / (1 + z))


def _silu(x: float) -> float:
    return _f32(_f32(x) * _sigmoid(x))


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) != len(b):
        raise ValueError('dot width')
    acc = 0.0
    for x, y in zip(a, b, strict=True):
        acc = _f32(acc + _f32(_f32(x) * _f32(y)))
    return acc


def _matvec(matrix: Sequence[Sequence[float]], vector: Sequence[float]) -> tuple[float, ...]:
    return tuple(_dot(row, vector) for row in matrix)


@dataclass(frozen=True)
class Route:
    expert_id: int
    weight: float


def route_topk(logits: Sequence[float], k: int) -> tuple[Route, ...]:
    if not 0 < k <= len(logits):
        raise ValueError('top-k')
    ids = sorted(range(len(logits)), key=lambda i: (-float(logits[i]), i))[:k]
    peak = max(float(logits[i]) for i in ids)
    raw = [math.exp(float(logits[i]) - peak) for i in ids]
    den = sum(raw)
    return tuple(Route(i, _f32(w / den)) for i, w in zip(ids, raw, strict=True))


def dispatch_plan(token_logits: Sequence[Sequence[float]], k: int) -> dict[int, list[tuple[int, float]]]:
    out: dict[int, list[tuple[int, float]]] = {}
    for token, logits in enumerate(token_logits):
        for route in route_topk(logits, k):
            out.setdefault(route.expert_id, []).append((token, route.weight))
    return out


def expert_batches(token_logits: Sequence[Sequence[float]], k: int, max_batch_tokens: int) -> tuple[tuple[int, tuple[tuple[int, float], ...]], ...]:
    if max_batch_tokens <= 0:
        raise ValueError('max_batch_tokens')
    out = []
    for expert, items in sorted(dispatch_plan(token_logits, k).items()):
        for offset in range(0, len(items), max_batch_tokens):
            out.append((expert, tuple(items[offset : offset + max_batch_tokens])))
    return tuple(out)


@dataclass(frozen=True)
class ExpertWeights:
    gate: tuple[tuple[float, ...], ...]
    up: tuple[tuple[float, ...], ...]
    down: tuple[tuple[float, ...], ...]

    @classmethod
    def random(cls, rng: random.Random, hidden: int, intermediate: int, scale: float = 0.20) -> 'ExpertWeights':
        def matrix(rows: int, cols: int) -> tuple[tuple[float, ...], ...]:
            return tuple(tuple(_f32(rng.uniform(-scale, scale)) for _ in range(cols)) for _ in range(rows))
        return cls(matrix(intermediate, hidden), matrix(intermediate, hidden), matrix(hidden, intermediate))

    @property
    def hidden(self) -> int:
        return len(self.down)

    def execute(self, hidden: Sequence[float]) -> tuple[float, ...]:
        gate = _matvec(self.gate, hidden)
        up = _matvec(self.up, hidden)
        product = tuple(_f32(_silu(g) * u) for g, u in zip(gate, up, strict=True))
        return _matvec(self.down, product)


@dataclass(frozen=True)
class MoeExecution:
    output: tuple[float, ...]
    routes: tuple[Route, ...]
    routed_output: tuple[float, ...]
    shared_output: tuple[float, ...]
    shared_gate: float


def execute_moe(
    hidden: Sequence[float],
    *,
    router: Sequence[Sequence[float]],
    experts: Sequence[ExpertWeights],
    top_k: int,
    shared_expert: ExpertWeights,
    shared_gate: Sequence[float],
) -> MoeExecution:
    if len(router) != len(experts):
        raise ValueError('router/expert count')
    if len(shared_gate) != len(hidden):
        raise ValueError('shared gate width')
    logits = _matvec(router, hidden)
    routes = route_topk(logits, top_k)
    routed = [0.0] * len(hidden)
    for route in routes:
        value = experts[route.expert_id].execute(hidden)
        for index, item in enumerate(value):
            routed[index] = _f32(routed[index] + _f32(item * route.weight))
    shared_raw = shared_expert.execute(hidden)
    shared_gain = _sigmoid(_dot(shared_gate, hidden))
    shared = tuple(_f32(x * shared_gain) for x in shared_raw)
    output = tuple(_f32(a + b) for a, b in zip(routed, shared, strict=True))
    return MoeExecution(output, routes, tuple(routed), shared, shared_gain)
