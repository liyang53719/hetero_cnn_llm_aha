# SPDX-License-Identifier: Apache-2.0
"""Independent small numerical golden and guarded-source software-only checks."""
import ctypes
import ctypes.util
import importlib.util
import math
from pathlib import Path
import shutil

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('qwen_recipe', ROOT/'scripts/qwen2_block_recipe_model.py')
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def test_guarded_extraction_and_no_simulator(tmp_path):
    helpers, maths, provenance = m.extract_sources(ROOT)
    assert 'std::fma' in maths and 'computeReference' in maths
    assert not any(word in helpers+maths for word in ('verilated','BlockDut','VQwen','d.eval'))
    assert provenance['section_sha256'] == m.SECTION_SHA256
    source = tmp_path/m.SOURCE
    source.parent.mkdir(parents=True)
    source.write_text((ROOT/m.SOURCE).read_text().replace('float inv=1.0f/sum;', 'float inv=2.0f/sum;'))
    layout = tmp_path/m.LAYOUT_SOURCE
    layout.parent.mkdir(parents=True)
    shutil.copyfile(ROOT/m.LAYOUT_SOURCE,layout)
    with pytest.raises(ValueError,match='canonical math section changed'):
        m.extract_sources(tmp_path)
    with pytest.raises(ValueError,match='boundary absent or ambiguous'):
        m.section('begin begin end','begin','end')


def test_layout_matches_existing_independent_vector():
    # Existing Scala test vectors predate this runner; do not derive expected
    # offsets from the implementation under test.
    path=ROOT/'chisel/continuous_prefill/src/test/resources/c03_3/legacy_layout_vectors.tsv'
    fields=next(line for line in path.read_text().splitlines() if line.startswith('legacy_tail\t')).split('\t')
    shape=dict(zip(m.SHAPE,map(int,fields[1:7])))
    layout=m.make_layout(shape)
    assert layout['writable_start']==int(fields[9])
    assert layout['arena_bytes']==int(fields[10])
    assert [(r['name'],r['offset'],r['words'],int(r['external'])) for r in layout['regions']] == [
        (x.split(':')[0],*map(int,x.split(':')[1:])) for x in fields[11].split(',')]
    real=m.make_layout()
    assert real['max_tokens']==128 and real['generated_by_chisel'] is False
    assert real['writable_start']==188043264
    assert real['arena_bytes']==209276928
    assert m.logical_macs(16)['total']==749101056
    assert m.logical_macs(128)['total']==6014828544


def bf16(value):
    x=np.asarray(value,dtype='<f4').copy()
    words=x.view('<u4')
    words[...] = (words + np.uint32(0x7fff) + ((words>>16)&1)) & np.uint32(0xffff0000)
    return x


def independent_golden(x, weights, gamma0, gamma1, biases):
    """Independent scalar expression model using libm fmaf, not C++ extraction."""
    lib=ctypes.CDLL(ctypes.util.find_library('m'))
    lib.fmaf.argtypes=[ctypes.c_float]*3
    lib.fmaf.restype=ctypes.c_float
    fp=np.float32
    def fma(a,b,c): return fp(lib.fmaf(float(a),float(b),float(c)))
    def round_bf(a): return fp(bf16(a))
    def norm(a,gamma):
        out=np.empty_like(a)
        for t,row in enumerate(a):
            total=fp(0)
            for v in row: total=fp(total+fp(v*v))
            inv=fp(fp(1)/fp(np.sqrt(fp(fp(total*fp(1/len(row)))+fp(1e-6)))))
            out[t]=bf16(fp(fp(row*inv)*gamma))
        return out
    def dense(a,w,bias=None):
        out=np.zeros((a.shape[0],w.shape[1]),dtype='<f4')
        for t in range(len(a)):
            for col in range(w.shape[1]):
                for k in range(w.shape[0]): out[t,col]=fma(round_bf(a[t,k]),round_bf(w[k,col]),out[t,col])
                if bias is not None: out[t,col]=fp(out[t,col]+bias[col])
        return out
    def rope(a):
        out=np.empty_like(a)
        for t in range(len(a)):
            for j in range(16):
                angle=t/(1000000.0**(2*j/32))
                c,s=fp(math.cos(angle)),fp(math.sin(angle))
                out[t,j]=fp(fp(a[t,j]*c)-fp(a[t,j+16]*s))
                out[t,j+16]=fp(fp(a[t,j]*s)+fp(a[t,j+16]*c))
        return out
    coefficients=[fp(math.pow(-math.log(2),i)/math.factorial(i)) for i in range(8)]
    def expneg(a):
        a=abs(a)
        if a>=80:return fp(0)
        z=fp(a*fp(1/math.log(2)));k=int(z);fraction=fp(z-fp(k))
        y=coefficients[-1]
        for coefficient in reversed(coefficients[:-1]):y=fp(fp(y*fraction)+coefficient)
        return fp(y*fp(2.0**-k))
    s={}
    s['n0']=norm(x,gamma0)
    for name,w,bias in [('qr','wq','bq'),('kr','wk','bk'),('v','wv','bv')]:
        s[name]=dense(s['n0'],weights[w],biases[bias])
    s['q'],s['k']=rope(s['qr']),rope(s['kr'])
    att=np.empty_like(x)
    for t in range(len(x)):
        score=[]
        for key in range(t+1):
            partial=[fp(0)]*16
            for j in range(32):partial[j%16]=fma(round_bf(s['q'][t,j]),round_bf(s['k'][key,j]),partial[j%16])
            total=fp(0)
            for v in partial:total=fp(total+v)
            score.append(fp(total*fp(1/math.sqrt(32))))
        probabilities=[expneg(fp(v-max(score))) for v in score]
        total=fp(0)
        for v in probabilities:total=fp(total+v)
        inv=fp(fp(1)/total)
        for j in range(32):
            total=fp(0)
            for key,p in enumerate(probabilities):total=fma(round_bf(fp(p*inv)),round_bf(s['v'][key,j]),total)
            att[t,j]=total
    s['att']=att;s['o']=dense(att,weights['wo']);s['r']=fp(x+s['o'])
    s['n1']=norm(s['r'],gamma1)
    s['gate']=dense(s['n1'],weights['wg']);s['up']=dense(s['n1'],weights['wu'])
    s['act']=np.empty_like(s['gate'])
    for ix in np.ndindex(s['act'].shape):
        g=s['gate'][ix];e=expneg(g);sig=fp(fp(1)/fp(fp(1)+e));sig=fp(sig*(e if np.signbit(g) else fp(1)))
        s['act'][ix]=fp(fp(sig*g)*s['up'][ix])
    s['down']=dense(s['act'],weights['wd']);s['y']=fp(s['r']+s['down'])
    return s


@pytest.mark.skipif(shutil.which('g++') is None,reason='ordinary C++ compiler unavailable')
def test_all_fifteen_stages_independent_small_golden(tmp_path):
    shape=dict(hidden=32,ffn=32,heads=1,kv_heads=1,head_dim=32,max_tokens=2)
    layout,provenance=m.generate_and_compile(ROOT,tmp_path/'generated',shape)
    assert provenance['compile_command'][1:5]==m.FLAGS
    text=(tmp_path/'generated/software_recipe.cpp').read_text()
    assert 'FE_TONEAREST' in text
    assert not any(x in text for x in ('verilated','VQwen','BlockDut','d.eval'))
    regions={r['name']:r for r in layout['regions']}
    arena=np.zeros(layout['writable_start']//4,dtype='<f4')
    def put(name,value):
        start=regions[name]['offset']//4
        arena[start:start+np.asarray(value).size]=np.asarray(value,dtype='<f4').reshape(-1)
    weights={}
    for number,name in enumerate(m.WEIGHTS):
        weights[name]=bf16(((np.arange(32*32).reshape(32,32)*(2*number+3))%29-14).astype('<f4')/128)
        put(name,weights[name])
    gamma0=bf16(1+np.arange(32,dtype='<f4')/128)
    gamma1=bf16(1-np.arange(32,dtype='<f4')/256)
    biases={name:(np.arange(32,dtype='<f4')%7-3)/64 for name in ('bq','bk','bv')}
    put('gamma0',gamma0);put('gamma1',gamma1)
    for name,value in biases.items():put(name,value)
    x=((np.arange(64).reshape(2,32)*7)%31-15).astype('<f4')/16
    put('x',x)
    angles=np.arange(2,dtype=np.float64)[:,None]/(1000000.0**(np.arange(16,dtype=np.float64)[None,:]/16))
    put('cos',np.cos(angles));put('sin',np.sin(angles))
    arena.tofile(tmp_path/'arena')
    m.execute(tmp_path/'generated',tmp_path/'arena',2,tmp_path,timeout_seconds=30)
    expected=independent_golden(x,weights,gamma0,gamma1,biases)
    for phase,name in enumerate(m.STAGE_NAMES):
        actual=np.fromfile(tmp_path/f'phase_{phase}_{name}_recipe.f32le',dtype='<f4').reshape(2,32)
        np.testing.assert_array_equal(actual.view('<u4'),expected[name].view('<u4'),err_msg=name)
    # A raw input perturbation must propagate through the model to the residual.
    assert not np.array_equal(expected['y'],x)
    with pytest.raises(ValueError,match='existing generated'):
        m.generate_and_compile(ROOT,tmp_path/'generated',shape)
    with pytest.raises(ValueError,match='timeout'):
        m.execute(tmp_path/'generated',tmp_path/'arena',2,tmp_path,timeout_seconds=601)


def test_packing_refuses_invalid_input(tmp_path):
    with pytest.raises(ValueError,match='token outside'):
        m.pack_readonly(m.make_layout(),{},[256],tmp_path/'bad')
    with pytest.raises(ValueError,match='missing payload'):
        m.pack_readonly(m.make_layout(),{},[0],tmp_path/'bad')


def test_existing_budget_and_diagnostics():
    budget=m.existing_budget(ROOT)
    assert budget['thresholds']==dict(max_relative_l2=.01,min_cosine=.9999,max_normalized_abs=.05)
    metrics=m.error_metrics(np.array([1.,2.]),np.array([1.,2.]))
    assert metrics['relative_l2']==metrics['max_abs']==metrics['normalized_max_abs']==0
    assert metrics['cosine']==pytest.approx(1)
    with pytest.raises(ValueError,match='nonfinite'):
        m.error_metrics(np.array([np.nan]),np.array([0.]))


def test_m128_requires_m16_before_loading_payload(tmp_path):
    with pytest.raises(ValueError,match='completed M16 prerequisite'):
        m.run_recipe(ROOT,tmp_path/'no_payload',tmp_path/'out',tokens=128)


@pytest.mark.skipif(shutil.which('g++') is None,reason='ordinary C++ compiler unavailable')
def test_float_probes_reject_a_bad_execution_assumption(tmp_path):
    import subprocess
    shape=dict(hidden=32,ffn=32,heads=1,kv_heads=1,head_dim=32,max_tokens=1)
    layout,provenance=m.generate_and_compile(ROOT,tmp_path/'generated',shape)
    cpp=tmp_path/'generated/software_recipe.cpp'
    assert 'before & ~((1u<<15)|(1u<<6))' in cpp.read_text()
    cpp.write_text(cpp.read_text().replace('bits(mul(tiny,one))==1u','bits(mul(tiny,one))==2u'))
    subprocess.run(provenance['compile_command'],check=True,capture_output=True)
    (tmp_path/'arena').write_bytes(bytes(layout['writable_start']))
    with pytest.raises(ValueError,match='software recipe failed'):
        m.execute(tmp_path/'generated',tmp_path/'arena',1,tmp_path,timeout_seconds=30)
    assert 'subnormal multiply probe failed' in (tmp_path/'run.log').read_text()
    assert not list(tmp_path.glob('*_recipe.f32le'))


@pytest.fixture
def native_fixture(tmp_path):
    """Cheap zero-valued stages with valid mask/probability/cache semantics."""
    import hashlib
    import json
    mod=m.load_module(ROOT/'scripts/qwen2_layer0_model_gate.py','test_native_receipt')
    config=json.loads((ROOT/mod.SOURCE/'config.json').read_text())
    report=dict(schema_version=1,tokens=16,layer=0,model_id='Qwen/Qwen2-1.5B-Instruct',
                status='PASS_BF16_STAGE_BUDGET',official_framework_forward=True,rtl_execution=False,
                identity=dict(source_sha256=mod.SOURCE_HASHES,model_revision=mod.MODEL_REVISION,
                              forward_revision=mod.FORWARD_REVISION,installed_sources_verified_exact=True,
                              runner_sha256=m.file_sha(ROOT/'scripts/qwen2_layer0_model_gate.py')),
                payload_manifest_sha256='fixture-payload',policy=mod.load_policy(ROOT),carried=False,modes={})
    recipe=dict(shape=dict(m.SHAPE,tokens=16),checkpoint_manifest_sha256='fixture-payload',
                input=dict(input_x_sha256=hashlib.sha256(bytes(16*1536*4)).hexdigest()))
    for mode in ('bf16','fp32'):
        shapes=mod.expected_shapes(config,16,0)
        values={name:np.zeros(shape,dtype='<f4') for name,shape in shapes.items()}
        values['mask']=mod.causal_mask(16,0,mode)
        for t in range(16):values['softmax_fp32'][:,:,t,:t+1]=np.float32(1/(t+1))
        values['prob']=mod.bf16(values['softmax_fp32']) if mode=='bf16' else values['softmax_fp32'].copy()
        stages={}
        for name,array in values.items():
            entry=mod.compare(array,array)
            entry.update(mod.stage_verdict(name,entry,mode,report['policy']))
            is_bf16=mode=='bf16' and name!='softmax_fp32'
            entry['actual_storage_dtype']='torch.bfloat16' if is_bf16 else 'torch.float32'
            entry['actual_storage_sha256']=mod.digest_array((array.view('<u4')>>16).astype('<u2') if is_bf16 else array)
            for kind in ('native','independent'):
                relative=f'{mode}/phase_0/{kind}_{name}.f32le'
                path=tmp_path/relative;path.parent.mkdir(parents=True,exist_ok=True)
                exported=mod.export_value(array,name);exported.tofile(path)
                entry[kind+'_file']=relative;entry[kind+'_file_sha256']=m.file_sha(path)
                entry[kind+'_export_shape']=list(exported.shape)
            stages[name]=entry
        report['modes'][mode]=dict(phases=[dict(phase=0,past_tokens=0,token_ids=list(range(16)),position_ids=list(range(16)),
            failed_stages=[],all_semantics_exact=True,semantics={'fixture_exact':True},stages=stages,
            status='PASS_BF16_STAGE_BUDGET' if mode=='bf16' else 'DIAGNOSTIC_FP32')])
    (tmp_path/'RESULT.json').write_text(json.dumps(report))
    return tmp_path,report,recipe


def test_native_receipt_rejects_stale_hash_wrong_tokens_and_payload(native_fixture):
    import json
    directory,report,recipe=native_fixture
    assert m.validate_native_receipt(ROOT,directory,recipe)['status']=='PASS_BF16_STAGE_BUDGET'
    report['modes']['bf16']['phases'][0]['token_ids'][0]=1
    (directory/'RESULT.json').write_text(json.dumps(report))
    with pytest.raises(ValueError,match='phase/input/semantic'):
        m.validate_native_receipt(ROOT,directory,recipe)
    report['modes']['bf16']['phases'][0]['token_ids'][0]=0
    (directory/'RESULT.json').write_text(json.dumps(report))
    recipe['checkpoint_manifest_sha256']='wrong-payload'
    with pytest.raises(ValueError,match='payload mismatch'):
        m.validate_native_receipt(ROOT,directory,recipe)
    recipe['checkpoint_manifest_sha256']='fixture-payload'
    path=directory/'bf16/phase_0/native_y.f32le'
    raw=bytearray(path.read_bytes());raw[3]=1;path.write_bytes(raw)
    with pytest.raises(ValueError,match='tensor path/bytes/hash'):
        m.validate_native_receipt(ROOT,directory,recipe)


def test_native_receipt_rejects_wrong_input_with_valid_receipt(native_fixture):
    directory,_,recipe=native_fixture
    recipe['input']['input_x_sha256']='wrong-input'
    with pytest.raises(ValueError,match='input bytes differ'):
        m.validate_native_receipt(ROOT,directory,recipe)


def test_diagnostic_admission_preserves_failure_and_checks_hashes(tmp_path,monkeypatch):
    import json
    provenance={key:'fixture' for key in ('source_sha256','committed_cpp_sha256','section_sha256',
        'generated_cpp_sha256','generated_header_sha256','compiler_version','generator_sha256',
        'numerical_contract','rounding_mode')}
    provenance['compile_command']=['g++',*m.FLAGS,'fixture.cpp']
    x=tmp_path/'input_x.f32le';x.write_bytes(bytes(16*1536*4))
    result=dict(status='COMPLETE_SOFTWARE_HARDWARE_RECIPE',shape=dict(m.SHAPE,tokens=16),
        checkpoint_manifest={},source_identity=provenance,float_environment={'rounding':'FE_TONEAREST','probes':'10'},
        input={'token_ids':list(range(16)),'input_x_sha256':m.file_sha(x)},stages=[],estimated_m128_wall_seconds=30)
    widths=[1536,1536,256,256,1536,256,1536,1536,1536,1536,8960,8960,8960,1536,1536]
    for i,(name,width) in enumerate(zip(m.STAGE_NAMES,widths)):
        path=tmp_path/f'phase_{i}_{name}_recipe.f32le';path.write_bytes(bytes(16*width*4))
        result['stages'].append(dict(name=name,path=path.name,shape=[16,width],sha256=m.file_sha(path)))
    result_path=tmp_path/'RESULT.json';result_path.write_text(json.dumps(result))
    comparison=dict(tokens=16,status='FAIL_EXISTING_FP32_FINAL_BUDGET',native_gate_status='PASS_BF16_STAGE_BUDGET',
        recipe_result_sha256=m.file_sha(result_path),budget=m.existing_budget(ROOT),native_directory='fixture')
    (tmp_path/'REFERENCE_COMPARISON.json').write_text(json.dumps(comparison))
    # Source and complete native validation have separate tests; isolate the
    # numerical-admission switch while exercising real artifact hash checks.
    monkeypatch.setattr(m,'validate_recipe_receipt',lambda root,directory:result)
    monkeypatch.setattr(m,'build_comparison',lambda root,directory,native:comparison.copy())
    with pytest.raises(ValueError,match='failed M16 numerical gate'):
        m.verify_m16_prerequisite(ROOT,tmp_path,{},provenance,x)
    verdict=m.verify_m16_prerequisite(ROOT,tmp_path,{},provenance,x,allow_accuracy_failure=True)
    assert verdict['diagnostic_only'] and not verdict['numerical_gate_passed']
    assert verdict['inherited_comparison_status']=='FAIL_EXISTING_FP32_FINAL_BUDGET'
    path=tmp_path/result['stages'][0]['path'];raw=bytearray(path.read_bytes());raw[0]=1;path.write_bytes(raw)
    with pytest.raises(ValueError,match='stage changed or invalid'):
        m.verify_m16_prerequisite(ROOT,tmp_path,{},provenance,x,allow_accuracy_failure=True)


def test_diagnostic_flag_cannot_label_m16(tmp_path):
    with pytest.raises(ValueError,match='requires 128 tokens'):
        m.run_recipe(ROOT,tmp_path/'no_payload',tmp_path/'out',tokens=16,diagnostic_m128=True)


def test_budget_fragment_cannot_silently_change(monkeypatch):
    from types import SimpleNamespace
    run=m.subprocess.run
    def changed(*args,**kwargs):
        result=run(*args,**kwargs)
        return SimpleNamespace(stdout=result.stdout.replace('MAX_RELATIVE_L2=0.01','MAX_RELATIVE_L2=0.02'))
    monkeypatch.setattr(m.subprocess,'run',changed)
    with pytest.raises(ValueError,match='constant fragment changed'):
        m.existing_budget(ROOT)


def test_recipe_receipt_rejects_readonly_arena_hash_change(tmp_path):
    import json
    result=dict(status='COMPLETE_SOFTWARE_HARDWARE_RECIPE',shape=dict(m.SHAPE,tokens=16),stages=[])
    widths=[1536,1536,256,256,1536,256,1536,1536,1536,1536,8960,8960,8960,1536,1536]
    for phase,(name,width) in enumerate(zip(m.STAGE_NAMES,widths)):
        path=tmp_path/f'phase_{phase}_{name}_recipe.f32le';path.write_bytes(bytes(16*width*4))
        result['stages'].append(dict(phase=phase,name=name,path=path.name,shape=[16,width],sha256=m.file_sha(path)))
    size=m.make_layout()['writable_start']
    with (tmp_path/'readonly_arena.f32le').open('wb') as f:f.truncate(size)
    result['input']=dict(readonly_bytes=size,readonly_sha256='changed-arena')
    (tmp_path/'RESULT.json').write_text(json.dumps(result))
    with pytest.raises(ValueError,match='readonly arena bytes/hash'):
        m.validate_recipe_receipt(ROOT,tmp_path)
