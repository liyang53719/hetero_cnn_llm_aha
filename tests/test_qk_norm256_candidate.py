"""Frozen authority, admission, integer policy and independent binary32 tests.

Acceptance checks call require, rather than relying on Python assert, and run
unchanged with PYTHONOPTIMIZE=1. The end-to-end runner scores every frozen head.
"""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import numpy as np
import pytest
from heteronpu.model_geometry import require
from heteronpu import qk_norm256_candidate as q
from heteronpu.rope_bf16_candidate import add_rne, mul_rne

ROOT = Path(__file__).resolve().parents[1]


def historical_available():
    """Fresh CI rebuilds official data; historical archives are optional locally."""
    return (q.FIXTURES / 'provenance.json').is_file()


historical_only = pytest.mark.skipif(
    not historical_available(), reason='optional historical archives absent; fresh official replay is a separate required CI gate')


@pytest.mark.parametrize('name', ['local', 'remote'])
@historical_only
def test_frozen_source_geometry_and_independent_authority(name):
    data, origin = q.load_corpus(name)
    require(data['input_bf16_u32'].shape == (2560, 256), 'full cold/carried corpus missing')
    require(data['gate_bf16_u32'].shape == (2048, 256), 'Q gate incomplete')
    require(np.count_nonzero(data['role'] == 0) == 2048 and np.count_nonzero(data['role'] == 1) == 512, 'head count drift')
    require(origin['original_audit_report']['sha256'] == q.ORIGINAL_REPORT_SHA256[name], 'report authority drift')
    require(origin['original_audit_arrays']['sha256'] == q.ORIGINAL_ARRAYS_SHA256[name], 'array authority drift')
    require(origin['historical_native_audit_status'] == 'BLOCKED_BF16_PRODUCER_GATE', 'historical failure was rewritten')
    for row in range(2560):
        require(q.admit(data['input_bf16_u32'][row],data['weight_bf16_u32'][data['role'][row]]) == 0,'frozen source outside admitted domain')
    with pytest.raises(ValueError): data['input_bf16_u32'][0, 0] = 0


@pytest.mark.parametrize('field,bad', [('policy',0),('policy',True),('role',2),('role',False),('head_dim',128),('epsilon',0x358637BE)])
def test_descriptor_fail_closed(field,bad):
    x=[0]*256
    require(q.admit(x,x,**{field:bad}) == q.STATUS_DESCRIPTOR,'descriptor accepted')


@pytest.mark.parametrize('word,status', [
    (0,0),(0x80000000,0),(95<<23,0),(0x80000000|(95<<23),0),((158<<23)|0x7F0000,0),
    (94<<23,3),(159<<23,3),(0x00010000,3),(0x3F800001,3),(0x7F800000,2),(0xFF800000,2),
    (0x7FC00000,2),(0x7F810000,2),
])
def test_admission_range_nonfinite_and_weight_domains(word,status):
    zeros=[0]*256;other=zeros.copy();other[91]=word
    require(q.admit(other,zeros)==status and q.admit(zeros,other)==status,'admission domain drift')


def test_rejection_priority_and_noncoercing_dtypes():
    x=[0]*256;w=[0]*256;x[0]=0x00010000;w[0]=0x7FC00000
    require(q.admit(x,w)==2,'nonfinite must outrank finite range')
    require(q.admit(x,w,policy=0)==1,'descriptor must outrank operands')
    for bad in ([0.0]*256,[False]*256,[0]*255,np.zeros(256,dtype=np.float32),np.zeros((1,256),dtype=np.uint32)):
        with pytest.raises(ValueError): q.head_trace(bad,[0]*256)
    with pytest.raises(ValueError): q.head_trace(x,[0]*256)


def test_zero_negative_zero_gamma_and_trace_shape():
    x=[0x80000000 if i%2 else 0 for i in range(256)]
    w=[0xBF800000 if i%3 else 0 for i in range(256)]
    t=q.head_trace(x,w)
    require(t['mean']==0 and t['mean_eps']==q.EPSILON,'zero mean arithmetic drift')
    require(t['output_bf16']==tuple(x),'signed zero transport drift')
    require(t['gamma']==tuple(0 if i%3 else 0x3F800000 for i in range(256)),'1+weight omitted')
    require(len(q.trace_words(t))==q.TRACE_WORDS==3132,'trace ABI drift')
    require(t['aggregate_flags']==(t['arithmetic_flags']|t['conversion_flags']),'aggregate flag drift')
    require(t['domain_error']==0,'admitted input domain error')


def test_literal_rsqrt_rom_and_exact_newton_sequence():
    import re
    rtl=(ROOT/'rtl/sfu/fp32_rsqrt_coeffs.svh').read_text()
    literals=tuple(int(s,16) for s in re.findall(r"rsqrt_pwl_coeff=64'h([0-9a-f]{16})",rtl))
    require(literals==q.RSQRT_COEFFICIENTS,'RTL literal ROM drift')
    for word in (q.EPSILON,0x3F800000,0x40000000,0x3FABCDEF,0x00800000,0x7F000000):
        t=q.rsqrt_trace(word);r=t['rsqrt_values'];f=t['rsqrt_flags']
        m,b=q.RSQRT_COEFFICIENTS[t['rsqrt_index']]>>32,q.RSQRT_COEFFICIENTS[t['rsqrt_index']]&0xFFFFFFFF
        operations=[mul_rne(m,t['rsqrt_norm']),add_rne(r[0],b),mul_rne(r[1],r[1]),mul_rne(t['rsqrt_norm'],r[2]),mul_rne(0x3F000000,r[3]),add_rne(0x3FC00000,r[4]^0x80000000),mul_rne(r[1],r[5]),mul_rne(r[6],t['rsqrt_scale'])]
        require(tuple(operations)==tuple(zip(r,f)),'Newton operation sequence drift')


def test_balanced_16_then_serial_16_reduction():
    x = np.asarray([((95 + i % 64) << 23) | ((i % 128) << 16) for i in range(256)], dtype=np.uint32)
    t = q.head_trace(x, np.zeros(256, dtype=np.uint32))
    total=0
    for chunk in range(16):
        level=list(t['squares'][chunk*16:chunk*16+16]);expected=[]
        while len(level)>1:
            level=[add_rne(level[i],level[i+1])[0] for i in range(0,len(level),2)];expected.extend(level)
        require(tuple(expected)==t['tree'][chunk*15:chunk*15+15],'balanced16 tree drift')
        require(level[0]==t['partials'][chunk],'partial drift')
        total=add_rne(total,level[0])[0]
        require(total==t['running'][chunk],'serial16 sum drift')
    require(t['mean']==mul_rne(total,0x3B800000)[0],'division by256 drift')


@historical_only
def test_frozen_data_tampering_rejected_before_use(tmp_path):
    for p in q.FIXTURES.iterdir():
        if p.is_file(): shutil.copy2(p,tmp_path/p.name)
    path=tmp_path/'local.npz';data=bytearray(path.read_bytes());data[-1]^=1;path.write_bytes(data)
    with pytest.raises(ValueError,match='corpus hash'): q.load_corpus('local',tmp_path)
    path=tmp_path/'provenance.json';d=json.loads(path.read_text());d['policy']=0;path.write_text(json.dumps(d))
    with pytest.raises(ValueError,match='provenance hash'): q.load_corpus('remote',tmp_path)


@historical_only
def test_array_schema_and_dtype_fail_closed():
    d,p=q.load_corpus('local')
    bad=dict(d);bad['extra']=np.zeros(1,dtype=np.uint32)
    with pytest.raises(ValueError,match='schema'): q._validate_arrays(bad,p)
    bad=dict(d);bad['input_bf16_u32']=bad['input_bf16_u32'].view(np.float32)
    with pytest.raises(ValueError,match='dtype'): q._validate_arrays(bad,p)
    bad=dict(d);bad['input_bf16_u32']=bad['input_bf16_u32'][:1]
    with pytest.raises(ValueError,match='shape'): q._validate_arrays(bad,p)


def test_independent_c_values_and_flags(tmp_path):
    cc=shutil.which('cc')
    if cc is None: pytest.skip('independent C compiler not installed')
    binary=tmp_path/'reference'
    subprocess.run([cc,'-std=c11','-O2','-fno-fast-math','-ffp-contract=off','-frounding-math',str(ROOT/'scripts/qk_norm256_reference.c'),'-lm','-o',str(binary)],check=True)
    rows=[]
    for name in (('local','remote') if historical_available() else ()):
        d,_=q.load_corpus(name)
        for i in (0,1,7,8,511,1023,1024,1279,1280,2047,2303,2304,2559):
            rows.append(np.concatenate((d['input_bf16_u32'][i],d['weight_bf16_u32'][d['role'][i]])))
    # Fully admitted extremal magnitudes, signed zeros, and cancellation gamma.
    rng=np.random.default_rng(193)
    for _ in range(32):
        words=((rng.integers(0,2,512,dtype=np.uint32)<<31)|(rng.integers(95,159,512,dtype=np.uint32)<<23)|(rng.integers(0,128,512,dtype=np.uint32)<<16))
        words[::17]=0x80000000;words[256::19]=0xBF800000;rows.append(words)
    rows.append(np.zeros(512,dtype=np.uint32))
    inputs=np.asarray(rows,dtype='<u4');inputs.tofile(tmp_path/'input.bin')
    expected=np.asarray([q.trace_words(q.head_trace(r[:256],r[256:])) for r in inputs],dtype='<u4')
    subprocess.run([str(binary),str(tmp_path/'input.bin'),str(tmp_path/'output.bin')],check=True)
    actual=np.fromfile(tmp_path/'output.bin',dtype='<u4').reshape(-1,q.TRACE_WORDS)
    require(actual.shape==expected.shape and np.array_equal(actual,expected),'independent C operation/value/flag mismatch; no tiny flag waivers')
    (tmp_path/'bad.bin').write_bytes(b'bad')
    rejected=subprocess.run([str(binary),str(tmp_path/'bad.bin'),str(tmp_path/'badout.bin')],capture_output=True)
    require(rejected.returncode==3,'partial C record accepted')


def test_fail_closed_checks_survive_python_optimization():
    code='from heteronpu.qk_norm256_candidate import *\ntry:\n head_trace([0.0]*256,[0]*256)\nexcept ValueError:\n pass\nelse:\n raise RuntimeError("optimized validation vanished")\n'
    subprocess.run([sys.executable,'-O','-c',code],check=True)
