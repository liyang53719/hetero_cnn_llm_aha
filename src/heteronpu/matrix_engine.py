from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

from .dtypes import (
    W4Tensor,
    bf16_round,
    dequantize_w4_grouped,
    quantize_int8_symmetric,
    quantize_w4_grouped,
)

MatrixMode = Literal["int8", "bf16", "w4a8"]
QuantizedW4 = W4Tensor


@dataclass
class MatrixStats:
    macs: int = 0
    input_bytes: int = 0
    weight_bytes: int = 0
    output_bytes: int = 0
    invocations: int = 0


class MatrixEngineModel:
    """Bit-aware functional model of the reusable Matrix Engine.

    It deliberately models the numerical contract, not Gemmini's cycle timing.
    Cycle estimates live in :mod:`heteronpu.scheduler`.
    """

    def __init__(self) -> None:
        self.stats = MatrixStats()

    @staticmethod
    def quantize_w4(weights: np.ndarray, group_size: int = 64) -> QuantizedW4:
        return quantize_w4_grouped(weights, group_size)

    def reset_stats(self) -> None:
        self.stats = MatrixStats()

    def gemm(
        self,
        a: np.ndarray,
        b: np.ndarray | QuantizedW4,
        *,
        mode: MatrixMode = "bf16",
        bias: np.ndarray | None = None,
        output_bf16: bool = False,
    ) -> np.ndarray:
        lhs = np.asarray(a)
        if lhs.ndim != 2:
            raise ValueError("A must be a rank-2 MxK matrix")

        if mode == "int8":
            rhs = np.asarray(b)
            if rhs.ndim != 2 or lhs.shape[1] != rhs.shape[0]:
                raise ValueError("A and B shapes are not GEMM-compatible")
            qa = lhs.astype(np.int8, copy=False)
            qb = rhs.astype(np.int8, copy=False)
            out = qa.astype(np.int32) @ qb.astype(np.int32)
            input_bytes = qa.nbytes
            weight_bytes = qb.nbytes
        elif mode == "bf16":
            rhs = np.asarray(b, dtype=np.float32)
            if rhs.ndim != 2 or lhs.shape[1] != rhs.shape[0]:
                raise ValueError("A and B shapes are not GEMM-compatible")
            qa = bf16_round(lhs.astype(np.float32))
            qb = bf16_round(rhs)
            out = qa.astype(np.float32) @ qb.astype(np.float32)
            out = out.astype(np.float32)
            input_bytes = qa.size * 2
            weight_bytes = qb.size * 2
        elif mode == "w4a8":
            if not isinstance(b, W4Tensor):
                raise TypeError("w4a8 mode requires a QuantizedW4 weight tensor")
            k, n = b.original_shape
            if lhs.shape[1] != k:
                raise ValueError("A and grouped W4 B shapes are not GEMM-compatible")
            qa, a_scale = quantize_int8_symmetric(lhs.astype(np.float32), axis=1)
            groups = b.q.shape[0] // b.group_size
            padded_k = groups * b.group_size
            qa_pad = np.zeros((qa.shape[0], padded_k), dtype=np.int8)
            qa_pad[:, :k] = qa
            qag = qa_pad.reshape(qa.shape[0], groups, b.group_size)
            qbg = b.q.reshape(groups, b.group_size, n)
            out = np.zeros((qa.shape[0], n), dtype=np.float32)
            row_scale = a_scale.reshape(qa.shape[0], 1)
            for group in range(groups):
                partial = qag[:, group, :].astype(np.int32) @ qbg[group].astype(np.int32)
                out += partial.astype(np.float32) * row_scale * b.scales[group][None, :]
            input_bytes = qa.nbytes
            weight_bytes = (b.q.size + 1) // 2 + b.scales.nbytes
        else:
            raise ValueError(f"unsupported matrix mode: {mode}")

        if bias is not None:
            out = out + np.asarray(bias, dtype=out.dtype)
        if output_bf16:
            out = bf16_round(out.astype(np.float32))

        m, k = lhs.shape
        n = out.shape[1]
        self.stats.macs += int(m * n * k)
        self.stats.input_bytes += int(input_bytes)
        self.stats.weight_bytes += int(weight_bytes)
        self.stats.output_bytes += int(out.nbytes)
        self.stats.invocations += 1
        return out

    def conv2d_nhwc(
        self,
        x: np.ndarray,
        weights: np.ndarray | QuantizedW4,
        *,
        stride: tuple[int, int] = (1, 1),
        padding: tuple[int, int] = (0, 0),
        dilation: tuple[int, int] = (1, 1),
        mode: MatrixMode = "int8",
        bias: np.ndarray | None = None,
    ) -> np.ndarray:
        """NHWC convolution lowered through an explicit im2col matrix."""

        inp = np.asarray(x)
        if inp.ndim != 4:
            raise ValueError("input must be NHWC")
        if isinstance(weights, W4Tensor):
            raise ValueError("conv2d requires explicit R,S,C,K weights in this v0 model")
        w = np.asarray(weights)
        if w.ndim != 4:
            raise ValueError("weights must be R,S,C,K")
        batch, in_h, in_w, in_c = inp.shape
        kh, kw, wc, out_c = w.shape
        if wc != in_c:
            raise ValueError("input and weight channels differ")
        sh, sw = stride
        ph, pw = padding
        dh, dw = dilation
        eff_h = (kh - 1) * dh + 1
        eff_w = (kw - 1) * dw + 1
        out_h = (in_h + 2 * ph - eff_h) // sh + 1
        out_w = (in_w + 2 * pw - eff_w) // sw + 1
        if out_h <= 0 or out_w <= 0:
            raise ValueError("invalid convolution geometry")
        padded = np.pad(inp, ((0, 0), (ph, ph), (pw, pw), (0, 0)))
        cols = np.empty((batch * out_h * out_w, kh * kw * in_c), dtype=inp.dtype)
        row = 0
        for n in range(batch):
            for oy in range(out_h):
                for ox in range(out_w):
                    patch = padded[
                        n,
                        oy * sh : oy * sh + eff_h : dh,
                        ox * sw : ox * sw + eff_w : dw,
                        :,
                    ]
                    cols[row] = patch.reshape(-1)
                    row += 1
        kernel = w.reshape(kh * kw * in_c, out_c)
        out = self.gemm(cols, kernel, mode=mode, bias=bias)
        return out.reshape(batch, out_h, out_w, out_c)

    @staticmethod
    def dequantize_w4(weights: QuantizedW4) -> np.ndarray:
        return dequantize_w4_grouped(weights)
