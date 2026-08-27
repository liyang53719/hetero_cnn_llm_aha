"""QSA indexer and sparse-attention stateful E0 layer."""
from __future__ import annotations

from dataclasses import dataclass, field
import math
import random
from typing import Sequence

from .gated_deltanet import f32, l2norm, sigmoid
from .hierarchical_attention import Summary, normalized, summarize
from .qwen38_math import (
    Matrix, TinyQwen38Config, Vector, _check_width, _matrix, dot, matvec, rmsnorm, rope,
)

@dataclass
class QSAState:
    raw_index_keys: list[Vector] = field(default_factory=list)
    keys: list[tuple[Vector, ...]] = field(default_factory=list)
    values: list[tuple[Vector, ...]] = field(default_factory=list)

    def copy(self) -> "QSAState":
        return QSAState(list(self.raw_index_keys), list(self.keys), list(self.values))


@dataclass(frozen=True)
class QSAResult:
    output: Vector
    selected_tokens: tuple[int, ...]
    summary: tuple[Summary, ...]


@dataclass
class QSAWeights:
    config: TinyQwen38Config
    index_qk: Matrix
    q_gate: Matrix
    k: Matrix
    v: Matrix
    out: Matrix

    @classmethod
    def random(cls, rng: random.Random, config: TinyQwen38Config) -> "QSAWeights":
        index_width = (config.qsa_index_q_heads + 1) * config.qsa_index_head_dim
        return cls(
            config,
            _matrix(rng, index_width, config.hidden_size),
            _matrix(rng, config.q_heads * config.head_dim * 2, config.hidden_size),
            _matrix(rng, config.kv_heads * config.head_dim, config.hidden_size),
            _matrix(rng, config.kv_heads * config.head_dim, config.hidden_size),
            _matrix(rng, config.hidden_size, config.q_heads * config.head_dim),
        )

    def _select(self, index_queries: tuple[Vector, ...], raw_keys: Sequence[Vector], position: int) -> tuple[int, ...]:
        cfg = self.config
        visible = tuple(range(position + 1))
        complete = len(visible) // cfg.qsa_compress_ratio
        block_topk = cfg.qsa_token_budget // cfg.qsa_compress_ratio
        scored: list[tuple[float, int]] = []
        query_rope = tuple(rope(l2norm(q), position, min(cfg.rotary_dim, len(q))) for q in index_queries)
        for block in range(complete):
            ids = visible[block * cfg.qsa_compress_ratio : (block + 1) * cfg.qsa_compress_ratio]
            pooled = tuple(f32(sum(raw_keys[idx][dim] for idx in ids) / cfg.qsa_compress_ratio) for dim in range(cfg.qsa_index_head_dim))
            pooled = rope(l2norm(pooled), ids[0], min(cfg.rotary_dim, len(pooled)))
            score = 0.0
            for query in query_rope:
                score = f32(score + max(0.0, dot(query, pooled)))
            scored.append((f32(score / math.sqrt(cfg.qsa_index_head_dim)), block))
        chosen = [block for _, block in sorted(scored, key=lambda item: (-item[0], item[1]))[: min(block_topk, complete)]]
        selected: list[int] = []
        for block in chosen:
            selected.extend(visible[block * cfg.qsa_compress_ratio : (block + 1) * cfg.qsa_compress_ratio])
        selected.extend(visible[complete * cfg.qsa_compress_ratio :])
        return tuple(selected)

    def step(self, hidden: Sequence[float], position: int, state: QSAState) -> tuple[QSAResult, QSAState]:
        cfg = self.config
        _check_width(hidden, cfg.hidden_size, "QSA hidden")
        state = state.copy()
        index = matvec(self.index_qk, hidden)
        qidx_width = cfg.qsa_index_q_heads * cfg.qsa_index_head_dim
        index_queries = tuple(tuple(index[h * cfg.qsa_index_head_dim : (h + 1) * cfg.qsa_index_head_dim]) for h in range(cfg.qsa_index_q_heads))
        raw_key = tuple(index[qidx_width : qidx_width + cfg.qsa_index_head_dim])
        state.raw_index_keys.append(raw_key)
        selected = self._select(index_queries, state.raw_index_keys, position)

        packed = matvec(self.q_gate, hidden)
        queries: list[Vector] = []
        gates: list[Vector] = []
        for head in range(cfg.q_heads):
            base = head * 2 * cfg.head_dim
            queries.append(rope(rmsnorm(packed[base : base + cfg.head_dim]), position, cfg.rotary_dim))
            gates.append(tuple(packed[base + cfg.head_dim : base + 2 * cfg.head_dim]))
        key_flat = matvec(self.k, hidden)
        value_flat = matvec(self.v, hidden)
        keys = tuple(rope(rmsnorm(key_flat[h * cfg.head_dim : (h + 1) * cfg.head_dim]), position, cfg.rotary_dim) for h in range(cfg.kv_heads))
        values = tuple(tuple(value_flat[h * cfg.head_dim : (h + 1) * cfg.head_dim]) for h in range(cfg.kv_heads))
        state.keys.append(keys)
        state.values.append(values)

        groups = cfg.q_heads // cfg.kv_heads
        outputs: list[float] = []
        summaries: list[Summary] = []
        inv_scale = f32(1.0 / math.sqrt(cfg.head_dim))
        for qh, query in enumerate(queries):
            kvh = qh // groups
            scores = [f32(dot(query, state.keys[token][kvh]) * inv_scale) for token in selected]
            vals = [state.values[token][kvh] for token in selected]
            summary = summarize(scores, vals, rtl=True)
            summaries.append(summary)
            head_out = normalized(summary)
            outputs.extend(f32(x * sigmoid(g)) for x, g in zip(head_out, gates[qh], strict=True))
        return QSAResult(matvec(self.out, outputs), selected, tuple(summaries)), state
