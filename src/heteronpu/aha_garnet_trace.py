"""Lossless lowering of exported AHA bitstreams into proc-packet beats."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re


BITSTREAM_LINE = re.compile(r"^([0-9A-Fa-f]{8})\s+([0-9A-Fa-f]{8})$")


@dataclass(frozen=True)
class AhaBitstreamEntry:
    address: int
    data: int

    @property
    def packed_word(self) -> int:
        """Match the official packed SV struct ``{addr, data}``."""

        return (self.address << 32) | self.data


@dataclass(frozen=True)
class AhaProcPacket512:
    address: int
    data: int
    byte_enable: int
    valid_words: int


@dataclass(frozen=True)
class AhaAxiWrite:
    address: int
    data: int


@dataclass(frozen=True)
class AhaControlTable:
    bitstream_tile: int
    bitstream_start_address: int
    bitstream_entries: int
    bs_cfg: tuple[AhaAxiWrite, ...]
    kernel_cfg: tuple[AhaAxiWrite, ...]
    interrupt_enable: tuple[AhaAxiWrite, ...]
    pcfg_start: AhaAxiWrite
    stream_start: AhaAxiWrite


def parse_bitstream(path: str | Path) -> tuple[AhaBitstreamEntry, ...]:
    entries: list[AhaBitstreamEntry] = []
    for line_number, raw in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        match = BITSTREAM_LINE.fullmatch(raw)
        if match is None:
            raise ValueError(f"{path}:{line_number}: expected exactly two 32-bit hex words")
        entries.append(AhaBitstreamEntry(int(match.group(1), 16), int(match.group(2), 16)))
    if not entries:
        raise ValueError(f"{path}: bitstream is empty")
    return tuple(entries)


def pack_proc_packets(entries: tuple[AhaBitstreamEntry, ...], *, base_address: int) -> tuple[AhaProcPacket512, ...]:
    """Pack eight AHA 64-bit bitstream entries per project 512-bit beat.

    The first source entry occupies bits ``[63:0]`` and goes to the first
    proc-packet write, precisely matching ``ProcDriver_write_bs`` followed by
    ``aha_garnet_proc_packet_writer``.
    """

    if not 0 <= base_address < (1 << 18):
        raise ValueError("base_address must fit the Garnet 18-bit proc-packet address")
    packets: list[AhaProcPacket512] = []
    for packet_index, start in enumerate(range(0, len(entries), 8)):
        group = entries[start:start + 8]
        data = sum(entry.packed_word << (64 * index) for index, entry in enumerate(group))
        byte_enable = (1 << (8 * len(group))) - 1
        packets.append(AhaProcPacket512(
            address=base_address + packet_index * 64,
            data=data,
            byte_enable=byte_enable,
            valid_words=len(group),
        ))
    return tuple(packets)


def load_control_table(path: str | Path) -> AhaControlTable:
    """Load the exact official AHA parser/map AXI control table."""

    raw = json.loads(Path(path).read_text(encoding="utf-8"))

    def write(item: object) -> AhaAxiWrite:
        if not isinstance(item, dict):
            raise ValueError("control-table entry must be a mapping")
        address = int(item["address"])
        data = int(item["data"])
        if not 0 <= address < (1 << 13):
            raise ValueError(f"AXI address {address:#x} does not fit Garnet's 13-bit interface")
        if not 0 <= data < (1 << 32):
            raise ValueError(f"AXI data {data:#x} does not fit 32 bits")
        return AhaAxiWrite(address, data)

    bs_cfg = tuple(write(item) for item in raw["bs_cfg"])
    kernel_cfg = tuple(write(item) for item in raw["kernel_cfg"])
    interrupt_enable = tuple(write(item) for item in raw["interrupt_enable"])
    if not bs_cfg or not kernel_cfg or not interrupt_enable:
        raise ValueError("official AHA control table has an empty configuration group")
    return AhaControlTable(
        bitstream_tile=int(raw["bitstream_tile"]),
        bitstream_start_address=int(raw["bitstream_start_address"]),
        bitstream_entries=int(raw["bitstream_entries"]),
        bs_cfg=bs_cfg,
        kernel_cfg=kernel_cfg,
        interrupt_enable=interrupt_enable,
        pcfg_start=write(raw["pcfg_start"]),
        stream_start=write(raw["stream_start"]),
    )


def pack_raw_packets(payload: bytes, *, base_address: int) -> tuple[AhaProcPacket512, ...]:
    """Pack a byte stream into low-byte-first 512-bit proc-packet beats."""

    if not payload:
        raise ValueError("payload must not be empty")
    if not 0 <= base_address < (1 << 18):
        raise ValueError("base_address must fit the Garnet 18-bit proc-packet address")
    packets: list[AhaProcPacket512] = []
    for index, start in enumerate(range(0, len(payload), 64)):
        chunk = payload[start:start + 64]
        packets.append(AhaProcPacket512(
            address=base_address + index * 64,
            data=int.from_bytes(chunk, byteorder="little", signed=False),
            byte_enable=(1 << len(chunk)) - 1,
            valid_words=(len(chunk) + 7) // 8,
        ))
    return tuple(packets)


def split_interleaved_u16(payload: bytes, tile_count: int) -> tuple[bytes, ...]:
    """Match test_app's default ``input_data[j + num_tiles*k]`` distribution."""

    if tile_count <= 0:
        raise ValueError("tile_count must be positive")
    if len(payload) % 2:
        raise ValueError("16-bit input payload has an odd byte count")
    words = [payload[index:index + 2] for index in range(0, len(payload), 2)]
    if len(words) % tile_count:
        raise ValueError("16-bit input word count is not divisible by tile_count")
    return tuple(b"".join(words[tile::tile_count]) for tile in range(tile_count))
