#!/usr/bin/env python3
"""Audit the exported official Gaussian map/PnR trace for L2 wrapper inputs."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENTRY = re.compile(r"^[0-9A-Fa-f]{8}\s+[0-9A-Fa-f]{8}$")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace-dir", type=Path,
                        default=ROOT / "work/generated/l2_aha_gaussian_trace")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "work/results/l2_aha_gaussian_trace_audit/result.json")
    args = parser.parse_args()
    app = args.trace_dir / "app_bin"
    metadata = json.loads((app / "design_meta.json").read_text())
    bitstream = (app / "gaussian.bs").read_text().splitlines()
    if not bitstream or not all(ENTRY.fullmatch(line) for line in bitstream):
        raise SystemExit("gaussian.bs is not a non-empty 32-bit address/data stream")

    ios = metadata["IOs"]
    inputs = ios["inputs"]
    outputs = ios["outputs"]
    if len(inputs) != 1 or len(outputs) != 1:
        raise SystemExit("Gaussian trace has unexpected IO tensor cardinality")
    input_tiles = inputs[0]["io_tiles"]
    output_tiles = outputs[0]["io_tiles"]
    if inputs[0]["bitwidth"] != 16 or outputs[0]["bitwidth"] != 16:
        raise SystemExit("Gaussian trace no longer exposes 16-bit data IO")
    if [tile["x_pos"] for tile in input_tiles] != [0, 2]:
        raise SystemExit("Gaussian input lane placement drifted")
    if [tile["x_pos"] for tile in output_tiles] != [1, 3]:
        raise SystemExit("Gaussian output lane placement drifted")

    bs_json = json.loads((app / "gaussian.bs.json").read_text())
    result = {
        "status": "PASS",
        "scope": "official Gaussian trace audit only; no AHA wrapper equivalence claimed",
        "bitstream_entries": len(bitstream),
        "input_16b_x_positions": [tile["x_pos"] for tile in input_tiles],
        "output_16b_x_positions": [tile["x_pos"] for tile in output_tiles],
        "output_port_name": bs_json["output_port_name"],
        "valid_port_name": bs_json["valid_port_name"],
        "input_shape": inputs[0]["shape"],
        "output_shape": outputs[0]["shape"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
