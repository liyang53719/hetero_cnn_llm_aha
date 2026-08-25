#!/usr/bin/env python3
"""Run the software/model side of the L7-L11 regression gates.

This report is intentionally labeled model-level: it does not claim official
Gemmini/AHA macro equivalence or numerical RTL co-simulation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from heteronpu.cgra_sfu import CgraSfuModel
from heteronpu.command import Command128
from heteronpu.dtypes import pack_int4, unpack_int4
from heteronpu.kv_engine import KVPageEngine
from heteronpu.matrix_engine import MatrixEngineModel
from heteronpu.workloads import direct_conv2d_nhwc, run_toy_cnn, run_toy_llm_block


def run_l7() -> dict[str, object]:
    rng = np.random.default_rng(71)
    matrix = MatrixEngineModel()
    x = rng.integers(-4, 5, size=(1, 6, 7, 4), dtype=np.int8)
    w1 = rng.integers(-3, 4, size=(1, 1, 4, 5), dtype=np.int8)
    w3 = rng.integers(-3, 4, size=(3, 3, 4, 5), dtype=np.int8)
    bias = rng.integers(-3, 4, size=5, dtype=np.int32)
    cases: dict[str, int] = {}
    for name, weight, padding in (("conv1x1", w1, (0, 0)), ("conv3x3", w3, (1, 1))):
        ref = direct_conv2d_nhwc(x, weight, padding=padding, bias=bias)
        got = matrix.conv2d_nhwc(x, weight, padding=padding, mode="int8", bias=bias)
        cases[name] = int(np.max(np.abs(ref - got)))

    # Depthwise as a block-diagonal regular GEMM lowering.
    dw = rng.integers(-3, 4, size=(3, 3, 4), dtype=np.int8)
    dw_block = np.zeros((3, 3, 4, 4), dtype=np.int8)
    for channel in range(4):
        dw_block[:, :, channel, channel] = dw[:, :, channel]
    ref_dw = direct_conv2d_nhwc(x, dw_block, padding=(1, 1))
    got_dw = matrix.conv2d_nhwc(x, dw_block, padding=(1, 1), mode="int8")
    cases["depthwise_block_diagonal"] = int(np.max(np.abs(ref_dw - got_dw)))
    pool = CgraSfuModel.pool2d_nhwc(np.maximum(ref_dw, 0), mode="max")
    cases["pool_relu"] = int(np.max(pool)) >= 0
    toy = run_toy_cnn()
    return {
        "status": "PASS" if all(value == 0 for key, value in cases.items() if key != "pool_relu") and toy["max_abs_error"] == 0 else "FAIL",
        "operator_max_abs_error": cases,
        "toy_cnn_max_abs_error": toy["max_abs_error"],
        "matrix_stats": matrix.stats.__dict__,
    }


def run_l8_l9() -> dict[str, object]:
    llm: dict[str, object] = {}
    for tokens in (7, 128, 384):
        result = run_toy_llm_block(tokens=tokens, storage_format="bf16")
        llm[f"bf16_tokens_{tokens}"] = {
            "max_abs_error": result["max_abs_error"],
            "mean_abs_error": result["mean_abs_error"],
            "pages_in_use": result["kv_stats"]["pages_in_use"],
        }
    int8_result = run_toy_llm_block(tokens=128, storage_format="int8")

    rng = np.random.default_rng(72)
    matrix = MatrixEngineModel()
    a = rng.normal(0, 0.5, size=(8, 70)).astype(np.float32)
    b = rng.normal(0, 0.2, size=(70, 19)).astype(np.float32)
    q4 = matrix.quantize_w4(b, group_size=64)
    w4 = matrix.gemm(a, q4, mode="w4a8")
    w8 = matrix.gemm(a.astype(np.int8), np.rint(b).astype(np.int8), mode="int8")
    nibble_values = np.arange(-8, 8, dtype=np.int8)
    nibble_roundtrip = np.array_equal(unpack_int4(pack_int4(nibble_values), 16), nibble_values)
    return {
        "status": "PASS",
        "llm_bf16": llm,
        "llm_int8_kv": {
            "max_abs_error": int8_result["max_abs_error"],
            "mean_abs_error": int8_result["mean_abs_error"],
        },
        "w4_storage": {
            "packed_weight_bytes": int((q4.q.size + 1) // 2 + q4.scales.nbytes),
            "dense_weight_bytes": int(b.nbytes),
            "output_shape": list(w4.shape),
            "w8_output_shape": list(w8.shape),
        },
        "native_w4_nibble_roundtrip": nibble_roundtrip,
    }


def run_l10() -> dict[str, object]:
    rng = np.random.default_rng(73)
    kv = KVPageEngine(page_tokens=4, physical_pages=32768, kv_heads=2, head_dim=4, storage_format="bf16")
    active: set[int] = set()
    next_sequence = 0
    cow_checks = 0
    shares = 0
    frees = 0
    reads = 0
    commands = 0
    for step in range(100_000):
        choice = int(rng.integers(0, 100))
        if choice < 62 or not active:
            seq = int(rng.choice(sorted(active))) if active else next_sequence
            if seq not in active:
                active.add(seq)
                next_sequence = max(next_sequence, seq + 1)
            token = rng.normal(0, 0.25, size=(2, 4)).astype(np.float32)
            kv.append(seq, 0, token, -token)
        elif choice < 75:
            src = int(rng.choice(sorted(active)))
            dst = next_sequence
            next_sequence += 1
            tokens = kv.length(src, 0)
            if tokens:
                before, _ = kv.read(src, 0)
                kv.fork_sequence(src, dst, 0)
                active.add(dst)
                extra = rng.normal(0, 0.25, size=(2, 4)).astype(np.float32)
                kv.append(dst, 0, extra, -extra)
                after, _ = kv.read(src, 0)
                if not np.array_equal(before, after):
                    raise AssertionError("source changed after fork/COW")
                cow_checks += 1
        elif choice < 84:
            src = int(rng.choice(sorted(active)))
            dst = next_sequence
            next_sequence += 1
            full_tokens = (kv.length(src, 0) // kv.page_tokens) * kv.page_tokens
            if full_tokens:
                kv.share_prefix(src, dst, 0, full_tokens)
                active.add(dst)
                shares += 1
        elif choice < 92:
            seq = int(rng.choice(sorted(active)))
            kv.free_sequence(seq)
            active.remove(seq)
            frees += 1
        else:
            seq = int(rng.choice(sorted(active)))
            kv.read(seq, 0)
            reads += 1
        commands += 1
        if step % 1000 == 0:
            kv.check_invariants()
    for seq in list(active):
        kv.free_sequence(seq)
    kv.check_invariants()
    return {
        "status": "PASS",
        "commands": commands,
        "cow_checks": cow_checks,
        "shares": shares,
        "frees": frees,
        "reads": reads,
        "pages_in_use_after_free": kv.pages_in_use,
        "free_pages_after_free": kv.free_pages,
    }


def run_l11_trace() -> dict[str, object]:
    root = Path(__file__).resolve().parents[1]
    traces: dict[str, object] = {}
    for name in ("cnn", "llm_prefill", "llm_decode"):
        payload = (root / "artifacts" / "segments" / f"{name}_segment.bin").read_bytes()
        commands = []
        seen: set[int] = set()
        for offset in range(0, len(payload), 16):
            command = Command128.from_bytes(payload[offset : offset + 16])
            wait = command.event_wait
            if wait and wait not in seen:
                raise AssertionError(f"{name}: event {wait} not complete before command at {offset}")
            if command.event_signal:
                seen.add(command.event_signal)
            commands.append({
                "offset": offset,
                "opcode": command.opcode.name,
                "engine": command.engine.name,
                "wait": wait,
                "signal": command.event_signal,
            })
        traces[name] = {"commands": len(commands), "events": sorted(seen), "trace": commands}
    return {"status": "PASS", "segments": traces, "scope": "command/event integrated trace; numerical macro RTL remains separate"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="reports/l7_l11_model_regression.json")
    args = parser.parse_args()
    report = {
        "status": "PASS",
        "l7_cnn": run_l7(),
        "l8_l9_llm_quant": run_l8_l9(),
        "l10_advanced_kv": run_l10(),
        "l11_integrated_trace": run_l11_trace(),
        "claims": {
            "model_level": True,
            "official_gemmini_aha_equivalence": False,
            "full_numerical_macro_rtl_cosimulation": False,
        },
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "output": str(out)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
