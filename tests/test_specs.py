from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _ranges(fields: dict[str, dict[str, int]]) -> list[tuple[int, int, str]]:
    return [(int(spec["lsb"]), int(spec["lsb"]) + int(spec["width"]), name) for name, spec in fields.items()]


def _assert_non_overlapping(fields: dict[str, dict[str, int]], bits: int) -> None:
    ranges = sorted(_ranges(fields))
    for lo, hi, name in ranges:
        assert 0 <= lo < hi <= bits, (name, lo, hi)
    for (_, prev_hi, prev_name), (lo, _, name) in zip(ranges, ranges[1:]):
        assert prev_hi <= lo, (prev_name, name)


def test_command_layout_is_128_bits_and_non_overlapping() -> None:
    spec = yaml.safe_load((ROOT / "spec/command_isa.yaml").read_text())
    assert spec["word_bits"] == 128
    _assert_non_overlapping(spec["fields"], spec["word_bits"])
    assert max(hi for _, hi, _ in _ranges(spec["fields"])) == 128


def test_descriptor_common_and_typed_payloads_fit_128_bits() -> None:
    spec = yaml.safe_load((ROOT / "spec/descriptor_schema.yaml").read_text())
    bits = int(spec["record_bits"])
    assert bits == 128
    _assert_non_overlapping(spec["common_fields"], bits)
    for record in spec["record_types"].values():
        payload = record.get("payload", {})
        if payload:
            _assert_non_overlapping(payload, bits)
            assert all(field["lsb"] >= spec["common_fields"]["payload"]["lsb"] for field in payload.values())


def test_sram_budget_and_frozen_top_level_contract() -> None:
    arch = yaml.safe_load((ROOT / "configs/arch_v0.yaml").read_text())
    sram = arch["on_chip_sram"]
    partition = sum(value for key, value in sram.items() if key.endswith("_KiB") and key != "total_KiB")
    assert partition == sram["total_KiB"] == 4096
    assert arch["clock_hz"] == 1_000_000_000
    assert arch["command_bits"] == 128
    assert arch["event_bits"] == 16
    assert arch["fabric"]["tensor_stream_bits"] == 512
