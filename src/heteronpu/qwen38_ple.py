"""Gated residual and PLE stateful E0 layers."""
from __future__ import annotations

from dataclasses import dataclass, field
import math
import random
from typing import Sequence

from .gated_deltanet import f32, sigmoid, silu
from .qwen38_ops import DilatedConvState, dilated_conv_step, multipliers, ngram_indices
from .qwen38_math import (
    Matrix, TinyQwen38Config, Vector, _check_width, _fvec, _matrix, _vector,
    add, dot, group_rmsnorm, matvec,
)

@dataclass
class GatedResidualWeights:
    branches: int
    hidden: int
    lowrank: int
    down: Matrix
    up: Matrix
    inject: Matrix

    @classmethod
    def random(cls, rng: random.Random, branches: int, hidden: int, lowrank: int) -> "GatedResidualWeights":
        width = branches * hidden
        return cls(branches, hidden, lowrank, _matrix(rng, lowrank, width), _matrix(rng, width, lowrank), _matrix(rng, branches, width))

    def read(self, hyper: Sequence[float]) -> tuple[Vector, Vector]:
        _check_width(hyper, self.branches * self.hidden, "gated residual input")
        normed = group_rmsnorm(hyper, self.branches, self.hidden)
        low = tuple(silu(f32(x / self.branches)) for x in matvec(self.down, normed))
        read_weights = tuple(sigmoid(x) for x in matvec(self.up, low))
        mixed: list[float] = []
        for dim in range(self.hidden):
            acc = 0.0
            for branch in range(self.branches):
                idx = branch * self.hidden + dim
                acc = f32(acc + f32(read_weights[idx] * normed[idx]))
            mixed.append(f32(acc / self.branches))
        inject_weights = tuple(f32(2.0 * sigmoid(f32(x / self.branches))) for x in matvec(self.inject, normed))
        return tuple(mixed), inject_weights

    def write(self, hyper: Sequence[float], block_output: Sequence[float], injection_weights: Sequence[float]) -> Vector:
        _check_width(hyper, self.branches * self.hidden, "gated residual write input")
        _check_width(block_output, self.hidden, "gated residual block")
        _check_width(injection_weights, self.branches, "gated residual injection")
        out = list(_fvec(hyper))
        for branch in range(self.branches):
            base = branch * self.hidden
            gain = f32(injection_weights[branch])
            for dim in range(self.hidden):
                out[base + dim] = f32(out[base + dim] + f32(block_output[dim] * gain))
        return tuple(out)


@dataclass
class PLEState:
    token_history: list[int]
    conv: DilatedConvState

    def copy(self) -> "PLEState":
        return PLEState(list(self.token_history), DilatedConvState(self.conv.channels, self.conv.kernel, self.conv.dilation, [list(x) for x in self.conv.history]))


@dataclass
class PLEWeights:
    config: TinyQwen38Config
    layer_index: int
    key_proj: Matrix
    value_proj: Matrix
    conv_weights: tuple[Vector, ...]
    head_vocab_sizes: tuple[int, ...]
    head_offsets: tuple[int, ...]
    hash_multipliers: tuple[int, ...]
    embedding_seed: int

    @classmethod
    def random(cls, rng: random.Random, config: TinyQwen38Config, layer_index: int) -> "PLEWeights":
        heads = (config.ple_ngram_size - 1) * config.ple_heads_per_ngram
        primes = (17, 19, 23, 29, 31, 37, 41, 43)
        if heads > len(primes):
            raise ValueError("tiny PLE prime table")
        sizes = primes[:heads]
        offsets: list[int] = []
        total = 0
        for size in sizes:
            offsets.append(total)
            total += size
        channels = config.branches * config.hidden_size
        return cls(
            config,
            layer_index,
            _matrix(rng, channels, config.ple_embed_dim),
            _matrix(rng, config.hidden_size, config.ple_embed_dim),
            tuple(_vector(rng, config.ple_conv_kernel) for _ in range(channels)),
            tuple(sizes),
            tuple(offsets),
            multipliers(config.vocab_size, config.ple_ngram_size, layer_index),
            rng.randrange(1 << 30),
        )

    def initial_state(self) -> PLEState:
        channels = self.config.branches * self.config.hidden_size
        return PLEState([], DilatedConvState.zeros(channels, self.config.ple_conv_kernel, self.config.ple_conv_dilation))

    def _embedding_row(self, row: int, width: int) -> Vector:
        rng = random.Random((self.embedding_seed << 32) ^ int(row))
        return tuple(f32(rng.uniform(-0.25, 0.25)) for _ in range(width))

    def step(self, hyper: Sequence[float], token_id: int, state: PLEState) -> tuple[Vector, PLEState, tuple[int, ...]]:
        cfg = self.config
        _check_width(hyper, cfg.branches * cfg.hidden_size, "PLE hyper")
        tokens = state.token_history + [int(token_id)]
        indices = ngram_indices(
            tokens,
            ngram_size=cfg.ple_ngram_size,
            heads_per_ngram=cfg.ple_heads_per_ngram,
            sizes=self.head_vocab_sizes,
            offsets=self.head_offsets,
            mults=self.hash_multipliers,
            sentinel=0,
        )[-1]
        head_count = len(indices)
        row_width = cfg.ple_embed_dim // head_count
        embedding: list[float] = []
        for row in indices:
            embedding.extend(self._embedding_row(row, row_width))
        key = matvec(self.key_proj, embedding)
        value = matvec(self.value_proj, embedding)
        key_normed = group_rmsnorm(key, cfg.branches, cfg.hidden_size)
        query_normed = group_rmsnorm(hyper, cfg.branches, cfg.hidden_size)
        gated: list[float] = []
        for branch in range(cfg.branches):
            start = branch * cfg.hidden_size
            raw = f32(dot(key_normed[start : start + cfg.hidden_size], query_normed[start : start + cfg.hidden_size]) / math.sqrt(cfg.hidden_size))
            transformed = f32(math.copysign(math.sqrt(max(abs(raw), 1e-6)), raw))
            gain = sigmoid(transformed)
            gated.extend(f32(gain * x) for x in value)
        gated_normed = group_rmsnorm(gated, cfg.branches, cfg.hidden_size)
        conv, new_conv = dilated_conv_step(gated_normed, self.conv_weights, state.conv)
        output = add(gated, conv)
        history = tokens[-(cfg.ple_ngram_size - 1) :]
        return output, PLEState(history, new_conv), tuple(indices)
