"""C02.1 negative policy identities and float bit-pattern boundary tests."""
import json
import struct

import pytest

from heteronpu import block_receipt as br
from test_precision_comparison import registered


def files(tmp_path, dtype='f32le', bits=None):
    width = br.WIDTHS[dtype]
    data = b''.join(int(x).to_bytes(width, 'little') for x in (bits or [0]))
    a, r = tmp_path/'actual.bin', tmp_path/'reference.bin'
    a.write_bytes(data)
    r.write_bytes(data)
    return a, r, {'dtype': dtype, 'shape': [len(data) // width]}


@pytest.mark.parametrize('index', [True, False, 7.0, 7.9, '7', -1, None])
def test_producer_identity_is_not_coerced(tmp_path, index):
    reg = registered(tmp_path)
    a, r, tensor = files(tmp_path)
    with pytest.raises(br.ReceiptError, match='producer index'):
        reg.compare('frozen', a, r, tensor, semantics='continuous',
                    producer={'kind': 'ggml_node', 'index': index},
                    fp32_indices=frozenset({0, 1, 7, -1}))


@pytest.mark.parametrize('policy', [frozenset({True}), frozenset({7.0}),
                                    frozenset({'7'}), frozenset({-1}), [7], {7}])
def test_precision_policy_identity_is_not_coerced(tmp_path, policy):
    reg = registered(tmp_path)
    a, r, tensor = files(tmp_path)
    with pytest.raises(br.ReceiptError, match='FP32 policy'):
        reg.compare('frozen', a, r, tensor, semantics='continuous',
                    producer={'kind': 'ggml_node', 'index': 7}, fp32_indices=policy)


@pytest.mark.parametrize('binding', [{}, {'kind': 'ggml_node'},
                                    {'kind': 'gguf_tensor', 'index': 7}, [], '7'])
def test_missing_malformed_producer_rejected(tmp_path, binding):
    reg = registered(tmp_path)
    a, r, tensor = files(tmp_path)
    with pytest.raises(br.ReceiptError):
        reg.compare('frozen', a, r, tensor, semantics='continuous',
                    producer=binding, fp32_indices=frozenset({7}))


@pytest.mark.parametrize('formula', ['bit_exact', 'abs_rel_elementwise_v1'])
@pytest.mark.parametrize('bits', [0x7F80, 0xFF80, 0x7FC1, 0x7F81])
@pytest.mark.parametrize('side', ['actual', 'reference'])
def test_bf16_nonfinite_at_last_element(tmp_path, formula, bits, side):
    reg = registered(tmp_path, formula)
    a, r, tensor = files(tmp_path, 'bf16le', [1, 0x8001, 0, 0])
    p = a if side == 'actual' else r
    p.write_bytes(p.read_bytes()[:-2] + bits.to_bytes(2, 'little'))
    tensor['shape'] = [2, 2]
    with pytest.raises(br.ReceiptError, match='nonfinite'):
        reg.compare('frozen', a, r, tensor, semantics='continuous',
                    producer={'kind': 'ggml_node', 'index': 7})


@pytest.mark.parametrize('dtype,maximum', [('f32le', 0x7F7FFFFF), ('bf16le', 0x7F7F)])
def test_finite_extremes_are_not_flushed_or_sampled(tmp_path, dtype, maximum):
    reg = registered(tmp_path, params={'atol': 0, 'rtol': 0})
    a, r, tensor = files(tmp_path, dtype, [0, 1, maximum])
    kw = dict(semantics='continuous', producer={'kind': 'ggml_node', 'index': 7},
              fp32_indices=frozenset({7}) if dtype == 'f32le' else frozenset())
    result = reg.compare('frozen', a, r, tensor, **kw)
    assert result['passed'] and result['elements'] == 3
    # The smallest subnormal is nonzero in this formula; no implicit FTZ.
    width = br.WIDTHS[dtype]
    a.write_bytes(a.read_bytes()[:width] + b'\0'*width + a.read_bytes()[2*width:])
    result = reg.compare('frozen', a, r, tensor, **kw)
    assert not result['passed'] and result['failed_elements'] == 1
    assert result['first_failure'] == 1 and result['max_absolute_error'] > 0


def test_signed_route_extremes_require_exact_bytes(tmp_path):
    reg = registered(tmp_path, 'bit_exact')
    a, r, tensor = files(tmp_path, 'i32le', [0x80000000, 0xFFFFFFFF, 0x7FFFFFFF])
    assert reg.compare('frozen', a, r, tensor, semantics='route')['passed']
    a.write_bytes(struct.pack('<iii', -2**31, -1, 2**31-2))
    result = reg.compare('frozen', a, r, tensor, semantics='route')
    assert result['failed_elements'] == 1 and result['first_failure'] == 2


def test_duplicate_json_key_does_not_replace_equation(tmp_path):
    reg = registered(tmp_path)
    p = tmp_path/'formula.json'
    text = p.read_text().replace('"version": 1', '"version": 1, "version": 1')
    p.write_text(text)
    with pytest.raises(br.ReceiptError):
        type(reg)().register(tmp_path, p.name, br.sha_file(p))
