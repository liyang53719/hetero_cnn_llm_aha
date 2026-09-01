"""Frozen typed-descriptor record parsing and pre-issue chain validation."""
from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping
from enum import IntEnum


NULL_INDEX = 0xFF_FFFF
MAX_RECORDS = 16


class RecordType(IntEnum):
    NULL = 0x00
    TENSOR_BASE = 0x01
    SHAPE4 = 0x02
    STRIDE3 = 0x03
    MATRIX_OP = 0x10
    CONV2D = 0x11
    MATRIX_AUX = 0x12
    SFU_PROGRAM = 0x20
    KV_ADDRESS = 0x30
    KV_FORMAT = 0x31
    QUANTIZATION = 0x40
    DMA_POLICY = 0x50
    EVENT_LIST4 = 0x60


class MatrixActivation(IntEnum):
    NONE = 0
    RELU = 1
    RELU6 = 2


class TensorDType(IntEnum):
    """Approved public tensor_base.dtype encoding."""

    INVALID = 0
    INT8 = 1
    INT32 = 4
    BF16 = 5
    FP16 = 6
    FP32 = 7


class CompletionStatus(IntEnum):
    OK = 0
    ILLEGAL_OPCODE_ENGINE = 1
    MALFORMED_CHAIN = 2
    DESCRIPTOR_FETCH_ERROR = 3
    UNSUPPORTED_POLICY = 4
    RANGE_RESOURCE_OVERFLOW = 5
    WATCHDOG_TIMEOUT = 6
    MACRO_PROTOCOL_ERROR = 7
    KV_OOM = 8
    KV_STALE_GENERATION = 9
    KV_REFCOUNT_COW_INVARIANT = 10


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
        if self.subtype != 0 or self.flags != 0:
            raise ValueError("descriptor v2 common subtype and flags must be zero")
        try:
            RecordType(self.record_type)
        except ValueError as exc:
            raise ValueError(f"unknown descriptor record type 0x{self.record_type:02x}") from exc

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


@dataclass(frozen=True)
class MatrixAux:
    bias_index: int = NULL_INDEX
    activation: MatrixActivation = MatrixActivation.NONE
    full_c: bool = False
    low_d: bool = False
    repeating_bias: bool = False
    no_pool: bool = True
    downsample: bool = False
    input_dilated: bool = False
    wrot180: bool = False
    trans_output_1203: bool = False
    trans_weight_1203: bool = False
    trans_weight_0132: bool = False
    trans_input_3120: bool = False
    depthwise: bool = False
    a_spad_id: int = 0
    b_spad_id: int = 0
    max_pixels_per_row: int = 1
    pad_bottom: int = 0
    pad_right: int = 0
    subarray_mask: int = 1

    def __post_init__(self) -> None:
        for name, value, bits in (
            ("bias_index", self.bias_index, 24), ("a_spad_id", self.a_spad_id, 2),
            ("b_spad_id", self.b_spad_id, 2),
            ("max_pixels_per_row", self.max_pixels_per_row, 8),
            ("pad_bottom", self.pad_bottom, 6), ("pad_right", self.pad_right, 6),
            ("subarray_mask", self.subarray_mask, 8),
        ):
            if not 0 <= int(value) < (1 << bits):
                raise ValueError(f"{name} does not fit in {bits} bits")
        if self.subarray_mask == 0:
            raise ValueError("matrix_aux subarray_mask must be nonzero")
        if int(self.activation) not in {0, 1, 2}:
            raise ValueError("matrix_aux activation is reserved")

    def payload(self) -> int:
        booleans = (
            self.full_c, self.low_d, self.repeating_bias, self.no_pool,
            self.downsample, self.input_dilated, self.wrot180,
            self.trans_output_1203, self.trans_weight_1203,
            self.trans_weight_0132, self.trans_input_3120, self.depthwise,
        )
        value = self.bias_index | int(self.activation) << 24
        for offset, enabled in enumerate(booleans, start=26):
            value |= int(enabled) << offset
        value |= self.a_spad_id << 38 | self.b_spad_id << 40
        value |= self.max_pixels_per_row << 42
        value |= self.pad_bottom << 50 | self.pad_right << 56
        value |= self.subarray_mask << 62
        return value

    def to_record(self, next_index: int = NULL_INDEX) -> DescriptorRecord:
        return DescriptorRecord(RecordType.MATRIX_AUX, 0, 0, next_index, self.payload())

    @classmethod
    def from_record(cls, record: DescriptorRecord) -> "MatrixAux":
        if record.record_type != RecordType.MATRIX_AUX:
            raise ValueError("record is not matrix_aux")
        p = record.payload
        if p >> 70:
            raise ValueError("matrix_aux reserved bits must be zero")
        flags = [bool((p >> bit) & 1) for bit in range(26, 38)]
        return cls(
            bias_index=p & 0xFFFFFF, activation=MatrixActivation((p >> 24) & 0x3),
            full_c=flags[0], low_d=flags[1], repeating_bias=flags[2],
            no_pool=flags[3], downsample=flags[4], input_dilated=flags[5],
            wrot180=flags[6], trans_output_1203=flags[7],
            trans_weight_1203=flags[8], trans_weight_0132=flags[9],
            trans_input_3120=flags[10], depthwise=flags[11],
            a_spad_id=(p >> 38) & 0x3, b_spad_id=(p >> 40) & 0x3,
            max_pixels_per_row=(p >> 42) & 0xFF,
            pad_bottom=(p >> 50) & 0x3F, pad_right=(p >> 56) & 0x3F,
            subarray_mask=(p >> 62) & 0xFF,
        )


@dataclass(frozen=True)
class SfuProgram:
    """Approved descriptor type 0x20 payload for dedicated or registry SFUs."""

    program_id: int
    input_count: int
    output_count: int = 1
    input_dtype: TensorDType = TensorDType.BF16
    output_dtype: TensorDType = TensorDType.BF16
    lane_width_bits: int = 16
    vector_lanes: int = 0
    program_flags: int = 0

    def __post_init__(self) -> None:
        for name, value, bits in (
            ("program_id", self.program_id, 16), ("input_count", self.input_count, 8),
            ("output_count", self.output_count, 8),
            ("input_dtype", int(self.input_dtype), 4),
            ("output_dtype", int(self.output_dtype), 4),
            ("lane_width_bits", self.lane_width_bits, 8),
            ("vector_lanes", self.vector_lanes, 8),
            ("program_flags", self.program_flags, 8),
        ):
            if not 0 <= int(value) < (1 << bits):
                raise ValueError(f"{name} does not fit in {bits} bits")
        if self.input_count not in {1, 2}:
            raise ValueError("SFU input_count must be one or two")
        if self.output_count != 1:
            raise ValueError("approved SFU output_count must be one")
        if self.input_dtype == TensorDType.INVALID or self.output_dtype == TensorDType.INVALID:
            raise ValueError("SFU dtype must not be invalid")

    def payload(self) -> int:
        return (self.program_id | self.input_count << 16 | self.output_count << 24 |
                int(self.input_dtype) << 32 | int(self.output_dtype) << 36 |
                self.lane_width_bits << 40 | self.vector_lanes << 48 |
                self.program_flags << 56)

    def to_record(self, next_index: int = NULL_INDEX) -> DescriptorRecord:
        return DescriptorRecord(RecordType.SFU_PROGRAM, 0, 0, next_index, self.payload())

    @classmethod
    def from_record(cls, record: DescriptorRecord) -> "SfuProgram":
        if record.record_type != RecordType.SFU_PROGRAM:
            raise ValueError("record is not sfu_program")
        p = record.payload
        if p >> 64:
            raise ValueError("sfu_program reserved bits must be zero")
        return cls(
            program_id=p & 0xFFFF, input_count=(p >> 16) & 0xFF,
            output_count=(p >> 24) & 0xFF,
            input_dtype=TensorDType((p >> 32) & 0xF),
            output_dtype=TensorDType((p >> 36) & 0xF),
            lane_width_bits=(p >> 40) & 0xFF,
            vector_lanes=(p >> 48) & 0xFF,
            program_flags=(p >> 56) & 0xFF,
        )


@dataclass(frozen=True)
class DmaPolicy:
    max_burst_beats: int
    max_outstanding: int
    read_qos: int = 0
    write_qos: int = 0
    allow_unaligned: bool = False
    coalesce: bool = False
    ordered: bool = True

    def __post_init__(self) -> None:
        for name, value, bits in (
            ("max_burst_beats", self.max_burst_beats, 8),
            ("max_outstanding", self.max_outstanding, 8),
            ("read_qos", self.read_qos, 4), ("write_qos", self.write_qos, 4),
        ):
            if not 0 <= int(value) < (1 << bits):
                raise ValueError(f"{name} does not fit in {bits} bits")
        if self.max_burst_beats == 0 or self.max_outstanding == 0:
            raise ValueError("DMA burst and outstanding values must be nonzero")

    def payload(self) -> int:
        return (self.max_burst_beats | self.max_outstanding << 8 |
                self.read_qos << 16 | self.write_qos << 20 |
                int(self.allow_unaligned) << 24 | int(self.coalesce) << 25 |
                int(self.ordered) << 26)

    def to_record(self, next_index: int = NULL_INDEX) -> DescriptorRecord:
        return DescriptorRecord(RecordType.DMA_POLICY, 0, 0, next_index, self.payload())

    @classmethod
    def from_record(cls, record: DescriptorRecord) -> "DmaPolicy":
        if record.record_type != RecordType.DMA_POLICY:
            raise ValueError("record is not dma_policy")
        p = record.payload
        if p >> 27:
            raise ValueError("dma_policy reserved bits must be zero")
        return cls(p & 0xFF, (p >> 8) & 0xFF, (p >> 16) & 0xF,
                   (p >> 20) & 0xF, bool((p >> 24) & 1),
                   bool((p >> 25) & 1), bool((p >> 26) & 1))


@dataclass(frozen=True)
class EventList4:
    events: tuple[int, ...]

    def __post_init__(self) -> None:
        if not 1 <= len(self.events) <= 4:
            raise ValueError("event_list4 contains one to four events")
        if any(not 1 <= int(event) < (1 << 16) for event in self.events):
            raise ValueError("barrier event IDs must be nonzero 16-bit values")

    def payload(self) -> int:
        value = len(self.events)
        for offset, event in enumerate(self.events):
            value |= int(event) << (4 + offset * 16)
        return value

    def to_record(self, next_index: int = NULL_INDEX) -> DescriptorRecord:
        return DescriptorRecord(RecordType.EVENT_LIST4, 0, 0, next_index, self.payload())

    @classmethod
    def from_record(cls, record: DescriptorRecord) -> "EventList4":
        if record.record_type != RecordType.EVENT_LIST4:
            raise ValueError("record is not event_list4")
        p = record.payload
        if p >> 68:
            raise ValueError("event_list4 reserved bits must be zero")
        count = p & 0xF
        if not 1 <= count <= 4:
            raise ValueError("event_list4 count must be in 1..4")
        return cls(tuple((p >> (4 + index * 16)) & 0xFFFF for index in range(count)))


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
