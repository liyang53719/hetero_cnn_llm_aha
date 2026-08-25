import pytest

from heteronpu.command import Command128, Engine, Opcode


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
