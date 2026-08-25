"""Pinned Gemmini RoCC micro-op encoders used by the L2 descriptor path.

This is intentionally a lowering *primitive*, not a replacement Gemmini model.
It transcribes the official ``gemmini.h`` C macros for the locked
GemminiRocketConfig.  A typed project descriptor supplies the addresses and
tile dimensions; RocketTile still supplies status, PTW and TileLink context.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


ADDR_LEN = 32
CUSTOM3_OPCODE = 0x7B


class GemminiFunct(IntEnum):
    CONFIG = 0
    MVIN2 = 1
    MVIN = 2
    MVOUT = 3
    COMPUTE_PRELOADED = 4
    COMPUTE_ACCUMULATE = 5
    PRELOAD = 6
    FLUSH = 7
    MVIN3 = 14
    MVOUT_SPAD = 23
    COUNTER = 126


@dataclass(frozen=True)
class RoCCMicroOp:
    """One official CUSTOM_3 RoCC instruction as seen by RocketTile."""

    funct: GemminiFunct
    rs1: int
    rs2: int
    # Standard Gemmini C macros use ``ROCC_INSTRUCTION_0_R_R``: no result.
    xd: bool = False
    xs1: bool = True
    xs2: bool = True
    rd: int = 0
    opcode: int = CUSTOM3_OPCODE

    def __post_init__(self) -> None:
        for name, value, bits in (
            ("funct", int(self.funct), 7), ("rs1", self.rs1, 64),
            ("rs2", self.rs2, 64), ("rd", self.rd, 5), ("opcode", self.opcode, 7),
        ):
            if not 0 <= value < (1 << bits):
                raise ValueError(f"{name} does not fit in {bits} bits")
        if self.opcode != CUSTOM3_OPCODE:
            raise ValueError("locked GemminiRocketConfig accepts only CUSTOM_3")


def _unsigned(name: str, value: int, bits: int) -> int:
    if not 0 <= value < (1 << bits):
        raise ValueError(f"{name} does not fit in {bits} bits")
    return value


def pack_local_addr_rows_cols(local_addr: int, cols: int, rows: int) -> int:
    """Exact ``gemmini_extended_*`` address/shape packing from gemmini.h."""

    return (
        _unsigned("local_addr", local_addr, ADDR_LEN)
        | (_unsigned("cols", cols, 16) << ADDR_LEN)
        | (_unsigned("rows", rows, 16) << (ADDR_LEN + 16))
    )


def mvin(dram_addr: int, local_addr: int, cols: int, rows: int, *, channel: int = 0) -> RoCCMicroOp:
    """Encode official mvin/mvin2/mvin3, without inventing DMA behavior."""

    funct = {0: GemminiFunct.MVIN, 1: GemminiFunct.MVIN2, 2: GemminiFunct.MVIN3}.get(channel)
    if funct is None:
        raise ValueError("channel must be 0 (mvin), 1 (mvin2), or 2 (mvin3)")
    return RoCCMicroOp(funct, _unsigned("dram_addr", dram_addr, 64),
                       pack_local_addr_rows_cols(local_addr, cols, rows))


def mvout(dram_addr: int, local_addr: int, cols: int, rows: int) -> RoCCMicroOp:
    return RoCCMicroOp(GemminiFunct.MVOUT, _unsigned("dram_addr", dram_addr, 64),
                       pack_local_addr_rows_cols(local_addr, cols, rows))


def preload(bd_local_addr: int, c_local_addr: int, bd_cols: int, bd_rows: int,
            c_cols: int, c_rows: int) -> RoCCMicroOp:
    return RoCCMicroOp(
        GemminiFunct.PRELOAD,
        pack_local_addr_rows_cols(bd_local_addr, bd_cols, bd_rows),
        pack_local_addr_rows_cols(c_local_addr, c_cols, c_rows),
    )


def compute(a_local_addr: int, bd_local_addr: int, a_cols: int, a_rows: int,
            bd_cols: int, bd_rows: int, *, accumulate: bool) -> RoCCMicroOp:
    return RoCCMicroOp(
        GemminiFunct.COMPUTE_ACCUMULATE if accumulate else GemminiFunct.COMPUTE_PRELOADED,
        pack_local_addr_rows_cols(a_local_addr, a_cols, a_rows),
        pack_local_addr_rows_cols(bd_local_addr, bd_cols, bd_rows),
    )


def flush(*, skip: bool = False) -> RoCCMicroOp:
    """Encode the official TLB flush command; this is not a GEMM completion."""

    return RoCCMicroOp(GemminiFunct.FLUSH, int(skip), 0)
