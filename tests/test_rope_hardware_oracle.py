import random
import struct

import numpy as np
import pytest

from heteronpu.rope_hardware_oracle import add_rne, mul_rne, pair_rne, bf16_rne_word, native_bf16_pair


def bits(x):
    return struct.unpack('<I', struct.pack('<f', x))[0]


def value(x):
    return struct.unpack('<f', struct.pack('<I', x))[0]


@pytest.mark.parametrize('operation, a, b, expected, flags', [
    (add_rne, 0x3F800000, 0x33800000, 0x3F800000, 1),
    (add_rne, 0x3F800001, 0x33800000, 0x3F800002, 1),
    (add_rne, 0x3F800000, 0xBF800000, 0, 0),
    (add_rne, 0x80000000, 0x80000000, 0x80000000, 0),
    (add_rne, 0x80000000, 0, 0, 0),
    (mul_rne, 0x80000000, 0x3F800000, 0x80000000, 0),
    (mul_rne, 1, 0x3F000000, 0, 3),
    (mul_rne, 3, 0x3F000000, 2, 3),
    (mul_rne, 0x00800000, 0x3F000000, 0x00400000, 0),
    (mul_rne, 0x00800000, 0x3F7FFFFF, 0x00800000, 3),
    (mul_rne, 0x00800001, 0x3F7FFFFE, 0x00800000, 1),
])
def test_ieee_directed(operation, a, b, expected, flags):
    assert operation(a,b) == (expected,flags)


@pytest.mark.parametrize('operation', [add_rne,mul_rne])
def test_exact_integer_rounding_matches_independent_float32(operation):
    r = random.Random(32721)
    for _ in range(3000):
        a,b = (bits(np.float32(r.uniform(-100,100))) for _ in range(2))
        x,y = np.float32(value(a)),np.float32(value(b))
        expected = bits(np.float32(x+y if operation is add_rne else x*y))
        assert operation(a,b)[0] == expected


@pytest.mark.parametrize('word', [0x7F800000,0xFF800000,0x7FC00000,-1,2**32,True,1.0])
def test_nonfinite_and_malformed_rejected(word):
    with pytest.raises((ValueError,TypeError)):
        pair_rne(word,0,0x3F800000,0)


def test_overflow_rejected():
    with pytest.raises(ValueError,match='overflow'):
        mul_rne(0x7F7FFFFF,0x40000000)
    with pytest.raises(ValueError,match='overflow'):
        bf16_rne_word(0x7F7FFFFF)


def test_native_rounding_is_distinct():
    r = random.Random(33)
    for _ in range(100):
        operands = [bf16_rne_word(bits(r.uniform(-4,4))) for _ in range(4)]
        hw = tuple(bf16_rne_word(v) for v in pair_rne(*operands)[:2])
        native = native_bf16_pair(*operands)
        if hw != native:
            break
    else:
        pytest.fail('no rounding-boundary witness')


def test_no_implicit_fma():
    # (1+2^-23)*(1-2^-23)-1 rounds product to 1, then cancels.
    assert pair_rne(0x3F800001,0x3F800000,0x3F7FFFFE,0x3F800000)[0] == 0
    assert (1+2**-23)*(1-2**-23)-1 != 0


def test_native_requires_bf16_operands():
    with pytest.raises(ValueError,match='BF16 operands'):
        native_bf16_pair(0x3F800001,0,0,0)


def load_runner():
    import importlib.util
    from pathlib import Path
    p=Path(__file__).resolve().parents[1]/'scripts/run_rope_hardware_oracle.py'
    spec=importlib.util.spec_from_file_location('rope_runner_test',p)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_frozen_existing_arithmetic_contract():
    c=load_runner().contract()
    assert len(c['rtl_source_sha256'])==4
    assert c['ports'].startswith('FP32 in/out')


@pytest.mark.parametrize('text', ['', '00000000 00000000 00\n00000000 00000000 00\n',
    '00000000 00000000 01\n', '00000001 00000000 00\n', 'x 00000000 00\n'])
def test_incomplete_or_mismatched_rtl_output_rejected(tmp_path,text):
    path=tmp_path/'out.txt';path.write_text(text)
    with pytest.raises(ValueError):
        load_runner().verify_outputs(path,np.zeros((1,7),dtype=np.uint32))


def test_exact_rtl_output_admitted(tmp_path):
    path=tmp_path/'out.txt';path.write_text('00000000 80000000 03\n')
    expected=np.array([[0,0,0,0,0,0x80000000,3]],dtype=np.uint32)
    np.testing.assert_array_equal(load_runner().verify_outputs(path,expected),expected[:,4:])


def test_untrusted_audit_rejected_before_loading_arrays(tmp_path):
    (tmp_path/'result.json').write_text('{}')
    runner=load_runner()
    with pytest.raises(ValueError,match='untrusted'):
        runner.load_audit(tmp_path,runner.contract())


def test_contract_drift_rejected(tmp_path,monkeypatch):
    runner=load_runner()
    p=tmp_path/runner.CONTRACT_PATH;p.parent.mkdir(parents=True);p.write_text('{}')
    monkeypatch.setattr(runner,'ROOT',tmp_path)
    with pytest.raises(ValueError,match='contract drift'):
        runner.contract()


def test_subnormal_random_against_independent_float32():
    r=random.Random(7881)
    for operation in (add_rne,mul_rne):
        for _ in range(1000):
            a=r.randrange(0x00800000) | (r.randrange(2)<<31)
            b=r.randrange(0x00800000) | (r.randrange(2)<<31)
            x,y=np.float32(value(a)),np.float32(value(b))
            with np.errstate(under='ignore'):
                expected=bits(np.float32(x+y if operation is add_rne else x*y))
            assert operation(a,b)[0]==expected


def load_manifest_module():
    import importlib.util
    from pathlib import Path
    p=Path(__file__).resolve().parents[1]/'chisel/rope_hardware_oracle/manifest.py'
    spec=importlib.util.spec_from_file_location('rope_manifest_test',p)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('extra', ['extra.sbt','project/evil.scala','lib/extra.jar','src/main/scala/target/Evil.scala'])
def test_extra_emission_source_rejected(tmp_path,extra):
    import shutil
    from pathlib import Path
    source=Path(__file__).resolve().parents[1]/'chisel/rope_hardware_oracle'
    project=tmp_path/'chisel/rope_hardware_oracle'
    shutil.copytree(source,project,ignore=shutil.ignore_patterns('target','__pycache__'))
    module=load_manifest_module()
    module.verify_project_inventory(tmp_path)
    p=project/extra;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('unapproved source')
    with pytest.raises(SystemExit,match='inventory mismatch'):
        module.verify_project_inventory(tmp_path)


def test_missing_emission_source_rejected(tmp_path):
    with pytest.raises(SystemExit,match='inventory mismatch'):
        load_manifest_module().verify_project_inventory(tmp_path)


@pytest.mark.parametrize('explicit',[False,True])
def test_verilator_selection_consistent(tmp_path,monkeypatch,explicit):
    monkeypatch.setenv('VERILATOR_BIN','unexpected-inherited-tool')
    runner=load_runner()
    selected=tmp_path/'chosen-verilator' if explicit else None
    env,path=runner.emission_environment(tmp_path,selected)
    if explicit:
        assert env['VERILATOR_BIN']==str(selected) and path==selected
    else:
        assert 'VERILATOR_BIN' not in env
        assert path==runner.ROOT/'work/rope_hardware_oracle/bin/verilator'
