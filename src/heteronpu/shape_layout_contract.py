"""C03.3 synthetic E0 shape/layout contracts and arbitrary-precision oracles.

This module is deliberately NOT used by the compiler or RTL frontend. Candidate
shape acceptance is not evidence that QwenBlockShape/HostBlockCommands support
it. All arithmetic precedes range checks: never wrap, mask or use floating point.
"""
from __future__ import annotations

from math import prod
from typing import Any


class ContractError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def need(ok: bool, code: str) -> None:
    if not ok:
        raise ContractError(code)


def integer(value: Any, minimum: int, maximum: int, code: str) -> int:
    need(type(value) is int and minimum <= value <= maximum, code)
    return value


def dimension(value: Any) -> int:
    return integer(value, 1, 65535, "dimension_u16")


def align64(value: int) -> int:
    return (value + 63) // 64 * 64


def shape_contract(*, hidden: int, ffn: int, q_heads: int, kv_heads: int,
                   head_dim: int, value_dim: int, query_tokens: int,
                   kv_tokens: int, max_query_tokens: int = 1024,
                   max_kv_tokens: int = 65535, extra_rows: dict[str, int] | None = None) -> dict:
    """Candidate owner geometry, independent Q/K/V widths and query/KV lengths.

    extra_rows are explicit logical row widths (e.g. gate/GDN/conv), not packed
    matrix tiles. No official profile is loaded or re-certified here. Alignment
    and the current maxTokens=1024 cap are backend gates, not u16 encoding rules.
    """
    h, f, qh, kh, hd, vd, tq, tk = map(dimension, (
        hidden, ffn, q_heads, kv_heads, head_dim, value_dim, query_tokens, kv_tokens))
    need(qh % kh == 0, "gqa_grouping")
    need(tk >= tq, "kv_shorter_than_query")
    mq, mk = dimension(max_query_tokens), dimension(max_kv_tokens)
    need(tq <= mq and tk <= mk, "token_capacity")
    widths = {"hidden": h, "ffn": f, "q": qh * hd, "k": kh * hd,
              "v": kh * vd, "context": qh * vd}
    if extra_rows is not None:
        need(type(extra_rows) is dict, "extra_rows")
        for name, width in extra_rows.items():
            need(type(name) is str and bool(name) and name not in widths, "extra_rows")
            widths[name] = dimension(width)
    for width in widths.values():
        dimension(width)
    return {"widths": widths, "max_row": max(widths.values()),
            "query_tokens": tq, "kv_tokens": tk,
            "max_query_tokens": mq, "max_kv_tokens": mk, "gqa_group_size": qh // kh,
            "tensors": {"q": [tq, widths["q"]], "k_new": [tq, widths["k"]],
                        "v_new": [tq, widths["v"]],
                        "k_cache": [tk, widths["k"]], "v_cache": [tk, widths["v"]],
                        "score": [qh, tq, tk], "probability": [qh, tq, tk],
                        "context": [tq, widths["context"]], "output": [tq, h]},
            "virtual_tensors": ["score", "probability"],
            "dense_mnk": {"q_proj": [tq, widths["q"], h],
                          "o_proj": [tq, h, widths["context"]]},
            "qk_mnk": [tq, tk, hd], "pv_mnk": [tq, vd, tk]}


def legacy_layout(*, hidden: int, ffn: int, heads: int, kv_heads: int,
                  head_dim: int, max_tokens: int) -> dict:
    """Safe legacy subset, same FP32 words/order/alignment as QwenBlockLayout.

    Requiring safe positive u16 inputs here must not be confused with validating
    the existing Scala constructor's unchecked Int arithmetic.
    """
    h, f, qh, kh, hd, t = map(dimension, (hidden, ffn, heads, kv_heads, head_dim, max_tokens))
    need(h == qh * hd and qh % kh == 0, "legacy_grouping")
    need(hd >= 32 and hd % 32 == 0 and f % 16 == 0 and h % 16 == 0, "legacy_alignment")
    need(t <= 1024, "legacy_tokens")
    kv = kh * hd
    regions: list[dict] = []
    cursor = 0

    def add(name: str, words: int, external: bool) -> None:
        nonlocal cursor
        cursor = align64(cursor)
        regions.append({"name": name, "offset": cursor, "words": words, "external": external})
        cursor += words * 4

    for name, rows, cols in (("wq", h, h), ("wk", h, kv), ("wv", h, kv),
                             ("wo", h, h), ("wg", h, f), ("wu", h, f), ("wd", f, h)):
        add(name, rows * cols, True)
    for name in ("gamma0", "gamma1", "bq"):
        add(name, h, True)
    for name in ("bk", "bv"):
        add(name, kv, True)
    for name in ("cos", "sin"):
        add(name, t * hd // 2, True)
    add("x", t * h, True)
    writable_start = align64(cursor)
    for name, width in (("n0", h), ("qr", h), ("kr", kv), ("v", kv), ("q", h),
                        ("k", kv), ("att", h), ("o", h), ("r", h), ("n1", h),
                        ("gate", f), ("up", f), ("act", f), ("down", h), ("y", h)):
        add(name, t * width, False)
    return {"max_row": max(h, f), "kv_width": kv, "writable_start": writable_start,
            "total": align64(cursor), "regions": regions}


def wide_address(*, base: int, dims: list[int], byte_strides: list[int],
                 element_bytes: int, indices: list[int], address_bits: int = 56,
                 stride_bits: int = 64, span_bits: int = 64) -> dict:
    """Positive C-order strided tensor span with a checked indexed address.

    Independent arithmetic stress oracle; NOT a v2 STRIDE3 encoding. Strides
    are BYTES here (v2 uses ELEMENTS). End is exclusive and may equal 2**bits.
    Unpadded span/payload/offset must fit span_bits; each stride fits stride_bits.
    Padded accesses include every 64-byte beat; unaligned base is rejected.
    """
    ab = integer(address_bits, 1, 64, "address_bits")
    sb = integer(stride_bits, 1, 64, "stride_bits")
    wb = integer(span_bits, 1, 64, "span_bits")
    b = integer(base, 0, (1 << ab) - 1, "base_range")
    need(b % 64 == 0, "base_alignment")
    need(type(dims) is list and 1 <= len(dims) <= 4, "rank")
    shape = [dimension(d) for d in dims]
    need(type(byte_strides) is list and len(byte_strides) == len(shape), "strides_rank")
    strides = [integer(s, 1, (1 << sb) - 1, "stride_range") for s in byte_strides]
    e = integer(element_bytes, 1, 8, "element_bytes")
    need(e in (1, 2, 4, 8), "element_bytes")
    need(strides[-1] == e and all(strides[i] >= strides[i+1] * shape[i+1]
                                 for i in range(len(shape)-1)), "stride_overlap")
    need(type(indices) is list and len(indices) == len(shape), "indices_rank")
    ix = [integer(i, 0, d - 1, "index_range") for i, d in zip(indices, shape)]
    elements = prod(shape)
    payload = elements * e
    span = sum((d - 1) * s for d, s in zip(shape, strides)) + e
    offset = sum(i * s for i, s in zip(ix, strides))
    need(max(payload, span, offset) < 1 << wb, "span_overflow")
    end = b + span
    padded_end = align64(end)
    need(end <= 1 << ab and padded_end <= 1 << ab, "address_overflow")
    return {"elements": elements, "payload_bytes": payload, "span_bytes": span,
            "offset": offset, "address": b + offset, "end": end, "padded_end": padded_end}


def tensor_v2(*, base: int, dims: list[int], rank: int, strides: list[int], dtype: int,
              region_base: int, region_limit: int) -> dict:
    """Launch-safe arithmetic subset of TypedTensorReader: no DMA or ACL.

    SHAPE4 is 18 bits, not the owner job's 16-bit m/n/k. The reader limits the
    element count to u32, requires inactive dimensions=1, signed24 positive
    ELEMENT strides, 64-byte base alignment, and an exclusive 56-bit limit.
    Region apertures follow HostBlockCommands launch checks; an isolated reader
    can accept a larger enclosing region. Permissions/chains are outside scope.
    """
    b = integer(base, 0, (1 << 56) - 1, "base_range")
    r = integer(rank, 1, 4, "rank")
    need(type(dims) is list and len(dims) == 4, "rank")
    ds = [integer(d, 1, (1 << 18) - 1, "dimension_u18") for d in dims]
    need(all(d == 1 for d in ds[r:]), "inactive_dimension")
    need(type(strides) is list and len(strides) == 3, "strides_rank")
    ss = [integer(s, -(1 << 23), (1 << 23) - 1, "stride_s24") for s in strides]
    need(type(dtype) is int and dtype in (5, 7), "dtype")
    rb = integer(region_base, 0, (1 << 56) - 1, "region_range")
    rl = integer(region_limit, 0, 1 << 56, "region_range")
    elements = prod(ds)
    payload = elements * (2 if dtype == 5 else 4)
    end = b + align64(payload)
    need(elements <= (1 << 32) - 1 and b % 64 == 0 and b < end <= 1 << 56, "bounds")
    expected = [prod(ds[1:]), prod(ds[2:]), ds[3]]
    need(ss == expected and min(ss) >= 0, "stride_unsupported")
    need(rb < rl and rb <= b and end <= rl, "region_bounds")
    return {"elements": elements, "payload_bytes": payload, "padded_end": end,
            "owner_dimensions_fit_u16": all(d <= 65535 for d in ds)}


OPERATIONS = {"shape": shape_contract, "legacy_layout": legacy_layout,
              "wide_address": wide_address, "tensor_v2": tensor_v2}


def evaluate(operation: str, inputs: dict) -> dict:
    try:
        need(type(operation) is str and operation in OPERATIONS, "unknown_operation")
        return {"accepted": True, "result": OPERATIONS[operation](**inputs)}
    except ContractError as exc:
        return {"accepted": False, "error": exc.code}
