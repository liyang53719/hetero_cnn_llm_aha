#!/usr/bin/env python3
import argparse
import hashlib
import json
import math
import struct
from pathlib import Path

import numpy as np

HEADS = 12
HEAD_DIM = 128
HIDDEN = 1536
EXPECTED_INPUT_HASHES = {
    "q_rope": "da6332ce70e15a4d10299ccc3b5dddede3f4c76feddb6c76f3399f301b4e5f22",
    "k_rope_gqa": "ced3130a6ca76bcec9c283b520a0a05421b7c3225af30ae92d015f0c3586bd4c",
    "v_gqa": "5115f712ef2a745f5e14434cc1ef7977c44a458031d8e2d5620e95ff3d95dd39",
}


def bits(value):
    return struct.unpack("<I", struct.pack("<f", float(np.float32(value))))[0]


def from_bits(value):
    return np.float32(struct.unpack("<f", struct.pack("<I", int(value, 16)))[0])


def add(a, b):
    return np.float32(np.float32(a) + np.float32(b))


def mul(a, b):
    return np.float32(np.float32(a) * np.float32(b))


def reduce16(values):
    level = np.array(values, dtype=np.float32)
    while len(level) > 1:
        level = np.array(
            [add(level[i], level[i + 1]) for i in range(0, len(level), 2)],
            dtype=np.float32,
        )
    return level[0]


def dot128(a, b):
    total = np.float32(0)
    for chunk in range(8):
        products = [mul(a[chunk * 16 + i], b[chunk * 16 + i]) for i in range(16)]
        total = add(total, reduce16(products))
    return mul(total, np.float32(struct.unpack("<f", struct.pack("<I", 0x3DB504F3))[0]))


def exp2_pwl(value):
    value = np.float32(value)
    if value < -16:
        return np.float32(0)
    if value >= 0:
        return np.float32(1)
    index = max(0, min(255, math.floor(float(value) * 16) + 256))
    x0 = np.float32(index / 16 - 16)
    x1 = np.float32(x0 + np.float32(1.0 / 16.0))
    y0 = np.float32(np.exp2(x0))
    y1 = np.float32(np.exp2(x1))
    slope = np.float32((np.float64(y1) - np.float64(y0)) / (1.0 / 16.0))
    intercept = np.float32(np.float64(y0) - np.float64(slope) * np.float64(x0))
    return add(mul(slope, value), intercept)


def reciprocal(value):
    word = bits(value)
    exponent = (word >> 23) & 0xFF
    fraction = word & 0x7FFFFF
    normalized = np.float32(struct.unpack("<f", struct.pack("<I", (127 << 23) | fraction))[0])
    index = fraction >> 19
    x0 = 1.0 + index / 16.0
    x1 = x0 + 1.0 / 16.0
    slope = np.float32(((1 / x1) - (1 / x0)) / (1.0 / 16.0))
    intercept = np.float32(1 / x0 - float(slope) * x0)
    estimate = add(mul(slope, normalized), intercept)
    refined = mul(estimate, add(np.float32(2.0), -mul(normalized, estimate)))
    scale = np.float32(struct.unpack("<f", struct.pack("<I", (254 - exponent) << 23))[0])
    return mul(refined, scale)


def load_fp32(path):
    return np.array([from_bits(line) for line in path.read_text().splitlines()], dtype=np.float32)


def write_fp32(path, values):
    path.write_text("\n".join(f"{bits(value):08x}" for value in values) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rope-dir", type=Path, required=True)
    parser.add_argument("--qkv-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    paths = {
        "q_rope": args.rope_dir / "q_rope.memh",
        "k_rope_gqa": args.rope_dir / "k_rope_gqa.memh",
        "v_gqa": args.qkv_dir / "v_gqa.memh",
    }
    for name, path in paths.items():
        observed = hashlib.sha256(path.read_bytes()).hexdigest()
        if observed != EXPECTED_INPUT_HASHES[name]:
            raise SystemExit(f"TARGET_MLO_INPUT_HASH_FAIL {name} {observed}")
    q = load_fp32(paths["q_rope"])
    k = load_fp32(paths["k_rope_gqa"])
    v = load_fp32(paths["v_gqa"])
    m_values = np.empty(HEADS, dtype=np.float32)
    l_values = np.empty(HEADS, dtype=np.float32)
    o_values = np.empty(HIDDEN, dtype=np.float32)
    attention = np.empty(HIDDEN, dtype=np.float32)
    max_attention_error = 0.0
    log2e = np.float32(1.4426950408889634)
    for head in range(HEADS):
        sl = slice(head * HEAD_DIM, (head + 1) * HEAD_DIM)
        score0 = dot128(q[sl], k[sl])
        score1 = dot128(q[sl], k[HIDDEN + head * HEAD_DIM:HIDDEN + (head + 1) * HEAD_DIM])
        m_state = score0
        l_state = np.float32(1)
        o_state = v[sl].copy()
        m_new = score1 if score1 > m_state else m_state
        alpha = exp2_pwl(mul(add(m_state, -m_new), log2e))
        beta = exp2_pwl(mul(add(score1, -m_new), log2e))
        l_state = add(mul(l_state, alpha), beta)
        o_state = np.array(
            [
                add(
                    mul(o_state[i], alpha),
                    mul(v[HIDDEN + head * HEAD_DIM + i], beta),
                )
                for i in range(HEAD_DIM)
            ],
            dtype=np.float32,
        )
        inverse_l = reciprocal(l_state)
        normalized = np.array([mul(value, inverse_l) for value in o_state], dtype=np.float32)
        true_weights = np.exp(
            np.array([float(score0), float(score1)], dtype=np.float64) -
            max(float(score0), float(score1))
        )
        true_weights /= np.sum(true_weights)
        true_output = (
            v[sl].astype(np.float64) * true_weights[0] +
            v[HIDDEN + head * HEAD_DIM:HIDDEN + (head + 1) * HEAD_DIM].astype(np.float64) * true_weights[1]
        )
        max_attention_error = max(
            max_attention_error,
            float(np.max(np.abs(normalized.astype(np.float64) - true_output))),
        )
        m_values[head] = m_new
        l_values[head] = l_state
        o_values[sl] = o_state
        attention[sl] = normalized
    nodes = {
        "m": m_values,
        "l": l_values,
        "o": o_values,
        "attention": attention,
    }
    for name, values in nodes.items():
        write_fp32(args.out / f"{name}.memh", values)
    manifest = {
        "input_sha256": EXPECTED_INPUT_HASHES,
        "heads": HEADS,
        "head_dim": HEAD_DIM,
        "tokens": 2,
        "dot_scale_fp32_bits": "0x3db504f3",
        "score_matrix_materialized": False,
        "dot_operations": 24,
        "online_updates": 24,
        "reciprocals": 12,
        "normalization_chunks": 96,
        "max_attention_error": max_attention_error,
        "attention_error_threshold": 0.002,
        "attention_error_pass": max_attention_error <= 0.002,
        "node_sha256": {
            name: hashlib.sha256((args.out / f"{name}.memh").read_bytes()).hexdigest()
            for name in nodes
        },
    }
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    if not manifest["attention_error_pass"]:
        raise SystemExit(f"TARGET_MLO_ERROR_FAIL {max_attention_error}")
    print(
        "L5_TARGET_MLO_VECTORS_PASS scores_streamed=24 score_matrix=false "
        f"max_attention_error={max_attention_error:.9g} "
        f"attention_sha256={manifest['node_sha256']['attention']}"
    )


if __name__ == "__main__":
    main()
