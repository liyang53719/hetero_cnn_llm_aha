"""Pinned GGML block-layout, dequantization, and dot-product references.

This module implements the byte layouts currently used by llama.cpp for
Q8_0, Q6_K, Q3_K, and FP16. It deliberately separates the operand frontend
(unpack/sign/scale) from the shared dot-product operation so the architecture
does not grow one multiplier array per storage format.

The Q3_K/Q6_K routines are layout/dequantization references. Official
llama.cpp C parity remains a separate local gate because this sandbox cannot
build the pinned upstream revision.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import random
import struct
from typing import Iterable, Sequence

QK8_0 = 32
QK_K = 256
Q8_0_BYTES = 2 + QK8_0
Q6_K_BYTES = QK_K // 2 + QK_K // 4 + QK_K // 16 + 2
Q3_K_BYTES = QK_K // 8 + QK_K // 4 + 12 + 2
PINNED_LLAMA_CPP_COMMIT = "0b5be7e4a25862bc2777d0c47eae18788a8c963a"


def fp16_to_float(bits: int) -> float:
    if not 0 <= int(bits) <= 0xFFFF:
        raise ValueError("FP16 bits")
    return struct.unpack("<e", int(bits).to_bytes(2, "little"))[0]


def float_to_fp16_bits(value: float) -> int:
    return int.from_bytes(struct.pack("<e", float(value)), "little")


def pack_fp16(values: Iterable[float]) -> bytes:
    return b"".join(struct.pack("<e", float(value)) for value in values)


def unpack_fp16(payload: bytes) -> tuple[float, ...]:
    if len(payload) % 2:
        raise ValueError("FP16 payload must contain complete half words")
    return tuple(
        struct.unpack_from("<e", payload, offset)[0]
        for offset in range(0, len(payload), 2)
    )


def _int8(value: int) -> int:
    value &= 0xFF
    return value - 256 if value >= 128 else value


@dataclass(frozen=True)
class OperandGroup:
    """Signed integer operands plus one post-dot scale."""

    offset: int
    quants: tuple[int, ...]
    scale: float

    def dot(self, activations: Sequence[float]) -> float:
        if len(activations) != len(self.quants):
            raise ValueError("activation group length")
        return self.scale * sum(
            quant * float(activation)
            for quant, activation in zip(self.quants, activations)
        )


@dataclass(frozen=True)
class Q8_0Block:
    d_bits: int
    qs: tuple[int, ...]

    def __post_init__(self) -> None:
        if len(self.qs) != QK8_0 or any(q < -128 or q > 127 for q in self.qs):
            raise ValueError("Q8_0 geometry")
        fp16_to_float(self.d_bits)

    @property
    def scale(self) -> float:
        return fp16_to_float(self.d_bits)

    def pack(self) -> bytes:
        return self.d_bits.to_bytes(2, "little") + bytes(q & 0xFF for q in self.qs)

    @classmethod
    def unpack(cls, payload: bytes) -> "Q8_0Block":
        if len(payload) != Q8_0_BYTES:
            raise ValueError("Q8_0 block size")
        return cls(
            int.from_bytes(payload[:2], "little"),
            tuple(_int8(value) for value in payload[2:]),
        )

    def groups(self) -> tuple[OperandGroup, ...]:
        return (OperandGroup(0, self.qs, self.scale),)

    def dequantize(self) -> tuple[float, ...]:
        return tuple(self.scale * quant for quant in self.qs)


@dataclass(frozen=True)
class Q6KBlock:
    ql: bytes
    qh: bytes
    scales: tuple[int, ...]
    d_bits: int

    def __post_init__(self) -> None:
        if len(self.ql) != 128 or len(self.qh) != 64 or len(self.scales) != 16:
            raise ValueError("Q6_K geometry")
        if any(scale < -128 or scale > 127 for scale in self.scales):
            raise ValueError("Q6_K scale range")
        fp16_to_float(self.d_bits)

    @property
    def d(self) -> float:
        return fp16_to_float(self.d_bits)

    def pack(self) -> bytes:
        return (
            self.ql
            + self.qh
            + bytes(scale & 0xFF for scale in self.scales)
            + self.d_bits.to_bytes(2, "little")
        )

    @classmethod
    def unpack(cls, payload: bytes) -> "Q6KBlock":
        if len(payload) != Q6_K_BYTES:
            raise ValueError("Q6_K block size")
        return cls(
            payload[:128],
            payload[128:192],
            tuple(_int8(value) for value in payload[192:208]),
            int.from_bytes(payload[208:210], "little"),
        )

    def _quant_and_scale(self) -> tuple[tuple[int, ...], tuple[float, ...]]:
        quants = [0] * QK_K
        scales = [0.0] * QK_K
        d = self.d
        for half in range(2):
            ql_base = half * 64
            qh_base = half * 32
            scale_base = half * 8
            output_base = half * 128
            for lane in range(32):
                scale_lane = lane // 16
                high = self.qh[qh_base + lane]
                q0 = (self.ql[ql_base + lane] & 0x0F) | (((high >> 0) & 0x03) << 4)
                q1 = (self.ql[ql_base + lane + 32] & 0x0F) | (((high >> 2) & 0x03) << 4)
                q2 = (self.ql[ql_base + lane] >> 4) | (((high >> 4) & 0x03) << 4)
                q3 = (self.ql[ql_base + lane + 32] >> 4) | (((high >> 6) & 0x03) << 4)
                for offset, quant, scale_index in (
                    (0, q0 - 32, scale_base + scale_lane),
                    (32, q1 - 32, scale_base + scale_lane + 2),
                    (64, q2 - 32, scale_base + scale_lane + 4),
                    (96, q3 - 32, scale_base + scale_lane + 6),
                ):
                    index = output_base + lane + offset
                    quants[index] = quant
                    scales[index] = d * self.scales[scale_index]
        return tuple(quants), tuple(scales)

    def groups(self) -> tuple[OperandGroup, ...]:
        quants, scales = self._quant_and_scale()
        groups: list[OperandGroup] = []
        for offset in range(0, QK_K, 16):
            scale = scales[offset]
            if any(value != scale for value in scales[offset : offset + 16]):
                raise AssertionError("Q6_K subscale boundary")
            groups.append(OperandGroup(offset, quants[offset : offset + 16], scale))
        return tuple(groups)

    def dequantize(self) -> tuple[float, ...]:
        quants, scales = self._quant_and_scale()
        return tuple(quant * scale for quant, scale in zip(quants, scales))


def unpack_q3k_scales(payload: bytes) -> tuple[int, ...]:
    """Unpack the 12-byte Q3_K field into sixteen signed scale values."""
    if len(payload) != 12:
        raise ValueError("Q3_K scale payload")
    aux = list(struct.unpack("<4I", payload + b"\x00" * 4))
    temporary = aux[2]
    aux[2] = ((aux[0] >> 4) & 0x0F0F0F0F) | (((temporary >> 0) & 0x03030303) << 4)
    aux[3] = ((aux[1] >> 4) & 0x0F0F0F0F) | (((temporary >> 2) & 0x03030303) << 4)
    aux[0] = (aux[0] & 0x0F0F0F0F) | (((temporary >> 4) & 0x03030303) << 4)
    aux[1] = (aux[1] & 0x0F0F0F0F) | (((temporary >> 6) & 0x03030303) << 4)
    return tuple(value - 32 for value in struct.pack("<4I", *aux))


@dataclass(frozen=True)
class Q3KBlock:
    hmask: bytes
    qs: bytes
    scales_packed: bytes
    d_bits: int

    def __post_init__(self) -> None:
        if len(self.hmask) != 32 or len(self.qs) != 64 or len(self.scales_packed) != 12:
            raise ValueError("Q3_K geometry")
        fp16_to_float(self.d_bits)

    @property
    def d(self) -> float:
        return fp16_to_float(self.d_bits)

    @property
    def scales(self) -> tuple[int, ...]:
        return unpack_q3k_scales(self.scales_packed)

    def pack(self) -> bytes:
        return self.hmask + self.qs + self.scales_packed + self.d_bits.to_bytes(2, "little")

    @classmethod
    def unpack(cls, payload: bytes) -> "Q3KBlock":
        if len(payload) != Q3_K_BYTES:
            raise ValueError("Q3_K block size")
        return cls(
            payload[:32],
            payload[32:96],
            payload[96:108],
            int.from_bytes(payload[108:110], "little"),
        )

    def _quant_and_scale(self) -> tuple[tuple[int, ...], tuple[float, ...]]:
        quants = [0] * QK_K
        scales = [0.0] * QK_K
        subscales = self.scales
        d = self.d
        for half in range(2):
            quant_base = half * 32
            output_base = half * 128
            mask_base = 1 << (half * 4)
            scale_base = half * 8
            for lane in range(32):
                scale_lane = lane // 16
                packed = self.qs[quant_base + lane]
                high_mask = self.hmask[lane]
                for group in range(4):
                    low = (packed >> (2 * group)) & 0x03
                    signed_quant = low if high_mask & (mask_base << group) else low - 4
                    index = output_base + lane + 32 * group
                    scale_index = scale_base + scale_lane + 2 * group
                    quants[index] = signed_quant
                    scales[index] = d * subscales[scale_index]
        return tuple(quants), tuple(scales)

    def groups(self) -> tuple[OperandGroup, ...]:
        quants, scales = self._quant_and_scale()
        groups: list[OperandGroup] = []
        for offset in range(0, QK_K, 16):
            scale = scales[offset]
            if any(value != scale for value in scales[offset : offset + 16]):
                raise AssertionError("Q3_K subscale boundary")
            groups.append(OperandGroup(offset, quants[offset : offset + 16], scale))
        return tuple(groups)

    def dequantize(self) -> tuple[float, ...]:
        quants, scales = self._quant_and_scale()
        return tuple(quant * scale for quant, scale in zip(quants, scales))


def dot_groups(groups: Iterable[OperandGroup], activations: Sequence[float]) -> float:
    total = 0.0
    covered = 0
    for group in groups:
        end = group.offset + len(group.quants)
        total += group.dot(activations[group.offset:end])
        covered = max(covered, end)
    if covered != len(activations):
        raise ValueError("operand groups do not cover activation vector")
    return total


def random_q8_0(seed: int) -> Q8_0Block:
    rng = random.Random(seed)
    return Q8_0Block(
        float_to_fp16_bits(rng.uniform(0.001, 0.25)),
        tuple(rng.randint(-127, 127) for _ in range(QK8_0)),
    )


def random_q6_k(seed: int) -> Q6KBlock:
    rng = random.Random(seed)
    return Q6KBlock(
        bytes(rng.randrange(256) for _ in range(128)),
        bytes(rng.randrange(256) for _ in range(64)),
        tuple(rng.randint(-127, 127) for _ in range(16)),
        float_to_fp16_bits(rng.uniform(0.0001, 0.1)),
    )


def random_q3_k(seed: int) -> Q3KBlock:
    rng = random.Random(seed)
    return Q3KBlock(
        bytes(rng.randrange(256) for _ in range(32)),
        bytes(rng.randrange(256) for _ in range(64)),
        bytes(rng.randrange(256) for _ in range(12)),
        float_to_fp16_bits(rng.uniform(0.0001, 0.1)),
    )


def format_contract() -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "PASS",
        "pinned_llama_cpp_commit": PINNED_LLAMA_CPP_COMMIT,
        "formats": {
            "FP16": {"values_per_word": 1, "bytes_per_value": 2},
            "Q8_0": {"values": QK8_0, "bytes": Q8_0_BYTES, "bits_per_weight": 8.5, "groups": 1},
            "Q6_K": {"values": QK_K, "bytes": Q6_K_BYTES, "bits_per_weight": 8 * Q6_K_BYTES / QK_K, "groups": 16},
            "Q3_K": {"values": QK_K, "bytes": Q3_K_BYTES, "bits_per_weight": 8 * Q3_K_BYTES / QK_K, "groups": 16},
        },
        "hardware_contract": {
            "shared_integer_dot_array": True,
            "format_specific_blocks": ["byte_unpack", "sign_restore", "subscale_lookup"],
            "format_specific_multiplier_array": False,
            "post_dot_scale": True,
        },
        "remaining_local_gate": "compile pinned llama.cpp and compare >=10000 blocks per format",
    }


def self_test_report(cases: int = 1000) -> dict[str, object]:
    digest = hashlib.sha256()
    maximum_error = 0.0
    for case in range(cases):
        for block in (random_q8_0(case), random_q6_k(case), random_q3_k(case)):
            payload = block.pack()
            if type(block).unpack(payload) != block:
                raise AssertionError("byte roundtrip")
            values = block.dequantize()
            activations = [
                math.sin((case + 1) * (index + 3) * 0.001)
                for index in range(len(values))
            ]
            direct = sum(weight * activation for weight, activation in zip(values, activations))
            grouped = dot_groups(block.groups(), activations)
            maximum_error = max(maximum_error, abs(direct - grouped))
            digest.update(payload)
            digest.update(struct.pack("<d", grouped))
    fp16_values = tuple(math.sin(index / 17) for index in range(257))
    fp16_payload = pack_fp16(fp16_values)
    if pack_fp16(unpack_fp16(fp16_payload)) != fp16_payload:
        raise AssertionError("FP16 byte roundtrip")
    return {
        "schema_version": 1,
        "status": "PASS",
        "cases_per_quant_format": cases,
        "byte_roundtrips": cases * 3,
        "maximum_grouped_dot_difference": maximum_error,
        "sha256": digest.hexdigest(),
        "contract": format_contract(),
        "evidence_class": "layout_dequant_dot_E0_not_official_llama_cpp_parity",
    }
