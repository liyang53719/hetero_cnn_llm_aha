#!/usr/bin/env python3
"""Audit padded Conv WS and requant/ReLU in retained RocketTile."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from heteronpu.gemmini_rocc_lowering import (  # noqa: E402
    ConvWsDescriptor, GemminiDataflow, config_ex, config_store,
    lower_loop_conv_ws,
)

COMMAND = re.compile(
    r"pc=\[([0-9a-f]+)\].*R\[r\s*\d+=([0-9a-f]+)\]\s+"
    r"R\[r\s*\d+=([0-9a-f]+)\]\s+inst=\[([0-9a-f]+)\]", re.I)
PASS = "GEMMINI_L2_CONV_REQUANT_EQ_PASS checksum=13907229944436499941"


def parse(path: Path):
    commands = []
    for line in path.read_text(errors="replace").splitlines():
        match = COMMAND.search(line)
        if match:
            pc, rs1, rs2, inst = (int(x, 16) for x in match.groups())
            if inst & 127 == 0x7B:
                commands.append({"pc": pc, "rs1": rs1, "rs2": rs2,
                                 "funct3": (inst >> 12) & 7,
                                 "funct7": (inst >> 25) & 127})
    return commands


def expected(segment, mode):
    activation = 0 if mode == 0 else 1
    scale_bits = 0x3F800000 if mode == 0 else 0x3F000000
    descriptor = ConvWsDescriptor(
        batch_size=1, in_row_dim=5, in_col_dim=5, in_channels=3,
        out_channels=4, out_row_dim=5, out_col_dim=5,
        pool_out_row_dim=5, pool_out_col_dim=5,
        stride=1, padding=1, kernel_dim=3, kernel_dilation=1,
        pool_size=1, pool_stride=1, pool_padding=0,
        batches=1, porows=5, pocols=5, pochs=4,
        krows=3, kcols=3, kchs=3,
        lpad=1, rpad=1, upad=1, dpad=1,
        plpad=0, prpad=0, pupad=0, pdpad=0,
        orows=5, ocols=5,
        weights_addr=segment[6]["rs1"], output_addr=segment[6]["rs2"],
        bias_addr=segment[7]["rs1"], input_addr=segment[7]["rs2"],
        activation=activation, max_pixels_per_row=3,
        in_stride=3, weight_stride=4, out_stride=4,
    )
    return [
        config_store(stride_bytes=4, acc_scale_bits=scale_bits,
                     activation=activation),
        config_ex(dataflow=GemminiDataflow.WEIGHT_STATIONARY,
                  c_stride=1, a_stride=1, acc_scale_bits=0),
        *lower_loop_conv_ws(descriptor),
    ]


def compare(label, expected_ops, observed):
    if len(expected_ops) != 9 or len(observed) != 9:
        raise SystemExit(f"{label} command count mismatch")
    for index, (op, cmd) in enumerate(zip(expected_ops, observed, strict=True)):
        if (int(op.funct), op.funct3, op.rs1, op.rs2) != (
            cmd["funct7"], cmd["funct3"], cmd["rs1"], cmd["rs2"]
        ):
            raise SystemExit(f"{label} differs at command {index}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--run-log", type=Path, required=True)
    parser.add_argument("--elf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    commands = parse(args.trace)
    if len(commands) != 36:
        raise SystemExit(f"expected 36 CUSTOM_3 commits, got {len(commands)}")
    pairs = [(commands[0:9], commands[9:18]),
             (commands[18:27], commands[27:36])]
    differences = []
    for mode, (official, raw) in enumerate(pairs):
        compare(f"mode {mode} official", expected(official, mode), official)
        compare(f"mode {mode} raw", expected(raw, mode), raw)
        for index, (left, right) in enumerate(zip(official, raw, strict=True)):
            fields = [field for field in ("funct3", "funct7", "rs1", "rs2")
                      if left[field] != right[field]]
            if fields:
                differences.append({"mode": mode, "command": index, "fields": fields})
                if index != 6 or fields != ["rs2"]:
                    raise SystemExit(f"unexpected mode {mode} difference at {index}")
    if len(differences) != 2:
        raise SystemExit("expected two destination-only differences")
    if PASS not in args.run_log.read_text(errors="replace"):
        raise SystemExit("numerical PASS marker absent")
    result = {
        "status": "PASS", "custom3_commits": 36,
        "workload": "1x5x5x3 input, padded 3x3, 4 output channels",
        "modes": ["bias+identity", "bias+scale0.5+ReLU"],
        "python_lowerer_matches_all_commands": True,
        "destination_only_differences": differences,
        "checksum": 13907229944436499941,
        "elf_sha256": hashlib.sha256(args.elf.read_bytes()).hexdigest(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
