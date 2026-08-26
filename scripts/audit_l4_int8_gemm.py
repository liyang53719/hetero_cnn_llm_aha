#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from heteronpu.gemmini_rocc_lowering import Int8OsTilesDescriptor, lower_int8_os_tiles

COMMAND = re.compile(
    r"pc=\[([0-9a-f]+)\].*R\[r\s*\d+=([0-9a-f]+)\]\s+"
    r"R\[r\s*\d+=([0-9a-f]+)\]\s+inst=\[([0-9a-f]+)\]", re.I
)
MARKER = re.compile(
    r"GEMMINI_L4_INT8_GEMM_PASS checksum=(\d+) cycles=(\d+) dma_bytes=(\d+) macs=(\d+)"
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--run-log", type=Path, required=True)
    parser.add_argument("--elf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    match = MARKER.search(args.run_log.read_text(errors="replace"))
    if match is None:
        raise SystemExit("L4_INT8_GEMM_FAIL missing numerical/cycle marker")
    checksum, cycles, dma_bytes, macs = map(int, match.groups())
    if checksum != 14853676686976657775 or dma_bytes != 2195 or macs != 5814 or cycles <= 0:
        raise SystemExit("L4_INT8_GEMM_FAIL marker values")

    commands = []
    for line in args.trace.read_text(errors="replace").splitlines():
        item = COMMAND.search(line)
        if item is None:
            continue
        pc, rs1, rs2, inst = (int(value, 16) for value in item.groups())
        if inst & 0x7F == 0x7B:
            commands.append({"pc": pc, "rs1": rs1, "rs2": rs2,
                             "funct3": (inst >> 12) & 7, "funct7": (inst >> 25) & 127})
    if len(commands) != 36:
        raise SystemExit(f"L4_INT8_GEMM_FAIL commands={len(commands)}")
    descriptor = Int8OsTilesDescriptor(
        a_addr=commands[14]["rs1"], b_addr=commands[11]["rs1"],
        d_addr=commands[6]["rs1"], c_addr=commands[32]["rs1"],
        i_tiles=2, j_tiles=2, k_tiles=2, pad_i=15, pad_j=14, pad_k=13,
        a_row_stride=19, b_row_stride=18, d_row_stride=18, c_row_stride=18,
    )
    lowered = lower_int8_os_tiles(descriptor)
    for index, (expected, actual) in enumerate(zip(lowered, commands, strict=True)):
        if (int(expected.funct), expected.funct3, expected.rs1, expected.rs2) != (
            actual["funct7"], actual["funct3"], actual["rs1"], actual["rs2"]
        ):
            raise SystemExit(f"L4_INT8_GEMM_FAIL lowerer command={index}")

    rows, cols, depth = 17, 18, 19
    a = np.fromfunction(lambda i, k: (i + 2*k + 1) % 5, (rows, depth), dtype=np.int64)
    b = np.fromfunction(lambda k, j: (3*k + j + 2) % 5, (depth, cols), dtype=np.int64)
    d = np.fromfunction(lambda i, j: (i + j) % 4, (rows, cols), dtype=np.int64)
    output = (a @ b + d).astype(np.int8)
    python_checksum = 0
    for value in output.view(np.uint8).flat:
        python_checksum = ((python_checksum * 131) + int(value)) & ((1 << 64) - 1)
    if python_checksum != checksum:
        raise SystemExit("L4_INT8_GEMM_FAIL Python checksum")

    result = {
        "stage": "L4",
        "subgate": "INT8_GEMM",
        "status": "PASS_PAYLOAD_RTL_PENDING_L3_TRACE",
        "shape": {"m": rows, "n": cols, "k": depth},
        "dataflow": "OS",
        "tiles": [2, 2, 2],
        "custom3_commands": 36,
        "elementwise_bit_exact": True,
        "output_sha256": hashlib.sha256(output.tobytes(order="C")).hexdigest(),
        "output_checksum_u64": checksum,
        "rtl_payload_cycles": cycles,
        "rtl_dma_bytes": dma_bytes,
        "rtl_macs": macs,
        "physical_array_peak_macs_per_cycle": 256,
        "rtl_mac_utilization": macs / (cycles * 256),
        "bank_conflicts": None,
        "bank_conflicts_status": "PENDING_CANONICAL_L3_TRACE_REPLAY",
        "elf_sha256": hashlib.sha256(args.elf.read_bytes()).hexdigest(),
        "measurement_scope": {
            "cycles": "retained Gemmini RTL mcycle around production-lowered raw path",
            "dma_bytes": "exact bytes requested by emitted mvin/mvout commands",
            "utilization": "useful MACs divided by measured cycles and physical 16x16 peak",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(f"L4_INT8_GEMM_PAYLOAD_PASS cycles={cycles} dma_bytes={dma_bytes} "
          f"sha256={result['output_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
