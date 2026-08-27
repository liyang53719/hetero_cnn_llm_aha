"""Gated DeltaNet stateful E0 layer."""
from __future__ import annotations

from dataclasses import dataclass, field
import math
import random
from typing import Sequence

from .gated_deltanet import (
    ConvState, Geometry, State as DeltaState, causal_conv_step, f32,
    step as delta_step,
)
from .qwen38_math import Matrix, TinyQwen38Config, Vector, _check_width, _matrix, _vector, matvec

@dataclass
class GDNState:
    recurrent: DeltaState
    conv: ConvState

    def copy(self) -> "GDNState":
        return GDNState(self.recurrent.copy(), ConvState(self.conv.channels, self.conv.kernel, [list(x) for x in self.conv.history]))


@dataclass
class GDNWeights:
    config: TinyQwen38Config
    qkv: Matrix
    z: Matrix
    b: Matrix
    a: Matrix
    out: Matrix
    conv: tuple[Vector, ...]
    a_log: Vector
    dt_bias: Vector
    norm_weight: Vector

    @classmethod
    def random(cls, rng: random.Random, config: TinyQwen38Config) -> "GDNWeights":
        q_width = config.gdn_qk_heads * config.gdn_key_dim
        v_width = config.gdn_v_heads * config.gdn_value_dim
        conv_dim = 2 * q_width + v_width
        return cls(
            config,
            _matrix(rng, conv_dim, config.hidden_size),
            _matrix(rng, v_width, config.hidden_size),
            _matrix(rng, config.gdn_v_heads, config.hidden_size),
            _matrix(rng, config.gdn_v_heads, config.hidden_size),
            _matrix(rng, config.hidden_size, v_width),
            tuple(_vector(rng, config.gdn_conv_kernel) for _ in range(conv_dim)),
            tuple(f32(math.log(rng.uniform(0.05, 1.5))) for _ in range(config.gdn_v_heads)),
            _vector(rng, config.gdn_v_heads),
            tuple(f32(1.0 + rng.uniform(-0.05, 0.05)) for _ in range(config.gdn_value_dim)),
        )

    def initial_state(self) -> GDNState:
        cfg = self.config
        geometry = Geometry(cfg.gdn_qk_heads, cfg.gdn_v_heads, cfg.gdn_key_dim, cfg.gdn_value_dim)
        conv_dim = 2 * cfg.gdn_qk_heads * cfg.gdn_key_dim + cfg.gdn_v_heads * cfg.gdn_value_dim
        return GDNState(DeltaState.zeros(geometry), ConvState.zeros(conv_dim, cfg.gdn_conv_kernel))

    def step(self, hidden: Sequence[float], state: GDNState) -> tuple[Vector, GDNState]:
        cfg = self.config
        _check_width(hidden, cfg.hidden_size, "GDN hidden")
        qkv = matvec(self.qkv, hidden)
        convolved, conv_state = causal_conv_step(qkv, self.conv, state.conv, activation="silu")
        q_width = cfg.gdn_qk_heads * cfg.gdn_key_dim
        v_width = cfg.gdn_v_heads * cfg.gdn_value_dim
        q_flat = convolved[:q_width]
        k_flat = convolved[q_width : 2 * q_width]
        v_flat = convolved[2 * q_width : 2 * q_width + v_width]
        query = tuple(tuple(q_flat[h * cfg.gdn_key_dim : (h + 1) * cfg.gdn_key_dim]) for h in range(cfg.gdn_qk_heads))
        key = tuple(tuple(k_flat[h * cfg.gdn_key_dim : (h + 1) * cfg.gdn_key_dim]) for h in range(cfg.gdn_qk_heads))
        value = tuple(tuple(v_flat[h * cfg.gdn_value_dim : (h + 1) * cfg.gdn_value_dim]) for h in range(cfg.gdn_v_heads))
        z_flat = matvec(self.z, hidden)
        z = tuple(tuple(z_flat[h * cfg.gdn_value_dim : (h + 1) * cfg.gdn_value_dim]) for h in range(cfg.gdn_v_heads))
        output_heads, recurrent = delta_step(
            geometry=state.recurrent.geometry,
            query=query,
            key=key,
            value=value,
            a=matvec(self.a, hidden),
            b=matvec(self.b, hidden),
            z=z,
            a_log=self.a_log,
            dt_bias=self.dt_bias,
            norm_weight=self.norm_weight,
            state=state.recurrent,
        )
        output = matvec(self.out, tuple(x for head in output_heads for x in head))
        return output, GDNState(recurrent, conv_state)
