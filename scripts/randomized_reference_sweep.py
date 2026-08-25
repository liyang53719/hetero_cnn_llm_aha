#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from heteronpu.cgra_sfu import CgraSfuModel
from heteronpu.dtypes import bf16_round, quantize_int8_symmetric
from heteronpu.kv_engine import KVPageEngine
from heteronpu.matrix_engine import MatrixEngineModel
from heteronpu.workloads import direct_conv2d_nhwc


def _stored_token(token: np.ndarray, storage_format: str) -> np.ndarray:
    token = np.asarray(token, dtype=np.float32)
    if storage_format == "bf16":
        return bf16_round(token)
    q, scale = quantize_int8_symmetric(token, axis=1)
    return q.astype(np.float32) * scale


def run(seed: int = 20260824) -> dict[str, object]:
    rng = np.random.default_rng(seed)
    matrix = MatrixEngineModel()

    gemm_cases = 100
    for _ in range(gemm_cases):
        m = int(rng.integers(1, 18))
        k = int(rng.integers(1, 35))
        n = int(rng.integers(1, 20))
        a = rng.integers(-128, 128, size=(m, k), dtype=np.int16).astype(np.int8)
        b = rng.integers(-128, 128, size=(k, n), dtype=np.int16).astype(np.int8)
        got = matrix.gemm(a, b, mode="int8")
        expected = a.astype(np.int32) @ b.astype(np.int32)
        np.testing.assert_array_equal(got, expected)

    conv_cases = 40
    for _ in range(conv_cases):
        batch = int(rng.integers(1, 3))
        h = int(rng.integers(3, 10))
        w = int(rng.integers(3, 10))
        channels = int(rng.integers(1, 6))
        out_channels = int(rng.integers(1, 8))
        kh = int(rng.integers(1, min(4, h + 1)))
        kw = int(rng.integers(1, min(4, w + 1)))
        sh = int(rng.integers(1, 3))
        sw = int(rng.integers(1, 3))
        ph = int(rng.integers(0, 2))
        pw = int(rng.integers(0, 2))
        if h + 2 * ph < kh or w + 2 * pw < kw:
            continue
        x = rng.integers(-8, 8, size=(batch, h, w, channels), dtype=np.int8)
        weights = rng.integers(-8, 8, size=(kh, kw, channels, out_channels), dtype=np.int8)
        bias = rng.integers(-64, 65, size=(out_channels,), dtype=np.int32)
        got = matrix.conv2d_nhwc(
            x,
            weights,
            stride=(sh, sw),
            padding=(ph, pw),
            mode="int8",
            bias=bias,
        )
        expected = direct_conv2d_nhwc(
            x,
            weights,
            stride=(sh, sw),
            padding=(ph, pw),
            bias=bias,
        )
        np.testing.assert_array_equal(got, expected)

    softmax_cases = 100
    softmax_max_abs = 0.0
    for _ in range(softmax_cases):
        length = int(rng.integers(1, 513))
        block = int(rng.integers(1, 65))
        x = rng.normal(0.0, 8.0, size=length).astype(np.float32)
        got = CgraSfuModel.online_softmax_1d(x, block=block)
        expected = CgraSfuModel.softmax(x)
        error = float(np.max(np.abs(got - expected)))
        softmax_max_abs = max(softmax_max_abs, error)
        np.testing.assert_allclose(got, expected, rtol=5e-6, atol=5e-7)

    kv_results: dict[str, object] = {}
    for storage_format in ("bf16", "int8"):
        kv = KVPageEngine(
            page_tokens=4,
            physical_pages=512,
            kv_heads=2,
            head_dim=8,
            storage_format=storage_format,
        )
        references: dict[int, tuple[np.ndarray, np.ndarray]] = {
            0: (
                np.empty((0, 2, 8), dtype=np.float32),
                np.empty((0, 2, 8), dtype=np.float32),
            )
        }
        next_sequence = 1
        commands = 0
        max_abs = 0.0
        for _ in range(600):
            sequence_ids = sorted(references)
            action = rng.choice(
                ["append", "append", "append", "read", "fork", "share", "free"],
                p=[0.28, 0.20, 0.14, 0.14, 0.09, 0.09, 0.06],
            )
            if action == "append":
                seq = int(rng.choice(sequence_ids))
                count = int(rng.integers(1, 4))
                k = rng.normal(size=(count, 2, 8)).astype(np.float32)
                v = rng.normal(size=(count, 2, 8)).astype(np.float32)
                kv.append(seq, 0, k, v)
                stored_k = np.stack([_stored_token(token, storage_format) for token in k])
                stored_v = np.stack([_stored_token(token, storage_format) for token in v])
                ref_k, ref_v = references[seq]
                references[seq] = (
                    np.concatenate([ref_k, stored_k], axis=0),
                    np.concatenate([ref_v, stored_v], axis=0),
                )
            elif action == "read":
                seq = int(rng.choice(sequence_ids))
                got_k, got_v = kv.read(seq, 0)
                ref_k, ref_v = references[seq]
                max_abs = max(
                    max_abs,
                    float(np.max(np.abs(got_k - ref_k))) if ref_k.size else 0.0,
                    float(np.max(np.abs(got_v - ref_v))) if ref_v.size else 0.0,
                )
                np.testing.assert_allclose(got_k, ref_k, rtol=0, atol=1e-6)
                np.testing.assert_allclose(got_v, ref_v, rtol=0, atol=1e-6)
            elif action == "fork" and len(references) < 24:
                src = int(rng.choice(sequence_ids))
                dst = next_sequence
                next_sequence += 1
                kv.fork_sequence(src, dst, 0)
                ref_k, ref_v = references[src]
                references[dst] = (ref_k.copy(), ref_v.copy())
            elif action == "share" and len(references) < 24:
                src = int(rng.choice(sequence_ids))
                tokens = int(rng.integers(0, references[src][0].shape[0] + 1))
                dst = next_sequence
                next_sequence += 1
                kv.share_prefix(src, dst, 0, tokens)
                ref_k, ref_v = references[src]
                references[dst] = (ref_k[:tokens].copy(), ref_v[:tokens].copy())
            elif action == "free" and len(references) > 1:
                candidates = [seq for seq in sequence_ids if seq != 0]
                seq = int(rng.choice(candidates))
                kv.free_sequence(seq)
                references.pop(seq)
            commands += 1
            kv.check_invariants()

        for seq, (ref_k, ref_v) in references.items():
            got_k, got_v = kv.read(seq, 0)
            np.testing.assert_allclose(got_k, ref_k, rtol=0, atol=1e-6)
            np.testing.assert_allclose(got_v, ref_v, rtol=0, atol=1e-6)
        kv_results[storage_format] = {
            "commands": commands,
            "active_sequences": len(references),
            "pages_in_use": kv.pages_in_use,
            "allocations": kv.allocations,
            "cow_copies": kv.cow_copies,
            "max_abs_error_vs_independent_storage_reference": max_abs,
        }

    return {
        "status": "PASS",
        "seed": seed,
        "int8_gemm_cases": gemm_cases,
        "int8_conv_cases": conv_cases,
        "online_softmax_cases": softmax_cases,
        "online_softmax_max_abs_error": softmax_max_abs,
        "kv": kv_results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="reports/randomized_reference_sweep.json")
    parser.add_argument("--seed", type=int, default=20260824)
    args = parser.parse_args()
    result = run(args.seed)
    rendered = json.dumps(result, indent=2, sort_keys=True)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered + "\n")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
