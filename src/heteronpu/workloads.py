from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .cgra_sfu import CgraSfuModel
from .dtypes import bf16_round
from .kv_engine import KVPageEngine
from .matrix_engine import MatrixEngineModel


def direct_conv2d_nhwc(
    x: np.ndarray,
    weights: np.ndarray,
    *,
    stride: tuple[int, int] = (1, 1),
    padding: tuple[int, int] = (0, 0),
    bias: np.ndarray | None = None,
) -> np.ndarray:
    inp = np.asarray(x)
    w = np.asarray(weights)
    n, h, width, c = inp.shape
    kh, kw, wc, oc = w.shape
    if wc != c:
        raise ValueError("channel mismatch")
    sh, sw = stride
    ph, pw = padding
    padded = np.pad(inp, ((0, 0), (ph, ph), (pw, pw), (0, 0)))
    oh = (h + 2 * ph - kh) // sh + 1
    ow = (width + 2 * pw - kw) // sw + 1
    out = np.zeros((n, oh, ow, oc), dtype=np.int32)
    for b in range(n):
        for y in range(oh):
            for x_pos in range(ow):
                patch = padded[b, y * sh : y * sh + kh, x_pos * sw : x_pos * sw + kw]
                for out_ch in range(oc):
                    out[b, y, x_pos, out_ch] = np.sum(
                        patch.astype(np.int32) * w[..., out_ch].astype(np.int32),
                        dtype=np.int32,
                    )
    if bias is not None:
        out += np.asarray(bias, dtype=np.int32)
    return out


def run_toy_cnn(seed: int = 3) -> dict[str, object]:
    rng = np.random.default_rng(seed)
    x = rng.integers(-4, 5, size=(1, 8, 8, 4), dtype=np.int8)
    w1 = rng.integers(-3, 4, size=(3, 3, 4, 8), dtype=np.int8)
    b1 = rng.integers(-8, 9, size=(8,), dtype=np.int32)
    w2 = rng.integers(-3, 4, size=(1, 1, 8, 6), dtype=np.int8)
    b2 = rng.integers(-8, 9, size=(6,), dtype=np.int32)

    ref1 = direct_conv2d_nhwc(x, w1, padding=(1, 1), bias=b1)
    ref1 = np.maximum(ref1, 0)
    ref_pool = CgraSfuModel.pool2d_nhwc(ref1, mode="max")
    reference = direct_conv2d_nhwc(ref_pool.astype(np.int8), w2, bias=b2)

    matrix = MatrixEngineModel()
    got1 = matrix.conv2d_nhwc(x, w1, padding=(1, 1), mode="int8", bias=b1)
    got1 = CgraSfuModel.relu(got1)
    got_pool = CgraSfuModel.pool2d_nhwc(got1, mode="max")
    output = matrix.conv2d_nhwc(got_pool.astype(np.int8), w2, mode="int8", bias=b2)

    return {
        "reference": reference,
        "output": output,
        "max_abs_error": int(np.max(np.abs(reference.astype(np.int64) - output.astype(np.int64)))),
        "matrix_stats": matrix.stats.__dict__.copy(),
    }


@dataclass(frozen=True)
class ToyLlmWeights:
    norm1: np.ndarray
    norm2: np.ndarray
    wq: np.ndarray
    wk: np.ndarray
    wv: np.ndarray
    wo: np.ndarray
    wg: np.ndarray
    wu: np.ndarray
    wd: np.ndarray


@dataclass(frozen=True)
class ToyLlmConfig:
    hidden: int = 16
    heads: int = 4
    kv_heads: int = 2
    head_dim: int = 4
    ffn: int = 32


def make_toy_llm(seed: int = 5, cfg: ToyLlmConfig = ToyLlmConfig()) -> ToyLlmWeights:
    rng = np.random.default_rng(seed)

    def weight(shape: tuple[int, ...], scale: float = 0.18) -> np.ndarray:
        return rng.normal(0.0, scale, size=shape).astype(np.float32)

    return ToyLlmWeights(
        norm1=np.ones(cfg.hidden, dtype=np.float32) + weight((cfg.hidden,), 0.02),
        norm2=np.ones(cfg.hidden, dtype=np.float32) + weight((cfg.hidden,), 0.02),
        wq=weight((cfg.hidden, cfg.heads * cfg.head_dim)),
        wk=weight((cfg.hidden, cfg.kv_heads * cfg.head_dim)),
        wv=weight((cfg.hidden, cfg.kv_heads * cfg.head_dim)),
        wo=weight((cfg.heads * cfg.head_dim, cfg.hidden)),
        wg=weight((cfg.hidden, cfg.ffn)),
        wu=weight((cfg.hidden, cfg.ffn)),
        wd=weight((cfg.ffn, cfg.hidden)),
    )


def _bf16_gemm(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return bf16_round(a) @ bf16_round(b)


def _attention_token(
    query: np.ndarray,
    keys: np.ndarray,
    values: np.ndarray,
    cfg: ToyLlmConfig,
) -> np.ndarray:
    out = np.empty((cfg.heads, cfg.head_dim), dtype=np.float32)
    groups = cfg.heads // cfg.kv_heads
    scale = np.float32(1.0 / np.sqrt(cfg.head_dim))
    for qh in range(cfg.heads):
        kvh = qh // groups
        scores = keys[:, kvh, :] @ query[qh]
        probs = CgraSfuModel.softmax(scores * scale)
        out[qh] = probs @ values[:, kvh, :]
    return out


def run_toy_llm_block(
    tokens: int = 6,
    seed: int = 7,
    storage_format: str = "bf16",
) -> dict[str, object]:
    cfg = ToyLlmConfig()
    weights = make_toy_llm(seed + 1, cfg)
    rng = np.random.default_rng(seed)
    x = bf16_round(rng.normal(0.0, 0.5, size=(tokens, cfg.hidden)).astype(np.float32))

    # Independent contiguous reference using the same frozen BF16 numerical contract.
    n1_ref = CgraSfuModel.rmsnorm(x, weights.norm1)
    q_ref = bf16_round(_bf16_gemm(n1_ref, weights.wq)).reshape(tokens, cfg.heads, cfg.head_dim)
    k_ref = bf16_round(_bf16_gemm(n1_ref, weights.wk)).reshape(tokens, cfg.kv_heads, cfg.head_dim)
    v_ref = bf16_round(_bf16_gemm(n1_ref, weights.wv)).reshape(tokens, cfg.kv_heads, cfg.head_dim)
    q_ref = CgraSfuModel.rope(q_ref)
    k_ref = CgraSfuModel.rope(k_ref)
    attn_ref = np.empty_like(q_ref)
    for token in range(tokens):
        attn_ref[token] = _attention_token(q_ref[token], k_ref[: token + 1], v_ref[: token + 1], cfg)
    o_ref = bf16_round(_bf16_gemm(attn_ref.reshape(tokens, -1), weights.wo))
    residual_ref = bf16_round(x + o_ref)
    n2_ref = CgraSfuModel.rmsnorm(residual_ref, weights.norm2)
    gate_ref = bf16_round(_bf16_gemm(n2_ref, weights.wg))
    up_ref = bf16_round(_bf16_gemm(n2_ref, weights.wu))
    ff_ref = bf16_round(CgraSfuModel.silu(gate_ref) * up_ref)
    down_ref = bf16_round(_bf16_gemm(ff_ref, weights.wd))
    reference = bf16_round(residual_ref + down_ref)

    matrix = MatrixEngineModel()
    n1 = CgraSfuModel.rmsnorm(x, weights.norm1)
    q = bf16_round(matrix.gemm(n1, weights.wq, mode="bf16")).reshape(tokens, cfg.heads, cfg.head_dim)
    k = bf16_round(matrix.gemm(n1, weights.wk, mode="bf16")).reshape(tokens, cfg.kv_heads, cfg.head_dim)
    v = bf16_round(matrix.gemm(n1, weights.wv, mode="bf16")).reshape(tokens, cfg.kv_heads, cfg.head_dim)
    q = CgraSfuModel.rope(q)
    k = CgraSfuModel.rope(k)
    kv = KVPageEngine(
        page_tokens=4,
        # Scale the software reference pool with the requested context so
        # q384/long-context regressions exercise paging instead of exhausting
        # the toy default pool at 32 pages.
        physical_pages=max(32, (tokens + 3) // 4),
        kv_heads=cfg.kv_heads,
        head_dim=cfg.head_dim,
        storage_format=storage_format,
    )
    attn = np.empty_like(q)
    for token in range(tokens):
        kv.append(0, 0, k[token], v[token])
        gathered_k, gathered_v = kv.read(0, 0)
        attn[token] = _attention_token(q[token], gathered_k, gathered_v, cfg)
    o = bf16_round(matrix.gemm(attn.reshape(tokens, -1), weights.wo, mode="bf16"))
    residual = bf16_round(x + o)
    n2 = CgraSfuModel.rmsnorm(residual, weights.norm2)
    gate = bf16_round(matrix.gemm(n2, weights.wg, mode="bf16"))
    up = bf16_round(matrix.gemm(n2, weights.wu, mode="bf16"))
    ff = bf16_round(CgraSfuModel.silu(gate) * up)
    down = bf16_round(matrix.gemm(ff, weights.wd, mode="bf16"))
    output = bf16_round(residual + down)
    kv.check_invariants()

    error = np.abs(reference - output)
    return {
        "reference": reference,
        "output": output,
        "max_abs_error": float(np.max(error)),
        "mean_abs_error": float(np.mean(error)),
        "matrix_stats": matrix.stats.__dict__.copy(),
        "kv_stats": {
            "pages_in_use": kv.pages_in_use,
            "free_pages": kv.free_pages,
            "allocations": kv.allocations,
            "cow_copies": kv.cow_copies,
            "written_tokens": kv.written_tokens,
            "read_tokens": kv.read_tokens,
        },
    }
