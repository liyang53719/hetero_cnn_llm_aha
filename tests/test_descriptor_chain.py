import pytest

from heteronpu.descriptor_chain import (
    DescriptorChainError, DescriptorRecord, MAX_RECORDS, NULL_INDEX,
    MatrixAux, MatrixActivation, DmaPolicy, EventList4, RecordType,
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


def test_descriptor_v2_typed_records_round_trip_and_reserved_rejection() -> None:
    aux = MatrixAux(bias_index=7, activation=MatrixActivation.RELU,
                    full_c=True, no_pool=True, max_pixels_per_row=3,
                    pad_bottom=1, pad_right=2, subarray_mask=5)
    assert MatrixAux.from_record(DescriptorRecord.unpack(aux.to_record().pack())) == aux
    dma = DmaPolicy(16, 4, read_qos=3, write_qos=2,
                    allow_unaligned=True, coalesce=True, ordered=False)
    assert DmaPolicy.from_record(DescriptorRecord.unpack(dma.to_record().pack())) == dma
    events = EventList4((1, 17, 65535))
    assert EventList4.from_record(DescriptorRecord.unpack(events.to_record().pack())) == events
    with pytest.raises(ValueError, match="subarray_mask"):
        MatrixAux(subarray_mask=0)
    with pytest.raises(ValueError, match="nonzero"):
        DmaPolicy(0, 1)
    with pytest.raises(ValueError, match="nonzero"):
        EventList4((0,))
    with pytest.raises(ValueError, match="subtype"):
        DescriptorRecord(RecordType.TENSOR_BASE, 1, 0, NULL_INDEX, 0)
    bad_dma = DescriptorRecord(RecordType.DMA_POLICY, 0, 0, NULL_INDEX,
                               dma.payload() | (1 << 30))
    with pytest.raises(ValueError, match="reserved"):
        DmaPolicy.from_record(bad_dma)
