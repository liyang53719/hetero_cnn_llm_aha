#!/usr/bin/env python3
"""Build the verified bitstream-packet portion of the Gaussian L2 transcript."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from heteronpu.aha_garnet_trace import (
    load_control_table,
    pack_proc_packets,
    pack_raw_packets,
    parse_bitstream,
    split_interleaved_u16,
)


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace-dir", type=Path,
                        default=ROOT / "work/generated/l2_aha_gaussian_trace")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "work/results/l2_aha_gaussian_packet_transcript.json")
    args = parser.parse_args()
    entries = parse_bitstream(args.trace_dir / "app_bin/gaussian.bs")
    control = load_control_table(args.trace_dir / "control_table.json")
    if control.bitstream_entries != len(entries):
        raise SystemExit("official control table bitstream count disagrees with gaussian.bs")
    packets = pack_proc_packets(entries, base_address=control.bitstream_start_address)
    input_blocks = split_interleaved_u16((args.trace_dir / "app_bin/hw_input_stencil.raw").read_bytes(), 2)
    input_bases = (0x00000, 0x20000)
    input_packets = tuple(pack_raw_packets(block, base_address=base)
                          for block, base in zip(input_blocks, input_bases, strict=True))
    result = {
        "status": "PARTIAL_PASS",
        "scope": "official Gaussian bitstream packets plus AXI control transcript; data payload execution remains open",
        "bitstream_entry_count": len(entries),
        "packet_count": len(packets),
        "packet_base_address": control.bitstream_start_address,
        "first_packet_words": [f"0x{entry.packed_word:016x}" for entry in entries[:8]],
        "last_packet_valid_words": packets[-1].valid_words,
        "last_packet_byte_enable": f"0x{packets[-1].byte_enable:016x}",
        "official_axi_control": {
            "bs_cfg_count": len(control.bs_cfg),
            "kernel_cfg_count": len(control.kernel_cfg),
            "interrupt_enable_count": len(control.interrupt_enable),
            "pcfg_start": {"address": f"0x{control.pcfg_start.address:03x}", "data": f"0x{control.pcfg_start.data:08x}"},
            "stream_start": {"address": f"0x{control.stream_start.address:03x}", "data": f"0x{control.stream_start.data:08x}"},
        },
        "ordered_phases": [
            "interrupt_enable_axi_writes",
            "bitstream_proc_packets",
            "bs_cfg_axi_writes",
            "kernel_cfg_axi_writes",
            "pcfg_start_axi_write",
            "wait_official_garnet_interrupt",
            "input_proc_packets",
            "stream_start_axi_write",
        ],
        "known_packet_bases": {"bitstream": "0x00000", "input_tiles": ["0x00000", "0x20000"],
                                 "output_tiles": ["0x10000", "0x30000"]},
        "input_payload": {
            "distribution": "default test_app interleaved u16: tile j receives source[j + 2*k]",
            "tile_byte_counts": [len(block) for block in input_blocks],
            "tile_packet_counts": [len(group) for group in input_packets],
        },
        "not_yet_proven": [
            "full Garnet numerical execution through the project wrapper",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
