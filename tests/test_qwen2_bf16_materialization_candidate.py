# SPDX-License-Identifier: Apache-2.0
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import numpy as np
import pytest
ROOT=Path(__file__).resolve().parents[1]
S=importlib.util.spec_from_file_location('candidate',ROOT/'scripts/qwen2_bf16_materialization_candidate.py')
m=importlib.util.module_from_spec(S);S.loader.exec_module(m)


def test_versioned_diagnostic_policy_and_exact_candidate_identity():
    source,identity=m.candidate_source(ROOT)
    assert m.R.sha(source.encode())==m.CPP_SHA256
    assert m.POLICY['status']=='DIAGNOSTIC_NOT_ACCEPTED'
    assert m.POLICY['hardware_v0_conformant'] is False
    assert 'RoPE' in m.__doc__ and 'v0' in m.POLICY['rope_difference']
    assert identity['section_sha256']==m.R.SECTION_SHA256
    assert 'std::fma(a[k],bf(weights[j]),sums[j])' in source
    assert 'bf(bias>=0?add(sums[j],get(bias,col+j)):sums[j])' in source
    assert not any(word in source for word in ('verilated','VQwen','BlockDut','d.eval'))


def test_patch_drift_and_ambiguous_source_fail_closed():
    helpers,maths,_=m.R.extract_sources(ROOT)
    source='// Ordinary C++ software numerical model; not a hardware simulator.\n'+helpers+m.R.HOST_PROBES+m.R.DRIVER+maths+m.R.MAIN
    original=m.PATCHES[0]['original']
    with pytest.raises(ValueError,match='boundary absent/ambiguous'):
        m.apply_patches(source.replace(original,'changed'))
    with pytest.raises(ValueError,match='boundary absent/ambiguous'):
        m.apply_patches(source+'\n'+original)


@pytest.mark.skipif(shutil.which('g++') is None,reason='ordinary C++ compiler unavailable')
def test_small_candidate_against_independent_bf16_equations(tmp_path):
    shape=dict(hidden=32,ffn=32,heads=1,kv_heads=1,head_dim=32,max_tokens=2)
    compiled=m.prepare(ROOT,tmp_path/'candidate',shape)
    weights={}
    for i,(region,(key,out_dim,in_dim)) in enumerate(m.R.WEIGHTS.items()):
        weights[key]=np.eye(32,dtype='<f4')*np.float32((i+1)/16)
    weights['input_layernorm.weight']=np.ones(32,dtype='<f4')
    weights['post_attention_layernorm.weight']=np.ones(32,dtype='<f4')
    for name in ('q_proj','k_proj','v_proj'):weights[f'self_attn.{name}.bias']=np.zeros(32,dtype='<f4')
    embeddings=np.zeros((256,32),dtype='<f4')
    embeddings[0]=np.arange(32,dtype='<f4')/16-1
    embeddings[1]=np.arange(32,dtype='<f4')[::-1]/32-.5
    raw={key:(m.N.bf16(value).view('<u4')>>16).astype('<u2').tobytes() for key,value in weights.items()}
    raw['embed_tokens.rows_0_255']=(embeddings.view('<u4')>>16).astype('<u2').tobytes()
    arena=tmp_path/'arena.f32le';m.R.pack_readonly(compiled['layout'],raw,[0,1],arena)
    stages=tmp_path/'stages';stages.mkdir()
    execution=subprocess.run([str(tmp_path/'candidate/candidate'),str(arena),'2',str(stages)],capture_output=True,text=True,check=True,timeout=30)
    assert 'SOFTWARE_FLOAT_ENV rounding=FE_TONEAREST probes=10' in execution.stdout
    actual=m.load_actual(stages,arena,tmp_path/'input_x.f32le',compiled['layout'],2)
    config=dict(hidden_size=32,intermediate_size=32,num_attention_heads=1,num_key_value_heads=1,rms_norm_eps=1e-6,rope_theta=1e6)
    expected,_=m.N.independent_forward(weights,embeddings[:2][None],config,'bf16')
    policy=m.N.load_policy(ROOT)
    assert set(actual)==m.N.REQUIRED_STAGES and len(actual)==29
    for name in actual:
        metrics=m.N.compare(actual[name],expected[name]);verdict=m.N.stage_verdict(name,metrics,'bf16',policy)
        assert verdict['passed'] is not False,(name,metrics)
        if name!='softmax_fp32':assert not np.any(actual[name].view('<u4')&0xffff),name
    assert all(m.N.audit_semantics(actual,None,config,'bf16').values())
    assert np.max(np.abs(actual['softmax_fp32'].sum(axis=-1)-1))<=2e-5
    # Adoption must derive its 29 nodes from actual ELF outputs, not accept
    # an edited derived tensor with a freshly rewritten self-declared hash.
    primary={'comparisons':{'native':[]}}
    for name in (*m.R.STAGE_NAMES,'scores','logits','softmax_fp32','prob','silu'):
        path=stages/(f'phase_{m.R.STAGE_NAMES.index(name)}_{name}_recipe.f32le' if name in m.R.STAGE_NAMES else name+'.f32le')
        primary['comparisons']['native'].append({'name':name,'sha256':m.R.file_sha(path)})
    shutil.copyfile(arena,tmp_path/'readonly_arena.f32le')
    assert len(m.bind_raw_outputs(primary,stages,tmp_path,compiled['layout'],2,actual))==29
    altered={name:a.copy() for name,a in actual.items()};altered['y'][0,0,0]+=1
    with pytest.raises(ValueError,match='export differs from actual raw'):
        m.bind_raw_outputs(primary,stages,tmp_path,compiled['layout'],2,altered)
    # Rewriting a derived file and its own manifest digest still cannot
    # supersede the unmodified execution outputs.
    derived=tmp_path/'candidate_y.f32le';m.N.export_value(altered['y'],'y').tofile(derived)
    forged={'candidate_sha256':m.R.file_sha(derived)}
    assert m.R.file_sha(derived)==forged['candidate_sha256']
    altered['y']=np.fromfile(derived,dtype='<f4').reshape(actual['y'].shape)
    with pytest.raises(ValueError,match='export differs from actual raw'):
        m.bind_raw_outputs(primary,stages,tmp_path,compiled['layout'],2,altered)
    # A migrated M16 receipt must recheck the same raw evidence on every
    # later admission, even if exports and their reported metrics were edited.
    primary_path=tmp_path/'RESULT.json';primary_path.write_text(json.dumps(primary))
    complete_path=tmp_path/'FULL_NODE_CHECK.json';complete_path.write_text(json.dumps(forged))
    migrated=dict(adoption=dict(observation_directory=str(tmp_path),
        primary_report_sha256=m.R.file_sha(primary_path),complete_report_sha256=m.R.file_sha(complete_path)),
        raw_outputs=m.raw_inventory(stages),tensors=[forged],evaluation={'node_gates_pass':{'native':True,'independent':True}})
    assert len(m.validate_raw_evidence(migrated,tmp_path/'migrated',tmp_path,compiled['layout'],2,actual))==29
    with pytest.raises(ValueError,match='export differs from actual raw'):
        m.validate_raw_evidence(migrated,tmp_path/'migrated',tmp_path,compiled['layout'],2,altered)
    complete_path.write_text('{}')
    with pytest.raises(ValueError,match='complete receipt changed'):
        m.validate_raw_evidence(migrated,tmp_path/'migrated',tmp_path,compiled['layout'],2,actual)
    complete_path.write_text(json.dumps(forged));primary_path.write_text('{}')
    with pytest.raises(ValueError,match='primary receipt changed'):
        m.validate_raw_evidence(migrated,tmp_path/'migrated',tmp_path,compiled['layout'],2,actual)
    primary_path.write_text(json.dumps(primary))
    incomplete={'comparisons':{'native':primary['comparisons']['native'][1:]}}
    with pytest.raises(ValueError,match='raw observation stage missing'):
        m.bind_raw_outputs(incomplete,stages,tmp_path,compiled['layout'],2,actual)
    raw_path=stages/'phase_0_n0_recipe.f32le';saved=raw_path.read_bytes()
    corrupted=bytearray(saved);corrupted[0]^=1;raw_path.write_bytes(corrupted)
    with pytest.raises(ValueError,match='raw observation output changed'):
        m.bind_raw_outputs(primary,stages,tmp_path,compiled['layout'],2,actual)
    with pytest.raises(ValueError,match='raw evidence changed'):
        m.validate_raw_evidence(migrated,tmp_path/'migrated',tmp_path,compiled['layout'],2,actual)
    raw_path.write_bytes(saved)
    # Signed-zero is legal BF16 but must remain bit-exactly bound to input.
    signed={name:a.copy() for name,a in actual.items()};signed['x'].view('<u4')[0,0,16]=0x80000000
    m.validate_dtypes(signed)
    with pytest.raises(ValueError,match='export differs from actual raw'):
        m.bind_raw_outputs(primary,stages,tmp_path,compiled['layout'],2,signed)
    with pytest.raises(ValueError,match='existing candidate'):
        m.prepare(ROOT,tmp_path/'candidate',shape)
    # A same-length corruption must not become valid model evidence.
    path=stages/'phase_14_y_recipe.f32le'
    data=np.fromfile(path,dtype='<u4');data[0]=0x7fc00000;data.tofile(path)
    with pytest.raises(ValueError,match='nonfinite'):
        m.load_actual(stages,arena,tmp_path/'input_x.f32le',compiled['layout'],2)


def export_fixture(tmp_path):
    shapes=m.N.expected_shapes(dict(hidden_size=1536,intermediate_size=8960,num_attention_heads=12,num_key_value_heads=2),16,0)
    arrays={name:np.zeros(shape,dtype='<f4') for name,shape in shapes.items()}
    records=m.export_actual(arrays,tmp_path)
    return records


def test_export_inventory_and_hash_are_checked(tmp_path):
    records=export_fixture(tmp_path)
    assert len(m.load_exports(tmp_path,records,16))==29
    with pytest.raises(ValueError,match='inventory/order'):
        m.load_exports(tmp_path,list(reversed(records)),16)
    path=tmp_path/'candidate_q.f32le';data=bytearray(path.read_bytes());data[0]=1;path.write_bytes(data)
    with pytest.raises(ValueError,match='export identity'):
        m.load_exports(tmp_path,records,16)


def test_export_shape_cannot_be_relabelled(tmp_path):
    records=export_fixture(tmp_path)
    records[0]['shape']=[1,16,1]
    with pytest.raises(ValueError,match='export identity'):
        m.load_exports(tmp_path,records,16)


def test_cli_never_claims_hardware_acceptance(monkeypatch,tmp_path,capsys):
    fake=dict(status='DIAGNOSTIC_NOT_ACCEPTED',tokens=16,evaluation={'node_gates_pass':{'native':True,'independent':True}})
    monkeypatch.setattr(m,'run',lambda *args,**kwargs:fake)
    monkeypatch.setattr(m.argparse.ArgumentParser,'parse_args',lambda _:type('Args',(),dict(root=ROOT,recipe_run=tmp_path,native_run=tmp_path,out=tmp_path,small_candidate=None,adopt_observation=None,observed_binary=None,timeout_seconds=120))())
    assert m.main()==1
    assert json.loads(capsys.readouterr().out)['status']=='DIAGNOSTIC_NOT_ACCEPTED'


def test_non_bf16_export_rejected_even_after_hash_rewrite(tmp_path):
    records=export_fixture(tmp_path)
    entry=next(e for e in records if e['name']=='n0');path=tmp_path/entry['path']
    words=np.fromfile(path,dtype='<u4');words[0]=0x3f800001;words.tofile(path)
    entry['sha256']=m.R.file_sha(path)
    with pytest.raises(ValueError,match='not BF16-representable: n0'):
        m.load_exports(tmp_path,records,16)
