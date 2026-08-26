#!/usr/bin/env python3
"""Generate production Matrix v2 descriptor records and expected RoCC programs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from heteronpu.command import Command128, Engine, Opcode
from heteronpu.descriptor_chain import MatrixActivation, MatrixAux, NULL_INDEX
from heteronpu.gemmini_descriptor_v2 import (
    conv2d_record, lower_matrix_v2, matrix_op_record, quantization_record,
    shape4_record, stride3_record, tensor_base_record,
)

ROOT = Path(__file__).resolve().parents[1]
JSON_PATH = ROOT / "tests/vectors/gemmini_descriptor_v2_programs.json"


def add_tensor(records: dict[int, object], root: int, *, address: int,
               shape: tuple[int, ...], strides: tuple[int, ...], dtype: int = 1,
               rank: int | None = None, tail: list[object] | None = None) -> None:
    entries = [
        lambda nxt: tensor_base_record(address, dtype=dtype, rank=rank or len(shape), next_index=nxt),
        lambda nxt: shape4_record(shape, next_index=nxt),
        lambda nxt: stride3_record(strides, next_index=nxt),
    ]
    for item in tail or []:
        entries.append(lambda nxt, item=item: type(item)(item.record_type, 0, 0, nxt, item.payload))
    for offset, factory in enumerate(entries):
        index = root + offset
        records[index] = factory(root + offset + 1 if offset + 1 < len(entries) else NULL_INDEX)


def case_program(name: str, opcode: Opcode, records: dict[int, object], roots: tuple[int, int, int],
                 scales: dict[int, int] | None = None) -> dict[str, object]:
    command = Command128(opcode, Engine.MATRIX, event_signal=0x1234,
                         src0=roots[0], src1=roots[1], dst=roots[2])
    ops = lower_matrix_v2(command, records, scale_bits=scales)
    return {
        "name": name, "command": f"0x{command.pack():032x}",
        "records": {f"0x{index:06x}": f"0x{record.pack():032x}"
                    for index, record in sorted(records.items())},
        "ops": [{"funct": int(op.funct), "rs1": f"0x{op.rs1:016x}",
                 "rs2": f"0x{op.rs2:016x}"} for op in ops],
    }


def matrix_case(*, dataflow: int) -> dict[str, object]:
    records: dict[int, object] = {}
    aux = MatrixAux(bias_index=30, no_pool=True, subarray_mask=1).to_record()
    op = matrix_op_record(m=17, n=18, k=19, dataflow=dataflow,
                          accumulate=dataflow == 1)
    if dataflow == 0:
        addresses = (0x80003240, 0x80003890, 0x80003B30, 0x800033C0)
    else:
        addresses = (0x80002B80, 0x800031D0, 0x80003470, 0x80002D00)
    add_tensor(records, 1, address=addresses[0], shape=(17, 19), strides=(19,), tail=[op, aux])
    add_tensor(records, 10, address=addresses[1], shape=(19, 18), strides=(18,))
    add_tensor(records, 20, address=addresses[2], shape=(17, 18), strides=(18,))
    add_tensor(records, 30, address=addresses[3], shape=(17, 18), strides=(72,), dtype=4)
    return case_program("multi_tile_os" if dataflow == 0 else "loop_ws",
                        Opcode.MATRIX_GEMM, records, (1, 10, 20))


def conv_case(*, relu_requant: bool) -> dict[str, object]:
    records: dict[int, object] = {}
    aux = MatrixAux(
        bias_index=30,
        activation=MatrixActivation.RELU if relu_requant else MatrixActivation.NONE,
        no_pool=True, max_pixels_per_row=3, pad_bottom=1, pad_right=1,
        subarray_mask=1,
    ).to_record()
    op = matrix_op_record(m=25, n=4, k=27, dataflow=1,
                          quant_mode=1 if relu_requant else 0)
    conv = conv2d_record(kernel_h=3, kernel_w=3, stride_h=1, stride_w=1,
                         dilation_h=1, dilation_w=1, pad_top=1, pad_left=1, groups=1)
    add_tensor(records, 1, address=0x80002E00, shape=(1, 5, 5, 3), strides=(3,),
               tail=[op, conv, aux])
    add_tensor(records, 10, address=0x80002E90, shape=(3, 3, 3, 4), strides=(4,))
    dst_tail = [quantization_record(scale_address=0x9000)] if relu_requant else []
    output_address = 0x800030A4 if relu_requant else 0x80003040
    add_tensor(records, 20, address=output_address, shape=(1, 5, 5, 4), strides=(4,),
               tail=dst_tail)
    add_tensor(records, 30, address=0x80002E80, shape=(1, 4), strides=(16,), dtype=4)
    return case_program("conv_relu_requant" if relu_requant else "conv_identity",
                        Opcode.MATRIX_CONV, records, (1, 10, 20),
                        {0x9000: 0x3F000000} if relu_requant else None)


def render() -> tuple[str, dict[str, str]]:
    cases = [matrix_case(dataflow=0), matrix_case(dataflow=1),
             conv_case(relu_requant=False), conv_case(relu_requant=True)]
    payload = {"schema_version": 2, "cases": cases}
    memh: dict[str, str] = {}
    for case in cases:
        lines = []
        for op in case["ops"]:
            packed = int(op["funct"]) << 128 | int(op["rs1"], 16) << 64 | int(op["rs2"], 16)
            lines.append(f"{packed:034x}")
        memh[str(case["name"])] = "\n".join(lines) + "\n"
    return json.dumps(payload, indent=2, sort_keys=True) + "\n", memh


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered, memh = render()
    outputs = {JSON_PATH: rendered}
    outputs.update({ROOT / f"tests/vectors/gemmini_{name}.memh": text for name, text in memh.items()})
    if args.check:
        stale = [str(path) for path, text in outputs.items()
                 if not path.exists() or path.read_text(encoding="utf-8") != text]
        if stale:
            raise SystemExit(f"Gemmini descriptor v2 vectors are stale: {stale}")
        print(f"GEMMINI_DESCRIPTOR_V2_PROGRAMS_CHECK_PASS outputs={len(outputs)}")
        return 0
    for path, text in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    print(f"GEMMINI_DESCRIPTOR_V2_PROGRAMS_GENERATED outputs={len(outputs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
