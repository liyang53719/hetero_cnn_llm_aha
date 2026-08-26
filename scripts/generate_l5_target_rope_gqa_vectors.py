#!/usr/bin/env python3
import argparse
import hashlib
import json
import math
import struct
from pathlib import Path

import numpy as np

HIDDEN = 1536
KV_WIDTH = 256
HEAD_DIM = 128
Q_HEADS = 12
KV_HEADS = 2
THETA = 1_000_000.0
EXPECTED_INPUT_HASHES = {
    "q_biased": "480793d57d47c2b9480bb7e4c874fda45f5f4da2ac33a0bc7fd81a174941880e",
    "k_biased": "7d81d5a946c343682719a8c9a5869b338ffb805ccc25a33e5410df6b7045dbf6",
    "v_biased": "f8c257caf593c14403b4bc2fe006ad4078804fa57560a10b2b21a77ff6a4b16f",
}


def bits(value):
    return struct.unpack("<I", struct.pack("<f", float(np.float32(value))))[0]


def from_bits(value):
    return np.float32(struct.unpack("<f", struct.pack("<I", int(value, 16)))[0])


def add(a, b):
    return np.float32(np.float32(a) + np.float32(b))


def mul(a, b):
    return np.float32(np.float32(a) * np.float32(b))


def load_fp32(path):
    return np.array([from_bits(line) for line in path.read_text().splitlines()], dtype=np.float32)


def write_fp32(path, values):
    path.write_text("\n".join(f"{bits(value):08x}" for value in values) + "\n")


def rope_coefficients(position):
    result = []
    for index in range(HEAD_DIM // 2):
        inverse_frequency = 1.0 / (THETA ** (2.0 * index / HEAD_DIM))
        angle = np.float32(position * inverse_frequency)
        result.extend(
            [np.float32(math.cos(float(angle))), np.float32(math.sin(float(angle)))]
        )
    return np.array(result, dtype=np.float32)


def split_half_rope(vector, heads, position, coefficients):
    output = vector.copy()
    for head in range(heads):
        base = head * HEAD_DIM
        for index in range(HEAD_DIM // 2):
            first = vector[base + index]
            second = vector[base + HEAD_DIM // 2 + index]
            cosine = coefficients[position * HEAD_DIM + 2 * index]
            sine = coefficients[position * HEAD_DIM + 2 * index + 1]
            output[base + index] = add(mul(first, cosine), -mul(second, sine))
            output[base + HEAD_DIM // 2 + index] = add(
                mul(second, cosine), mul(first, sine)
            )
    return output


def expand_gqa(vector):
    output = np.empty(HIDDEN, dtype=np.float32)
    for query_head in range(Q_HEADS):
        kv_head = query_head // 6
        output[query_head * HEAD_DIM:(query_head + 1) * HEAD_DIM] = vector[
            kv_head * HEAD_DIM:(kv_head + 1) * HEAD_DIM
        ]
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for name, expected in EXPECTED_INPUT_HASHES.items():
        observed = hashlib.sha256((args.input_dir / f"{name}.memh").read_bytes()).hexdigest()
        if observed != expected:
            raise SystemExit(f"TARGET_ROPE_INPUT_HASH_FAIL {name} {observed}")

    q_biased = load_fp32(args.input_dir / "q_biased.memh")
    k_biased = load_fp32(args.input_dir / "k_biased.memh")
    coefficients = np.concatenate((rope_coefficients(0), rope_coefficients(1)))
    q_rope = split_half_rope(q_biased, Q_HEADS, 1, coefficients)
    k_previous_rope = split_half_rope(k_biased[:KV_WIDTH], KV_HEADS, 0, coefficients)
    k_current_rope = split_half_rope(k_biased[KV_WIDTH:], KV_HEADS, 1, coefficients)
    k_rope = np.concatenate((k_previous_rope, k_current_rope))
    k_rope_gqa = np.concatenate((expand_gqa(k_previous_rope), expand_gqa(k_current_rope)))

    nodes = {
        "rope_coeff": coefficients,
        "q_rope": q_rope,
        "k_rope": k_rope,
        "k_rope_gqa": k_rope_gqa,
    }
    for name, values in nodes.items():
        write_fp32(args.out / f"{name}.memh", values)
    manifest = {
        "input_sha256": EXPECTED_INPUT_HASHES,
        "theta": THETA,
        "head_dim": HEAD_DIM,
        "q_heads": Q_HEADS,
        "kv_heads": KV_HEADS,
        "positions": [0, 1],
        "pairing": "split-half lane i with lane i+64",
        "rope_pairs": 1024,
        "multicast_inputs": 32,
        "multicast_outputs": 192,
        "node_sha256": {
            name: hashlib.sha256((args.out / f"{name}.memh").read_bytes()).hexdigest()
            for name in nodes
        },
    }
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(
        "L5_TARGET_ROPE_GQA_VECTORS_PASS "
        f"rope_pairs={manifest['rope_pairs']} multicast_outputs=192 "
        f"q_rope_sha256={manifest['node_sha256']['q_rope']}"
    )


if __name__ == "__main__":
    main()
