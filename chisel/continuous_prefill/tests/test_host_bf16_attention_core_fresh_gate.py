"""Orchestration controls only; no model, C reference, build or DUT is executed."""
from contextlib import nullcontext
import importlib
import json
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(SCRIPTS))
gate = importlib.import_module('run_host_bf16_attention_core_fresh_gate')


@pytest.fixture
def harness(tmp_path,monkeypatch):
    root = tmp_path/'repo'; root.mkdir(); (root/'work').mkdir(); (root/'entry.py').write_text('# CONTROL ONLY\n')
    monkeypatch.setattr(gate,'ROOT',root); monkeypatch.setattr(gate,'SCRIPT_DIR',root)
    monkeypatch.setattr(gate,'ENTRY_SOURCES',('entry.py',))
    monkeypatch.setattr(gate,'_git_head',lambda:'a'*40)
    checked=[]; monkeypatch.setattr(gate,'verify_checkout',lambda *args:checked.append(args))
    monkeypatch.setattr(gate,'merge_sources',lambda dst,src:dst.update(src))
    monkeypatch.setattr(gate,'_preflight',lambda *args:{'control_only':True})
    monkeypatch.setattr(gate,'total_budget',lambda *args:nullcontext())
    state=dict(captures=0,builds=0,cases=[],original=True,clock=0.,timeout_build=False,
               bad_status=False,bad_hash=False,bad_authority=False,missing_mode=False,final_drift=False)
    monkeypatch.setattr(gate.time,'monotonic',lambda:state['clock'])
    class Capture:
        fresh=True;manifest_sha256='b'*64
        def evidence(self):return dict(fresh_official_executions=2,reused_official_executions=0)
        def verify(self):return dict(source_sha256={})
    capture=Capture()
    def rebuild(*args):state['captures']+=1;return capture
    monkeypatch.setattr(gate,'rebuild_session',rebuild)
    failures={variant:{'gate_pass':False,'failed_producers':['original failure']} for variant in ('baseline','avx2')}
    monkeypatch.setattr(gate,'_native_failure_evidence',lambda session:failures)
    class Projection:
        receipt_sha256='c'*64
        def verify(self,*,session):
            assert session is capture
            return dict(source_sha256={},head_jobs=24,matrix_accumulator_steps=10485760,
                requested_windows=[list(w) for w in gate.WINDOWS],native_operator_gate_pass=True,
                status='CONTROL_ONLY',origin='CONTROL_ONLY',native_thresholds={'max_abs':.03125,'mean_abs':.005},
                full128_reference_generated=False,cross_variant_input_identity_assumed=False)
    projection=Projection()
    def projected(session,output,*,variants,windows):
        assert session is capture and variants==('baseline',) and windows==(('cold',0,1),('cold',1,1))
        return projection
    monkeypatch.setattr(gate,'generate_projection_references',projected)
    class Attention:
        receipt_sha256='d'*64
        def verify(self,*,session,projection_reference_session):
            assert session is capture and projection_reference_session is projection
            return dict(source_sha256={},original_operator_gate_pass=state['original'])
    attention=Attention()
    monkeypatch.setattr(gate,'generate_attention_references',lambda *a,**k:attention)
    class Core:
        receipt_sha256='e'*64
        def verify(self,*,session,projection_session,attention_session):
            assert session is capture and projection_session is projection and attention_session is attention
            return dict(source_sha256={},native_context_gate='UNASSIGNED_DIAGNOSTIC_ONLY_NOT_NATIVE_ACCEPTANCE')
    core=Core()
    monkeypatch.setattr(gate,'generate_core_reference',lambda *a:core)
    authority=dict(core_session=core,session=capture,projection_session=projection,attention_session=attention)
    admission=dict(live_authorities_verified=True,input_sha256={'activation.bf16le':'f'*64},source_sha256={})
    def pack(path,**given):assert given==authority;path.mkdir();return admission
    monkeypatch.setattr(gate,'pack_fixture',pack)
    def admit(path,**given):assert given==authority;return admission
    monkeypatch.setattr(gate,'admit_fixture',admit)
    def build(argv,**kwargs):
        state['builds']+=1;state['build_timeout']=kwargs['timeout']
        path=Path(argv[2]);(path/'obj').mkdir(parents=True);(path/'generated').mkdir()
        (path/'obj/VHostBlockTop').write_bytes(b'CONTROL_ONLY_NOT_AN_ELF')
        (path/'generated/HostBlockTop.sv').write_text('// CONTROL ONLY\n')
        ready=dict(status=gate.BUILD_STATUS,numerical_pass=False,binary_sha256=gate.sha(path/'obj/VHostBlockTop'),
                   rtl_sha256=gate.sha(path/'generated/HostBlockTop.sv'))
        for name,value in [('build_ready.json',ready),('sources.sha256.json',{}),('toolchain.json',{'control_only':True})]:
            (path/name).write_text(json.dumps(value))
        if state['timeout_build']:state['clock']=gate.RUNNER_BUDGET_SECONDS+1
    monkeypatch.setattr(gate.subprocess,'run',build)
    identities=[]
    def identity(*args):
        identities.append(None)
        return {'identity':'changed' if state['final_drift'] and len(identities)>1 else 'CONTROL_ONLY'}
    monkeypatch.setattr(gate,'build_identity',identity)
    def run_case(build,path,mode,*,timeout_seconds,**given):
        assert given==authority
        state['cases'].append((mode,timeout_seconds));ready=json.loads((build/'build_ready.json').read_text())
        return dict(status='BAD' if state['bad_status'] else gate.CASE_STATUS,actual_dut_identity_verified=True,
            live_authorities_verified=not state['bad_authority'],same_dut_launches=2,resets_between_launches=0,
            numerical_acceptance_eligible=mode=='pass',binary_sha256='0'*64 if state['bad_hash'] else ready['binary_sha256'],
            rtl_sha256=ready['rtl_sha256'],build_ready_sha256=gate.sha(build/'build_ready.json'),
            core_reference_receipt_sha256=core.receipt_sha256,runs=[dict(phase=p) for p in gate.fixture.PHASES],
            actual_sha256={p:{name:'a'*64 for name in gate.fixture.NAMES} for p in gate.fixture.PHASES})
    monkeypatch.setattr(gate,'run_case',run_case)
    monkeypatch.setattr(gate,'verify_all_build_sources',lambda *args:None)
    monkeypatch.setattr(gate,'verify_case_outputs',lambda *args:None)
    args=SimpleNamespace(output=root/'work/result',payload_layer0=root/'p0',payload_layer3=root/'p3',payload_extra=root/'px')
    return args,state,checked


def test_three_pairs_keep_live_authorities_native_failures_and_compact_hashes(harness):
    args,state,checked=harness;summary,code=gate.run(args)
    assert code==0 and summary['frozen_recipe_core_acceptance'] is True
    assert state['captures']==state['builds']==1 and len(state['cases'])==3 and len(checked)==3
    assert [row[0] for row in state['cases']]==['pass','cache-v-write-error','context-write-error']
    assert state['build_timeout']==7200 and all(row[1]==3600 for row in state['cases'])
    assert summary['planned_actual_launches']==6 and summary['source_tokens']==[0,1]
    for field in ('native_context_acceptance','native_full_block_acceptance','full128_executed','full_block_supported','input_norm_dut','sigmoid_gate_dut','output_projection_dut','ffn_supported'):
        assert summary[field] is False
    assert all(row['gate_pass'] is False for row in summary['native_full_block_failures'].values())
    compact=args.output/'compact';assert {p.name for p in compact.iterdir()}=={'summary.json','source_input_hashes.json'}
    hashes=json.loads((compact/'source_input_hashes.json').read_text())
    assert set(hashes['output_sha256'])==set(gate.MODES)
    assert all(set(row)=={'cold0','carried1'} for row in hashes['output_sha256'].values())


def test_original_native_gate_failure_blocks_actual_build(harness):
    args,state,_=harness;state['original']=False;summary,code=gate.run(args)
    assert code==1 and not summary['numerical_acceptance'] and state['builds']==0 and not state['cases']
    assert 'original limits retained' in summary['error']['message']
    assert summary['native_full_block_failures']['baseline']['gate_pass'] is False


@pytest.mark.parametrize('fault',['bad_status','bad_hash','bad_authority'])
def test_unproven_case_cannot_be_promoted(harness,fault):
    args,state,_=harness;state[fault]=True;summary,code=gate.run(args)
    assert code==1 and not summary['numerical_acceptance'] and not summary['cases']
    assert len(state['cases'])==1


def test_final_drift_revokes_entire_gate_even_after_all_modes(harness):
    args,state,_=harness;state['final_drift']=True;summary,code=gate.run(args)
    assert code==1 and not summary['frozen_recipe_core_acceptance'] and len(summary['cases'])==3
    assert 'final DUT/build/tool identity drift' in summary['error']['message']


def test_total_budget_stops_before_next_actual_process(harness):
    args,state,_=harness;state['timeout_build']=True;summary,code=gate.run(args)
    assert code==1 and not summary['numerical_acceptance'] and not state['cases']
    assert summary['remaining_budget_seconds']==0 and 'total budget exhausted' in summary['error']['message']
    saved=json.loads((args.output/'compact/summary.json').read_text())
    assert saved['status']=='FAIL_FRESH_HOST_ATTENTION_CORE_M1'


def test_timer_restored_even_when_caught_stage_fails():
    import signal
    before=signal.getsignal(signal.SIGALRM)
    with pytest.raises(ValueError):
        with gate.total_budget(60):raise ValueError('control-only stage')
    assert signal.getsignal(signal.SIGALRM)==before and signal.getitimer(signal.ITIMER_REAL)==(0.,0.)


@pytest.mark.parametrize('mode',['normal','timeout','interrupt','interrupt_int'])
def test_real_process_group_cleans_grandchild_on_every_exit(tmp_path,mode,record_property):
    """Real tiny Python processes only; the grandchild ignores TERM deliberately."""
    import os
    import signal
    import time
    marker=tmp_path/'grandchild.pid'
    grandchild = (
        'import os,signal,sys,time; '
        'signal.pthread_sigmask(signal.SIG_UNBLOCK,(signal.SIGINT,signal.SIGTERM)); '
        'signal.signal(signal.SIGTERM,signal.SIG_IGN); '
        'open(sys.argv[1],"w").write(str(os.getpid())); '
        'time.sleep(60)')
    worker = (
        'import os,signal,subprocess,sys,time; '
        'signal.pthread_sigmask(signal.SIG_UNBLOCK,(signal.SIGINT,signal.SIGTERM)); '
        'subprocess.Popen([sys.executable,"-c",sys.argv[1],sys.argv[2]]); '
        'deadline=time.monotonic()+5\n'
        'while not os.path.exists(sys.argv[2]) and time.monotonic()<deadline: time.sleep(.005)\n'
        'if not os.path.exists(sys.argv[2]): raise SystemExit(2)\n'
        'if sys.argv[3]=="interrupt": os.kill(os.getppid(),signal.SIGTERM)\n'
        'if sys.argv[3]=="interrupt_int": os.kill(os.getppid(),signal.SIGINT)\n'
        'if sys.argv[3]!="normal": time.sleep(60)\n')
    handlers={sig:signal.getsignal(sig) for sig in (signal.SIGINT,signal.SIGTERM)}
    started=time.monotonic()
    result=gate.supervise_process([sys.executable,'-c',worker,grandchild,str(marker),mode],
                                 timeout_seconds=1.0 if mode=='timeout' else 5.0,grace_seconds=.1)
    elapsed=time.monotonic()-started
    assert marker.is_file(), 'grandchild must have started before cleanup is tested'
    pid=int(marker.read_text())
    def active():
        try:
            # Zombies cannot execute or retain pipes. Container PID 1 may
            # reap adopted grandchildren later than the supervisor exits.
            return Path('/proc/'+str(pid)+'/stat').read_text().split()[2] not in ('Z','X')
        except FileNotFoundError:
            return False
    deadline=time.monotonic()+2
    while active() and time.monotonic()<deadline:time.sleep(.01)
    try:
        assert not active(), 'grandchild survived full process-group cleanup'
        assert elapsed<4 and result['cleanup']['direct_child_reaped'] is True
        assert result['cleanup']['term_sent'] is True and result['cleanup']['kill_sent'] is True
        assert result['reason']=={'normal':'worker_exit','timeout':'total_budget_timeout','interrupt':'interrupted','interrupt_int':'interrupted'}[mode]
        assert result['returncode']==(0 if mode=='normal' else 1)
        assert all(signal.getsignal(sig)==handler for sig,handler in handlers.items())
        record_property('process_group_cleanup',json.dumps(dict(mode=mode,grandchild_pid=pid,
            grandchild_active_after_cleanup=active(),elapsed_seconds=elapsed,result=result),sort_keys=True))
    finally:
        if active():os.kill(pid,signal.SIGKILL)


def test_supervisor_failure_preserves_original_native_evidence_and_downgrades_partial_pass(tmp_path,monkeypatch):
    root=tmp_path/'repo';root.mkdir();(root/'work').mkdir();out=root/'work/run';out.mkdir()
    monkeypatch.setattr(gate,'ROOT',root)
    summary=dict(status='PASS_FRESH_HOST_ATTENTION_CORE_M1_FROZEN_RECIPE',numerical_acceptance=True,
                 frozen_recipe_core_acceptance=True,stage='complete',native_full_block_failures={'baseline':{'gate_pass':False}})
    hashes={'source_sha256':{'source.py':'a'*64}}
    gate._write_compact(out,summary,hashes)
    result=gate._supervisor_failure(out,dict(reason='total_budget_timeout',forced_shutdown=True,returncode=1))
    assert result['status']=='FAIL_FRESH_HOST_ATTENTION_CORE_M1' and result['numerical_acceptance'] is False
    assert result['frozen_recipe_core_acceptance'] is False
    assert result['native_full_block_failures']==summary['native_full_block_failures']
    assert json.loads((out/'compact/source_input_hashes.json').read_text())==hashes
    assert {p.name for p in (out/'compact').iterdir()}=={'summary.json','source_input_hashes.json'}


def test_supervisor_failure_creates_compact_evidence_if_worker_never_checkpointed(tmp_path,monkeypatch):
    root=tmp_path/'repo';root.mkdir();(root/'work').mkdir();out=root/'work/run'
    monkeypatch.setattr(gate,'ROOT',root)
    result=gate._supervisor_failure(out,dict(reason='interrupted',forced_shutdown=True,returncode=1))
    assert result['numerical_acceptance'] is False and result['stage']=='supervised_worker_start'
    assert (out/'compact/summary.json').is_file() and (out/'compact/source_input_hashes.json').is_file()


def test_supervisor_preserves_relative_paths_before_worker_cwd_change(tmp_path,monkeypatch):
    root=tmp_path/'repo';root.mkdir();(root/'work').mkdir()
    caller=root/'caller';caller.mkdir();monkeypatch.chdir(caller)
    monkeypatch.setattr(gate,'ROOT',root)
    args=SimpleNamespace(output=Path('../work/run'),payload_layer0=Path('p0'),
                         payload_layer3=Path('../p3'),payload_extra=Path('px'))
    monkeypatch.setattr(gate,'_arguments',lambda:args)
    seen=[]
    def supervise(argv,**kwargs):
        seen.extend(argv[4:])
        return dict(forced_shutdown=False,returncode=0)
    monkeypatch.setattr(gate,'supervise_process',supervise)
    with pytest.raises(SystemExit) as finished:
        gate.main()
    assert finished.value.code==0
    assert dict(zip(seen[::2],seen[1::2]))=={
        '--output':str(root/'work/run'),'--payload-layer0':str(caller/'p0'),
        '--payload-layer3':str(root/'p3'),'--payload-extra':str(caller/'px')}
