# SPDX-License-Identifier: Apache-2.0
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess

import numpy as np
import pytest

ROOT=Path(__file__).resolve().parents[1]
S=importlib.util.spec_from_file_location('carried',ROOT/'scripts/qwen2_carried_prefill_candidate.py')
m=importlib.util.module_from_spec(S);S.loader.exec_module(m)


def test_source_retains_arithmetic_and_versioned_failure():
    source,identity=m.carried_source(ROOT)
    assert 'DIAGNOSTIC_NOT_ACCEPTED' in source
    assert 'std::fma(a[k],bf(weights[j]),sums[j])' in source
    assert 'float parts[16]={}' in source and 'expneg(add(p[k],-max))' in source
    assert 'k<=past+t' in source and 'cacheK.at(size_t(k)*KV+kh*HD+j)' in source
    assert identity['section_sha256']==m.R.SECTION_SHA256
    with pytest.raises(ValueError,match='boundary absent/ambiguous'):
        m.replace_once('xx','x','y')
    with pytest.raises(ValueError,match='boundary absent/ambiguous'):
        m.replace_once('xx','z','y')


def test_layout_alias_rejected():
    layout=m.R.make_layout();m.validate_layout(layout)
    layout['regions'][-1]['offset']=layout['regions'][-2]['offset']
    with pytest.raises(ValueError,match='alias/offset/shape'):m.validate_layout(layout)


def test_wrong_previous_receipt_hash_rejected_before_loading(tmp_path):
    (tmp_path/'RESULT.json').write_text('{}')
    with pytest.raises(ValueError,match='cold launch receipt hash mismatch'):
        m.load_cold(ROOT,tmp_path,16,'0'*64)


def test_reference_cache_changed_after_admission_rejected_at_consumption(tmp_path):
    path=tmp_path/'native_cache.f32le';np.ones((1,2,16,32),dtype='<f4').tofile(path)
    sha=m.R.file_sha(path)
    assert m.read_bound_tensor(path,(1,2,16,32),sha).shape==(1,2,16,32)
    a=np.fromfile(path,dtype='<f4');a[0]=2;a.tofile(path)
    with pytest.raises(ValueError,match='changed at consumption'):
        m.read_bound_tensor(path,(1,2,16,32),sha)


def tiny_payload():
    weights={}
    for i,(_, (key, _, _)) in enumerate(m.R.WEIGHTS.items()):
        weights[key]=np.eye(32,dtype='<f4')*np.float32((i+1)/16)
    weights['input_layernorm.weight']=np.ones(32,dtype='<f4')
    weights['post_attention_layernorm.weight']=np.ones(32,dtype='<f4')
    for name in ('q_proj','k_proj','v_proj'): weights[f'self_attn.{name}.bias']=np.zeros(32,dtype='<f4')
    embedding=np.zeros((256,32),dtype='<f4')
    for i in range(4):embedding[i]=np.roll(np.arange(32,dtype='<f4')/32-.375,7*i)
    raw={key:(m.N.bf16(value).view('<u4')>>16).astype('<u2').tobytes() for key,value in weights.items()}
    raw['embed_tokens.rows_0_255']=(embedding.view('<u4')>>16).astype('<u2').tobytes()
    return raw,weights,embedding


def execute(binary,arena,tokens,directory,past,k,v):
    directory.mkdir()
    return subprocess.run([str(binary),str(arena),str(tokens),str(directory),str(past),str(k),str(v)],
                          capture_output=True,text=True,timeout=30,check=True)


@pytest.mark.skipif(shutil.which('g++') is None,reason='ordinary C++ compiler unavailable')
def test_tiny_cold_bit_equivalence_carried_dependency_and_corruption(tmp_path):
    shape=dict(hidden=32,ffn=32,heads=1,kv_heads=1,head_dim=32,max_tokens=4)
    build=m.prepare(ROOT,tmp_path/'new',shape);base=m.C.prepare(ROOT,tmp_path/'base',shape)
    payload,weights,embedding=tiny_payload();layout=build['layout'];tokens=2
    cold_dir=tmp_path/'cold';cold_dir.mkdir()
    m.R.pack_readonly(layout,payload,[0,1],cold_dir/'readonly_arena.f32le')
    empty=tmp_path/'empty';empty.write_bytes(b'')
    execution=execute(tmp_path/'new/candidate',cold_dir/'readonly_arena.f32le',2,cold_dir/'raw_stages',0,empty,empty)
    assert 'unused_sentinels_exact=1' in execution.stdout
    base_stages=tmp_path/'base_stages';base_stages.mkdir()
    subprocess.run([str(tmp_path/'base/candidate'),str(cold_dir/'readonly_arena.f32le'),'2',str(base_stages)],check=True,capture_output=True,timeout=30)
    for p in base_stages.iterdir(): assert p.read_bytes()==(cold_dir/'raw_stages'/p.name).read_bytes(),p.name
    cold=m.C.load_actual(base_stages,cold_dir/'readonly_arena.f32le',cold_dir/'input_x.f32le',layout,2)
    # This proof uses previous actual writes, not a NumPy/native-injected cache.
    carry=tmp_path/'carry';carry.mkdir();m.write_arena(layout,payload,tokens,carry)
    k=cold_dir/'raw_stages/cache_k.f32le';v=cold_dir/'raw_stages/cache_v.f32le'
    execute(tmp_path/'new/candidate',carry/'readonly_arena.f32le',2,carry/'raw_stages',2,k,v)
    actual=m.load_actual(carry,layout,2,cold)
    expected,_=m.N.independent_forward(weights,embedding[2:4][None],m.config_for(layout),'bf16',
                                      (cold['cache_k'],cold['cache_v']))
    assert all(m.N.audit_semantics(actual,cold,m.config_for(layout),'bf16').values())
    for name in m.N.REQUIRED_STAGES:
        verdict=m.N.stage_verdict(name,m.N.compare(actual[name],expected[name]),'bf16',m.N.load_policy(ROOT))
        assert verdict['passed'] is not False,name
    assert actual['prob'].shape==(1,1,2,4)
    assert np.all(actual['prob'][...,0,3:]==0)
    assert actual['prob'][...,0,:2].sum()>0
    for name,path in (('cache_k',k),('cache_v',v)):
        changed=tmp_path/(name+'_changed');a=np.fromfile(path,dtype='<f4');a[:32]+=np.float32(4);a=m.N.bf16(a);a.tofile(changed)
        destination=tmp_path/name
        execute(tmp_path/'new/candidate',carry/'readonly_arena.f32le',2,destination,2,
                changed if name=='cache_k' else k,changed if name=='cache_v' else v)
        assert (destination/'phase_6_att_recipe.f32le').read_bytes()!=(carry/'raw_stages/phase_6_att_recipe.f32le').read_bytes()
        assert (destination/'phase_14_y_recipe.f32le').read_bytes()!=(carry/'raw_stages/phase_14_y_recipe.f32le').read_bytes()
        for stage in ('phase_4_q_recipe.f32le','phase_5_k_recipe.f32le','phase_3_v_recipe.f32le'):
            assert (destination/stage).read_bytes()==(carry/'raw_stages'/stage).read_bytes()
    bad=tmp_path/'truncated';bad.write_bytes(k.read_bytes()[:-4])
    with pytest.raises(subprocess.CalledProcessError):
        execute(tmp_path/'new/candidate',carry/'readonly_arena.f32le',2,tmp_path/'bad',2,bad,v)
    (carry/'raw_stages/phase_14_y_recipe.f32le').write_bytes(np.full((2,32),np.nan,dtype='<f4').tobytes())
    with pytest.raises(ValueError,match='nonfinite'):m.load_actual(carry,layout,2,cold)


def binding_fixture(tmp_path):
    cold_dir=tmp_path/'cold';cold_dir.mkdir();(cold_dir/'RESULT.json').write_text('{}')
    cold={name:np.full((1,2,2,32),i+1,dtype='<f4') for i,name in enumerate(('cache_k','cache_v'))}
    report=dict(candidate_binary_sha256='b'*64,raw_outputs=[{'sha256':'c'*64}],
                tensors=[dict(name=name,sha256=m.R.sha(a.tobytes())) for name,a in cold.items()])
    binding=m.cache_binding(cold_dir,report,cold,tmp_path,2)
    return binding,cold


@pytest.mark.parametrize('field,value',[
    ('source_cpp_sha256','0'*64),('source_binary_sha256','0'*64),('cold_result_sha256','0'*64),
    ('past_tokens',1),('position_ids',[0,1]),('token_ids',[4,5]),('prior_position_ids',[1,2])])
def test_cache_source_and_position_metadata_fail_closed(tmp_path,field,value):
    binding,cold=binding_fixture(tmp_path);changed=copy.deepcopy(binding);changed[field]=value
    with pytest.raises(ValueError,match='metadata mismatch'):m.validate_binding(changed,binding,tmp_path,cold,2)


def test_cache_corruption_swap_and_forged_local_hash_rejected(tmp_path):
    binding,cold=binding_fixture(tmp_path);m.validate_binding(binding,binding,tmp_path,cold,2)
    k,v=tmp_path/'previous_cache_k.f32le',tmp_path/'previous_cache_v.f32le'
    original=k.read_bytes();k.write_bytes(v.read_bytes())
    forged=copy.deepcopy(binding);forged['records'][0]['sha256']=m.R.file_sha(k)
    with pytest.raises(ValueError,match='cache bytes/hash/source/role'):
        m.validate_binding(forged,forged,tmp_path,cold,2)
    k.write_bytes(original);k.unlink();os.link(v,k)
    with pytest.raises(ValueError,match='cache bytes/hash/source/role|alias'):
        m.validate_binding(binding,binding,tmp_path,cold,2)


def test_cache_path_traversal_rejected_even_with_forged_local_binding(tmp_path):
    binding,cold=binding_fixture(tmp_path)
    binding['records'][0]['path']='cold/../previous_cache_k.f32le'
    with pytest.raises(ValueError,match='cache bytes/hash/source/role'):
        m.validate_binding(binding,binding,tmp_path,cold,2)


@pytest.mark.skipif(shutil.which('g++') is None,reason='ordinary C++ compiler unavailable')
def test_m16_admission_rechecks_freeze_raw_reference_and_gate(tmp_path,monkeypatch):
    # Tiny width, real C++ 16->32 token execution. Only the expensive official
    # checkpoint revalidation is replaced; all warm files/metrics are real.
    shape=dict(hidden=32,ffn=32,heads=1,kv_heads=1,head_dim=32,max_tokens=16)
    build=m.prepare(ROOT,tmp_path/'build',shape);payload,_,_=tiny_payload()
    cold_dir=tmp_path/'cold';cold_dir.mkdir();(cold_dir/'RESULT.json').write_text('{}')
    m.R.pack_readonly(build['layout'],payload,list(range(16)),cold_dir/'readonly_arena.f32le')
    empty=tmp_path/'empty';empty.write_bytes(b'')
    execute(tmp_path/'build/candidate',cold_dir/'readonly_arena.f32le',16,cold_dir/'raw_stages',0,empty,empty)
    cold=m.C.load_actual(cold_dir/'raw_stages',cold_dir/'readonly_arena.f32le',cold_dir/'input_x.f32le',build['layout'],16)
    cold_report=dict(candidate_binary_sha256='b'*64,raw_outputs=[{'sha256':'c'*64}],
                     tensors=[dict(name=n,sha256=m.R.sha(a.tobytes())) for n,a in cold.items()])
    warm=tmp_path/'warm';warm.mkdir();m.write_arena(build['layout'],payload,16,warm)
    binding=m.cache_binding(cold_dir,cold_report,cold,warm,16)
    execute(tmp_path/'build/candidate',warm/'readonly_arena.f32le',16,warm/'raw_stages',16,
            warm/'previous_cache_k.f32le',warm/'previous_cache_v.f32le')
    actual=m.load_actual(warm,build['layout'],16,cold)
    refs={method:actual for method in m.METHODS}
    for method in m.METHODS:
        dest=warm/'references'/method;dest.mkdir(parents=True)
        for name,a in actual.items():np.ascontiguousarray(a).tofile(dest/(name+'.f32le'))
    policy=m.N.load_policy(ROOT)
    frozen=dict(carry_binding=binding,generator_sha256=m.R.file_sha(Path(m.__file__)),build=build,inputs={},
                payload_manifest_sha256='d'*64,payload_pin_sha256=m.R.file_sha(ROOT/'config/payload_pins/qwen2_layer0.json'),
                official_reference_identity={},resource_preflight={},launch_small_result_sha256=None,
                launch_cold_result_sha256=m.R.file_sha(cold_dir/'RESULT.json'),threshold_policy=policy,
                files=[])
    (warm/'FROZEN.json').write_text(json.dumps(frozen))
    report=dict(tokens=16,status='DIAGNOSTIC_NOT_ACCEPTED',generator_sha256=m.R.file_sha(Path(m.__file__)),
                build=build,payload_manifest_sha256='d'*64,cold=dict(directory=str(cold_dir),result_sha256=m.R.file_sha(cold_dir/'RESULT.json')),
                carry_binding=binding,frozen_sha256=m.R.file_sha(warm/'FROZEN.json'),artifacts=m.inventory(warm),
                evaluation=m.comparisons(actual,refs,m.config_for(build['layout']),cold,ROOT))
    report.update(inputs={},payload_pin_sha256=frozen['payload_pin_sha256'],official_reference_identity={},
                  resource_preflight={},small_result_sha256=None)
    report_path=warm/'RESULT.json'
    def save():report_path.write_text(json.dumps(report))
    save();monkeypatch.setattr(m,'load_cold',lambda *args:(cold_report,cold,{},{}))
    def validate():return m.validate_small(warm,ROOT,build['cpp_sha256'],'d'*64)
    assert validate()['tokens']==16
    raw=warm/'raw_stages/phase_14_y_recipe.f32le';original=raw.read_bytes()
    changed=bytearray(original);changed[0]^=1;raw.write_bytes(changed)
    with pytest.raises(ValueError,match='artifact changed'):validate()
    raw.write_bytes(original)
    reference=warm/'references/official_self_cache/y.f32le';saved=reference.read_bytes()
    a=np.fromfile(reference,dtype='<f4');a[0]+=1;a.tofile(reference)
    # Even a rewritten untrusted local inventory cannot preserve the old metrics.
    report['artifacts']=m.inventory(warm);save()
    with pytest.raises(ValueError,match='comparison/semantics changed'):validate()
    reference.write_bytes(saved);report['artifacts']=m.inventory(warm);save()
    (warm/'FROZEN.json').write_text('{}')
    with pytest.raises(ValueError,match='freeze changed'):validate()
    # A forged post-execution digest must not bless conflicting launch metadata.
    changed=copy.deepcopy(frozen);changed['launch_cold_result_sha256']='0'*64
    (warm/'FROZEN.json').write_text(json.dumps(changed))
    report['frozen_sha256']=m.R.file_sha(warm/'FROZEN.json');save()
    with pytest.raises(ValueError,match='freeze/result identity'):validate()
    (warm/'FROZEN.json').write_text(json.dumps(frozen));save()
    report['carry_binding']['position_ids']=list(range(16));save()
    with pytest.raises(ValueError,match='metadata mismatch'):validate()


def test_preflight_requires_four_threads(tmp_path,monkeypatch):
    for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):monkeypatch.setenv(key,'4')
    assert m.preflight(tmp_path/'result')['threads']==4
    monkeypatch.setenv('OMP_NUM_THREADS','64')
    with pytest.raises(ValueError,match='set OPENBLAS'):m.preflight(tmp_path/'result')
