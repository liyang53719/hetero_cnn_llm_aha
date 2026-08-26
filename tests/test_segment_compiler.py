from heteronpu.command import Opcode, NULL_INDEX
from heteronpu.segment_compiler import load_and_compile
from pathlib import Path
import json


def test_cnn_segment_inserts_join_barrier() -> None:
    segment = load_and_compile("examples/cnn_segment.yaml")
    assert segment.name == "cnn_conv_activation_pool"
    assert len(segment.barriers) == 1
    names = [item.name for item in segment.commands]
    assert "__join__conv" in names
    conv = next(item for item in segment.commands if item.name == "conv")
    assert conv.command.event_wait != 0
    assert conv.command.opcode == Opcode.MATRIX_CONV
    barrier = next(item for item in segment.commands if item.name == "__join__conv")
    assert barrier.command.src1 == barrier.command.dst == NULL_INDEX


def test_llm_prefill_segment_round_trips_all_commands() -> None:
    segment = load_and_compile("examples/llm_prefill_segment.yaml")
    assert len(segment.barriers) == 3
    for item in segment.commands:
        assert item.command.from_bytes(item.command.to_bytes()) == item.command
    assert segment.commands[-1].name == "down_projection"


def test_decode_segment_uses_distinct_k_v_and_metadata_roots() -> None:
    segment = load_and_compile("examples/llm_decode_segment.yaml")
    append = next(item.command for item in segment.commands if item.name == "append")
    assert append.src0 == 209 and append.src1 == 210 and append.dst == 222


def test_committed_segment_reports_match_frozen_examples() -> None:
    root = Path(__file__).resolve().parents[1]
    for source, report in (
        ("cnn_segment.yaml", "cnn_segment_commands.json"),
        ("llm_prefill_segment.yaml", "llm_prefill_segment_commands.json"),
        ("llm_decode_segment.yaml", "llm_decode_segment_commands.json"),
    ):
        expected = load_and_compile(root / "examples" / source).to_dict()
        actual = json.loads((root / "reports" / report).read_text(encoding="utf-8"))
        assert actual == expected
