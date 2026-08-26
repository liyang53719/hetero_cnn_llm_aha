import pytest

from heteronpu.command import Command128, Engine, Opcode, NULL_INDEX


def test_command_round_trip_and_byte_order() -> None:
    command = Command128(
        opcode=Opcode.MATRIX_GEMM,
        engine=Engine.MATRIX,
        flags=0x123,
        event_wait=0x4567,
        event_signal=0x89AB,
        src0=0x123456,
        src1=0x789ABC,
        dst=0xDEF012,
    )
    packed = command.pack()
    assert packed.bit_length() <= 128
    assert Command128.unpack(packed) == command
    assert Command128.from_bytes(command.to_bytes()) == command
    assert command.to_bytes()[0] == Opcode.MATRIX_GEMM


def test_command_rejects_wrong_engine() -> None:
    with pytest.raises(ValueError, match="belongs to"):
        Command128(Opcode.KV_APPEND, Engine.MATRIX)


def test_command_rejects_overflow() -> None:
    with pytest.raises(ValueError, match="src0"):
        Command128(Opcode.DMA_1D, Engine.DMA, src0=1 << 24)


def test_unused_roots_are_null_and_opcode_roles_are_enforced() -> None:
    nop = Command128(Opcode.NOP, Engine.CONTROL)
    assert (nop.src0, nop.src1, nop.dst) == (NULL_INDEX,) * 3
    with pytest.raises(ValueError, match="descriptor roots"):
        Command128(Opcode.DMA_2D, Engine.DMA, src0=1, dst=2)
    with pytest.raises(ValueError, match="unexpected=.*src1"):
        Command128(Opcode.KV_GATHER, Engine.KV, src0=1, src1=2, dst=3)
    assert Command128(Opcode.KV_GATHER, Engine.KV, src0=1, dst=3).src1 == NULL_INDEX


@pytest.mark.parametrize("opcode,engine,roots", [
    (Opcode.NOP, Engine.CONTROL, {}),
    (Opcode.DMA_1D, Engine.DMA, {"src0": 1, "src1": 2, "dst": 3}),
    (Opcode.MATRIX_GEMV, Engine.MATRIX, {"src0": 1, "src1": 2, "dst": 3}),
    (Opcode.SFU_ROPE, Engine.SFU_CGRA, {"src0": 1, "dst": 3}),
    (Opcode.KV_APPEND, Engine.KV, {"src0": 1, "src1": 2, "dst": 3}),
    (Opcode.KV_SHARE_PREFIX, Engine.KV, {"src0": 1, "dst": 3}),
    (Opcode.KV_FREE, Engine.KV, {"src0": 1}),
    (Opcode.BARRIER, Engine.CONTROL, {"src0": 1}),
])
def test_all_opcode_root_families_accept_only_their_frozen_shape(
    opcode: Opcode, engine: Engine, roots: dict[str, int]
) -> None:
    command = Command128(opcode, engine, **roots)
    assert Command128.unpack(command.pack()) == command
