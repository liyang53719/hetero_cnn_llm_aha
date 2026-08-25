"""Frozen typed-descriptor record parsing and pre-issue chain validation."""
from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping


NULL_INDEX = 0xFF_FFFF
MAX_RECORDS = 16


class DescriptorChainError(ValueError):
    """Descriptor chain is unsafe to issue to an engine."""


@dataclass(frozen=True)
class DescriptorRecord:
    record_type: int
    subtype: int
    flags: int
    next_index: int
    payload: int

    def __post_init__(self) -> None:
        for name, value, bits in (
            ("record_type", self.record_type, 8), ("subtype", self.subtype, 8),
            ("flags", self.flags, 16), ("next_index", self.next_index, 24),
            ("payload", self.payload, 72),
        ):
            if not 0 <= value < (1 << bits):
                raise ValueError(f"{name} does not fit in {bits} bits")

    def pack(self) -> int:
        return (self.record_type | self.subtype << 8 | self.flags << 16 |
                self.next_index << 32 | self.payload << 56)

    @classmethod
    def unpack(cls, word: int) -> "DescriptorRecord":
        if not 0 <= word < (1 << 128):
            raise ValueError("descriptor word must be unsigned 128-bit")
        return cls(record_type=word & 0xFF, subtype=(word >> 8) & 0xFF,
                   flags=(word >> 16) & 0xFFFF,
                   next_index=(word >> 32) & 0xFF_FFFF,
                   payload=(word >> 56) & ((1 << 72) - 1))


def validate_descriptor_chain(
    first_index: int,
    records: Mapping[int, int | DescriptorRecord],
    *,
    allow_null_first: bool = False,
) -> tuple[tuple[int, DescriptorRecord], ...]:
    """Return a validated chain or reject before any engine command is issued."""

    if not 0 <= first_index <= NULL_INDEX:
        raise DescriptorChainError("first descriptor index does not fit in 24 bits")
    if first_index == NULL_INDEX:
        if allow_null_first:
            return ()
        raise DescriptorChainError("required descriptor chain starts at null index")

    result: list[tuple[int, DescriptorRecord]] = []
    visited: set[int] = set()
    index = first_index
    while index != NULL_INDEX:
        if index in visited:
            raise DescriptorChainError(f"descriptor chain cycle at index 0x{index:06x}")
        if len(result) >= MAX_RECORDS:
            raise DescriptorChainError(f"descriptor chain exceeds {MAX_RECORDS} records")
        if index not in records:
            raise DescriptorChainError(f"descriptor record 0x{index:06x} is missing")
        value = records[index]
        record = value if isinstance(value, DescriptorRecord) else DescriptorRecord.unpack(value)
        visited.add(index)
        result.append((index, record))
        index = record.next_index
    return tuple(result)
