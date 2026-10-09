"""Diagnostic admission/timing accounting only; no RTL/numerical proof."""
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import pytest

PATH = Path(__file__).with_name('run_profile.py')
SPEC = importlib.util.spec_from_file_location('attention_profile_runner', PATH)
R = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(R)


def sample():
    return dict(numerical_acceptance=False, prefix_reached=True, cycle_limit=4096,
                cycles=4096, eval_calls=12288, eval_ns=900, step_elapsed_ns=1000,
                driver_excluding_eval_ns=100, deterministic={'ar_handshakes':17,'r_handshakes':100,'cycles':4096,
                'terminal_event':{'end_issued_jobs':1,'end_pipeline_issues':3,'end_run':0,'end_pc':0,'end_reset_required':0}})


def test_identical_semantics_allow_different_clock_measurements():
    a=sample(); b=deepcopy(a)
    b.update(eval_ns=1900,step_elapsed_ns=2000)
    R.check_profiles(a,b,'a'*64,'a'*64)


@pytest.mark.parametrize('field,value', [('numerical_acceptance',True),('prefix_reached',False),
    ('cycles',4095),('cycle_limit',8192),('eval_calls',12287),('eval_ns',0),
    ('driver_excluding_eval_ns',101),('step_elapsed_ns',899),('deterministic',{})])
def test_invalid_partial_or_claim_is_rejected(field,value):
    a=sample(); b=sample(); b[field]=value
    with pytest.raises(ValueError): R.check_profiles(a,b,'a'*64,'a'*64)


def test_changed_handshake_or_payload_digest_is_rejected():
    a=sample(); b=sample(); b['deterministic']['ar_handshakes']=18
    with pytest.raises(ValueError,match='prefix differs'): R.check_profiles(a,b,'a'*64,'a'*64)
    with pytest.raises(ValueError,match='prefix differs'): R.check_profiles(a,a,'a'*64,'b'*64)


def test_idle_or_poisoned_prefix_is_not_active_matrix_profile():
    a=sample(); b=sample(); b['deterministic']['terminal_event']['end_pipeline_issues']=0
    with pytest.raises(ValueError,match='progress'): R.check_profiles(a,b,'a'*64,'a'*64)
    b=sample(); b['deterministic']['terminal_event']['end_reset_required']=1
    with pytest.raises(ValueError,match='pc0 scope'): R.check_profiles(a,b,'a'*64,'a'*64)


def test_frozen_builder_has_two_substitutions_and_readonly_precompile_guard(tmp_path):
    source_root=Path(os.environ.get('ATTENTION_PROFILE_SOURCE_ROOT',R.DIAGNOSTIC_ROOT))
    raw=subprocess.check_output(['git','-C',str(source_root),'show',R.PIN+':chisel/continuous_prefill/scripts/run_host_bf16_attention_core_gate.sh'])
    root=tmp_path/'source with spaces'; driver=tmp_path/'profile driver.cpp'
    text=R.relocated_builder(raw,root,driver)
    p=tmp_path/'build.sh';p.write_text(text)
    subprocess.run(['bash','-n',str(p)],check=True)
    import shlex
    restored=text.replace('ROOT='+shlex.quote(str(root))+';P="$ROOT/chisel/continuous_prefill"',
        'ROOT=$(cd "$(dirname "$0")/../../.." && pwd);P="$ROOT/chisel/continuous_prefill"',1)
    restored=restored.replace(shlex.quote(str(driver)),'"$P/tests/host_bf16_attention_core.cpp"',1)
    assert restored.count(R.rtl_admission_guard())==1
    assert restored.index(R.rtl_admission_guard()) < restored.index('python3 "$P/scripts/prepare_idma_export.py"')
    restored=restored.replace(R.rtl_admission_guard(),'')
    assert restored.encode()==raw
    assert R.RTL_SHA256=='4f061c48397979339ff97bef5a5e9f9dee2bd4a0dec7a5637f8a95b5de2e45f9'
    with pytest.raises(ValueError): R.relocated_builder(raw.replace(b'OPT_FAST=-O2',b'OPT_FAST=-Ofast'),root,driver)
    with pytest.raises(ValueError): R.relocated_builder(raw.replace(b'"$P/tests/host_bf16_attention_core.cpp"',b'"wrong.cpp"'),root,driver)


def test_exact_sv_admission_stops_before_compile_and_never_normalizes(tmp_path):
    import hashlib
    root=tmp_path/'build';(root/'generated').mkdir(parents=True)
    rtl=root/'generated/HostBlockTop.sv';rtl.write_text('module T; // exact source path\nendmodule\n')
    digest=hashlib.sha256(rtl.read_bytes()).hexdigest()
    guard=R.rtl_admission_guard()
    assert R.RTL_SHA256 in guard
    # A tiny explicit test fixture supplies only this test's expected digest.
    script='set -e\n'+guard.replace(R.RTL_SHA256,digest)+'touch "$OUT/compile_started"\n'
    env={**os.environ,'OUT':str(root)}
    assert subprocess.run(['bash','-c',script],env=env,capture_output=True).returncode==0
    assert (root/'compile_started').exists()
    (root/'compile_started').unlink()
    rtl.write_text(rtl.read_text().replace('exact source path','different source path'))
    failed=subprocess.run(['bash','-c',script],env=env,capture_output=True,text=True)
    assert failed.returncode!=0 and not (root/'compile_started').exists()
    receipt=json.loads((root/'generated_rtl_identity.json').read_text())
    assert receipt['exact_match'] is False and receipt['expected_sha256']==digest
    assert receipt['checked_before_verilation_and_cpp'] is True
    assert receipt['numerical_acceptance'] is False
    assert 'compilation not started' in failed.stderr


def test_gqa_ab_changes_only_one_simulator_config_argument_and_appended_boundary(tmp_path):
    source_root=Path(os.environ.get('ATTENTION_PROFILE_SOURCE_ROOT',R.DIAGNOSTIC_ROOT))
    raw=subprocess.check_output(['git','-C',str(source_root),'show',R.PIN+':chisel/continuous_prefill/scripts/run_host_bf16_attention_core_gate.sh'])
    config=subprocess.check_output(['git','-C',str(source_root),'show',R.PIN+':chisel/continuous_prefill/tests/native_weight_hierarchy.vlt'])
    candidate=R.gqa_boundary_configuration(config)
    assert candidate.encode()==config+b'\nhier_block -module "Bf16CausalGqaOwner"\n'
    with pytest.raises(ValueError):R.gqa_boundary_configuration(candidate.encode())
    with pytest.raises(ValueError):R.gqa_boundary_configuration(b'not a config')
    root=tmp_path/'source';driver=tmp_path/'profile.cpp';hierarchy=tmp_path/'new hierarchy.vlt'
    base=R.relocated_builder(raw,root,driver)
    changed=R.relocated_builder(raw,root,driver,hierarchy)
    import shlex
    assert changed.replace(shlex.quote(str(hierarchy)),'"$P/tests/native_weight_hierarchy.vlt"',1)==base
    p=tmp_path/'candidate.sh';p.write_text(changed);subprocess.run(['bash','-n',str(p)],check=True)


def test_candidate_registration_cannot_rebind_baseline_driver_or_builder(tmp_path):
    driver=tmp_path/'driver.cpp';driver.write_text('frozen shared driver')
    builder=tmp_path/'baseline.sh';builder.write_text('frozen baseline builder')
    original=R.bind_instrumented_sources(tmp_path,[driver,builder],{})
    candidate=tmp_path/'candidate.vlt';candidate.write_text('new boundary')
    appended=R.bind_instrumented_sources(tmp_path,[driver,builder,candidate],original)
    assert {k:appended[k] for k in original}==original and len(appended)==3
    assert len(original)==2
    driver.write_text('unexpected source drift')
    with pytest.raises(ValueError,match='previously frozen'):
        R.bind_instrumented_sources(tmp_path,[driver,builder,candidate],original)
    with pytest.raises(ValueError,match='previously frozen'):
        R.bind_instrumented_sources(tmp_path,[],appended)


def test_ab_reports_timing_only_and_rejects_changed_semantics():
    a=sample();b=sample();b.update(eval_ns=450,step_elapsed_ns=550)
    base=dict(prefixes=[a,deepcopy(a)]);candidate=dict(prefixes=[b,deepcopy(b)])
    R.check_profiles(a,b,'a'*64,'a'*64)
    result=R.compare_variant_measurements(base,candidate,200,100)
    assert result['baseline_over_candidate_eval']==2
    assert result['baseline_over_candidate_build']==2
    assert result['numerical_acceptance'] is False and result['original_full_chain_completed'] is False
    candidate['prefixes'][0]['deterministic']['terminal_event']['end_pipeline_issues']=4
    with pytest.raises(ValueError,match='prefix differs'):R.check_profiles(a,b,'a'*64,'a'*64)
    with pytest.raises(ValueError):R.compare_variant_measurements(base,dict(prefixes=[b]),200,100)


@pytest.mark.parametrize('enabled',[False,True])
def test_supervisor_forwards_explicit_ab_selection_with_original_total_budget(tmp_path,monkeypatch,enabled):
    from types import SimpleNamespace
    seen={}
    def supervise(command,timeout_seconds):
        seen.update(command=command,timeout=timeout_seconds)
        return {'returncode':0,'forced_shutdown':False}
    monkeypatch.setattr(R,'arguments',lambda:SimpleNamespace(gqa_boundary_ab=enabled))
    monkeypatch.setattr(R,'checked_paths',lambda args:(tmp_path/'source',tmp_path/'out'))
    monkeypatch.setattr(R,'imports',lambda source:SimpleNamespace(supervise_process=supervise))
    monkeypatch.setattr(R,'finalize_supervision',lambda out,result:result['returncode'])
    with pytest.raises(SystemExit) as stopped:R.main()
    assert stopped.value.code==0 and seen['timeout']==7800
    assert seen['command'].count('--gqa-boundary-ab')==int(enabled)


def test_actual_compile_flag_collection_and_missing_strict_flags(tmp_path):
    b=tmp_path/'bounded_build';b.mkdir()
    (b/'result.json').write_text(json.dumps({'status':'PASS','stages':[]}))
    p=b/'01.log';p.write_text('g++ -Os -O2 -ffp-contract=off -fno-fast-math -c -o p.o /tmp/profile_driver.cpp\n'
        'c++ -O0 -ffp-contract=off -fno-fast-math -c -o s.o VHost__Slow.cpp\n')
    r=R.compiler_evidence(tmp_path)
    assert {x['effective_optimization'] for x in r['commands']}=={'-O2','-O0'}
    assert sum(x['compile_commands'] for x in r['commands'])==2
    p.write_text(p.read_text().replace('-ffp-contract=off',''))
    with pytest.raises(ValueError,match='strict FP'):R.compiler_evidence(tmp_path)


def test_two_checkout_identity_is_explicit_before_source_environment_switch():
    original={'GITHUB_SHA':'a'*40,'OTHER':'retained'}
    changed=R.source_environment(original,'a'*40,R.PIN)
    assert original['GITHUB_SHA']=='a'*40
    assert changed=={'GITHUB_SHA':R.PIN,'ATTENTION_PROFILE_DIAGNOSTIC_SHA':'a'*40,'OTHER':'retained'}
    with pytest.raises(ValueError,match='triggering'): R.source_environment(original,'b'*40,R.PIN)
    with pytest.raises(ValueError,match='source identity'): R.source_environment(original,'a'*40,'b'*40)


@pytest.mark.parametrize('kind', ['missing','partial','valid'])
def test_supervisor_preserves_interrupted_receipt_and_never_invents_success(tmp_path,kind):
    if kind!='missing':
        c=tmp_path/'compact';c.mkdir()
        (c/'summary.json').write_text('{"stage":' if kind=='partial' else '{"status":"COMPLETE","stage":"complete"}')
        (c/'source_input_hashes.json').write_text('{}')
    code=R.finalize_supervision(tmp_path,{'returncode':0,'forced_shutdown':False})
    s=json.loads((tmp_path/'compact/summary.json').read_text())
    assert s['numerical_acceptance'] is False
    assert code==(0 if kind=='valid' else 1)
    assert s['status']==('COMPLETE' if kind=='valid' else 'INCOMPLETE_BOUNDED_FULL_TOP_PROFILE')
    assert {p.name for p in (tmp_path/'compact').iterdir()}=={'summary.json','source_input_hashes.json'}
    if kind=='partial':assert (tmp_path/'supervisor_previous_summary.json.partial').read_text()=='{"stage":'
