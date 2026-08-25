from __future__ import annotations

import math
from typing import Literal

import numpy as np

from .dtypes import bf16_round


class CgraSfuModel:
    """Functional semantics for the programmable CGRA/SFU island."""

    @staticmethod
    def relu(x: np.ndarray) -> np.ndarray:
        return np.maximum(np.asarray(x), 0)

    @staticmethod
    def silu(x: np.ndarray) -> np.ndarray:
        a = np.asarray(x, dtype=np.float32)
        return a / (np.float32(1.0) + np.exp(-a, dtype=np.float32))

    @staticmethod
    def gelu(x: np.ndarray) -> np.ndarray:
        a = np.asarray(x, dtype=np.float32)
        coeff = np.float32(math.sqrt(2.0 / math.pi))
        return np.float32(0.5) * a * (
            np.float32(1.0) + np.tanh(coeff * (a + np.float32(0.044715) * a**3))
        )

    @staticmethod
    def rmsnorm(
        x: np.ndarray,
        weight: np.ndarray,
        eps: float = 1e-6,
        *,
        input_bf16: bool = True,
        output_bf16: bool = True,
    ) -> np.ndarray:
        a = np.asarray(x, dtype=np.float32)
        if input_bf16:
            a = bf16_round(a)
        w = bf16_round(np.asarray(weight, dtype=np.float32)) if input_bf16 else np.asarray(weight, dtype=np.float32)
        mean_square = np.mean(a * a, axis=-1, keepdims=True, dtype=np.float32)
        y = a * (np.float32(1.0) / np.sqrt(mean_square + np.float32(eps), dtype=np.float32)) * w
        return bf16_round(y) if output_bf16 else y.astype(np.float32)

    @staticmethod
    def layernorm(
        x: np.ndarray,
        weight: np.ndarray,
        bias: np.ndarray,
        eps: float = 1e-5,
    ) -> np.ndarray:
        a = np.asarray(x, dtype=np.float32)
        mean = np.mean(a, axis=-1, keepdims=True, dtype=np.float32)
        var = np.mean((a - mean) ** 2, axis=-1, keepdims=True, dtype=np.float32)
        return (a - mean) / np.sqrt(var + np.float32(eps), dtype=np.float32) * weight + bias

    @staticmethod
    def softmax(x: np.ndarray, axis: int = -1) -> np.ndarray:
        a = np.asarray(x, dtype=np.float32)
        maximum = np.max(a, axis=axis, keepdims=True)
        e = np.exp(a - maximum, dtype=np.float32)
        return e / np.sum(e, axis=axis, keepdims=True, dtype=np.float32)

    @staticmethod
    def online_softmax_1d(x: np.ndarray, block: int = 16) -> np.ndarray:
        """Two-pass blockwise online-softmax equivalent used by the SFU plan."""

        a = np.asarray(x, dtype=np.float32).reshape(-1)
        if block <= 0:
            raise ValueError("block size must be positive")
        running_m = np.float32(-np.inf)
        running_l = np.float32(0.0)
        for start in range(0, a.size, block):
            chunk = a[start : start + block]
            cm = np.max(chunk)
            new_m = np.maximum(running_m, cm)
            running_l = running_l * np.exp(running_m - new_m, dtype=np.float32)
            running_l += np.sum(np.exp(chunk - new_m, dtype=np.float32), dtype=np.float32)
            running_m = np.float32(new_m)
        return np.exp(a - running_m, dtype=np.float32) / running_l

    @staticmethod
    def rope(
        x: np.ndarray,
        positions: np.ndarray | None = None,
        theta: float = 10000.0,
    ) -> np.ndarray:
        """Interleaved pairwise RoPE for shape [..., head_dim]."""

        a = np.asarray(x, dtype=np.float32)
        d = a.shape[-1]
        if d % 2:
            raise ValueError("RoPE head dimension must be even")
        tokens = a.shape[0]
        pos = np.arange(tokens, dtype=np.float32) if positions is None else np.asarray(positions, dtype=np.float32)
        inv_freq = np.float32(1.0) / (
            np.float32(theta) ** (np.arange(0, d, 2, dtype=np.float32) / np.float32(d))
        )
        angles = pos[:, None] * inv_freq[None, :]
        shape = (tokens,) + (1,) * (a.ndim - 2) + (d // 2,)
        c = np.cos(angles, dtype=np.float32).reshape(shape)
        s = np.sin(angles, dtype=np.float32).reshape(shape)
        even = a[..., 0::2]
        odd = a[..., 1::2]
        out = np.empty_like(a, dtype=np.float32)
        out[..., 0::2] = even * c - odd * s
        out[..., 1::2] = even * s + odd * c
        return bf16_round(out)

    @staticmethod
    def pool2d_nhwc(
        x: np.ndarray,
        kernel: tuple[int, int] = (2, 2),
        stride: tuple[int, int] = (2, 2),
        mode: Literal["max", "avg"] = "max",
    ) -> np.ndarray:
        a = np.asarray(x)
        if a.ndim != 4:
            raise ValueError("pool input must be NHWC")
        n, h, w, c = a.shape
        kh, kw = kernel
        sh, sw = stride
        oh = (h - kh) // sh + 1
        ow = (w - kw) // sw + 1
        out = np.empty((n, oh, ow, c), dtype=a.dtype if mode == "max" else np.float32)
        for b in range(n):
            for y in range(oh):
                for x_pos in range(ow):
                    window = a[b, y * sh : y * sh + kh, x_pos * sw : x_pos * sw + kw]
                    if mode == "max":
                        out[b, y, x_pos] = np.max(window, axis=(0, 1))
                    elif mode == "avg":
                        out[b, y, x_pos] = np.mean(window, axis=(0, 1), dtype=np.float32)
                    else:
                        raise ValueError(f"unsupported pool mode: {mode}")
        return out
