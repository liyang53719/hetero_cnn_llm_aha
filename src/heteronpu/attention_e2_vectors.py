"""Deterministic Blocked-Attention E2 vector-pack generator.

This module generates reviewable q128/q384/q1024 numerical vectors without
storing complete score or probability matrices. Inputs are deterministic BF16
Q/K/V tensors. The reference path computes dense causal GQA attention, while
the candidate path uses 32-token microtiles, Block128 summaries and FP32 M/L/O
merge order. Large-sequence packs store hashes and reviewed rows rather than
large tensors.

The output is an E0/E2-harness contract. It is not RTL E2 evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import struct
from typing import Sequence

import numpy as np

Q_HEADS = 12
KV_HEADS = 2
GQA_RATIO = Q_HEADS // KV_HEADS
HEAD_DIM = 128
QUERY_TILE = 16
KV_TILE = 32
BLOCK_TOKENS = 128


def float32_to_bf16_bits(values: np.ndarray | Sequence[float] | float) -> np.ndarray:
    array = np.asarray(values, dtype=np.float32)
    words = array.view(np.uint32).copy()
    exponent = words & np.uint32(0x7F800000)
    fraction = words & np.uint32(0x007FFFFF)
    nan_mask = (exponent == np.uint32(0x7F800000)) & (fraction != 0)
    bias = np.uint32(0x7FFF) + ((words >> np.uint32(16)) & np.uint32(1))
    rounded = words + bias
    bits = (rounded >> np.uint32(16)).astype(np.uint16)
    if np.any(nan_mask):
        bits = bits.copy()
        bits[nan_mask] |= np.uint16(0x0040)
    return bits


def bf16_bits_to_float32(bits: np.ndarray | Sequence[int] | int) -> np.ndarray:
    array = np.asarray(bits, dtype=np.uint16)
    return (array.astype(np.uint32) << np.uint32(16)).view(np.float32)


def _bf16(values: np.ndarray) -> np.ndarray:
    return bf16_bits_to_float32(float32_to_bf16_bits(values))


def deterministic_qkv(sequence: int, seed: int = 0xA77E) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if sequence <= 0:
        raise ValueError("sequence")
    dim = np.arange(HEAD_DIM, dtype=np.float32)[None, None, :]
    pos = np.arange(sequence, dtype=np.float32)[None, :, None]
    qhead = np.arange(Q_HEADS, dtype=np.float32)[:, None, None]
    kvhead = np.arange(KV_HEADS, dtype=np.float32)[:, None, None]
    s = np.float32((seed & 0xFFFF) * 1e-6)
    q = np.sin((pos + 1.0) * (dim + 3.0) * np.float32(0.0013) + qhead * 0.071 + s)
    q += np.cos((pos + 5.0) * (dim + 1.0) * np.float32(0.00037) + qhead * 0.019)
    k = np.cos((pos + 2.0) * (dim + 7.0) * np.float32(0.0011) + kvhead * 0.113 + s)
    k += np.sin((pos + 11.0) * (dim + 2.0) * np.float32(0.00029) + kvhead * 0.041)
    v = np.sin((pos + 3.0) * (dim + 13.0) * np.float32(0.00083) + kvhead * 0.089 - s)
    v += np.cos((pos + 17.0) * (dim + 4.0) * np.float32(0.00023) + kvhead * 0.053)
    return _bf16(q), _bf16(k), _bf16(v)


def dense_causal_row(q: np.ndarray, k: np.ndarray, v: np.ndarray, q_head: int, row: int) -> np.ndarray:
    kv_head = q_head // GQA_RATIO
    query = q[q_head, row].astype(np.float64)
    keys = k[kv_head, : row + 1].astype(np.float64)
    values = v[kv_head, : row + 1].astype(np.float64)
    scores = keys @ query / math.sqrt(HEAD_DIM)
    scores -= np.max(scores)
    weights = np.exp(scores)
    weights /= np.sum(weights)
    return (weights @ values).astype(np.float32)


@dataclass(frozen=True)
class Summary:
    m: np.float32
    l: np.float32
    o: np.ndarray


def _empty_summary() -> Summary:
    return Summary(np.float32(-np.inf), np.float32(0.0), np.zeros(HEAD_DIM, dtype=np.float32))


def _tile_summary(scores: np.ndarray, values: np.ndarray) -> Summary:
    if scores.size == 0:
        return _empty_summary()
    scores32 = np.asarray(scores, dtype=np.float32)
    m = np.float32(np.max(scores32))
    weights = np.exp(np.asarray(scores32 - m, dtype=np.float32)).astype(np.float32)
    l = np.sum(weights, dtype=np.float32)
    o = np.sum(weights[:, None] * values.astype(np.float32), axis=0, dtype=np.float32)
    return Summary(m, np.float32(l), np.asarray(o, dtype=np.float32))


def merge_summary(a: Summary, b: Summary) -> Summary:
    if a.l == 0:
        return Summary(b.m, b.l, b.o.copy())
    if b.l == 0:
        return Summary(a.m, a.l, a.o.copy())
    m = np.float32(max(float(a.m), float(b.m)))
    alpha = np.float32(np.exp(np.float32(a.m - m)))
    beta = np.float32(np.exp(np.float32(b.m - m)))
    l = np.float32(np.float32(a.l * alpha) + np.float32(b.l * beta))
    o = np.asarray(np.float32(a.o * alpha) + np.float32(b.o * beta), dtype=np.float32)
    return Summary(m, l, o)


def blocked_causal_row(q: np.ndarray, k: np.ndarray, v: np.ndarray, q_head: int, row: int) -> tuple[np.ndarray, int]:
    kv_head = q_head // GQA_RATIO
    query = q[q_head, row].astype(np.float32)
    global_summary = _empty_summary()
    merged_blocks = 0
    for block_start in range(0, row + 1, BLOCK_TOKENS):
        block_end = min(row + 1, block_start + BLOCK_TOKENS)
        block_summary = _empty_summary()
        for tile_start in range(block_start, block_end, KV_TILE):
            tile_end = min(block_end, tile_start + KV_TILE)
            keys = k[kv_head, tile_start:tile_end].astype(np.float32)
            values = v[kv_head, tile_start:tile_end].astype(np.float32)
            scores = np.asarray(keys @ query / np.float32(math.sqrt(HEAD_DIM)), dtype=np.float32)
            block_summary = merge_summary(block_summary, _tile_summary(scores, values))
        if global_summary.l != 0:
            merged_blocks += 1
        global_summary = merge_summary(global_summary, block_summary)
    return np.asarray(global_summary.o / global_summary.l, dtype=np.float32), merged_blocks


def controller_task_count(sequence: int) -> int:
    query_tiles = math.ceil(sequence / QUERY_TILE)
    per_head = sum(math.ceil(min(sequence, (tile + 1) * QUERY_TILE) / KV_TILE) for tile in range(query_tiles))
    return per_head * Q_HEADS


def summary_merge_rows(sequence: int) -> int:
    return Q_HEADS * sum(row // BLOCK_TOKENS for row in range(sequence))


def _hash_array(digest: "hashlib._Hash", array: np.ndarray) -> None:
    digest.update(np.asarray(array, dtype=np.float32).tobytes(order="C"))


def _sample_record(q: np.ndarray, k: np.ndarray, v: np.ndarray, sequence: int, q_head: int, row: int) -> tuple[dict[str, object], float, float]:
    dense = dense_causal_row(q, k, v, q_head, row)
    blocked, merges = blocked_causal_row(q, k, v, q_head, row)
    error = np.abs(dense.astype(np.float64) - blocked.astype(np.float64))
    denom = np.linalg.norm(dense.astype(np.float64))
    relative_l2 = float(np.linalg.norm(error) / max(denom, 1e-30))
    record = {
        "sequence": sequence,
        "q_head": q_head,
        "kv_head": q_head // GQA_RATIO,
        "row": row,
        "block_merges": merges,
        "dense_sha256": hashlib.sha256(dense.tobytes()).hexdigest(),
        "blocked_sha256": hashlib.sha256(blocked.tobytes()).hexdigest(),
        "max_abs": float(np.max(error)),
        "relative_l2": relative_l2,
        "first8_dense": [float(x) for x in dense[:8]],
        "first8_blocked": [float(x) for x in blocked[:8]],
    }
    return record, float(np.max(error)), relative_l2


def _task_manifest_hash(sequence: int) -> str:
    digest = hashlib.sha256()
    task_id = 0
    for query_tile in range(math.ceil(sequence / QUERY_TILE)):
        valid_rows = min(QUERY_TILE, sequence - query_tile * QUERY_TILE)
        kv_tiles = math.ceil(min(sequence, (query_tile + 1) * QUERY_TILE) / KV_TILE)
        for q_head in range(Q_HEADS):
            kv_head = q_head // GQA_RATIO
            for kv_tile in range(kv_tiles):
                last_kv = kv_tile + 1 == kv_tiles
                close_block = last_kv or ((kv_tile + 1) * KV_TILE) % BLOCK_TOKENS == 0
                merge_global = close_block and kv_tile >= BLOCK_TOKENS // KV_TILE
                digest.update(struct.pack("<IHHBBBB", task_id, query_tile, kv_tile, q_head, kv_head, valid_rows, int(last_kv)))
                digest.update(bytes((int(close_block), int(merge_global))))
                task_id += 1
    if task_id != controller_task_count(sequence):
        raise AssertionError((task_id, controller_task_count(sequence)))
    return digest.hexdigest()


def attention_e2_pack_report(seed: int = 0xA77E) -> dict[str, object]:
    cases: dict[str, object] = {}
    maximum_abs = 0.0
    maximum_relative_l2 = 0.0
    aggregate = hashlib.sha256()
    q, k, v = deterministic_qkv(128, seed)
    q128_digest = hashlib.sha256()
    q128_max_abs = 0.0
    q128_max_rel = 0.0
    for q_head in range(Q_HEADS):
        for row in range(128):
            dense = dense_causal_row(q, k, v, q_head, row)
            blocked, merges = blocked_causal_row(q, k, v, q_head, row)
            if merges != row // BLOCK_TOKENS:
                raise AssertionError("q128 merge count")
            error = np.abs(dense.astype(np.float64) - blocked.astype(np.float64))
            relative = float(np.linalg.norm(error) / max(np.linalg.norm(dense.astype(np.float64)), 1e-30))
            q128_max_abs = max(q128_max_abs, float(np.max(error)))
            q128_max_rel = max(q128_max_rel, relative)
            _hash_array(q128_digest, dense)
            _hash_array(q128_digest, blocked)
    cases["128"] = {
        "review": "full_all_rows_all_heads",
        "rows_compared": 128 * Q_HEADS,
        "max_abs": q128_max_abs,
        "max_relative_l2": q128_max_rel,
        "output_pair_sha256": q128_digest.hexdigest(),
        "controller_tasks": controller_task_count(128),
        "summary_merge_rows": summary_merge_rows(128),
        "task_manifest_sha256": _task_manifest_hash(128),
    }
    maximum_abs = max(maximum_abs, q128_max_abs)
    maximum_relative_l2 = max(maximum_relative_l2, q128_max_rel)
    aggregate.update(q128_digest.digest())
    reviewed = {
        384: (tuple(range(Q_HEADS)), (0, 1, 15, 16, 31, 32, 63, 64, 127, 128, 191, 255, 256, 319, 383)),
        1024: ((0, 1, 5, 6, 10, 11), (0, 1, 15, 16, 31, 32, 63, 64, 127, 128, 255, 256, 511, 512, 767, 768, 895, 1023)),
    }
    for sequence, (heads, rows) in reviewed.items():
        q, k, v = deterministic_qkv(sequence, seed)
        records = []
        case_max_abs = 0.0
        case_max_rel = 0.0
        for q_head in heads:
            for row in rows:
                record, max_abs, relative_l2 = _sample_record(q, k, v, sequence, q_head, row)
                records.append(record)
                case_max_abs = max(case_max_abs, max_abs)
                case_max_rel = max(case_max_rel, relative_l2)
        record_digest = hashlib.sha256(json.dumps(records, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        cases[str(sequence)] = {
            "review": "fixed_rows_all_or_boundary_heads",
            "rows_compared": len(records),
            "q_heads": list(heads),
            "rows": list(rows),
            "max_abs": case_max_abs,
            "max_relative_l2": case_max_rel,
            "records_sha256": record_digest,
            "records": records,
            "controller_tasks": controller_task_count(sequence),
            "summary_merge_rows": summary_merge_rows(sequence),
            "task_manifest_sha256": _task_manifest_hash(sequence),
        }
        maximum_abs = max(maximum_abs, case_max_abs)
        maximum_relative_l2 = max(maximum_relative_l2, case_max_rel)
        aggregate.update(bytes.fromhex(record_digest))
    expected = {128: (240, 0), 384: (1872, 4608), 1024: (12672, 43008)}
    for sequence, (tasks, merges) in expected.items():
        case = cases[str(sequence)]
        if case["controller_tasks"] != tasks or case["summary_merge_rows"] != merges:
            raise AssertionError((sequence, case))
    if maximum_abs > 2e-5 or maximum_relative_l2 > 2e-5:
        raise AssertionError((maximum_abs, maximum_relative_l2))
    return {
        "schema_version": 1,
        "status": "PASS",
        "evidence_class": "deterministic_Attention_E2_vector_pack_not_RTL_E2",
        "geometry": {"q_heads": Q_HEADS, "kv_heads": KV_HEADS, "head_dim": HEAD_DIM, "query_tile": QUERY_TILE, "kv_tile": KV_TILE, "block_tokens": BLOCK_TOKENS, "gqa_ratio": GQA_RATIO, "inputs": "deterministic_BF16", "state": "FP32_MLO"},
        "seed": seed,
        "max_abs": maximum_abs,
        "max_relative_l2": maximum_relative_l2,
        "cases": cases,
        "aggregate_sha256": aggregate.hexdigest(),
        "local_gate": "regenerate this pack and compare integrated RTL q128 full, q384 reviewed/full and q1024 reviewed rows",
    }
