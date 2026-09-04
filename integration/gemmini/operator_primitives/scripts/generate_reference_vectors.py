#!/usr/bin/env python3
"""Generate deterministic, timing-independent vectors for local RTL differential tests."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE))
from reference.operator_primitives_reference import (  # noqa: E402
    MODEL_REQUIRED_OPERATORS,
    bilinear_index,
    block_pool_schedule,
    causal_conv_schedule,
    fp32_bits,
    gated_residual_schedule,
    gdn_recurrent_step,
    gdn_state_schedule,
    mrope_map,
    moe_route_merge,
    mtp_verify,
    norm_schedule,
    ple_hash_rows,
    qsa_selected_tokens,
    restoring_divide,
    shift_add_multiply,
    stable_topk,
    tagged_gather_reorder,
    terminal_sequence,
    vision_patch3d_schedule,
    vision_patch_merge_schedule,
    vision_window_schedule,
)


def _hex32(value: int) -> str:
    return f"0x{value & 0xFFFF_FFFF:08x}"


def _f32_hex(values):
    return [_hex32(fp32_bits(v)) for v in values]


def build_payload() -> dict:
    topk_items = [
        (0x7F80_0000, 9),       # +inf
        (0x0000_0000, 5),       # +0
        (0x8000_0000, 3),       # -0; ties by ascending index
        (0x3F80_0000, 7),       # 1
        (0x3F80_0000, 2),       # 1, lower index wins
        (0xFF80_0000, 1),       # -inf
        (0x7FC0_0001, 0),       # NaN sorts after numbers
    ]
    requests = [
        (0x1000 + i * 0x40, i % 3, 8 + i, i == 5)
        for i in range(6)
    ]
    gdn_out, gdn_state = gdn_recurrent_step(
        ((0.25, -0.5), (0.75, 0.125)),
        (0.5, -1.0),
        (1.25, 0.75),
        (0.2, -0.3),
        a=-0.4,
        b=0.75,
        a_log=-0.2,
        dt_bias=0.1,
    )
    model_sequences = {
        model: {
            op: list(terminal_sequence(op))
            for op in operators
        }
        for model, operators in MODEL_REQUIRED_OPERATORS.items()
    }
    payload = {
        "schema_version": 1,
        "contract": "HeteroNPU Qwen-family terminal primitive differential vectors",
        "clock_independent": True,
        "integer": {
            "divide_u16": [
                {"dividend": a, "divisor": b, "quotient": q, "remainder": r}
                for a, b in ((0, 1), (65535, 255), (49153, 97), (12345, 0))
                for q, r in (restoring_divide(a, b, 16),)
            ],
            "multiply_u16": [
                {"left": a, "right": b, "product": shift_add_multiply(a, b, 16)}
                for a, b in ((0, 0), (1, 65535), (257, 513), (65535, 65535))
            ],
        },
        "selection": {
            "stable_topk_fp32": {
                "items": [{"score": _hex32(s), "index": i} for s, i in topk_items],
                "k": 5,
                "expected": [
                    {"score": _hex32(s), "index": i}
                    for s, i in stable_topk(topk_items, 5)
                ],
            },
            "qsa_tokens": {
                "block_scores": [_hex32(x) for x in (0x3F80_0000, 0x4000_0000, 0x3F00_0000, 0x4000_0000)],
                "block_topk": 2,
                "compress_ratio": 4,
                "tail_count": 3,
                "expected": list(qsa_selected_tokens(
                    (0x3F80_0000, 0x4000_0000, 0x3F00_0000, 0x4000_0000),
                    block_topk=2,
                    compress_ratio=4,
                    tail_count=3,
                )),
            },
        },
        "sparse_memory": {
            "tagged_gather": {
                "requests": [list(x) for x in requests],
                "response_order": [5, 2, 0, 4, 1, 3],
                "expected": [list(x) for x in tagged_gather_reorder(requests, (5, 2, 0, 4, 1, 3))],
            },
            "ple_hash": {
                "tokens": [11, 7, 23, 5],
                "ngram_size": 3,
                "heads_per_ngram": 2,
                "sizes": [17, 19, 23, 29],
                "offsets": [0, 17, 36, 59],
                "multipliers": [3, 5, 7],
                "expected": [list(x) for x in ple_hash_rows(
                    (11, 7, 23, 5), ngram_size=3, heads_per_ngram=2,
                    sizes=(17, 19, 23, 29), offsets=(0, 17, 36, 59),
                    multipliers=(3, 5, 7), sentinel=0,
                )],
            },
        },
        "moe": {
            "weights_fp32": _f32_hex((0.5, 0.25, 0.125, 0.125)),
            "results_fp32": [_f32_hex(row) for row in (
                (1.0, 2.0, 3.0),
                (-1.0, 4.0, 0.5),
                (8.0, -2.0, 1.0),
                (0.25, 0.5, -4.0),
            )],
            "response_order": [3, 1, 0, 2],
            "expected_fp32": _f32_hex(moe_route_merge(
                (0.5, 0.25, 0.125, 0.125),
                ((1.0, 2.0, 3.0), (-1.0, 4.0, 0.5), (8.0, -2.0, 1.0), (0.25, 0.5, -4.0)),
                (3, 1, 0, 2),
            )),
        },
        "state": {
            "causal_conv_k4_d1": [x.__dict__ for x in causal_conv_schedule(2, 2, 4, 1, 2, 1)],
            "dilated_conv_k4_d3": [x.__dict__ for x in causal_conv_schedule(1, 2, 4, 3, 5, 4)],
            "gdn_address_small": [list(x) for x in gdn_state_schedule(2, 3, 2)],
            "norm_layer_small": [list(x) for x in norm_schedule("layer_norm", 2, 4)],
            "gated_residual_small": [list(x) for x in gated_residual_schedule(4, 3)],
            "mtp_all_match": mtp_verify((10, 20, 30), (10, 20, 30)),
            "mtp_first_mismatch": mtp_verify((10, 20, 30, 40), (10, 21, 30, 40)),
            "gdn_numeric": {
                "output_fp32": _f32_hex(gdn_out),
                "state_fp32": [_f32_hex(row) for row in gdn_state],
            },
        },
        "vision": {
            "mrope": [list(x) for x in mrope_map(12, 3, 2)],
            "window_odd": [list(x) for x in vision_window_schedule(1, 3, 5, 4, 6, 2, 3)],
            "patch_merge_odd": [list(x) for x in vision_patch_merge_schedule(1, 3, 5, 2, 2)],
            "bilinear_center": list(bilinear_index(2, 3, 4, 5, 5, 7, 16)),
            "bilinear_single_dest": list(bilinear_index(0, 0, 4, 5, 1, 1, 16)),
            "patch3d_small": [list(x) for x in vision_patch3d_schedule(1, 2, 2, 2, 2, 2, 2, 2, 2, 2)],
            "block_pool_small": [list(x) for x in block_pool_schedule(2, 4, 3)],
        },
        "model_terminal_sequences": model_sequences,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return {**payload, "payload_sha256": hashlib.sha256(canonical).hexdigest()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    text = json.dumps(build_payload(), indent=2, sort_keys=True) + "\n"
    if args.check:
        if not args.output.exists() or args.output.read_text() != text:
            raise SystemExit(f"reference vector mismatch: regenerate {args.output}")
        print(f"PASS_REFERENCE_VECTORS {args.output}")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
