#!/usr/bin/env python3
import argparse
import json
import random
import struct
from pathlib import Path

import numpy as np


def bits(value):
    return struct.unpack("<I", struct.pack("<f", float(np.float32(value))))[0]


def fp_add(a, b):
    return np.float32(np.float32(a) + np.float32(b))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--expected", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--count", type=int, default=10000)
    args = parser.parse_args()
    rng = random.Random(0x6A0B1A5)
    input_lines = []
    output_lines = []
    illegal_count = 0
    fnv = 0xCBF29CE484222325
    for index in range(args.count):
        role = index % 3
        if index % 200 == 99:
            role = 3
            chunk = 0
        elif index % 200 == 199:
            chunk = 96 if role == 0 else 16
        else:
            chunk = rng.randrange(96 if role == 0 else 16)
        illegal = role == 3 or (role == 0 and chunk >= 96) or (role in (1, 2) and chunk >= 16)
        tag = rng.randrange(65536)
        data = np.array([rng.uniform(-4, 4) for _ in range(16)], dtype=np.float32)
        bias = np.array([rng.uniform(-0.5, 0.5) for _ in range(16)], dtype=np.float32)
        input_record = 0
        for lane in range(16):
            input_record |= bits(data[lane]) << (lane * 32)
            input_record |= bits(bias[lane]) << (512 + lane * 32)
        input_record |= tag << 1024
        input_record |= chunk << 1040
        input_record |= role << 1047
        input_lines.append(f"{input_record:0264x}")

        if illegal:
            outputs = [(0, 0, 0, 0, 1, np.zeros(16, dtype=np.float32))]
            illegal_count += 1
        else:
            biased = np.array([fp_add(data[lane], bias[lane]) for lane in range(16)])
            head_chunk = chunk & 7
            last = int(head_chunk == 7)
            if role == 0:
                query_head = chunk // 8
                outputs = [(query_head, int(query_head >= 6), head_chunk, last, 0, biased)]
            else:
                kv_head = int(chunk >= 8)
                base = 6 if kv_head else 0
                outputs = [
                    (base + replica, kv_head, head_chunk, last, 0, biased)
                    for replica in range(6)
                ]
        for query_head, kv_head, head_chunk, last, output_illegal, output_data in outputs:
            output_record = 0
            for lane in range(16):
                word = bits(output_data[lane])
                output_record |= word << (lane * 32)
                fnv = ((fnv ^ word) * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
            output_record |= tag << 512
            output_record |= chunk << 528
            output_record |= role << 535
            output_record |= query_head << 537
            output_record |= kv_head << 541
            output_record |= head_chunk << 542
            output_record |= last << 545
            output_record |= output_illegal << 546
            output_lines.append(f"{output_record:0137x}")
    result = {
        "input_count": len(input_lines),
        "output_count": len(output_lines),
        "illegal_count": illegal_count,
        "q_chunks": 96,
        "kv_chunks": 16,
        "gqa_replicas": 6,
        "output_data_fnv1a64": f"{fnv:016x}",
    }
    require = (10000, 43000, 100)
    if (result["input_count"], result["output_count"], result["illegal_count"]) != require:
        raise SystemExit(f"QKV_GQA_VECTOR_COUNT_FAIL {result}")
    args.inputs.parent.mkdir(parents=True, exist_ok=True)
    args.inputs.write_text("\n".join(input_lines) + "\n")
    args.expected.write_text("\n".join(output_lines) + "\n")
    args.manifest.write_text(json.dumps(result, indent=2) + "\n")
    print(
        "QKV_BIAS_GQA_VECTORS_PASS "
        f"inputs={len(input_lines)} outputs={len(output_lines)} illegal={illegal_count} "
        f"fnv64={fnv:016x}"
    )


if __name__ == "__main__":
    main()
