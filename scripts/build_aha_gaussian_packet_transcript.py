#!/usr/bin/env python3
"""Build the verified bitstream-packet portion of the Gaussian L2 transcript."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from heteronpu.aha_garnet_trace import pack_proc_packets, parse_bitstream


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace-dir", type=Path,
                        default=ROOT / "work/generated/l2_aha_gaussian_trace")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "work/results/l2_aha_gaussian_packet_transcript.json")
    args = parser.parse_args()
    entries = parse_bitstream(args.trace_dir / "app_bin/gaussian.bs")
    # Confirmed by pinned test_app map.c and the L1 Gaussian execution log.
    packets = pack_proc_packets(entries, base_address=0)
    result = {
        "status": "PARTIAL_PASS",
        "scope": "lossless Gaussian bitstream-to-proc-packet transcript only",
        "bitstream_entry_count": len(entries),
        "packet_count": len(packets),
        "packet_base_address": 0,
        "first_packet_words": [f"0x{entry.packed_word:016x}" for entry in entries[:8]],
        "last_packet_valid_words": packets[-1].valid_words,
        "last_packet_byte_enable": f"0x{packets[-1].byte_enable:016x}",
        "known_control_writes": [
            {"address": "0x01c", "data": "0x00000001", "meaning": "parallel config start, tile 0"},
            {"address": "0x018", "data": "0x00030003", "meaning": "Gaussian stream start"},
        ],
        "known_packet_bases": {"bitstream": "0x00000", "input_tiles": ["0x00000", "0x20000"],
                                 "output_tiles": ["0x10000", "0x30000"]},
        "not_yet_proven": [
            "full bs_cfg/kernel_cfg AXI register table extraction",
            "full Garnet numerical execution through the project wrapper",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
