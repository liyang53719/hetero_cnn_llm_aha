import hashlib
import json
import math
import struct
import pytest
from heteronpu import block_receipt as br
from heteronpu.precision_comparison import FormulaRegistry, EQUATIONS
from heteronpu.precision_policy import fp32_boundary_indices


def contract(tmp_path, name='abs_rel_elementwise_v1', params=None, **changes):
    obj = dict(version=1, contract_id='frozen', formula=name, equation=EQUATIONS.get(name, 'unknown'),
               parameters=({} if name == 'bit_exact' else {'atol': 0.125, 'rtol': 0.25}) if params is None else params,
               source_revision='a'*40, source_anchor='synthetic fixture: explicit equation, not official threshold',
               evidence_class='synthetic_test')
    obj.update(changes)
    p = tmp_path / 'formula.json'
    p.write_text(json.dumps(obj))
    return p, br.sha_file(p)


def registered(tmp_path, *args, **kwargs):
    p, h = contract(tmp_path, *args, **kwargs)
    reg = FormulaRegistry()
    reg.register(tmp_path, p.name, h)
    return reg


def compare(tmp_path, reg, x, y, dtype='f32le', **kwargs):
    def pack(values):
        if dtype == 'bf16le':
            return b''.join(struct.pack('<H', struct.unpack('<I', struct.pack('<f', v))[0] >> 16) for v in values)
        return struct.pack('<' + ('f' if dtype == 'f32le' else 'I') * len(values), *values)
    a, r = tmp_path/'actual.bin', tmp_path/'reference.bin'
    a.write_bytes(pack(x)); r.write_bytes(pack(y))
    return reg.compare('frozen', a, r, {'dtype': dtype, 'shape': [len(x)]},
                       semantics=kwargs.pop('semantics', 'continuous'),
                       producer={'kind':'ggml_node', 'index':7},
                       fp32_indices=frozenset({7}) if dtype == 'f32le' else frozenset(), **kwargs)


@pytest.mark.parametrize('dtype', ['f32le', 'bf16le'])
def test_zero_reference_boundary_and_full_failures(tmp_path, dtype):
    reg = registered(tmp_path)
    got = compare(tmp_path, reg, [0.125, 0.25, 1.375, 1.5, -1.5], [0, 0, 1, 1, -1], dtype)
    assert not got['passed'] and got['elements'] == 5 and got['failed_elements'] == 3
    assert got['first_failure'] == 1 and got['max_absolute_error'] == .5
    assert not got['official_model_accepted'] and not got['hardware_execution_verified']


@pytest.mark.parametrize('dtype', ['f32le', 'bf16le'])
def test_late_difference_across_stream_boundary(tmp_path, dtype):
    reg = registered(tmp_path, params={'atol':0, 'rtol':0})
    x = [0.] * (1048576 // br.WIDTHS[dtype] + 3)
    y = x.copy(); x[-1] = 1
    got = compare(tmp_path, reg, x, y, dtype)
    assert got['elements'] == len(x) and got['first_failure'] == len(x)-1
    assert got['failed_elements'] == 1


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -float('inf')])
@pytest.mark.parametrize('side', ['actual', 'reference'])
@pytest.mark.parametrize('name', list(EQUATIONS))
def test_nonfinite_never_accepted(tmp_path, value, side, name):
    reg = registered(tmp_path, name)
    with pytest.raises(br.ReceiptError, match='nonfinite'):
        compare(tmp_path, reg, [value if side=='actual' else 0], [value if side=='reference' else 0])


@pytest.mark.parametrize('semantics', ['route','index','selection','counter'])
def test_no_approx_discrete_even_if_identical(tmp_path, semantics):
    reg = registered(tmp_path)
    with pytest.raises(br.ReceiptError, match='bit-exact'):
        compare(tmp_path, reg, [1], [1], semantics=semantics)
    reg = registered(tmp_path, 'bit_exact')
    assert compare(tmp_path, reg, [1], [1], semantics=semantics)['passed']


def test_unsigned_routes_and_signed_zero(tmp_path):
    reg = registered(tmp_path, 'bit_exact')
    assert compare(tmp_path, reg, [0xffffffff], [0xffffffff], 'u32le', semantics='route')['passed']
    assert not compare(tmp_path, reg, [-0.0], [0.0])['passed']
    reg = registered(tmp_path)
    assert compare(tmp_path, reg, [-0.0], [0.0])['passed']


@pytest.mark.parametrize('params', [{'atol':True,'rtol':0}, {'atol':-1,'rtol':0},
    {'atol':math.inf,'rtol':0}, {'atol':0.002}, {'threshold':0.002}, {'atol':0,'rtol':0,'extra':1}])
def test_bad_tolerance_contract(tmp_path, params):
    with pytest.raises(br.ReceiptError):
        registered(tmp_path, params=params)


@pytest.mark.parametrize('changes', [{'formula':'relative_0.002'}, {'source_anchor':''},
    {'source_revision':'main'}, {'equation':'abs(a-r)/r <= 0.002'}, {'version':True},
    {'evidence_class':'official_accepted'}, {'extra':'surprise'}])
def test_missing_or_unknown_source_contract(tmp_path, changes):
    with pytest.raises(br.ReceiptError):
        registered(tmp_path, **changes)


def test_missing_duplicate_mutated_source_and_hash(tmp_path):
    reg = FormulaRegistry()
    with pytest.raises(br.ComparisonUnavailable): reg.get('undefined')
    p, h = contract(tmp_path)
    with pytest.raises(br.ReceiptError): reg.register(tmp_path, p.name, '0'*64)
    reg.register(tmp_path, p.name, h)
    with pytest.raises(br.ReceiptError): reg.register(tmp_path, p.name, h)
    p.write_text(p.read_text()+' ')
    with pytest.raises(br.ReceiptError): reg.get('frozen')
    with pytest.raises(br.ReceiptError): FormulaRegistry().register(tmp_path,'../escape',h)


def test_metric_overflow_fails_closed(tmp_path):
    reg = registered(tmp_path, params={'atol':0, 'rtol':1e308})
    with pytest.raises(br.ReceiptError, match='overflow'): compare(tmp_path, reg, [3.0], [3.0])


def test_registered_formula_does_not_enable_receipt_v1_approximation(tmp_path):
    registered(tmp_path)
    from test_block_receipt import fixture, write
    spec, _ = fixture(tmp_path)
    spec['tensors'][0]['comparison'] = 'frozen'
    write(tmp_path/'manifest.json', spec)
    with pytest.raises(br.ComparisonUnavailable):
        br.verify(tmp_path/'manifest.json', tmp_path/'receipt.json', tmp_path)


def test_producer_policy_and_truncation(tmp_path):
    reg=registered(tmp_path)
    a,r=tmp_path/'a',tmp_path/'r'; a.write_bytes(struct.pack('<f',1)); r.write_bytes(a.read_bytes())
    indices=fp32_boundary_indices([{'operation':'layer.oproj','roots':{'dst':2},
        'root_bindings':{'2':{'kind':'ggml_node','index':7}}}])
    assert reg.compare('frozen',a,r,{'dtype':'f32le','shape':[1]},semantics='continuous',
                       producer={'kind':'ggml_node','index':7},fp32_indices=indices)['passed']
    for tensor, producer in [({'dtype':'f32le','shape':[1]}, None),
                            ({'dtype':'bf16le','shape':[1]}, {'kind':'ggml_node','index':7}),
                            ({'dtype':'f32le','shape':[2]}, {'kind':'ggml_node','index':7})]:
        with pytest.raises(br.ReceiptError):
            reg.compare('frozen',a,r,tensor,semantics='continuous',producer=producer,fp32_indices=indices)
    with pytest.raises(br.ReceiptError):
        reg.compare('frozen',a,a,{'dtype':'f32le','shape':[1]},semantics='continuous',
                    producer={'kind':'ggml_node','index':7},fp32_indices=indices)


@pytest.mark.parametrize('target', ['actual', 'reference', 'formula'])
def test_mutation_between_byte_and_metric_passes(tmp_path, monkeypatch, target):
    reg = registered(tmp_path)
    original = br.compare_files
    def changed(a, r, dtype, size):
        got = original(a, r, dtype, size)
        if target == 'formula':
            p = tmp_path/'formula.json'; p.write_text(p.read_text()+' ')
        else:
            p = a if target == 'actual' else r
            p.write_bytes(struct.pack('<f', 1.125))
        return got
    monkeypatch.setattr(br, 'compare_files', changed)
    with pytest.raises(br.ReceiptError, match='changed'):
        compare(tmp_path, reg, [1], [1])


def test_exact_contract_cannot_acquire_tolerance(tmp_path):
    with pytest.raises(br.ReceiptError):
        registered(tmp_path, 'bit_exact', params={'atol':0.002,'rtol':0})
