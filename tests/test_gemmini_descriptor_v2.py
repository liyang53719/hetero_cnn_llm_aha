import json
from pathlib import Path

from heteronpu.command import Command128
from heteronpu.descriptor_chain import DescriptorRecord
from heteronpu.gemmini_descriptor_v2 import lower_matrix_v2


ROOT = Path(__file__).resolve().parents[1]


def test_committed_v2_programs_regenerate_from_descriptor_records() -> None:
    payload = json.loads((ROOT / "tests/vectors/gemmini_descriptor_v2_programs.json").read_text())
    expected_counts = {"multi_tile_os": 36, "loop_ws": 11, "loop_ws_no_bias": 11,
                       "conv1x1": 9,
                       "conv_identity": 9, "conv_relu_requant": 9}
    for case in payload["cases"]:
        records = {int(index, 16): DescriptorRecord.unpack(int(word, 16))
                   for index, word in case["records"].items()}
        scales = {0x9000: 0x3F000000} if case["name"] == "conv_relu_requant" else None
        ops = lower_matrix_v2(Command128.unpack(int(case["command"], 16)), records,
                              scale_bits=scales)
        observed = [(int(op.funct), op.rs1, op.rs2) for op in ops]
        expected = [(entry["funct"], int(entry["rs1"], 16), int(entry["rs2"], 16))
                    for entry in case["ops"]]
        assert observed == expected
        assert len(observed) == expected_counts[case["name"]]


def test_v2_program_funct_sequences_match_pinned_macro_paths() -> None:
    payload = json.loads((ROOT / "tests/vectors/gemmini_descriptor_v2_programs.json").read_text())
    functs = {case["name"]: [op["funct"] for op in case["ops"]] for case in payload["cases"]}
    assert functs["loop_ws"] == [0, 0, 0, 0, 0, 9, 10, 11, 12, 13, 8]
    assert functs["loop_ws_no_bias"] == functs["loop_ws"]
    assert functs["conv1x1"] == [0, 0, 16, 17, 18, 19, 20, 21, 15]
    assert functs["conv_identity"] == [0, 0, 16, 17, 18, 19, 20, 21, 15]
    assert functs["conv_relu_requant"] == functs["conv_identity"]
    assert len(functs["multi_tile_os"]) == 36
