"""Reject stale/forged authority and execution evidence without running a DUT."""
import importlib
import json
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(SCRIPTS))
live=importlib.import_module('host_bf16_attention_block_live_gate')


def test_no_saved_receipt_constructor_or_unissued_object_authority(tmp_path):
    with pytest.raises(TypeError):live.FreshAttentionBlockSession(tmp_path,'a'*64)
    forged=object.__new__(live.FreshAttentionBlockSession)
    with pytest.raises(ValueError,match='unissued'):
        forged.verify(session=None,projection_session=None,attention_session=None)
    with pytest.raises(ValueError,match='live block factory'):
        live.admit_fixture(tmp_path,block_session={'receipt_sha256':'a'*64},session=None,projection_session=None,attention_session=None)


def test_nonfresh_or_missing_capture_cannot_create_core(tmp_path):
    with pytest.raises(ValueError,match='live fresh capture'):
        live.generate_block_reference(None,None,None,tmp_path/'bundle')


def test_invalid_upstream_authorities_fail_before_any_compiler(tmp_path,monkeypatch):
    capture=live.CaptureSession(tmp_path,'a'*64,tmp_path,tmp_path,tmp_path,True)
    called=[]
    monkeypatch.setattr(live.reference,'compile_full_block_dense_tools',lambda *a:called.append(a))
    with pytest.raises(ValueError,match='live independent projection'):
        live.generate_block_reference(capture,None,None,tmp_path/'bundle')
    assert called==[]


def test_fixture_saved_receipt_must_match_live_factory(tmp_path,monkeypatch):
    path=tmp_path/'fixture';path.mkdir();(path/'reference_receipt.json').write_text(json.dumps({'origin':'saved'}))
    core=object.__new__(live.FreshAttentionBlockSession)
    monkeypatch.setattr(live.FreshAttentionBlockSession,'verify',lambda *a,**k:{'origin':'live'})
    monkeypatch.setattr(live.fixture,'verify',lambda *a:{})
    with pytest.raises(ValueError,match='differs from live'):
        live.admit_fixture(path,block_session=core,session=None,projection_session=None,attention_session=None)


@pytest.fixture
def actual_harness(tmp_path,monkeypatch):
    build=tmp_path/'build';build.mkdir();path=tmp_path/'fixture';path.mkdir()
    admission=dict(source_sha256={'source':'a'*64},input_sha256={'input':'b'*64})
    monkeypatch.setattr(live,'admit_fixture',lambda *a,**k:admission)
    state=dict(returncode=0,timeout=False,audit_claim=False,drift=False,verifies=0)
    identity={'obj/VHostBlockTop':'c'*64,'generated/HostBlockTop.sv':'d'*64,'build_ready.json':'e'*64}
    def built(*args):
        state['verifies']+=1
        return dict(identity,changed=True) if state['drift'] and state['verifies']>1 else dict(identity)
    monkeypatch.setattr(live,'build_identity',built)
    monkeypatch.setattr(live,'verify_all_build_sources',lambda *a:None)
    def execute(argv,**kwargs):
        state['argv']=argv;state['timeout_seconds']=kwargs['timeout']
        if state['timeout']:raise live.subprocess.TimeoutExpired(argv,kwargs['timeout'])
        output=Path(argv[2])
        for phase in live.fixture.PHASES:
            (output/phase).mkdir(parents=True)
            for name in live.fixture.NAMES:(output/phase/('actual_'+name+'.bf16le')).write_bytes(b'CONTROL ONLY')
        return SimpleNamespace(returncode=state['returncode'])
    monkeypatch.setattr(live.subprocess,'run',execute)
    def audit(path,output,log,mode):
        return dict(status='CONSISTENT_ATTENTION_BLOCK_ARTIFACTS_ONLY',actual_dut_identity_verified=state['audit_claim'],
            numerical_acceptance_eligible=False,log_sha256=live.sha(log),mode=mode,
            runs=[dict(phase=p) for p in live.fixture.PHASES])
    monkeypatch.setattr(live.execution,'audit',audit)
    authority=dict(block_session=SimpleNamespace(receipt_sha256='f'*64),session=None,projection_session=None,attention_session=None)
    return build,path,state,authority


@pytest.mark.parametrize('mode',live.MODES)
def test_actual_runner_one_process_for_two_launches_and_faults(actual_harness,mode):
    build,path,state,authority=actual_harness
    result=live.run_case(build,path,mode,**authority)
    assert state['argv']==[str(build/'obj/VHostBlockTop'),str(path),str(build/mode.replace('-','_')),mode]
    assert result['status']==live.CASE_STATUS and result['same_dut_launches']==2
    assert result['numerical_acceptance_eligible'] is (mode=='pass')
    assert result['native_full_block_acceptance'] is False and result['overall_pass'] is False
    assert result['frozen_recipe_block_acceptance'] is (mode=='pass')
    assert set(result['actual_sha256'])=={'cold0','carried1'} and state['verifies']==2


@pytest.mark.parametrize('fault,reason',[('timeout','timeout'),('returncode','execution failed'),('audit_claim','generic auditor'),('drift','identity changed')])
def test_actual_runner_rejects_incomplete_unbound_or_drifting_evidence(actual_harness,fault,reason):
    build,path,state,authority=actual_harness;state[fault]=True if fault!='returncode' else 1
    with pytest.raises(ValueError,match=reason):live.run_case(build,path,'pass',**authority)
    assert not (build/'pass.result.json').exists()


def test_run_timeout_cannot_be_extended_past_ci_contract(actual_harness):
    build,path,state,authority=actual_harness
    for value in (0,3601,True):
        with pytest.raises(ValueError,match='bounded actual timeout'):live.run_case(build,path,'pass',timeout_seconds=value,**authority)
    assert state['verifies']==0


@pytest.fixture
def identity_harness(tmp_path,monkeypatch):
    # This is a minimal control fixture with ELF magic, never a runnable binary.
    root=tmp_path/'repo';root.mkdir();(root/'source.py').write_text('# control only\n')
    build=tmp_path/'build';build.mkdir();(build/'obj').mkdir();(build/'generated').mkdir()
    monkeypatch.setattr(live,'ROOT',root)
    sources={'source.py':live.sha(root/'source.py')}
    scope=dict(scope=live.SCOPE,attention_block_policy_version=3,default_enabled=False,
        input_norm_dut=True,sigmoid_gate_dut=True,output_projection_dut=True,ffn_supported=True,
        full_block_supported=True,numerical_acceptance=False,fault_restore_supported=False,
        full_m128_supported=False,max_declared_rows=128,active_tokens_supported=1,max_cache_tokens=256,
        logical_matrix_engines=1,physical_matrix_slices=8,pinned_idma_instances=1,scalar_service_shared=True)
    (build/'obj/VHostBlockTop').write_bytes(b'\x7fELF CONTROL ONLY, NOT EXECUTABLE')
    (build/'generated/HostBlockTop.sv').write_text('// CONTROL ONLY\n')
    records={'sources.sha256.json':sources,'generated/SCOPE.json':scope,'toolchain.json':{'control_only':True},
             'actual_verilator_after.json':{'actual_elf':'CONTROL ONLY'},'compiler_jars.sha256.json':{},'hardfloat.sha256.json':{}}
    for name,value in records.items():(build/name).write_text(json.dumps(value))
    keys={'obj/VHostBlockTop':'binary_sha256','generated/HostBlockTop.sv':'rtl_sha256',
          'sources.sha256.json':'source_manifest_sha256','generated/SCOPE.json':'scope_sha256',
          'toolchain.json':'toolchain_sha256','actual_verilator_after.json':'actual_verilator_sha256',
          'compiler_jars.sha256.json':'compiler_jars_sha256','hardfloat.sha256.json':'hardfloat_manifest_sha256'}
    ready=dict(status=live.BUILD_STATUS,numerical_pass=False,initial_verilation_exit=0,
               actual_verilator=records['actual_verilator_after.json'])
    ready.update({key:live.sha(build/name) for name,key in keys.items()})
    (build/'build_ready.json').write_text(json.dumps(ready))
    monkeypatch.setattr(live,'_verify_tool_files',lambda *a:None)
    return root,build,sources,ready,keys


@pytest.mark.parametrize('name',['obj/VHostBlockTop','generated/HostBlockTop.sv','generated/SCOPE.json',
    'toolchain.json','actual_verilator_after.json','compiler_jars.sha256.json','hardfloat.sha256.json'])
def test_build_identity_rejects_modified_elf_rtl_scope_and_tool_receipts(identity_harness,name):
    root,build,sources,ready,keys=identity_harness
    before=live.build_identity(build,sources)
    with (build/name).open('ab') as stream:stream.write(b' ')
    with pytest.raises(ValueError,match='receipt drift'):live.build_identity(build,sources)
    assert before['build_ready.json']==live.sha(build/'build_ready.json')


def test_build_identity_rejects_checkout_source_drift(identity_harness):
    root,build,sources,ready,keys=identity_harness
    (root/'source.py').write_text('# changed\n')
    with pytest.raises(ValueError,match='source closure mismatch'):live.build_identity(build,sources)


def test_resealed_scope_cannot_expand_acceptance(identity_harness):
    root,build,sources,ready,keys=identity_harness
    path=build/'generated/SCOPE.json';scope=json.loads(path.read_text());scope['full_m128_supported']=True
    path.write_text(json.dumps(scope));ready['scope_sha256']=live.sha(path)
    (build/'build_ready.json').write_text(json.dumps(ready))
    with pytest.raises(ValueError,match='scope inflation'):live.build_identity(build,sources)


def test_tool_inventory_cannot_be_empty(tmp_path):
    with pytest.raises(ValueError,match='build tool inventory'):
        live._verify_tool_files(tmp_path,{'tools':{}})


@pytest.mark.parametrize('target',['log','actual','snapshot'])
def test_final_execution_identity_rejects_changed_or_added_artifacts(actual_harness,target):
    build,path,state,authority=actual_harness
    result=live.run_case(build,path,'pass',**authority)
    live.verify_case_outputs(build,result)
    changed=build/'pass.log' if target=='log' else build/'pass/cold0/actual_context.bf16le' if target=='actual' else build/'pass/cold0/unexpected_snapshot.bin'
    changed.write_bytes(b'CHANGED CONTROL EVIDENCE')
    with pytest.raises(ValueError,match='evidence changed after audit'):live.verify_case_outputs(build,result)
