"""Independent transport admission/packing and strict actual-store parsing."""
import importlib.util
from pathlib import Path
import numpy as np
import pytest
from heteronpu.rope_bf16_l2_candidate import (
    admit, tensor_from_pairs, adversarial_tail, pack_beat, expected_packets)

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('l2_runner', ROOT / 'scripts/run_rope_bf16_l2_candidate.py')
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def valid():
    return dict(heads=1, head_dim=256, rotary_dim=64, data_beats=8, policy=0xB1,
                source=0x1000, trig=0x2000, destination=0x3000)


@pytest.mark.parametrize('heads', [1, 2])
@pytest.mark.parametrize('offset', range(0, 64, 2))
def test_exact_shape_and_byte_offset_counts(heads, offset):
    cfg = valid(); cfg.update(heads=heads, data_beats=heads*8, destination=0x3000+offset)
    assert admit(**cfg) == dict(reads=heads*8+2, pairs=heads*32,
                               writes=heads*8+bool(offset))


@pytest.mark.parametrize('field,value', [
    ('heads', 0), ('heads', 3), ('heads', 8), ('heads', 1023),
    ('head_dim', 128), ('head_dim', 255), ('rotary_dim', 32), ('rotary_dim', 256),
    ('data_beats', 0), ('data_beats', 7), ('data_beats', 9), ('data_beats', 16),
    ('policy', 0), ('policy', 0xB0), ('policy', 0xB2),
    ('source', 1), ('source', 0x10002), ('source', 0x10000), ('source', 0xFFC0),
    ('trig', 1), ('trig', 0x10000), ('trig', 0xFFC0),
    ('destination', 1), ('destination', 0x10000), ('destination', 0xFE02),
    ('source', -64), ('trig', -64), ('destination', -2),
    ('source', 2**64-64), ('trig', 2**64-64), ('destination', 2**64-2),
    ('heads', True), ('heads', 1.0), ('policy', '177'), ('source', None),
])
def test_fail_closed(field, value):
    cfg = valid(); cfg[field] = value
    with pytest.raises(ValueError): admit(**cfg)


def test_actual_default_fabric_aperture_not_address_width():
    cfg = valid(); cfg.update(addr_width=15, source=0x180000-512,
                              trig=0x180000-128, destination=0x180000-512)
    assert admit(**cfg)['reads'] == 10
    for field in ('source', 'trig', 'destination'):
        bad = cfg.copy(); bad[field] = 0x180000
        with pytest.raises(ValueError): admit(**bad)
    cfg['l2_beats'] = 32768
    cfg.update(source=0x180000, trig=0x190000, destination=0x1A0000)
    assert admit(**cfg)['reads'] == 10


@pytest.mark.parametrize('capacity', [0, -1, 1025, True, 1.0])
def test_invalid_fabric_capacity(capacity):
    with pytest.raises(ValueError): admit(**valid(), l2_beats=capacity)


def example(heads=1):
    inputs = np.tile(np.array([[0x3F800000, 0x40000000, 0x3F800000, 0]], dtype=np.uint32), (32*heads, 1))
    native = inputs[:, :2].copy()
    return inputs, native, adversarial_tail(42, heads)


@pytest.mark.parametrize('heads', [1, 2])
def test_half_split_mapping_and_raw_nonfinite_tail(heads):
    x, native, tail = example(heads)
    for h in range(heads):
        x[h*32:(h+1)*32, 0] += h*0x10000
        native[h*32:(h+1)*32, 0] += h*0x10000
    source, trig, expected = tensor_from_pairs(x, native, tail)
    assert source.shape == expected.shape == (heads, 256)
    assert np.array_equal(source, expected)
    assert np.array_equal(source[:, 64:], tail)
    assert np.all(source[:, 32:64] == 0x4000)
    assert set(int(x) for x in tail[0, :12]) >= {0x7F81, 0xFF81, 0x7FC1, 0xFFC2, 0x8000}
    assert trig.shape == (2, 32) and np.all(trig[0] == 0x3F80) and not np.any(trig[1])


@pytest.mark.parametrize('mutation', ['input_dtype', 'native_dtype', 'tail_dtype', 'shape', 'non_bf16', 'coefficients'])
def test_reject_malformed_transport_arrays(mutation):
    x, native, tail = example(2)
    if mutation == 'input_dtype': x = x.astype(np.float32)
    elif mutation == 'native_dtype': native = native.astype(np.uint16)
    elif mutation == 'tail_dtype': tail = tail.astype(np.uint32)
    elif mutation == 'shape': x = x[:-1]
    elif mutation == 'non_bf16': x[0, 0] |= 1
    elif mutation == 'coefficients': x[32, 2] ^= 0x10000
    with pytest.raises(ValueError): tensor_from_pairs(x, native, tail)


@pytest.mark.parametrize('offset', range(0, 64, 2))
def test_packet_masks_and_bytes_independent(offset):
    tensor = np.arange(512, dtype=np.uint16).reshape(2, 256)
    destination = 0x3000 + offset
    packets = expected_packets(tensor, destination)
    memory = bytearray([0xA5] * (18*64))
    for address, mask, value in packets:
        assert all(((mask >> i) & 3) in (0, 3) for i in range(0, 64, 2))
        for i in range(64):
            if mask & (1 << i): memory[(address-0x3000//64)*64+i] = (value >> (i*8)) & 255
    assert memory[:offset] == bytes([0xA5])*offset
    assert memory[offset:offset+1024] == tensor.astype('<u2').tobytes()
    assert memory[offset+1024:] == bytes([0xA5])*(len(memory)-offset-1024)
    assert sum(mask.bit_count() for _, mask, _ in packets) == 1024


def one_record():
    x, native, _ = example()
    return runner.make_record(x, native, np.zeros(32, dtype=np.uint32), 1, 'synthetic', 0, True)


def trace_text(record):
    packets = expected_packets(record['expected'], record['destination'])
    text = ''.join(f'W 0 {a:x} {m:016x} {d:0128x}\n' for a, m, d in packets)
    c = record['counts']
    return text + f'D 0 {c["reads"]} {c["pairs"]} {c["writes"]} {record["flags"]}\n'


def test_actual_store_trace_strict_parser(tmp_path):
    r = one_record(); path = tmp_path / 'trace'; path.write_text(trace_text(r))
    result = runner.verify_store_trace(path, [r])
    assert result['transactions'] == 1 and result['masked_bytes'] == 512
    assert result['data'].dtype == np.uint16 and result['physical_write_beats'] == 9


@pytest.mark.parametrize('flags', [0, 1, 3, 5, 16, 17, 21, 31])
def test_completion_flags_are_decimal_not_hex(tmp_path, flags):
    r = one_record(); r['flags'] = flags
    path = tmp_path / 'trace'; path.write_text(trace_text(r))
    assert runner.verify_store_trace(path, [r])['transactions'] == 1


def test_legacy_body_still_matches_frozen_production():
    import hashlib
    source = (ROOT / 'rtl/integration/qwen2_shared_l2_rope_payload.sv').read_text()
    assert "parameter bit EXPERIMENTAL_BF16_ROPE=1'b0" in source
    legacy = source.split('end else begin : g_legacy\n', 1)[1].split(' assign ready_o=st==I;', 1)[0]
    assert hashlib.sha256(legacy.encode()).hexdigest() == 'cf3a795524f71835c180d0f169fb9d3a83568bc0b4818c7df78849518c280511'


@pytest.mark.parametrize('mutation', ['missing', 'extra', 'order', 'mask', 'value', 'early', 'count', 'flag', 'garbage', 'width'])
def test_actual_trace_rejects_transport_mutations(tmp_path, mutation):
    r = one_record(); lines = trace_text(r).splitlines()
    if mutation == 'missing': lines.pop(0)
    elif mutation == 'extra': lines.insert(0, lines[0])
    elif mutation == 'order': lines[0], lines[1] = lines[1], lines[0]
    elif mutation in ('mask', 'value', 'width'):
        fields = lines[0].split()
        if mutation == 'width': fields[4] = fields[4][1:]
        else:
            idx = 3 if mutation == 'mask' else 4
            fields[idx] = f'{int(fields[idx], 16)^1:0{len(fields[idx])}x}'
        lines[0] = ' '.join(fields)
    elif mutation == 'early': lines.insert(0, lines.pop())
    elif mutation == 'count': lines[-1] = lines[-1].replace('10 32', '11 32')
    elif mutation == 'flag': lines[-1] = lines[-1][:-1] + '1'
    elif mutation == 'garbage': lines.append('PASS')
    path = tmp_path / 'trace'; path.write_text('\n'.join(lines)+'\n')
    with pytest.raises(ValueError): runner.verify_store_trace(path, [r])


def test_word_order_and_record_padding(tmp_path):
    r = one_record(); path = tmp_path / 'vectors'; runner.write_vectors(path, [r])
    words = path.read_text().splitlines()
    assert len(words) == 35 and all(len(w) == 128 for w in words)
    assert int(words[0], 16) == 1 | 2 << 8
    assert all(int(w, 16) == 0 for w in words[9:17] + words[27:35])
    assert int(words[1], 16) == pack_beat(r['source'][0, :32])
