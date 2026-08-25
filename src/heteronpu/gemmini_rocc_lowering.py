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


class GemminiDataflow(IntEnum):
    """Values used by the pinned official ``gemmini.h`` API."""

    OUTPUT_STATIONARY = 0
    WEIGHT_STATIONARY = 1


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


def config_ex(*, dataflow: GemminiDataflow, c_stride: int, a_stride: int,
              a_transpose: bool = False, b_transpose: bool = False,
              sys_activation: int = 0, sys_shift: int = 0,
              acc_scale_bits: int = 0x3F80_0000) -> RoCCMicroOp:
    """Encode ``gemmini_extended3_config_ex`` with explicit frozen operands."""

    rs1 = (
        _unsigned("acc_scale_bits", acc_scale_bits, 32) << 32
        | _unsigned("a_stride", a_stride, 16) << 16
        | int(bool(b_transpose)) << 9
        | int(bool(a_transpose)) << 8
        | _unsigned("sys_activation", sys_activation, 2) << 3
        | _unsigned("dataflow", int(dataflow), 1) << 2
    )
    rs2 = _unsigned("c_stride", c_stride, 16) << 48 | _unsigned("sys_shift", sys_shift, 32)
    return RoCCMicroOp(GemminiFunct.CONFIG, rs1, rs2)


def config_load(*, stride_bytes: int, scale_bits: int = 0x3F80_0000,
                shrunk: bool = False, block_mvin_stride: int = 16,
                pixel_repeats: int = 1, channel: int = 0) -> RoCCMicroOp:
    """Encode ``gemmini_extended5_config_ld`` without hidden defaults."""

    rs1 = (
        _unsigned("scale_bits", scale_bits, 32) << 32
        | _unsigned("block_mvin_stride", block_mvin_stride, 16) << 16
        | _unsigned("pixel_repeats", pixel_repeats, 8) << 8
        | _unsigned("channel", channel, 2) << 3
        | int(bool(shrunk)) << 2
        | 1  # CONFIG_LD
    )
    return RoCCMicroOp(GemminiFunct.CONFIG, rs1, _unsigned("stride_bytes", stride_bytes, 32))


def config_store(*, stride_bytes: int, acc_scale_bits: int = 0x3F80_0000) -> RoCCMicroOp:
    """Encode the non-pooling ``gemmini_config_st`` form."""

    rs1 = 2  # CONFIG_ST, with all pooling/activation fields zero
    rs2 = _unsigned("acc_scale_bits", acc_scale_bits, 32) << 32 | _unsigned("stride_bytes", stride_bytes, 32)
    return RoCCMicroOp(GemminiFunct.CONFIG, rs1, rs2)


@dataclass(frozen=True)
class Int8SingleTileDescriptor:
    """Typed L2 descriptor view for one official output-stationary Gemmini tile.

    The architectural descriptor schema owns the logical M/N/K and tensor
    bases.  This object is its resolved one-tile view: local addresses already
    carry official scratchpad/accumulator address bits, so this lowerer never
    invents a memory map.  It deliberately rejects tiles beyond DIM=16 and
    weight-stationary sequencing until the project descriptor allocator and
    official loop path are connected in RocketTile.
    """

    a_dram_addr: int
    b_dram_addr: int
    c_dram_addr: int
    a_local_addr: int
    b_local_addr: int
    c_local_addr: int
    m: int
    n: int
    k: int
    a_stride_bytes: int
    b_stride_bytes: int
    c_stride_bytes: int
    bias_dram_addr: int | None = None
    bias_local_addr: int | None = None
    bias_stride_bytes: int | None = None
    dataflow: GemminiDataflow = GemminiDataflow.OUTPUT_STATIONARY
    transpose_a: bool = False
    transpose_b: bool = False


def lower_int8_single_tile(descriptor: Int8SingleTileDescriptor) -> tuple[RoCCMicroOp, ...]:
    """Lower one resolved OS INT8 tile using the official C macro ordering.

    The returned program intentionally has no synthetic response or completion
    command.  Completion remains a retained-RocketTile observation, because
    normal Gemmini commands do not produce a generic ``io_resp`` transaction.
    """

    for name, value in (("m", descriptor.m), ("n", descriptor.n), ("k", descriptor.k)):
        if not 1 <= value <= 16:
            raise ValueError(f"{name} must be in 1..16 for the single-tile lowerer")
    if descriptor.dataflow is not GemminiDataflow.OUTPUT_STATIONARY:
        raise ValueError("weight-stationary lowering requires the retained official loop path")
    if (descriptor.bias_dram_addr is None) != (descriptor.bias_local_addr is None):
        raise ValueError("bias dram/local addresses must either both be present or both be absent")
    if descriptor.bias_dram_addr is not None and descriptor.bias_stride_bytes is None:
        raise ValueError("bias_stride_bytes is required with a bias descriptor")

    ops = [
        config_ex(
            dataflow=descriptor.dataflow,
            # Match gemmini_config_ex() in the pinned basic OS C path.  DMA
            # row strides are owned by config_st/config_ld below; placing
            # them here changes the official CUSTOM_3 transcript.
            c_stride=1,
            a_stride=1,
            a_transpose=descriptor.transpose_a,
            b_transpose=descriptor.transpose_b,
        ),
        config_store(stride_bytes=descriptor.c_stride_bytes),
        config_load(stride_bytes=descriptor.a_stride_bytes),
        mvin(descriptor.a_dram_addr, descriptor.a_local_addr, descriptor.k, descriptor.m),
        config_load(stride_bytes=descriptor.b_stride_bytes),
        mvin(descriptor.b_dram_addr, descriptor.b_local_addr, descriptor.n, descriptor.k),
    ]
    if descriptor.bias_dram_addr is not None:
        assert descriptor.bias_local_addr is not None and descriptor.bias_stride_bytes is not None
        ops.extend((
            config_load(stride_bytes=descriptor.bias_stride_bytes),
            mvin(descriptor.bias_dram_addr, descriptor.bias_local_addr, descriptor.n, descriptor.m),
            preload(descriptor.bias_local_addr, descriptor.c_local_addr,
                    descriptor.n, descriptor.m, descriptor.n, descriptor.m),
        ))
    else:
        ops.append(preload((1 << 32) - 1, descriptor.c_local_addr,
                           16, 16, descriptor.n, descriptor.m))
    ops.extend((
        compute(descriptor.a_local_addr, descriptor.b_local_addr,
                descriptor.k, descriptor.m, descriptor.n, descriptor.k, accumulate=False),
        mvout(descriptor.c_dram_addr, descriptor.c_local_addr, descriptor.n, descriptor.m),
    ))
    return tuple(ops)
