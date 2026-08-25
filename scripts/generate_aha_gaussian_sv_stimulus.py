#!/usr/bin/env python3
"""Generate SystemVerilog constants for the verified Gaussian transcript."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from heteronpu.aha_garnet_trace import (
    load_control_table,
    pack_proc_packets,
    pack_u16be_proc_packets,
    parse_bitstream,
    split_interleaved_u16,
)


ROOT = Path(__file__).resolve().parents[1]


def emit_packet_array(declarations: list[str], assignments: list[str], name: str, packets) -> None:
    declarations.append(f"localparam int {name}_COUNT = {len(packets)};")
    declarations.append(f"logic [17:0] {name}_ADDR [0:{name}_COUNT-1];")
    declarations.append(f"logic [511:0] {name}_DATA [0:{name}_COUNT-1];")
    declarations.append(f"logic [63:0] {name}_STRB [0:{name}_COUNT-1];")
    for index, packet in enumerate(packets):
        assignments.append(f"  {name}_ADDR[{index}] = 18'h{packet.address:05x};")
        assignments.append(f"  {name}_DATA[{index}] = 512'h{packet.data:0128x};")
        assignments.append(f"  {name}_STRB[{index}] = 64'h{packet.byte_enable:016x};")


def emit_axi_array(declarations: list[str], assignments: list[str], name: str, writes) -> None:
    declarations.append(f"localparam int {name}_COUNT = {len(writes)};")
    declarations.append(f"logic [12:0] {name}_ADDR [0:{name}_COUNT-1];")
    declarations.append(f"logic [31:0] {name}_DATA [0:{name}_COUNT-1];")
    for index, write in enumerate(writes):
        assignments.append(f"  {name}_ADDR[{index}] = 13'h{write.address:03x};")
        assignments.append(f"  {name}_DATA[{index}] = 32'h{write.data:08x};")


def emit_expected_output(declarations: list[str], assignments: list[str], name: str,
                         base_address: int, payload: bytes) -> None:
    if len(payload) % 8:
        raise SystemExit(f"{name} output payload is not 64-bit aligned")
    word_count = len(payload) // 8
    declarations.append(f"localparam logic [17:0] {name}_BASE = 18'h{base_address:05x};")
    declarations.append(f"localparam int {name}_WORDS = {word_count};")
    declarations.append(f"logic [63:0] {name}_EXPECTED [0:{name}_WORDS-1];")
    for index in range(word_count):
        # The official testbench `$fread`s the raw 16-bit golden into
        # `bit [15:0]` entries: file bytes `00 70` become 16'h0070.  Proc
        # readback returns four of those numeric lanes low-word first.
        lane_bytes = payload[index * 8:(index + 1) * 8]
        lanes = [int.from_bytes(lane_bytes[offset:offset + 2], byteorder="big")
                 for offset in range(0, 8, 2)]
        word = sum(lane << (16 * lane_index) for lane_index, lane in enumerate(lanes))
        assignments.append(f"  {name}_EXPECTED[{index}] = 64'h{word:016x};")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace-dir", type=Path,
                        default=ROOT / "work/generated/l2_aha_gaussian_trace")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "work/generated/l2_aha_gaussian_trace/gaussian_transcript_stim.svh")
    args = parser.parse_args()
    entries = parse_bitstream(args.trace_dir / "app_bin/gaussian.bs")
    control = load_control_table(args.trace_dir / "control_table.json")
    if len(entries) != control.bitstream_entries:
        raise SystemExit("bitstream entry count disagrees with official control table")
    bitstream = pack_proc_packets(entries, base_address=control.bitstream_start_address)
    blocks = split_interleaved_u16((args.trace_dir / "app_bin/hw_input_stencil.raw").read_bytes(), 2)
    input0 = pack_u16be_proc_packets(blocks[0], base_address=0x00000)
    input1 = pack_u16be_proc_packets(blocks[1], base_address=0x20000)
    layout = json.loads((args.trace_dir / "control_table.json").read_text(encoding="utf-8"))
    cgra_stall_mask = int(layout["cgra_stall_mask"])
    if not 0 < cgra_stall_mask < (1 << 32):
        raise SystemExit("official CGRA stall mask must be a nonzero 32-bit value")
    output_layout = layout.get("outputs", [])
    if len(output_layout) != 1 or len(output_layout[0].get("tiles", [])) != 2:
        raise SystemExit("expected exactly one two-tile Gaussian output from official mapper")
    gold = (args.trace_dir / "app_bin/hw_output.raw").read_bytes()
    if len(gold) != int(output_layout[0]["file_size"]):
        raise SystemExit("Gaussian golden byte count disagrees with official mapper")
    output_blocks = split_interleaved_u16(gold, 2)

    declarations = ["// Generated from the pinned official Gaussian control transcript."]
    declarations.append(f"localparam logic [31:0] CGRA_STALL_MASK = 32'h{cgra_stall_mask:08x};")
    assignments: list[str] = []
    emit_packet_array(declarations, assignments, "BS", bitstream)
    emit_packet_array(declarations, assignments, "INPUT0", input0)
    emit_packet_array(declarations, assignments, "INPUT1", input1)
    emit_expected_output(declarations, assignments, "OUTPUT0",
                         int(output_layout[0]["tiles"][0]["gold_check_start_address"]), output_blocks[0])
    emit_expected_output(declarations, assignments, "OUTPUT1",
                         int(output_layout[0]["tiles"][1]["gold_check_start_address"]), output_blocks[1])
    emit_axi_array(declarations, assignments, "INTERRUPT_ENABLE", control.interrupt_enable)
    emit_axi_array(declarations, assignments, "BS_CFG", control.bs_cfg)
    emit_axi_array(declarations, assignments, "KERNEL_CFG", control.kernel_cfg)
    assignments.append(f"  PCFG_ADDR = 13'h{control.pcfg_start.address:03x};")
    assignments.append(f"  PCFG_DATA = 32'h{control.pcfg_start.data:08x};")
    assignments.append(f"  STREAM_ADDR = 13'h{control.stream_start.address:03x};")
    assignments.append(f"  STREAM_DATA = 32'h{control.stream_start.data:08x};")
    assignments.append("  stimulus_ready = 1'b1;")
    lines = declarations + ["initial begin"] + assignments + ["end"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"generated {args.output}: {len(bitstream)} bitstream packets, {len(input0)}+{len(input1)} input packets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
