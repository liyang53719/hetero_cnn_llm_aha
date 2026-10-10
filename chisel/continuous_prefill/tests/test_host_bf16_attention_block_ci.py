"""Static CI/budget/serialization contracts only; no production execution."""
from pathlib import Path
import sys

import yaml

ROOT=next(p for p in Path(__file__).resolve().parents if (p/'pyproject.toml').is_file())
SCRIPTS=ROOT/'chisel/continuous_prefill/scripts'
sys.path.insert(0,str(SCRIPTS))
FLOW=ROOT/'.github/workflows/host-bf16-attention-block.yml'
SHELL=SCRIPTS/'run_host_bf16_attention_block_gate.sh'
import run_host_bf16_attention_block_fresh_gate as gate


def test_workflow_full_owner_controls_finite_serial_build_and_no_raw_upload():
    flow=yaml.load(FLOW.read_text(),Loader=yaml.BaseLoader)
    job=flow['jobs']['build']
    assert set(flow['jobs'])=={'build','pass','fault','acceptance'}
    assert gate.BUILD_RUNNER_BUDGET_SECONDS < int(job['timeout-minutes'])*60 < 6*3600
    assert job['env']['BUILD_JOBS']=='1' and '-Xss8m' in job['env']['JVM_OPTS']
    controls=next(step for step in job['steps'] if step.get('name','').startswith('Shared Scalar'))
    assert 'Bf16CausalGqaOwnerSpec' in controls['run'] and 'Bf16KvAppendOwnerSpec' in controls['run']
    assert 'HostAttentionBlockCommandsSpec' in controls['run'] and ' -- ' not in controls['run']
    assert 'HostAttentionCoreCommandsSpec' in controls['run'] and 'AttentionSigmoidOwnerSpec' in controls['run']
    assert 'ATTENTION_SIGMOID_FIXED_VECTORS' in controls['run'] and 'ATTENTION_SIGMOID_FIXED_SHA256' in controls['run']
    assert 'scripts/attention_sigmoid_reference.py --output' in controls['run']
    assert flow['concurrency']['cancel-in-progress']=='false'
    assert 'VM_PARALLEL_BUILDS=0' in controls['env']['MAKEFLAGS']
    uploads=[step for step in job['steps'] if step.get('uses','').startswith('actions/upload-artifact')]
    assert len(uploads)==2 and uploads[1]['if']=='always()'
    assert uploads[0]['with']['path']=='work/host_attention_block_build_ci/host_attention_block_build.tar.gz'
    assert uploads[1]['with']['path'].split()==[
        'work/host_attention_block_build_ci/compact/summary.json',
        'work/host_attention_block_build_ci/compact/source_input_hashes.json']


def test_split_jobs_run_complete_pairs_and_only_share_the_immutable_build():
    flow=yaml.load(FLOW.read_text(),Loader=yaml.BaseLoader)
    assert sum(int(job['timeout-minutes']) for job in flow['jobs'].values())==570
    for key,mode in [('pass','pass'),('fault','final-residual-ack-error')]:
        job=flow['jobs'][key]
        assert job['needs']=='build'
        assert gate.SPLIT_CASE_BUDGET_SECONDS < gate.SPLIT_RUNNER_BUDGET_SECONDS < int(job['timeout-minutes'])*60 < 6*3600
        execute=next(step for step in job['steps'] if step.get('id')=='execute')
        assert '--mode '+mode in execute['run'] and '--archive ' in execute['run']
        assert '--expected-sha256 "$TRUSTED_PACKAGE_SHA"' in execute['run']
        assert '--expected-commit "$TRUSTED_SOURCE_COMMIT"' in execute['run']
        assert 'run_host_bf16_attention_block_gate.sh' not in '\n'.join(s.get('run','') for s in job['steps'])
        assert '--build-only' not in execute['run']
        uploads=[s for s in job['steps'] if s.get('uses','').startswith('actions/upload-artifact')]
        assert len(uploads)==1 and uploads[0]['if']=='always()'
        assert uploads[0]['with']['path'].split()==[
            'work/host_attention_block_'+key+'_ci/compact/summary.json',
            'work/host_attention_block_'+key+'_ci/compact/source_input_hashes.json']
        assert '--prepare-jars --archive ' in '\n'.join(s.get('run','') for s in job['steps'])
        assert 'bash chisel/continuous_prefill/scripts/prepare_hardfloat.sh' in '\n'.join(s.get('run','') for s in job['steps'])
    final=flow['jobs']['acceptance']
    assert final['needs']==['build','pass','fault'] and final['if']=='always()'
    dependencies=next(s for s in final['steps'] if s.get('name')=='Install pinned compact-verifier dependencies')
    assert dependencies['run']=='python -m pip install numpy==2.3.5 PyYAML==6.0.3'
    verify=next(s for s in final['steps'] if s.get('name','').startswith('Verify trusted'))
    assert verify['env']['PASS_SUMMARY']=='${{ needs.pass.outputs.summary_sha256 }}'
    assert verify['env']['FAULT_HASHES']=='${{ needs.fault.outputs.hashes_sha256 }}'
    assert '--expected-package-sha256 "$PACKAGE"' in verify['run']
    assert '--expected-rtl-sha256 "$RTL"' in verify['run']
    assert 'same-stimulus cross-job fault comparison is claimed' in FLOW.read_text()


def test_build_only_uses_real_top_and_strict_optimized_driver():
    script=SHELL.read_text()
    assert 'EmitHostBf16AttentionBlock' in script and '--top-module HostBlockTop' in script
    assert 'host_bf16_attention_block.cpp' in script
    assert 'OPT_FAST=-O2 OPT_SLOW=-O0' in script and '-ffp-contract=off -fno-fast-math' in script
    assert 'numerical_pass=False' in script and 'BUILT_HOST_ATTENTION_BLOCK_NOT_NUMERICAL_PASS' in script
    assert 'production_source_identity.py" record' in script and 'production_source_identity.py" verify' in script
    assert 'actual_verilator_before.json' in script and 'actual_verilator_after.json' in script


def test_new_workflow_retains_existing_regressions_and_binds_block_source_closure():
    flow=yaml.load(FLOW.read_text(),Loader=yaml.BaseLoader)
    steps=flow['jobs']['build']['steps']
    source=next(step for step in steps if step.get('name','').startswith('Source payload'))['run']
    assert source.count('test_host_bf16_attention_core*.py')==2
    assert source.count('test_host_bf16_attention_block*.py')==2
    assert source.count('tests/test_host_bf16_attention_block_reference.py')==2
    assert source.count('tests/test_attention_sigmoid_reference.py')==2
    assert 'python -O -m pytest' in source
    shell=SHELL.read_text()
    assert 'from host_bf16_attention_block_reference import source_identity as block_sources' in shell
    assert 'block_sources(),fixture_sources()' in shell
    assert 'run_host_bf16_attention_core_fresh_gate.py' in shell
    assert "scope.get('attention_block_policy_version')!=3" in shell
    assert "'QWEN35_LAYER3_ATTENTION_BLOCK_M1'" in shell
    assert 'commands_per_launch=22,descriptors_per_launch=296,owner_jobs_per_successful_launch=19' in shell
    assert 'acknowledged_bytes_per_successful_launch=68608' in shell
    assert 'native_full_block_acceptance=False,overall_pass=False' in shell
