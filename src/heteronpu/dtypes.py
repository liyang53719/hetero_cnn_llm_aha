from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import numpy as np


def bf16_round(values: np.ndarray | float) -> np.ndarray:
    """Round float32 values to BF16 using round-to-nearest-even.

    NumPy does not expose a portable bfloat16 dtype.  This function retains the
    values in float32 containers but clears the low 16 mantissa bits after RNE.
    """

    x = np.asarray(values, dtype=np.float32)
    bits = x.view(np.uint32).copy()
    lsb = (bits >> np.uint32(16)) & np.uint32(1)
    bits = bits + np.uint32(0x7FFF) + lsb
    bits &= np.uint32(0xFFFF0000)
    return bits.view(np.float32)


def quantize_int8_symmetric(
    values: np.ndarray,
    axis: int | tuple[int, ...] | None = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """Symmetric signed INT8 quantization with an explicit scale."""

    x = np.asarray(values, dtype=np.float32)
    max_abs = np.max(np.abs(x), axis=axis, keepdims=True)
    scale = max_abs / np.float32(127.0)
    scale = np.where(scale == 0, np.float32(1.0), scale).astype(np.float32)
    q = np.clip(np.rint(x / scale), -127, 127).astype(np.int8)
    return q, scale


def dequantize_int8(values: np.ndarray, scale: np.ndarray) -> np.ndarray:
    return np.asarray(values, dtype=np.float32) * np.asarray(scale, dtype=np.float32)


@dataclass(frozen=True)
class W4Tensor:
    q: np.ndarray
    scales: np.ndarray
    group_size: int
    original_shape: tuple[int, int]


def quantize_w4_grouped(weights: np.ndarray, group_size: int) -> W4Tensor:
    """Quantize a KxN weight matrix to signed INT4, grouped along K."""

    w = np.asarray(weights, dtype=np.float32)
    if w.ndim != 2:
        raise ValueError("W4 weights must be a KxN matrix")
    if group_size <= 0:
        raise ValueError("group_size must be positive")
    k, n = w.shape
    groups = (k + group_size - 1) // group_size
    padded_k = groups * group_size
    padded = np.zeros((padded_k, n), dtype=np.float32)
    padded[:k] = w
    reshaped = padded.reshape(groups, group_size, n)
    max_abs = np.max(np.abs(reshaped), axis=1, keepdims=True)
    scales = max_abs / np.float32(7.0)
    scales = np.where(scales == 0, np.float32(1.0), scales).astype(np.float32)
    q = np.clip(np.rint(reshaped / scales), -8, 7).astype(np.int8)
    return W4Tensor(
        q=q.reshape(padded_k, n),
        scales=scales[:, 0, :],
        group_size=group_size,
        original_shape=(k, n),
    )


def dequantize_w4_grouped(tensor: W4Tensor) -> np.ndarray:
    k, n = tensor.original_shape
    groups = tensor.q.shape[0] // tensor.group_size
    q = tensor.q.reshape(groups, tensor.group_size, n).astype(np.float32)
    w = q * tensor.scales[:, None, :]
    return w.reshape(groups * tensor.group_size, n)[:k]


def pack_int4(values: np.ndarray) -> np.ndarray:
    """Pack signed INT4 values, low nibble first, into uint8 bytes."""

    q = np.asarray(values, dtype=np.int8).reshape(-1)
    if np.any(q < -8) or np.any(q > 7):
        raise ValueError("INT4 values must be in [-8, 7]")
    if q.size % 2:
        q = np.concatenate([q, np.zeros(1, dtype=np.int8)])
    nib = (q.astype(np.int16) & 0xF).astype(np.uint8)
    return nib[0::2] | (nib[1::2] << np.uint8(4))


def unpack_int4(packed: np.ndarray, count: int | None = None) -> np.ndarray:
    p = np.asarray(packed, dtype=np.uint8).reshape(-1)
    lo = p & np.uint8(0xF)
    hi = (p >> np.uint8(4)) & np.uint8(0xF)
    nibbles = np.empty(p.size * 2, dtype=np.int8)
    nibbles[0::2] = lo.astype(np.int8)
    nibbles[1::2] = hi.astype(np.int8)
    nibbles = np.where(nibbles >= 8, nibbles - 16, nibbles).astype(np.int8)
    return nibbles if count is None else nibbles[:count]
