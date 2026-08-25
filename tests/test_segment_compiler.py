from heteronpu.command import Opcode
from heteronpu.segment_compiler import load_and_compile


def test_cnn_segment_inserts_join_barrier() -> None:
    segment = load_and_compile("examples/cnn_segment.yaml")
    assert segment.name == "cnn_conv_activation_pool"
    assert len(segment.barriers) == 1
    names = [item.name for item in segment.commands]
    assert "__join__conv" in names
    conv = next(item for item in segment.commands if item.name == "conv")
    assert conv.command.event_wait != 0
    assert conv.command.opcode == Opcode.MATRIX_CONV


def test_llm_prefill_segment_round_trips_all_commands() -> None:
    segment = load_and_compile("examples/llm_prefill_segment.yaml")
    assert len(segment.barriers) == 3
    for item in segment.commands:
        assert item.command.from_bytes(item.command.to_bytes()) == item.command
    assert segment.commands[-1].name == "down_projection"
