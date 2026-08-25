import pytest

from heteronpu.gemmini_rocc_lowering import (
    CUSTOM3_OPCODE,
    GemminiFunct,
    compute,
    flush,
    mvin,
    mvout,
    pack_local_addr_rows_cols,
    preload,
)


def test_official_mvin_and_mvout_packing() -> None:
    packed = (0x78 << 48) | (0x56 << 32) | 0x1234
    op = mvin(0x8000_1234, 0x1234, 0x56, 0x78)
    assert (op.funct, op.rs1, op.rs2, op.opcode) == (
        GemminiFunct.MVIN, 0x8000_1234, packed, CUSTOM3_OPCODE
    )
    assert not op.xd and op.xs1 and op.xs2 and op.rd == 0
    assert mvout(0x8000_5678, 0x1234, 0x56, 0x78).funct == GemminiFunct.MVOUT


def test_preload_and_compute_match_official_two_operand_shape_packing() -> None:
    a = pack_local_addr_rows_cols(0x11, 2, 3)
    b = pack_local_addr_rows_cols(0x22, 4, 5)
    c = pack_local_addr_rows_cols(0x33, 6, 7)
    assert preload(0x22, 0x33, 4, 5, 6, 7).rs1 == b
    assert preload(0x22, 0x33, 4, 5, 6, 7).rs2 == c
    op = compute(0x11, 0x22, 2, 3, 4, 5, accumulate=False)
    assert (op.funct, op.rs1, op.rs2) == (GemminiFunct.COMPUTE_PRELOADED, a, b)
    assert compute(0x11, 0x22, 2, 3, 4, 5, accumulate=True).funct == GemminiFunct.COMPUTE_ACCUMULATE


def test_channel_and_width_validation() -> None:
    assert mvin(0, 0, 1, 1, channel=1).funct == GemminiFunct.MVIN2
    assert mvin(0, 0, 1, 1, channel=2).funct == GemminiFunct.MVIN3
    assert flush(skip=True).rs1 == 1
    with pytest.raises(ValueError, match="channel"):
        mvin(0, 0, 1, 1, channel=3)
    with pytest.raises(ValueError, match="cols"):
        pack_local_addr_rows_cols(0, 1 << 16, 1)
