import pytest

from heteronpu.gemmini_rocc_lowering import (
    CUSTOM3_OPCODE,
    GemminiDataflow,
    GemminiFunct,
    Int8SingleTileDescriptor,
    LoopWsDescriptor,
    config_ex,
    config_load,
    config_store,
    compute,
    flush,
    mvin,
    mvout,
    pack_local_addr_rows_cols,
    preload,
    lower_int8_single_tile,
    lower_loop_ws,
)


def test_official_mvin_and_mvout_packing() -> None:
    packed = (0x78 << 48) | (0x56 << 32) | 0x1234
    op = mvin(0x8000_1234, 0x1234, 0x56, 0x78)
    assert (op.funct, op.rs1, op.rs2, op.opcode) == (
        GemminiFunct.MVIN, 0x8000_1234, packed, CUSTOM3_OPCODE
    )
    assert not op.xd and op.xs1 and op.xs2 and op.rd == 0
    assert op.funct3 == 0x3  # pinned ROCC_INSTRUCTION_0_R_R
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


def test_config_encoders_match_pinned_gemmini_h_bit_layouts() -> None:
    ex = config_ex(dataflow=GemminiDataflow.OUTPUT_STATIONARY, c_stride=5, a_stride=7)
    assert (ex.funct, ex.rs1, ex.rs2) == (GemminiFunct.CONFIG, 0x3F80_0000_0007_0000, 5 << 48)
    ld = config_load(stride_bytes=7)
    assert (ld.funct, ld.rs1, ld.rs2) == (GemminiFunct.CONFIG, 0x3F80_0000_0010_0101, 7)
    st = config_store(stride_bytes=5)
    assert (st.funct, st.rs1, st.rs2) == (GemminiFunct.CONFIG, 2, 0x3F80_0000_0000_0005)


def test_channel_and_width_validation() -> None:
    assert mvin(0, 0, 1, 1, channel=1).funct == GemminiFunct.MVIN2
    assert mvin(0, 0, 1, 1, channel=2).funct == GemminiFunct.MVIN3
    assert flush(skip=True).rs1 == 1
    with pytest.raises(ValueError, match="channel"):
        mvin(0, 0, 1, 1, channel=3)
    with pytest.raises(ValueError, match="cols"):
        pack_local_addr_rows_cols(0, 1 << 16, 1)


def test_resolved_int8_descriptor_lowers_in_official_os_macro_order() -> None:
    descriptor = Int8SingleTileDescriptor(
        a_dram_addr=0x8000_0000, b_dram_addr=0x8000_1000, c_dram_addr=0x8000_2000,
        a_local_addr=0x000, b_local_addr=0x010, c_local_addr=0x030,
        m=3, n=5, k=7, a_stride_bytes=7, b_stride_bytes=5, c_stride_bytes=5,
        bias_dram_addr=0x8000_3000, bias_local_addr=0x020, bias_stride_bytes=5,
    )
    program = lower_int8_single_tile(descriptor)
    assert [op.funct for op in program] == [
        GemminiFunct.CONFIG, GemminiFunct.CONFIG, GemminiFunct.CONFIG,
        GemminiFunct.MVIN, GemminiFunct.CONFIG, GemminiFunct.MVIN,
        GemminiFunct.CONFIG, GemminiFunct.MVIN, GemminiFunct.PRELOAD,
        GemminiFunct.COMPUTE_PRELOADED, GemminiFunct.MVOUT,
    ]
    assert program[8].rs1 == pack_local_addr_rows_cols(0x020, 5, 3)
    assert program[-1].rs2 == pack_local_addr_rows_cols(0x030, 5, 3)
    # gemmini_config_ex() in the pinned basic OS C path passes unit strides;
    # tensor strides belong to the subsequent config_st/config_ld commands.
    assert program[0].rs1 == 0x3F80_0000_0001_0000
    assert program[0].rs2 == 1 << 48
    assert program[1].rs2 == 0x3F80_0000_0000_0005
    assert program[2].rs2 == 7
    assert all(op.opcode == CUSTOM3_OPCODE and not op.xd for op in program)


def test_single_tile_lowerer_rejects_unsupported_or_incomplete_policy() -> None:
    base = dict(
        a_dram_addr=0, b_dram_addr=0, c_dram_addr=0,
        a_local_addr=0, b_local_addr=0, c_local_addr=0,
        m=1, n=1, k=1, a_stride_bytes=1, b_stride_bytes=1, c_stride_bytes=1,
    )
    with pytest.raises(ValueError, match="1..16"):
        lower_int8_single_tile(Int8SingleTileDescriptor(**(base | {"m": 17})))
    with pytest.raises(ValueError, match="weight-stationary"):
        lower_int8_single_tile(Int8SingleTileDescriptor(
            **base, dataflow=GemminiDataflow.WEIGHT_STATIONARY
        ))


def test_loop_ws_lowering_matches_official_six_command_macro() -> None:
    descriptor = LoopWsDescriptor(
        i=2, j=2, k=2, pad_i=15, pad_j=14, pad_k=13,
        a_addr=0x80002000, b_addr=0x80003000, d_addr=0x80004000, c_addr=0x80005000,
        a_stride=19, b_stride=18, d_stride=18, c_stride=18,
        b_transpose=True, full_c=True, low_d=True, ex_accumulate=True,
        activation=1, a_spad_id=2, b_spad_id=1,
    )
    ops = lower_loop_ws(descriptor)
    assert [op.funct for op in ops] == [
        GemminiFunct.LOOP_WS_CONFIG_BOUNDS, GemminiFunct.LOOP_WS_CONFIG_ADDRS_AB,
        GemminiFunct.LOOP_WS_CONFIG_ADDRS_DC, GemminiFunct.LOOP_WS_CONFIG_STRIDES_AB,
        GemminiFunct.LOOP_WS_CONFIG_STRIDES_DC, GemminiFunct.LOOP_WS,
    ]
    assert ops[0].rs1 == (13 << 32) | (14 << 16) | 15
    assert ops[0].rs2 == (2 << 32) | (2 << 16) | 2
    assert (ops[1].rs1, ops[1].rs2) == (0x80002000, 0x80003000)
    assert (ops[4].rs1, ops[4].rs2) == (18, 18)
    assert ops[5].rs1 == (2 << 18) | (1 << 16) | (1 << 8) | 0b111
    assert ops[5].rs2 == 0b10
    assert all(op.funct3 == 3 for op in ops)
