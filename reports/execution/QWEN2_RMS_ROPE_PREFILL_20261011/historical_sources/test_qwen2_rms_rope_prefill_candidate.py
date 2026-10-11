"""Meaningful local controls for the versioned RMS1536 cold/carried candidate."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import numpy as np
import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('rms_prefill',ROOT/'scripts/qwen2_rms_rope_prefill_candidate.py')
M=importlib.util.module_from_spec(spec);spec.loader.exec_module(M)


@pytest.fixture(scope='module')
def binary(tmp_path_factory):
    directory=tmp_path_factory.mktemp('rms_prefill')
    shape=dict(hidden=1536,ffn=32,heads=12,kv_heads=2,head_dim=128,max_tokens=16)
    build=M.prepare(directory/'build',shape)
    M.generate_tables(directory/'build/candidate',directory/'tables.f32le')
    return directory,build


def execute(binary,arena,tokens,target,past,k,v,check=True):
    target.mkdir()
    return subprocess.run([str(binary),str(arena),str(tokens),str(target),str(past),str(k),str(v)],
                          capture_output=True,text=True,timeout=20,check=check)


def test_dependencies_and_old_v1_source_are_unchanged():
    M.verify_pins()
    parent,_=M.G.carried_source(ROOT);source,identity=M.candidate_source()
    assert identity['parent_carried_cpp_sha256']==M.R.sha(parent.encode())
    assert M.C.candidate_source(ROOT)[0] and M.C.CPP_SHA256=='fa8e35755dfd17fb00c911b11b69d55b10cb5cc88002867a7484167d35320f79'
    for begin,end in [('  void dense(','  void rope('),('  void rope(','  void attention('),
                      ('  void attention(','  void computeReference('),('  void computeReference(','\n};')]:
        assert source[source.index(begin):source.index(end)]==parent[parent.index(begin):parent.index(end)]
    assert M.POLICY['policy_approval'] is False and M.POLICY['hardware_v0_conformant'] is False
    assert 'cold evidence reused' not in source


def test_all_ten_rms_nodes_match_reviewed_module(binary,tmp_path):
    directory,_=binary
    rng=np.random.default_rng(1417)
    x=M.D.bf16((rng.normal(size=(1,16,1536))*np.exp2(rng.integers(-8,4,size=(1,16,1536)))).astype('<f4'))
    x[0,0]=np.float32(0);x[0,0,1]=np.float32(-0.0)
    gamma=M.D.bf16(rng.uniform(-1.5,1.5,size=1536).astype('<f4'))
    x.tofile(tmp_path/'x');gamma.tofile(tmp_path/'g')
    subprocess.run([str(directory/'build/candidate'),'--rms-nodes','16',str(tmp_path/'x'),str(tmp_path/'g'),str(tmp_path/'out')],check=True,capture_output=True,timeout=10)
    data=np.fromfile(tmp_path/'out',dtype='<f4');rows=16
    actual={name:data[i*rows:(i+1)*rows].reshape(1,rows,1) for i,name in enumerate(M.D.SCALARS)}
    actual.update({name:data[5*rows+i*rows*1536:5*rows+(i+1)*rows*1536].reshape(x.shape) for i,name in enumerate(M.D.VECTORS)})
    expected=M.D.rms_recipe(x,gamma)
    assert all(M.D.compare(actual[name],expected[name])['bit_exact'] for name in expected)
    assert M.D.check_scalar_rne(*(actual[n] for n in ('variance','root','sum','mean','inverse')))['rows']==16
    assert actual['output'].view('<u4')[0,0,1] == expected['output'].view('<u4')[0,0,1]


def test_all_position_trig_tables_match_reviewed_fp32_and_bf16(binary,tmp_path):
    directory,_=binary;tables=M.table_values(directory/'tables.f32le')
    lib,_=M.D.build_c(tmp_path)
    data=np.empty(192+5*16384,dtype='<f4');assert lib.rope(data)==1
    for trig,index in (('cos',1),('sin',2)):
        for kind,offset in (('fp32',index),('bf16',index+2)):
            reviewed=data[192+offset*16384:192+(offset+1)*16384].reshape(256,64)
            actual=tables[trig+('_bf16' if kind=='bf16' else '')]
            assert np.array_equal(actual.view('<u4'),reviewed.view('<u4'))
        doubled=np.concatenate((tables[trig+'_bf16'],tables[trig+'_bf16']),axis=1)
        assert M.R.sha(doubled.tobytes())==M.TABLE_DIGESTS[trig]


def tiny_payload():
    h,f,kv=1536,32,256
    rng=np.random.default_rng(880)
    shape=dict(hidden=h,ffn=f,kv=kv)
    weights={}
    for _,(name,output,input_) in M.R.WEIGHTS.items():
        a=np.zeros((shape[output],shape[input_]),dtype='<f4')
        for j in range(a.shape[0]):a[j,(j*13)%a.shape[1]]=np.float32(.5)
        weights[name]=a
    for n in ('input_layernorm.weight','post_attention_layernorm.weight'):weights[n]=np.ones(h,dtype='<f4')
    for n,width in (('q',h),('k',kv),('v',kv)):weights['self_attn.'+n+'_proj.bias']=np.zeros(width,dtype='<f4')
    embedding=M.D.bf16(rng.normal(size=(256,h)).astype('<f4'))
    payload={name:(value.view('<u4')>>16).astype('<u2').tobytes() for name,value in weights.items()}
    payload['embed_tokens.rows_0_255']=(embedding.view('<u4')>>16).astype('<u2').tobytes()
    return payload,weights


def test_actual_raw_cache_dependency_and_absolute_position(binary,tmp_path):
    directory,build=binary;payload,weights=tiny_payload();exe=directory/'build/candidate'
    cold=tmp_path/'cold';cold.mkdir();empty=tmp_path/'empty';empty.write_bytes(b'')
    M.write_arena(build['layout'],payload,2,0,cold,directory/'tables.f32le')
    execute(exe,cold/'readonly_arena.f32le',2,cold/'raw_stages',0,empty,empty)
    actual=M.C.load_actual(cold/'raw_stages',cold/'readonly_arena.f32le',cold/'input_x.f32le',build['layout'],2)
    (cold/'RESULT.json').write_text('{}')
    report=dict(build=build)
    binding=M.cache_binding(cold,report,actual,2);M.validate_binding(binding,binding,actual,2)
    carried=tmp_path/'carried';carried.mkdir()
    info=M.write_arena(build['layout'],payload,2,2,carried,directory/'tables.f32le')
    assert info['position_ids']==info['token_ids']==[2,3]
    k,v=(cold/'raw_stages'/f'cache_{n}.f32le' for n in ('k','v'))
    execute(exe,carried/'readonly_arena.f32le',2,carried/'raw_stages',2,k,v)
    warm=M.G.load_actual(carried,build['layout'],2,actual)
    assert all(M.N.audit_semantics(warm,actual,M.G.config_for(build['layout']),'bf16').values())
    for values in (actual,warm):
        for name,input_,gamma in [('n0','x','input_layernorm.weight'),('n1','r','post_attention_layernorm.weight')]:
            expected=M.D.rms_recipe(values[input_],weights[gamma])['output']
            assert M.D.compare(values[name],expected)['bit_exact']
    for name,path in (('cache_k',k),('cache_v',v)):
        original=path.read_bytes();a=np.frombuffer(original,dtype='<f4').copy();a[:256]=M.D.bf16(a[:256]+4);path.write_bytes(a.tobytes())
        forged=copy.deepcopy(binding);forged['records'][0 if name=='cache_k' else 1]['sha256']=M.R.file_sha(path)
        with pytest.raises(ValueError,match='raw previous cache'):M.validate_binding(forged,forged,actual,2)
        target=tmp_path/name;execute(exe,carried/'readonly_arena.f32le',2,target,2,k,v)
        assert (target/'phase_6_att_recipe.f32le').read_bytes()!=(carried/'raw_stages/phase_6_att_recipe.f32le').read_bytes()
        assert (target/'phase_14_y_recipe.f32le').read_bytes()!=(carried/'raw_stages/phase_14_y_recipe.f32le').read_bytes()
        for file in ('phase_4_q_recipe.f32le','phase_5_k_recipe.f32le','phase_3_v_recipe.f32le'):
            assert (target/file).read_bytes()==(carried/'raw_stages'/file).read_bytes()
        path.write_bytes(original)
    bad=tmp_path/'short';bad.write_bytes(k.read_bytes()[:-4])
    result=execute(exe,carried/'readonly_arena.f32le',2,tmp_path/'bad',2,bad,v,False)
    assert result.returncode!=0 and 'cache length mismatch' in result.stderr
    result=execute(exe,carried/'readonly_arena.f32le',2,tmp_path/'badpast',1,k,v,False)
    assert result.returncode!=0 and 'past must be zero' in result.stderr
    for field,value in [('position_ids',[0,1]),('token_ids',[0,1]),('past_tokens',1),('source_policy',M.G.POLICY_ID)]:
        forged=copy.deepcopy(binding);forged[field]=value
        with pytest.raises(ValueError,match='metadata mismatch'):M.validate_binding(forged,binding,actual,2)


def log_fixture():
    layout=M.R.make_layout();widths={r['name']:r['words']//128 for r in layout['regions']}
    lines=['SOFTWARE_FLOAT_ENV rounding=FE_TONEAREST probes=10','CARRIED_LIFETIME readonly_exact=1 cache_prefix_exact=1 unused_sentinels_exact=1']
    lines += [f'SOFTWARE_RECIPE_STAGE phase={i} name={n} values={16*widths[n]}' for i,n in enumerate(M.R.STAGE_NAMES)]
    lines += ['SOFTWARE_RECIPE_COMPLETE tokens=16 stages=15']
    return '\n'.join(lines)+'\n'


def test_software_completion_ack_is_scoped_and_fail_closed():
    valid=log_fixture();assert M.software_ack(valid,16,0)['hardware_ack_verified'] is False
    for bad in (valid+valid,valid.replace('phase=1 ','phase=2 '),valid.replace('SOFTWARE_RECIPE_COMPLETE','MISSING'),valid.replace('name=n0','name=x')):
        with pytest.raises(ValueError,match='ACK'):M.software_ack(bad,16,0)
    with pytest.raises(ValueError,match='ACK'):M.software_ack(valid,16,1)


def test_no_numerical_pass_can_approve_policy():
    assert M.STATUS=='DIAGNOSTIC_NOT_ACCEPTED'
    assert M.POLICY['policy_approval'] is M.POLICY['hardware_v0_conformant'] is False
    policy=M.N.load_policy(ROOT)
    assert policy['operator']=={'max_abs':.03125,'mean_abs':.005}
    assert policy['block']=={'max_abs':.05,'mean_abs':.01}
    assert M.N.stage_verdict('softmax_fp32',{},'bf16',policy)['passed'] is None
