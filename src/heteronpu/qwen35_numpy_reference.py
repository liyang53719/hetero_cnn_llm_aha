"""Independent float64 mathematical audit of pinned 0.8B attention layer 3.

No torch/Transformers import and no copied forward dispatch. This deliberately
does not emulate every BF16 producer or define an RTL acceptance comparator.
"""
from __future__ import annotations

import numpy as np


def synthetic_input(position_start: int = 0) -> np.ndarray:
    """Explicitly synthetic hidden state, never an official upstream activation."""
    i = (np.arange(128 * 1024, dtype=np.int64) + position_start * 1024).reshape(1, 128, 1024)
    return (((73 * i + 19) % 1021 - 510) / 512).astype(np.float32)


def decode_bf16(raw: bytes, shape: list[int]) -> np.ndarray:
    bits = np.frombuffer(raw, dtype="<u2").astype(np.uint32) << 16
    return bits.view(np.float32).reshape(shape)


def forward(x, weights, past=None, *, position_start=0):
    """FP64 math reference with dense causal GQA, partial RoPE and Q gate."""
    x = np.asarray(x, dtype=np.float64)
    w = {k: np.asarray(v, dtype=np.float64) for k, v in weights.items()}

    def norm(y, name):
        return y / np.sqrt(np.mean(y * y, axis=-1, keepdims=True) + 1e-6) * (1 + w[name])

    def linear(y, name):
        return y @ w[name].T

    n = norm(x, "input_layernorm.weight")
    packed = linear(n, "self_attn.q_proj.weight").reshape(1, 128, 8, 512)
    q, gate = packed[..., :256], packed[..., 256:]
    q = norm(q, "self_attn.q_norm.weight").transpose(0, 2, 1, 3)
    k = norm(linear(n, "self_attn.k_proj.weight").reshape(1, 128, 2, 256),
             "self_attn.k_norm.weight").transpose(0, 2, 1, 3)
    v = linear(n, "self_attn.v_proj.weight").reshape(1, 128, 2, 256).transpose(0, 2, 1, 3)
    # Text-only three axes are identical. The official interleaved composition
    # is therefore this ordinary 64-wide partial RoPE for this synthetic case.
    freq = np.arange(position_start, position_start + 128)[:, None] / (10000000.0 ** (np.arange(0, 64, 2) / 64))
    c = np.tile(np.cos(freq), (1, 2))[None, None]
    s = np.tile(np.sin(freq), (1, 2))[None, None]

    def rope(y):
        a = y[..., :64]
        rotated = np.concatenate((-a[..., 32:], a[..., :32]), axis=-1)
        return np.concatenate((a * c + rotated * s, y[..., 64:]), axis=-1)

    q, k = rope(q), rope(k)
    past_length = 0 if past is None else past[0].shape[2]
    if past is not None:
        k, v = np.concatenate((past[0], k), axis=2), np.concatenate((past[1], v), axis=2)
    logits = q @ np.repeat(k, 4, axis=1).swapaxes(-1, -2) / 16
    allowed = np.arange(k.shape[2])[None, :] <= (np.arange(128)[:, None] + past_length)
    logits = np.where(allowed[None, None], logits, -np.inf)
    exp = np.exp(logits - logits.max(axis=-1, keepdims=True))
    probability = exp / exp.sum(axis=-1, keepdims=True)
    attention = (probability @ np.repeat(v, 4, axis=1)).transpose(0, 2, 1, 3)
    gated = attention * (1 / (1 + np.exp(-gate)))
    residual = x + linear(gated.reshape(1, 128, 2048), "self_attn.o_proj.weight")
    n = norm(residual, "post_attention_layernorm.weight")
    gate = linear(n, "mlp.gate_proj.weight")
    mlp = gate / (1 + np.exp(-gate)) * linear(n, "mlp.up_proj.weight")
    output = residual + linear(mlp, "mlp.down_proj.weight")
    return output, (k, v)


def compare(actual, reference, *, atol=1e-4, rtol=1e-4):
    """Every-element smoke comparator, frozen before the first numerical run."""
    actual, reference = np.asarray(actual, dtype=np.float64), np.asarray(reference, dtype=np.float64)
    if actual.shape != reference.shape:
        raise ValueError("comparison shape mismatch")
    if not np.isfinite(actual).all() or not np.isfinite(reference).all():
        raise ValueError("comparison rejects nonfinite values")
    error = np.abs(actual - reference)
    tolerance = atol + rtol * np.abs(reference)
    return {"elements": actual.size, "atol": atol, "rtol": rtol,
            "mismatches": int(np.count_nonzero(error > tolerance)),
            "max_abs_error": float(error.max()),
            "rmse": float(np.sqrt(np.mean(error ** 2))),
            "max_tolerance_ratio": float((error / tolerance).max())}
