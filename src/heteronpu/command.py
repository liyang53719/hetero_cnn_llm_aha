from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

NULL_INDEX = 0xFF_FFFF


class Engine(IntEnum):
    CONTROL = 0
    DMA = 1
    MATRIX = 2
    SFU_CGRA = 3
    KV = 4
    COLLECTIVE = 5


class Opcode(IntEnum):
    NOP = 0x00
    DMA_1D = 0x10
    DMA_2D = 0x11
    MATRIX_GEMM = 0x20
    MATRIX_GEMV = 0x21
    MATRIX_CONV = 0x22
    MATRIX_QK = 0x23
    MATRIX_PV = 0x24
    SFU_VECTOR = 0x30
    SFU_REDUCE = 0x31
    SFU_RMSNORM = 0x32
    SFU_SOFTMAX = 0x33
    SFU_ROPE = 0x34
    SFU_ACTIVATION = 0x35
    KV_ALLOC = 0x40
    KV_APPEND = 0x41
    KV_GATHER = 0x42
    KV_SHARE_PREFIX = 0x43
    KV_FREE = 0x44
    BARRIER = 0x50


_EXPECTED_ENGINE: dict[Opcode, Engine] = {
    Opcode.NOP: Engine.CONTROL,
    Opcode.DMA_1D: Engine.DMA,
    Opcode.DMA_2D: Engine.DMA,
    Opcode.MATRIX_GEMM: Engine.MATRIX,
    Opcode.MATRIX_GEMV: Engine.MATRIX,
    Opcode.MATRIX_CONV: Engine.MATRIX,
    Opcode.MATRIX_QK: Engine.MATRIX,
    Opcode.MATRIX_PV: Engine.MATRIX,
    Opcode.SFU_VECTOR: Engine.SFU_CGRA,
    Opcode.SFU_REDUCE: Engine.SFU_CGRA,
    Opcode.SFU_RMSNORM: Engine.SFU_CGRA,
    Opcode.SFU_SOFTMAX: Engine.SFU_CGRA,
    Opcode.SFU_ROPE: Engine.SFU_CGRA,
    Opcode.SFU_ACTIVATION: Engine.SFU_CGRA,
    Opcode.KV_ALLOC: Engine.KV,
    Opcode.KV_APPEND: Engine.KV,
    Opcode.KV_GATHER: Engine.KV,
    Opcode.KV_SHARE_PREFIX: Engine.KV,
    Opcode.KV_FREE: Engine.KV,
    Opcode.BARRIER: Engine.CONTROL,
}


@dataclass(frozen=True)
class Command128:
    """Frozen 128-bit command envelope.

    The three 24-bit address fields index typed descriptors.  Tensor shapes,
    strides, datatypes, scales and KV metadata are intentionally not embedded
    in the instruction word.
    """

    opcode: Opcode
    engine: Engine
    flags: int = 0
    event_wait: int = 0
    event_signal: int = 0
    src0: int = NULL_INDEX
    src1: int = NULL_INDEX
    dst: int = NULL_INDEX

    def __post_init__(self) -> None:
        limits = {
            "flags": (self.flags, 13),
            "event_wait": (self.event_wait, 16),
            "event_signal": (self.event_signal, 16),
            "src0": (self.src0, 24),
            "src1": (self.src1, 24),
            "dst": (self.dst, 24),
        }
        for name, (value, bits) in limits.items():
            if not 0 <= int(value) < (1 << bits):
                raise ValueError(f"{name} does not fit in {bits} bits")
        expected = _EXPECTED_ENGINE.get(self.opcode)
        if expected is not None and expected != self.engine:
            raise ValueError(
                f"opcode {self.opcode.name} belongs to {expected.name}, not {self.engine.name}"
            )
        required, forbidden = _root_contract(self.opcode)
        roots = {"src0": self.src0, "src1": self.src1, "dst": self.dst}
        missing = sorted(name for name in required if roots[name] == NULL_INDEX)
        unexpected = sorted(name for name in forbidden if roots[name] != NULL_INDEX)
        if missing or unexpected:
            raise ValueError(
                f"opcode {self.opcode.name} descriptor roots invalid: "
                f"missing={missing} unexpected={unexpected}"
            )

    def pack(self) -> int:
        word = int(self.opcode)
        word |= int(self.engine) << 8
        word |= int(self.flags) << 11
        word |= int(self.event_wait) << 24
        word |= int(self.event_signal) << 40
        word |= int(self.src0) << 56
        word |= int(self.src1) << 80
        word |= int(self.dst) << 104
        if word >= (1 << 128):
            raise AssertionError("packed command exceeds 128 bits")
        return word

    def to_bytes(self) -> bytes:
        return self.pack().to_bytes(16, byteorder="little", signed=False)

    @classmethod
    def unpack(cls, word: int) -> "Command128":
        if not 0 <= int(word) < (1 << 128):
            raise ValueError("word must be an unsigned 128-bit integer")
        opcode = Opcode(word & 0xFF)
        engine = Engine((word >> 8) & 0x7)
        return cls(
            opcode=opcode,
            engine=engine,
            flags=(word >> 11) & 0x1FFF,
            event_wait=(word >> 24) & 0xFFFF,
            event_signal=(word >> 40) & 0xFFFF,
            src0=(word >> 56) & 0xFFFFFF,
            src1=(word >> 80) & 0xFFFFFF,
            dst=(word >> 104) & 0xFFFFFF,
        )

    @classmethod
    def from_bytes(cls, payload: bytes) -> "Command128":
        if len(payload) != 16:
            raise ValueError("a command must contain exactly 16 bytes")
        return cls.unpack(int.from_bytes(payload, byteorder="little", signed=False))


def _root_contract(opcode: Opcode) -> tuple[frozenset[str], frozenset[str]]:
    all_roots = frozenset({"src0", "src1", "dst"})
    if opcode is Opcode.NOP:
        return frozenset(), all_roots
    if opcode in {Opcode.DMA_1D, Opcode.DMA_2D, Opcode.MATRIX_GEMM,
                  Opcode.MATRIX_GEMV, Opcode.MATRIX_CONV, Opcode.MATRIX_QK,
                  Opcode.MATRIX_PV, Opcode.KV_APPEND}:
        return all_roots, frozenset()
    if opcode in {Opcode.SFU_VECTOR, Opcode.SFU_REDUCE, Opcode.SFU_RMSNORM,
                  Opcode.SFU_SOFTMAX, Opcode.SFU_ROPE, Opcode.SFU_ACTIVATION}:
        return frozenset({"src0", "dst"}), frozenset()
    if opcode in {Opcode.KV_GATHER, Opcode.KV_SHARE_PREFIX}:
        return frozenset({"src0", "dst"}), frozenset({"src1"})
    if opcode in {Opcode.KV_ALLOC, Opcode.KV_FREE, Opcode.BARRIER}:
        return frozenset({"src0"}), frozenset({"src1", "dst"})
    raise ValueError(f"root contract is undefined for opcode {opcode!r}")
