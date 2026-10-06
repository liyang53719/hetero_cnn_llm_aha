"""Independent FP64 mathematical audit of pinned Qwen3.5-0.8B GDN layer 0.

This module imports neither torch nor Transformers. It uses a token-by-token
rank-one delta update, independently of the upstream multi-token chunk solver.
The default geometry comes from config/upstream/qwen3_5_0p8b/config.json;
weights use decoder-local state_dict names (``linear_attn.*``, ``mlp.*``).

The caller must decode each payload with its original storage dtype before
calling this module. In particular, do not reinterpret FP32 A_log/norm.weight as
BF16. All decoded values are promoted directly to FP64 here. Upstream performs
Q/K L2 normalization, decay and recurrent accumulation in FP32, even in a BF16
run, and returns core attention in the query dtype. This mathematical reference
deliberately does not simulate those rounding boundaries or certify BF16/RTL
producer precision. Its returned recurrent state is FP64, not a claim that the
model's configured mamba_ssm_dtype is anything other than float32.

Only unmasked, nonempty, batch-one decoder inputs are supported. Sequence length
is variable to test partition equivalence; the payload audit uses M=128. No
position IDs/RoPE, attention KV cache, MoE, or full-model execution is involved.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields

import numpy as np


@dataclass(frozen=True)
class GDNConfig:
    """Pinned geometry by default; overrides permit small mathematical tests."""

    hidden_size: int = 1024
    intermediate_size: int = 3584
    linear_num_key_heads: int = 16
    linear_num_value_heads: int = 16
    linear_key_head_dim: int = 128
    linear_value_head_dim: int = 128
    linear_conv_kernel_dim: int = 4
    rms_norm_eps: float = 1e-6

    def __post_init__(self):
        for name in (field.name for field in fields(self) if field.name != "rms_norm_eps"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if self.linear_num_value_heads % self.linear_num_key_heads:
            raise ValueError("value-head count must be a multiple of key-head count")
        _check_epsilon(self.rms_norm_eps)

    @property
    def key_width(self):
        return self.linear_num_key_heads * self.linear_key_head_dim

    @property
    def value_width(self):
        return self.linear_num_value_heads * self.linear_value_head_dim

    @property
    def conv_channels(self):
        return 2 * self.key_width + self.value_width


def _check_epsilon(epsilon):
    if isinstance(epsilon, bool) or not np.isscalar(epsilon) or not np.isfinite(epsilon) or epsilon <= 0:
        raise ValueError("epsilon must be finite and positive")


def _config(config):
    if config is None:
        return GDNConfig()
    if isinstance(config, GDNConfig):
        return config
    if not isinstance(config, Mapping):
        raise ValueError("config must be GDNConfig or a config mapping")
    config = config.get("text_config", config)
    if not isinstance(config, Mapping):
        raise ValueError("text_config must be a mapping")
    if config.get("hidden_act", "silu") != "silu":
        raise ValueError("only the pinned silu activation is supported")
    if config.get("mamba_ssm_dtype", "float32") != "float32":
        raise ValueError("the pinned recurrent state contract is float32")
    return GDNConfig(**{field.name: config[field.name] for field in fields(GDNConfig) if field.name in config})


def _array(value, name, shape=None):
    raw = np.asarray(value)
    if raw.dtype.kind not in "fiu":
        raise ValueError(f"{name} must contain real numeric values")
    array = np.asarray(raw, dtype=np.float64)
    if shape is not None and array.shape != shape:
        raise ValueError(f"{name} shape {array.shape} != {shape}")
    if not np.isfinite(array).all():
        raise ValueError(f"{name} contains nonfinite values")
    return array


def _sigmoid(value):
    return np.exp(-np.logaddexp(0.0, -value))


def _silu(value):
    return value * _sigmoid(value)


def l2_normalize(value, *, eps=1e-6):
    """Official epsilon placement: x / sqrt(sum(x*x) + eps), not max(norm, eps)."""
    _check_epsilon(eps)
    value = _array(value, "L2 input")
    if value.ndim == 0 or value.shape[-1] == 0:
        raise ValueError("L2 input needs a nonempty final dimension")
    return _array(value / np.sqrt(np.sum(value * value, axis=-1, keepdims=True) + eps), "L2 output")


def causal_conv1d(projected, weight, past=None):
    """Depthwise causal cross-correlation plus SiLU, with raw-input cache.

    projected: [B, channels, tokens]; weight: [channels, 1, K] or [channels, K].
    past/returned state: [B, channels, K], chronological oldest-to-newest.
    The oldest cached column is retained for upstream-compatible state shape,
    but cannot affect the next output of a K-tap causal convolution.

    Pinned LinearAttentionLayer.update_conv_state prepends all K cached columns
    for carried multi-token calls; the model convolves that stream and selects
    its final M outputs. The windows below give precisely those samples. This
    also matches the single-token update and cold left-zero-padding paths.
    Neither past nor projected is modified.
    """
    projected = _array(projected, "projected QKV")
    if projected.ndim != 3 or any(size <= 0 for size in projected.shape):
        raise ValueError("projected QKV must have nonempty [batch, channels, tokens] shape")
    batch, channels, tokens = projected.shape
    weight = _array(weight, "conv weight")
    if weight.ndim == 3 and weight.shape[1] == 1:
        weight = weight[:, 0, :]
    if weight.ndim != 2 or weight.shape[0] != channels or weight.shape[1] <= 0:
        raise ValueError("conv weight must have shape [channels, 1, K] or [channels, K]")
    kernel = weight.shape[1]
    state_shape = (batch, channels, kernel)
    history = np.zeros(state_shape, dtype=np.float64) if past is None else _array(past, "conv state", state_shape)
    stream = np.concatenate((history, projected), axis=-1)
    output = np.empty_like(projected)
    # The window ending at stream[..., K+t] starts at t+1; no kernel reversal.
    for token in range(tokens):
        output[..., token] = np.sum(stream[..., token + 1:token + kernel + 1] * weight, axis=-1)
    return _array(_silu(output), "conv output"), stream[..., -kernel:].copy()


def recurrent_gated_delta_rule(query, key, value, g, beta, initial_state=None, *, normalize_qk=True):
    """Sequential delta-rule math returning (core_output, final_state), in FP64.

    Q/K: [B,T,Hk,Dk], V: [B,T,Hv,Dv], g/beta: [B,T,Hv]. Each key head is
    repeated Hv/Hk times when needed. g is log decay (<=0), beta lies in [0,1].
    State: [B,Hv,Dk,Dv]. Queries additionally receive the official 1/sqrt(Dk).

    For each token: D = exp(g)*S; e = beta*(v-k^T D);
    S = D + k e^T; output = (q/sqrt(Dk))^T S.
    This is the actual gated delta rule, including decay before prediction and
    the subtractive correction; it is not ordinary linear attention.
    """
    query, key, value = (_array(x, name) for x, name in ((query, "query"), (key, "key"), (value, "value")))
    if query.ndim != 4 or any(size <= 0 for size in query.shape) or key.shape != query.shape:
        raise ValueError("query and key must share nonempty [batch, tokens, heads, key_dim] shape")
    batch, tokens, key_heads, key_dim = query.shape
    if value.ndim != 4 or value.shape[:2] != (batch, tokens) or value.shape[2] <= 0 or value.shape[3] <= 0:
        raise ValueError("value must have nonempty [batch, tokens, value_heads, value_dim] shape")
    value_heads, value_dim = value.shape[2:]
    if value_heads % key_heads:
        raise ValueError("value-head count must be a multiple of key-head count")
    g = _array(g, "log decay", (batch, tokens, value_heads))
    beta = _array(beta, "beta", (batch, tokens, value_heads))
    if np.any(g > 0):
        raise ValueError("log decay must be <= 0")
    if np.any((beta < 0) | (beta > 1)):
        raise ValueError("beta must lie in [0, 1]")
    if not isinstance(normalize_qk, (bool, np.bool_)):
        raise ValueError("normalize_qk must be boolean")
    if normalize_qk:
        query, key = l2_normalize(query), l2_normalize(key)
    repeats = value_heads // key_heads
    query = np.repeat(query, repeats, axis=2) / np.sqrt(key_dim)
    key = np.repeat(key, repeats, axis=2)
    state_shape = (batch, value_heads, key_dim, value_dim)
    state = np.zeros(state_shape, dtype=np.float64) if initial_state is None else _array(initial_state, "recurrent state", state_shape).copy()
    output = np.empty_like(value)
    for token in range(tokens):
        state *= np.exp(g[:, token, :, None, None])
        k = key[:, token]
        prediction = np.einsum("bhk,bhkv->bhv", k, state)
        correction = beta[:, token, :, None] * (value[:, token] - prediction)
        state += k[..., None] * correction[..., None, :]
        output[:, token] = np.einsum("bhk,bhkv->bhv", query[:, token], state)
    return _array(output, "core attention output"), _array(state, "final recurrent state")


def forward(x, weights, past=None, *, config=None, return_stages=False):
    """Full GDN + dense SwiGLU decoder; return (output, (conv, recurrent)).

    x: [1,M,hidden_size]. weights: mapping of decoded arrays, using local
    decoder tensor names. past=None initializes both states to zero. Pass the
    returned pair from the same independent run for carried-state calls; using
    official states instead would no longer be an independent carried audit.

    config may be GDNConfig, the upstream text_config mapping, or the complete
    upstream config. return_stages=True adds a third return value containing
    named FP64 producer arrays for diagnostics. Inputs/weights/state are never
    mutated. There are no stochastic operators or hidden global state.
    """
    cfg = _config(config)
    x = _array(x, "hidden states")
    if x.ndim != 3 or x.shape[0] != 1 or x.shape[1] <= 0 or x.shape[2] != cfg.hidden_size:
        raise ValueError(f"hidden states must have shape [1, M>0, {cfg.hidden_size}]")
    if not isinstance(weights, Mapping):
        raise ValueError("weights must be a mapping")
    shapes = {
        "input_layernorm.weight": (cfg.hidden_size,),
        "post_attention_layernorm.weight": (cfg.hidden_size,),
        "linear_attn.in_proj_qkv.weight": (cfg.conv_channels, cfg.hidden_size),
        "linear_attn.in_proj_z.weight": (cfg.value_width, cfg.hidden_size),
        "linear_attn.in_proj_b.weight": (cfg.linear_num_value_heads, cfg.hidden_size),
        "linear_attn.in_proj_a.weight": (cfg.linear_num_value_heads, cfg.hidden_size),
        "linear_attn.conv1d.weight": (cfg.conv_channels, 1, cfg.linear_conv_kernel_dim),
        "linear_attn.A_log": (cfg.linear_num_value_heads,),
        "linear_attn.dt_bias": (cfg.linear_num_value_heads,),
        "linear_attn.norm.weight": (cfg.linear_value_head_dim,),
        "linear_attn.out_proj.weight": (cfg.hidden_size, cfg.value_width),
        "mlp.gate_proj.weight": (cfg.intermediate_size, cfg.hidden_size),
        "mlp.up_proj.weight": (cfg.intermediate_size, cfg.hidden_size),
        "mlp.down_proj.weight": (cfg.hidden_size, cfg.intermediate_size),
    }
    missing = shapes.keys() - weights.keys()
    if missing:
        raise ValueError(f"missing weights: {', '.join(sorted(missing))}")
    w = {name: _array(weights[name], name, shape) for name, shape in shapes.items()}
    if past is not None and (not isinstance(past, (tuple, list)) or len(past) != 2 or any(s is None for s in past)):
        raise ValueError("past must contain both conv and recurrent states, or be None")
    conv_past, recurrent_past = (None, None) if past is None else past
    stages = {}

    def stage(name, array):
        array = _array(array, name)
        if return_stages:
            stages[name] = array
        return array

    def norm(array, name, zero_centered=True):
        multiplier = 1.0 + w[name] if zero_centered else w[name]
        return array / np.sqrt(np.mean(array * array, axis=-1, keepdims=True) + cfg.rms_norm_eps) * multiplier

    def linear(array, name):
        return array @ w[name].T

    normalized = stage("input_norm", norm(x, "input_layernorm.weight"))
    projected = stage("qkv_projection", linear(normalized, "linear_attn.in_proj_qkv.weight"))
    batch, tokens, _ = x.shape
    z = stage("z_projection", linear(normalized, "linear_attn.in_proj_z.weight").reshape(batch, tokens, cfg.linear_num_value_heads, cfg.linear_value_head_dim))
    a = stage("a_projection", linear(normalized, "linear_attn.in_proj_a.weight"))
    b = stage("b_projection", linear(normalized, "linear_attn.in_proj_b.weight"))
    convolved, conv_state = causal_conv1d(projected.transpose(0, 2, 1), w["linear_attn.conv1d.weight"], conv_past)
    convolved = stage("conv_output", convolved.transpose(0, 2, 1))
    query = stage("query", convolved[..., :cfg.key_width].reshape(batch, tokens, cfg.linear_num_key_heads, cfg.linear_key_head_dim))
    key = stage("key", convolved[..., cfg.key_width:2 * cfg.key_width].reshape(query.shape))
    value = stage("value", convolved[..., 2 * cfg.key_width:].reshape(batch, tokens, cfg.linear_num_value_heads, cfg.linear_value_head_dim))
    beta = stage("beta", _sigmoid(b))
    with np.errstate(over="ignore", invalid="ignore"):
        g = stage("g", -np.exp(w["linear_attn.A_log"]) * np.logaddexp(0.0, a + w["linear_attn.dt_bias"]))
    core, recurrent_state = recurrent_gated_delta_rule(query, key, value, g, beta, recurrent_past)
    core = stage("core_attn_out", core)
    gated = stage("gated_norm", norm(core, "linear_attn.norm.weight", zero_centered=False) * _silu(z))
    attention = stage("attention_output", linear(gated.reshape(batch, tokens, cfg.value_width), "linear_attn.out_proj.weight"))
    residual = stage("post_attention_residual", x + attention)
    normalized = stage("post_attention_norm", norm(residual, "post_attention_layernorm.weight"))
    gate = stage("ffn_gate", linear(normalized, "mlp.gate_proj.weight"))
    up = stage("ffn_up", linear(normalized, "mlp.up_proj.weight"))
    product = stage("ffn_product", _silu(gate) * up)
    mlp = stage("ffn_output", linear(product, "mlp.down_proj.weight"))
    output = stage("output", residual + mlp)
    result = (output, (conv_state, recurrent_state))
    return (*result, stages) if return_stages else result
