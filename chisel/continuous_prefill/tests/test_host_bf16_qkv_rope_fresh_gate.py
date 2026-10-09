"""CI orchestration CONTROL ONLY. Capture/reference/build/DUT are test doubles."""
import importlib
import json
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(SCRIPTS))
gate=importlib.import_module('run_host_bf16_qkv_rope_fresh_gate')


@pytest.fixture
def harness(tmp_path,monkeypatch):
    root=tmp_path/'repo';root.mkdir();(root/'work').mkdir();(root/'entry.py').write_text('# control fixture\n')
    monkeypatch.setattr(gate,'ROOT',root);monkeypatch.setattr(gate,'SCRIPT_DIR',root)
    monkeypatch.setattr(gate,'ENTRY_SOURCES',('entry.py',))
    monkeypatch.setattr(gate,'_git_head',lambda:'a'*40)
    checked=[];monkeypatch.setattr(gate,'verify_checkout',lambda head,sources:checked.append((head,dict(sources))))
    monkeypatch.setattr(gate,'merge_sources',lambda target,source:target.update(source))
    monkeypatch.setattr(gate,'_preflight',lambda env,out:{'test_double':True})
    state=dict(builds=0,cases=[],original=True,clock=0.,timeout_build=False,bad_status=False,bad_hash=False)
    monkeypatch.setattr(gate.time,'monotonic',lambda:state['clock'])
    class Capture:
        fresh=True;manifest_sha256='b'*64
        def evidence(self):return dict(fresh_official_executions=2,reused_official_executions=0)
        def verify(self):return dict(source_sha256={})
    capture=Capture()
    monkeypatch.setattr(gate,'rebuild_session',lambda *a:capture)
    failures={'baseline':{'gate_pass':False},'avx2':{'gate_pass':False}}
    monkeypatch.setattr(gate,'_native_failure_evidence',lambda session:failures)
    class Projection:
        receipt_sha256='c'*64
        def verify(self,*,session):
            assert session is capture
            return dict(source_sha256={},head_jobs=24,matrix_accumulator_steps=10485760,
                        native_operator_gate_pass=True,status='MOCK',origin='MOCK',native_thresholds={},
                        full128_reference_generated=False,cross_variant_input_identity_assumed=False)
    projection=Projection()
    monkeypatch.setattr(gate,'generate_projection_references',lambda session,output,*,variants:projection)
    class Attention:
        receipt_sha256='d'*64
        def verify(self,*,session,reference_session):
            assert session is capture and reference_session is projection
            return dict(source_sha256={},original_operator_gate_pass=state['original'])
    attention=Attention()
    monkeypatch.setattr(gate,'generate_attention_references',lambda session,ref,out,*,variants:attention)
    def build(argv,**kwargs):
        state['builds']+=1;state['build_timeout']=kwargs['timeout']
        path=Path(argv[2]);(path/'obj').mkdir(parents=True);(path/'generated').mkdir()
        (path/'obj/VHostBlockTop').write_bytes(b'CONTROL_ONLY_NOT_AN_ELF')
        (path/'generated/HostBlockTop.sv').write_text('// CONTROL ONLY\n')
        ready=dict(status=gate.BUILD_STATUS,numerical_pass=False,initial_verilation_exit=0,
                   binary_sha256=gate.sha(path/'obj/VHostBlockTop'),rtl_sha256=gate.sha(path/'generated/HostBlockTop.sv'))
        for name,value in [('build_ready.json',ready),('sources.sha256.json',{}),('toolchain.json',{'mock':True})]:
            (path/name).write_text(json.dumps(value))
        if state['timeout_build']:state['clock']=9001.
    monkeypatch.setattr(gate.subprocess,'run',build)
    def pack(path,case,**authority):
        assert authority==dict(session=capture,reference_session=projection,attention_reference_session=attention)
        path.mkdir()
    monkeypatch.setattr(gate,'pack',pack)
    monkeypatch.setattr(gate,'verify',lambda *a,**k:dict(input_sha256={'activation_window':'e'*64}))
    def run_case(build,fixture,mode,*,label,timeout_seconds,**authority):
        state['cases'].append((label,mode,timeout_seconds))
        ready=json.loads((build/'build_ready.json').read_text())
        return dict(status='BAD' if state['bad_status'] else 'PASS_PRODUCTION_HOST_QKV_QKNORM_ROPE_CASE',
                    actual_dut_identity_verified=True,
                    binary_sha256='f'*64 if state['bad_hash'] else ready['binary_sha256'],rtl_sha256=ready['rtl_sha256'],
                    runs=[dict(actual_sha256={'q':str(i)*64}) for i in range(2 if mode=='reset-recovery' else 1)])
    monkeypatch.setattr(gate,'run_case',run_case)
    monkeypatch.setattr(gate,'verify_all_build_sources',lambda *a:None)
    args=SimpleNamespace(output=root/'work/result',payload_layer0=root/'p0',payload_layer3=root/'p3',payload_extra=root/'px')
    return args,state,checked


def test_orchestration_keeps_recovery_run_hashes_and_native_failures(harness):
    args,state,checked=harness;summary,code=gate.run(args)
    assert code==0 and summary['numerical_acceptance'] is True
    assert state['builds']==1 and len(state['cases'])==8 and len(checked)>=3
    assert state['build_timeout']==7200 and all(case[2]==3600 for case in state['cases'])
    assert summary['native_full_block_failures']['baseline']['gate_pass'] is False
    assert summary['full128_executed'] is False and summary['full_block_supported'] is False
    compact=args.output/'compact';assert {p.name for p in compact.iterdir()}=={'summary.json','source_input_hashes.json'}
    hashes=json.loads((compact/'source_input_hashes.json').read_text())
    assert set(hashes['output_sha256']['cold0_reset_recovery'])=={'0','1'}
    assert all(value for runs in hashes['output_sha256'].values() for value in runs.values())


def test_original_operator_failure_blocks_build(harness):
    args,state,_=harness;state['original']=False;summary,code=gate.run(args)
    assert code==1 and not summary['numerical_acceptance']
    assert state['builds']==0 and not state['cases']
    assert 'original limits retained' in summary['error']['message']


@pytest.mark.parametrize('fault',['bad_status','bad_hash'])
def test_case_identity_or_status_cannot_be_promoted(harness,fault):
    args,state,_=harness;state[fault]=True;summary,code=gate.run(args)
    assert code==1 and not summary['numerical_acceptance'] and not summary['cases']
    assert len(state['cases'])==1


def test_total_budget_stops_before_next_dut_and_saves_failure(harness):
    args,state,_=harness;state['timeout_build']=True;summary,code=gate.run(args)
    assert code==1 and not summary['numerical_acceptance'] and not state['cases']
    assert summary['remaining_budget_seconds']==0
    assert 'total budget exhausted' in summary['error']['message']
    saved=json.loads((args.output/'compact/summary.json').read_text())
    assert saved['status']=='FAIL_FRESH_HOST_QKV_NORM_ROPE_M1'
