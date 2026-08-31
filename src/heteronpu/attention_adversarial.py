"""Multi-seed and adversarial Block128 Attention numerical contracts.

This module is self-contained so it can run in the sandbox without RTL tools.
It freezes deterministic BF16 Q/K/V distributions, dense causal GQA results,
Block32/Block128 FP32 M/L/O results, merge counts and stable review hashes.
It is an E0/vector contract, not RTL E2 evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Iterable

import numpy as np

Q_HEADS = 12
KV_HEADS = 2
GQA_RATIO = 6
HEAD_DIM = 128
KV_TILE = 32
BLOCK = 128


def f32_to_bf16(values: np.ndarray) -> np.ndarray:
    x = np.asarray(values, dtype=np.float32)
    words = x.view(np.uint32).copy()
    nan = ((words & 0x7F800000) == 0x7F800000) & ((words & 0x007FFFFF) != 0)
    rounded = words + np.uint32(0x7FFF) + ((words >> 16) & np.uint32(1))
    out = (rounded >> 16).astype(np.uint16)
    out[nan] |= np.uint16(0x40)
    return out


def bf16_to_f32(bits: np.ndarray) -> np.ndarray:
    return (np.asarray(bits, dtype=np.uint16).astype(np.uint32) << 16).view(np.float32)


def bf16(values: np.ndarray) -> np.ndarray:
    return bf16_to_f32(f32_to_bf16(values))


@dataclass(frozen=True)
class CaseSpec:
    name: str
    sequence: int
    seed: int
    pattern: str
    rows: tuple[int, ...]
    heads: tuple[int, ...]


def _deterministic_qkv(sequence: int, seed: int, pattern: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    q = rng.standard_normal((Q_HEADS, sequence, HEAD_DIM), dtype=np.float32) * np.float32(0.25)
    k = rng.standard_normal((KV_HEADS, sequence, HEAD_DIM), dtype=np.float32) * np.float32(0.25)
    v = rng.standard_normal((KV_HEADS, sequence, HEAD_DIM), dtype=np.float32) * np.float32(0.35)

    if pattern == "random":
        pass
    elif pattern == "identical_scores":
        # Every causal key has the same dot product for each query.
        base = np.linspace(-0.5, 0.5, HEAD_DIM, dtype=np.float32)
        k[:] = base
        q[:] = np.roll(base, 7)
    elif pattern == "near_tie":
        base = np.linspace(-0.25, 0.25, HEAD_DIM, dtype=np.float32)
        for p in range(sequence):
            k[:, p, :] = base + np.float32((p % 7) * 1e-5)
        q[:] = base[::-1]
    elif pattern == "dominant_boundary":
        q[:] = 0
        q[:, :, 0] = np.float32(8.0)
        k[:] = 0
        # Put dominant keys exactly around Block128 boundaries.
        for p in (0, 31, 32, 127, 128, 255, 256, sequence - 1):
            if 0 <= p < sequence:
                k[:, p, 0] = np.float32(10.0 if p % 2 == 0 else -10.0)
        v[:, :, 0] = np.arange(sequence, dtype=np.float32)[None, :] / max(sequence, 1)
    elif pattern == "extreme_range":
        q[:] = 0
        q[:, :, 0] = np.float32(1.0)
        k[:] = 0
        # Produces score range approximately [-80, 80] after scale.
        ramp = np.linspace(-80.0 * math.sqrt(HEAD_DIM), 80.0 * math.sqrt(HEAD_DIM), sequence, dtype=np.float32)
        k[:, :, 0] = ramp[None, :]
    elif pattern == "alternating_extreme":
        q[:] = 0
        q[:, :, 0] = np.float32(1.0)
        k[:] = 0
        amp = np.float32(70.0 * math.sqrt(HEAD_DIM))
        k[:, :, 0] = np.where(np.arange(sequence) % 2 == 0, amp, -amp)[None, :]
    elif pattern == "underflow_tail":
        q[:] = 0
        q[:, :, 0] = np.float32(1.0)
        k[:] = 0
        k[:, :, 0] = np.linspace(0.0, -120.0 * math.sqrt(HEAD_DIM), sequence, dtype=np.float32)[None, :]
    elif pattern == "block_pulse":
        q[:] = 0
        q[:, :, 0] = np.float32(1.0)
        k[:] = 0
        for p in range(sequence):
            if p % BLOCK in (0, BLOCK - 1):
                k[:, p, 0] = np.float32((1 if p % BLOCK == 0 else -1) * 25.0 * math.sqrt(HEAD_DIM))
    else:
        raise ValueError(pattern)
    return bf16(q), bf16(k), bf16(v)


def _dense_row(q: np.ndarray, k: np.ndarray, v: np.ndarray, head: int, row: int) -> np.ndarray:
    kh = head // GQA_RATIO
    query = q[head, row].astype(np.float64)
    scores = k[kh, : row + 1].astype(np.float64) @ query / math.sqrt(HEAD_DIM)
    scores -= np.max(scores)
    w = np.exp(scores)
    w /= np.sum(w)
    return (w @ v[kh, : row + 1].astype(np.float64)).astype(np.float32)


@dataclass
class Summary:
    m: np.float32
    l: np.float32
    o: np.darray


def _empty() -> Summary:
    return Summary(np.float32(-np.inf), np.float32(0), np.zeros(HEAD_DIM, dtype=np.float32))


def _merge(a: Summary, b: Summary) -> Summary:
    if a.l == 0:
        return Summary(b.m, b.l, b.o.copy())
    if b.l == 0:
        return Summary(a.m, a.l, a.o.copy())
    m = np.float32(max(float(a.m), float(b.m)))
    aa = np.float32(np.exp(np.float32(a.m - m)))
    bb = np.float32(np.exp(np.float32(b.m - m)))
    l = np.float32(np.float32(a.l * aa) + np.float32(b.l * bb))
    o = np.float32(a.o * aa) + np.float32(b.o * bb)
    return Summary(m, l, np.asarray(o, dtype=np.float32))


def _tile(scores: np.ndarray, values: np.ndarray) -> Summary:
    s = np.asarray(scores, dtype=np.float32)
    m = np.float32(np.max(s))
    w = np.exp(np.asarray(s - m, dtype=np.float32)).astype(np.float32)
    return Summary(m, np.sum(w, dtype=np.float32), np.sum(w[:, None] * values.astype(np.float32), axis=0, dtype=np.float32))


def _blocked_row(q: np.ndarray, k: np.ndarray, v: np.ndarray, head: int, row: int, *, reverse_block_merge: bool = False) -> tuple[np.ndarray, int]:
    kh = head // GQA_RATIO
    query = q[head, row].astype(np.float32)
    block_summaries: list[Summary] = []
    for bs in range(0, row + 1, BLOCK):
        be = min(row + 1, bs + BLOCK)
        block = _empty()
        for ts in range(bs, be, KV_TILE):
            te = min(be, ts + KV_TILE)
            scores = np.asarray(k[kh, ts:te].astype(np.float32) @ query / np.float32(math.sqrt(HEAD_DIM)), dtype=np.float32)
            block = _merge(block, _tile(scores, v[kh, ts:te]))
        block_summaries.append(block)
    if reverse_block_merge:
        block_summaries.reverse()
    total = _empty()
    merges = 0
    for block in block_summaries:
        if total.l != 0:
            merges += 1
        total = _merge(total, block)
    return np.asarray(total.o / total.l, dtype=np.float32), merges


def default_cases() -> tuple[CaseSpec, ...]:
    boundary_rows = (0, 1, 15, 16, 31, 32, 63, 64, 126, 127, 128, 129, 254, 255, 256)
    cases: list[CaseSpec] = []
    for seed in (1, 7, 38, 42878):
        cases.append(CaseSpec(f"random_seed_{seed}", 128, seed, "random", tuple(range(128)), tuple(range(Q_HEADS)))
    adversarial = (
        ("identical_scores", 257),
        ("near_tie", 257),
        ("dominant_boundary", 257),
        ("extreme_range", 257),
        ("alternating_extreme", 257),
        ("underflow_tail", 257),
        ("block_pulse", 257),
    )
    rows = tuple(sorted(set(r for r in boundary_rows if r < 257) | {257 - 1}))
    for index, (pattern, seq) in enumerate(adversarial):
        cases.append(CaseSpec(pattern, seq, 1000 + index, pattern, rows, (0, 1, 5, 6, 10, 11)))
    return tuple(cases)


def adversarial_attention_report() -> dict[str, object]:
    records: list[dict[str, object]] = []
    max_abs = 0.0
    max_rel = 0.0
    merge_order_max = 0.0
    digest = hashlib.sha256()
    for spec in default_cases():
        q, k, v = _deterministic_qkv(spec.sequence, spec.seed, spec.pattern)
        case_abs = 0.0
        case_rel = 0.0
        case_merge_order = 0.0
        rows_compared = 0
        for h in spec.heads:
            for row in spec.rows:
                dense = _dense_row(q, k, v, h, row)
                blocked, merges = _blocked_row(q, k, v, h, row)
                reversed_out, reversed_merges = _blocked_row(q, k, v, h, row, reverse_block_merge=True)
                if merges != row // BLOCK or reversed_merges != merges:
                    raise AssertionError((spec.name, h, row, merges))
                err = np.abs(dense.astype(np.float64) - blocked.astype(np.float64))
                rel = float(np.linalg.norm(err) / max(np.linalg.norm(dense.astype(np.float64)), 1e-30))
                order_err = float(np.max(np.abs(blocked.astype(np.float64) - reversed_out.astype(np.float64))))
                case_abs = max(case_abs, float(np.max(err)))
                case_rel = max(case_rel, rel)
                case_merge_order = max(case_merge_order, order_err)
                rows_compared += 1
                digest.update(spec.name.encode())
                digest.update(h.to_bytes(2, "little"))
                digest.update(row.to_bytes(4, "little"))
                digest.update(blocked.tobytes())
        records.append({
            "name": spec.name,
            "pattern": spec.pattern,
            "sequence": spec.sequence,
            "seed": spec.seed,
            "rows_compared": rows_compared,
            "max_abs": case_abs,
            "max_relative_l2": case_rel,
            "reverse_merge_max_abs": case_merge_order,
        })
        max_abs = max(max_abs, case_abs)
        max_rel = max(max_rel, case_rel)
        merge_order_max = max(merge_order_max, case_merge_order)
    # The extreme score tests are deliberately harsh; require a tight but not bit-exact contract.
    if max_abs > 5e-5 or max_rel > 5e-5 or merge_order_max > 5e-5:
        raise AssertionError((max_abs, max_rel, merge_order_max))
    return {
        "schema_version": 1,
        "status": "PASS",
        "evidence_class": "multi_seed_adversarial_Attention_E0_not_RTL_E2",
        "cases": records,
        "case_count": len(records),
        "random_seed_count": 4,
        "adversarial_pattern_count": 7,
        "max_abs": max_abs,
        "max_relative_l2": max_rel,
        "reverse_merge_max_abs": merge_order_max,
        "sha256": digest.hexdigest(),
        "local_gate": "Replay all manifests through the single-simulation Controller+QK+MLO+PV E2 harness.",
    }
