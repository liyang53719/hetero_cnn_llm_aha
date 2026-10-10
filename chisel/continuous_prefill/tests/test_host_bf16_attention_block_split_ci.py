"""Split scheduling controls, without a model, compiler, or simulated DUT."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_host_bf16_attention_block_fresh_gate import gate, harness
import host_bf16_attention_block_build_artifact as transfer


def test_public_split_policy_preserves_old_default_and_finite_budgets():
    old = gate.invocation_policy(SimpleNamespace())
    assert old['modes'] == gate.MODES and old['runner_seconds'] == 18000
    assert old['case_seconds'] == 3600 and not old['split']
    built = gate.invocation_policy(SimpleNamespace(build_only=True))
    assert built['runner_seconds'] == 6300 and built['build_only']
    args = SimpleNamespace(archive=Path('archive'), expected_sha256='b'*64,
                           expected_commit='a'*40, mode='pass')
    split = gate.invocation_policy(args)
    assert split['modes'] == ('pass',) and split['runner_seconds'] == 12000
    assert split['case_seconds'] == 10800 and split['split']


@pytest.mark.parametrize('fields', [
    {'mode':'pass'}, {'archive':Path('archive')}, {'build_only':1},
    {'archive':Path('archive'),'expected_sha256':'b'*64,'expected_commit':'a'*40,'mode':'pass','build_only':True},
    {'archive':Path('archive'),'expected_sha256':'bad','expected_commit':'a'*40,'mode':'pass'},
    {'archive':Path('archive'),'expected_sha256':'b'*64,'expected_commit':'bad','mode':'pass'},
    {'archive':Path('archive'),'expected_sha256':'b'*64,'expected_commit':'a'*40,'mode':'invalid'},
])
def test_incomplete_or_unbounded_transfer_policy_rejected(fields):
    with pytest.raises(ValueError): gate.invocation_policy(SimpleNamespace(**fields))


@pytest.fixture
def split_harness(harness, monkeypatch):
    args,state,checked = harness
    args.archive = args.output.parent/'sealed.tar.gz'
    args.expected_sha256 = 'b'*64
    args.expected_commit = 'a'*40
    args.mode = 'pass'
    state['restores'] = 0
    def forbidden_build(*args, **kwargs):
        raise AssertionError('a transferred numerical job must never rebuild')
    monkeypatch.setattr(gate.subprocess, 'run', forbidden_build)
    def restore(archive, path, digest, commit):
        assert (archive,digest,commit) == (args.archive,args.expected_sha256,args.expected_commit)
        state['restores'] += 1
        (path/'obj').mkdir(parents=True); (path/'generated').mkdir()
        (path/'obj/VHostBlockTop').write_bytes(b'CONTROL_ONLY_NOT_AN_ELF')
        (path/'generated/HostBlockTop.sv').write_text('// CONTROL ONLY\n')
        ready = dict(status=gate.BUILD_STATUS,numerical_pass=False,
            binary_sha256=gate.sha(path/'obj/VHostBlockTop'),rtl_sha256=gate.sha(path/'generated/HostBlockTop.sv'))
        for name,value in [('build_ready.json',ready),('sources.sha256.json',{}),('toolchain.json',{'control_only':True})]:
            (path/name).write_text(json.dumps(value))
        monkeypatch.setattr(gate, 'EXPECTED_RTL_SHA256', ready['rtl_sha256'])
        return dict(package_sha256=digest,source_commit=commit,**ready)
    monkeypatch.setattr(transfer, 'restore', restore)
    return args,state,checked


@pytest.mark.parametrize('mode', gate.MODES)
def test_transferred_case_keeps_fresh_live_pair_and_its_exact_mode(split_harness, mode):
    args,state,checked = split_harness; args.mode=mode
    summary,code = gate.run(args)
    assert code == 0 and state['restores'] == 1 and state['builds'] == 0
    assert state['captures'] == 1 and state['prefixes'] == 1
    assert state['cases'] == [(mode,10800)]
    assert summary['status'] == 'PASS_FRESH_HOST_ATTENTION_BLOCK_CASE_M1'
    assert summary['requested_mode'] == mode and summary['runner_budget_seconds'] == 12000
    assert summary['planned_actual_invocations'] == 1 and summary['planned_actual_launches'] == 2
    assert summary['numerical_acceptance'] is (mode=='pass')
    assert summary['frozen_recipe_block_acceptance'] is (mode=='pass')
    assert summary['paired_identical_stimulus_fault_comparison'] is False
    assert summary['native_full_block_acceptance'] is False and summary['overall_pass'] is False
    assert set(summary['measured_mac_profiles']) == {mode}
    assert set(summary['native_full_block_failures']) == {'baseline','avx2'}


def test_wrong_transfer_commit_rejected_before_unpack_or_actual_run(split_harness):
    args,state,_ = split_harness; args.expected_commit='c'*40
    summary,code=gate.run(args)
    assert code==1 and state['restores']==0 and not state['cases']
    assert 'source commit' in summary['error']['message']


def test_failed_transfer_never_launches_dut(split_harness,monkeypatch):
    args,state,_=split_harness
    def reject(*args): raise ValueError('archive SHA mismatch')
    monkeypatch.setattr(transfer,'restore',reject)
    summary,code=gate.run(args)
    assert code==1 and not state['cases'] and not summary['numerical_acceptance']
    assert summary['error']['message']=='archive SHA mismatch'


def test_timeout_preserves_counter_observations_without_utilization(split_harness,monkeypatch):
    args,state,_=split_harness
    def timeout(build,path,mode,**kwargs):
        (build/'pass.log').write_text('HOST_MAC_PROFILE_BEGIN run=0 cycle=36 wide_steps=0 pipeline_stalls=0 idma_transfers=0\n')
        raise ValueError('actual pair timeout')
    monkeypatch.setattr(gate,'run_case',timeout)
    summary,code=gate.run(args)
    assert code==1 and not summary['numerical_acceptance']
    partial=summary['partial_mac_profile_observations']['pass']
    assert partial['complete'] is False and partial['useful_utilization'] is None
    assert partial['numerical_acceptance'] is False and len(partial['records'])==1


def test_ci_output_digests_are_from_completed_compact_files(harness,tmp_path):
    args,state,_=harness
    summary,code=gate.run(args); assert code==0
    args.github_output=tmp_path/'github-output'
    gate.publish_ci_outputs(args,summary)
    fields=dict(line.split('=',1) for line in args.github_output.read_text().splitlines())
    assert fields==dict(source_commit='a'*40,
        summary_sha256=gate.sha(args.output/'compact/summary.json'),
        hashes_sha256=gate.sha(args.output/'compact/source_input_hashes.json'))


def test_build_only_seals_once_without_capture_or_numerical_acceptance(harness,monkeypatch):
    args,state,_=harness; args.build_only=True
    monkeypatch.setattr(gate,'EXPECTED_RTL_SHA256',hashlib.sha256(b'// CONTROL ONLY\n').hexdigest())
    sealed=[]
    def seal(build,archive,commit):
        sealed.append((build,archive,commit))
        ready=json.loads((build/'build_ready.json').read_text())
        return dict(source_commit=commit,package_sha256='c'*64,
            binary_sha256=ready['binary_sha256'],rtl_sha256=ready['rtl_sha256'],
            build_ready_sha256=gate.sha(build/'build_ready.json'),
            source_manifest_sha256='d'*64,toolchain_sha256='e'*64)
    monkeypatch.setattr(transfer,'seal',seal)
    summary,code=gate.run_build(args)
    assert code==0 and summary['status']=='PASS_HOST_ATTENTION_BLOCK_BUILD_ONLY'
    assert state['builds']==1 and state['captures']==0 and not state['cases']
    assert state['build_timeout']==6300-gate.FAILURE_RESERVE_SECONDS
    assert len(sealed)==1 and sealed[0][2]=='a'*40
    assert summary['numerical_acceptance'] is False and summary['overall_pass'] is False


def test_build_rtl_drift_rejects_before_archive_seal(harness,monkeypatch):
    args,state,_=harness; args.build_only=True
    def forbidden(*args):raise AssertionError('drifting RTL must not be sealed')
    monkeypatch.setattr(transfer,'seal',forbidden)
    summary,code=gate.run_build(args)
    assert code==1 and 'RTL identity drift' in summary['error']['message']
    assert state['builds']==1 and not summary['numerical_acceptance']
