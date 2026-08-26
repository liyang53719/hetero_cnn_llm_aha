#!/usr/bin/env python3
"""Generate immutable descriptor/command v2 contract vectors."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from heteronpu.command import Command128, Engine, Opcode, NULL_INDEX
from heteronpu.descriptor_chain import DmaPolicy, EventList4, MatrixActivation, MatrixAux


ROOT = Path(__file__).resolve().parents[1]


def vectors() -> dict[str, object]:
    aux = MatrixAux(
        bias_index=0x123456, activation=MatrixActivation.RELU,
        full_c=True, repeating_bias=True, no_pool=True,
        max_pixels_per_row=3, pad_bottom=1, pad_right=2,
        subarray_mask=0x05,
    ).to_record(next_index=0x000102)
    dma = DmaPolicy(
        max_burst_beats=16, max_outstanding=4, read_qos=3, write_qos=2,
        allow_unaligned=True, coalesce=True, ordered=False,
    ).to_record()
    events = EventList4((1, 17, 0xFFFF)).to_record(next_index=0x100001)
    commands = {
        "nop": Command128(Opcode.NOP, Engine.CONTROL),
        "matrix": Command128(Opcode.MATRIX_GEMM, Engine.MATRIX,
                             event_wait=4, event_signal=5, src0=1, src1=2, dst=3),
        "dma": Command128(Opcode.DMA_2D, Engine.DMA,
                          event_signal=6, src0=10, src1=11, dst=12),
        "gather": Command128(Opcode.KV_GATHER, Engine.KV,
                             event_signal=7, src0=20, dst=21),
        "barrier": Command128(Opcode.BARRIER, Engine.CONTROL,
                              event_signal=8, src0=30),
    }
    return {
        "schema_version": 2,
        "null_index": f"0x{NULL_INDEX:06x}",
        "records": {
            "matrix_aux": f"0x{aux.pack():032x}",
            "dma_policy": f"0x{dma.pack():032x}",
            "event_list4": f"0x{events.pack():032x}",
        },
        "commands": {name: f"0x{command.pack():032x}" for name, command in commands.items()},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path,
                        default=ROOT / "tests/vectors/descriptor_v2_vectors.json")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = json.dumps(vectors(), indent=2, sort_keys=True) + "\n"
    if args.check:
        if not args.output.exists() or args.output.read_text(encoding="utf-8") != rendered:
            raise SystemExit(f"descriptor v2 vectors are stale: {args.output}")
        print(f"DESCRIPTOR_V2_VECTORS_CHECK_PASS path={args.output}")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(f"DESCRIPTOR_V2_VECTORS_GENERATED path={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
