"""Lossless lowering of exported AHA bitstreams into proc-packet beats."""
from __future__ import annotations

from dataclasses import dataclass
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
