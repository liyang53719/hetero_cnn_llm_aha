"""C04.1 negative boundaries and byte goldens captured from the pinned old code."""
import json
from pathlib import Path

import numpy as np
import pytest

from heteronpu import command as q, descriptor_chain as c, descriptor_v3 as v
from heteronpu import gemmini_descriptor_v2 as g

BAD = [True, False, 1.0, 1.75, "1", None, float("nan"), float("inf"), -1]


@pytest.mark.parametrize("field,width", [
    ("flags", 13), ("event_wait", 16), ("event_signal", 16),
    ("src0", 24), ("src1", 24), ("dst", 24),
])
@pytest.mark.parametrize("value", BAD)
def test_command_rejects_coercion(field, width, value):
    args = dict(opcode=q.Opcode.MATRIX_GEMM, engine=q.Engine.MATRIX, src0=1, src1=2, dst=3)
    args[field] = value
    with pytest.raises(ValueError):
        q.Command128(**args)


@pytest.mark.parametrize("field,width", [("flags", 13), ("event_wait", 16), ("event_signal", 16), ("src0", 24), ("src1", 24), ("dst", 24)])
def test_command_overflow(field, width):
    args = dict(opcode=q.Opcode.MATRIX_GEMM, engine=q.Engine.MATRIX, src0=1, src1=2, dst=3)
    args[field] = 1 << width
    with pytest.raises(ValueError):
        q.Command128(**args)


@pytest.mark.parametrize("bad", BAD + [255, 256])
def test_invalid_opcode_enum(bad):
    with pytest.raises(ValueError):
        q.Command128(bad, q.Engine.CONTROL)


@pytest.mark.parametrize("bad", BAD + [6, 7, 8, q.Opcode.NOP])
def test_invalid_engine_enum(bad):
    with pytest.raises(ValueError):
        q.Command128(q.Opcode.NOP, bad)


@pytest.mark.parametrize("decoder", [q.Command128.unpack, c.DescriptorRecord.unpack, v.DescriptorRecord.unpack])
@pytest.mark.parametrize("bad", BAD + [1 << 128, (1 << 128) | 4])
def test_raw_word_rejects_truncation(decoder, bad):
    with pytest.raises(ValueError):
        decoder(bad)


@pytest.mark.parametrize("module,typ", [(c, 1), (v, 4)])
@pytest.mark.parametrize("field,width", [("record_type", 8), ("subtype", 8), ("flags", 16), ("next_index", 24), ("payload", 72)])
@pytest.mark.parametrize("bad", BAD + ["overflow"])
def test_descriptor_header_fields(module, typ, field, width, bad):
    args = dict(record_type=typ, subtype=0, flags=0, next_index=c.NULL_INDEX, payload=0)
    args[field] = (1 << width) if bad == "overflow" else bad
    with pytest.raises(ValueError):
        module.DescriptorRecord(**args)


@pytest.mark.parametrize("bad", BAD + [1 << 56])
def test_address_56bit_rejection(bad):
    with pytest.raises(ValueError):
        g.tensor_base_record(bad)


@pytest.mark.parametrize("bad", BAD + [1 << 24])
def test_chain_root_and_table_key_do_not_alias(bad):
    record = c.DescriptorRecord(1, 0, 0, c.NULL_INDEX, 0)
    with pytest.raises(c.DescriptorChainError):
        c.validate_descriptor_chain(bad, {1: record})
    # None, NaN and floats are hashable here; reject even if the entry is unreachable.
    with pytest.raises(c.DescriptorChainError):
        c.validate_descriptor_chain(1, {bad: record, 1: record})


@pytest.mark.parametrize("factory,args", [
    (c.MatrixAux, {"bias_index": True}), (c.MatrixAux, {"activation": 1.5}),
    (c.MatrixAux, {"full_c": 2}), (c.MatrixAux, {"subarray_mask": 256}),
    (c.DmaPolicy, {"max_burst_beats": True, "max_outstanding": 1}),
    (c.DmaPolicy, {"max_burst_beats": 1, "max_outstanding": 1, "ordered": "yes"}),
    (c.SfuProgram, {"program_id": 1, "input_count": 1, "input_dtype": 2}),
    (c.SfuProgram, {"program_id": 1, "input_count": True}),
    (c.EventList4, {"events": [True]}), (c.EventList4, {"events": [1.0]}),
    (g.matrix_op_record, {"m": 65536, "n": 0, "k": 1, "dataflow": 0}),
    (g.matrix_op_record, {"m": 1, "n": 65536, "k": 1, "dataflow": 0}),
    (g.matrix_op_record, {"m": 1, "n": 1, "k": 1 << 24, "dataflow": 0}),
    (g.matrix_op_record, {"m": 1, "n": 1, "k": 1, "dataflow": 3}),
    (g.matrix_op_record, {"m": 1, "n": 1, "k": 1, "dataflow": 0, "transpose_a": 2}),
    (g.tensor_base_record, {"address": 0, "rank": 16}),
    (g.tensor_base_record, {"address": 0, "dtype": 2}),
    (g.tensor_base_record, {"address": 0, "memory_space": 16}),
    (g.quantization_record, {"scale_address": 1 << 48}),
    (v.shape2_32, {"a": 1.9, "b": 2}),
    (v.kv_epoch32, {"generation": True, "logical_page_count": 2}),
])
def test_typed_fields_reject_spill_and_reserved_enums(factory, args):
    with pytest.raises(ValueError):
        factory(**args)


@pytest.mark.parametrize("factory,value", [
    (g.shape4_record, [1] * 5), (g.shape4_record, [True]),
    (g.shape4_record, [1.5]), (g.shape4_record, [1 << 18]),
    (g.stride3_record, [1] * 4), (g.stride3_record, [1.0]),
    (g.stride3_record, [1 << 23]), (g.stride3_record, [-(1 << 23) - 1]),
])
def test_no_sequence_truncation_or_coercion(factory, value):
    with pytest.raises(ValueError):
        factory(value)


def test_chain_sixteen_boundary_and_packed_invalid_record():
    records = {i: c.DescriptorRecord(1, 0, 0, i + 1 if i < 15 else c.NULL_INDEX, i) for i in range(16)}
    assert len(c.validate_descriptor_chain(0, records)) == 16
    records[15] = (1 << 128) | 1
    with pytest.raises(c.DescriptorChainError):
        c.validate_descriptor_chain(0, records)


def test_signed_strides_and_explicit_boolean_bits_are_legal():
    x = g.stride3_record([-(1 << 23), -1, (1 << 23) - 1])
    assert x.payload == 0x7fffffffffff800000
    assert c.MatrixAux(full_c=True).payload() == c.MatrixAux(full_c=1).payload()
    assert q.Command128(0, 0).to_bytes() == q.Command128(q.Opcode.NOP, q.Engine.CONTROL).to_bytes()


def test_integral_scalars_do_not_overflow_in_numpy_arithmetic():
    x = g.tensor_base_record(np.uint64(2**56 - 1), dtype=5)
    assert (x.payload >> 64) == 255
    x = g.conv2d_record(kernel_h=np.uint64(255), kernel_w=255, stride_h=255,
        stride_w=255, dilation_h=255, dilation_w=255, pad_top=63, pad_left=63, groups=np.uint64(4095))
    assert x.payload == (1 << 72) - 1


VECTORS = json.loads((Path(__file__).parent / "fixtures/block_contracts/abi_legacy_vectors.json").read_text())["vectors"]


@pytest.mark.parametrize("case", VECTORS, ids=lambda x: x["family"] + "." + x["name"])
def test_frozen_legacy_byte_identity(case):
    module = {"command": q, "chain": c, "v3": v, "gemmini": g}[case["family"]]
    obj = getattr(module, case["name"])(*case["args"], **case["kwargs"])
    word = obj.pack() if hasattr(obj, "pack") else obj.to_record().pack()
    assert word.to_bytes(16, "little").hex() == case["hex"]


@pytest.mark.parametrize("payload", [[0] * 16, b"", b"x" * 15, b"x" * 17, memoryview(b"x" * 32)[::2]])
def test_command_byte_buffer_contract(payload):
    with pytest.raises(ValueError):
        q.Command128.from_bytes(payload)
