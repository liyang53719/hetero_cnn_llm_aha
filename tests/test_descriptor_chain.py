import pytest

from heteronpu.descriptor_chain import (
    DescriptorChainError, DescriptorRecord, MAX_RECORDS, NULL_INDEX,
    validate_descriptor_chain,
)


def record(next_index: int, record_type: int = 1) -> DescriptorRecord:
    return DescriptorRecord(record_type, 0, 0, next_index, 0x123)


def test_descriptor_record_round_trip_and_valid_chain() -> None:
    records = {3: record(7), 7: record(NULL_INDEX, 0x10)}
    assert DescriptorRecord.unpack(records[3].pack()) == records[3]
    chain = validate_descriptor_chain(3, records)
    assert [index for index, _ in chain] == [3, 7]
    assert [entry.record_type for _, entry in chain] == [1, 0x10]


def test_descriptor_chain_rejects_cycle_missing_and_null_first() -> None:
    with pytest.raises(DescriptorChainError, match="cycle"):
        validate_descriptor_chain(1, {1: record(2), 2: record(1)})
    with pytest.raises(DescriptorChainError, match="missing"):
        validate_descriptor_chain(1, {1: record(2)})
    with pytest.raises(DescriptorChainError, match="starts at null"):
        validate_descriptor_chain(NULL_INDEX, {})
    assert validate_descriptor_chain(NULL_INDEX, {}, allow_null_first=True) == ()


def test_descriptor_chain_rejects_more_than_sixteen_records() -> None:
    records = {index: record(index + 1) for index in range(MAX_RECORDS + 1)}
    records[MAX_RECORDS] = record(NULL_INDEX)
    with pytest.raises(DescriptorChainError, match="exceeds 16"):
        validate_descriptor_chain(0, records)


def test_descriptor_field_widths_are_enforced() -> None:
    with pytest.raises(ValueError, match="next_index"):
        record(1 << 24)
    with pytest.raises(DescriptorChainError, match="24 bits"):
        validate_descriptor_chain(1 << 24, {})
