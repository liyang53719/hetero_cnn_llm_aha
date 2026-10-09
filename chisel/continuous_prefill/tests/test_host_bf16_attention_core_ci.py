"""Static CI/budget/serialization contracts only; no production execution."""
from pathlib import Path
import sys

import yaml

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'chisel/continuous_prefill/scripts'))
import run_host_bf16_attention_core_fresh_gate as gate


def test_workflow_full_owner_controls_finite_serial_build_and_no_raw_upload():
    flow=yaml.load((ROOT/'.github/workflows/host-bf16-attention-core.yml').read_text(),Loader=yaml.BaseLoader)
    job=flow['jobs']['representative-attention-core']
    assert gate.RUNNER_BUDGET_SECONDS+gate.FAILURE_RESERVE_SECONDS < int(job['timeout-minutes'])*60 < 6*3600
    assert job['env']['BUILD_JOBS']=='1' and '-Xss8m' in job['env']['JVM_OPTS']
    controls=next(step for step in job['steps'] if step.get('name','').startswith('Shared Scalar'))
    assert 'Bf16CausalGqaOwnerSpec' in controls['run'] and 'Bf16KvAppendOwnerSpec' in controls['run']
    assert 'HostAttentionCoreCommandsSpec' in controls['run'] and ' -- ' not in controls['run']
    assert 'VM_PARALLEL_BUILDS=0' in controls['env']['MAKEFLAGS']
    uploads=[step for step in job['steps'] if step.get('uses','').startswith('actions/upload-artifact')]
    assert len(uploads)==1 and uploads[0]['if']=='always()'
    assert uploads[0]['with']['path'].split()==[
        'work/host_attention_core_fresh_ci/compact/summary.json',
        'work/host_attention_core_fresh_ci/compact/source_input_hashes.json']


def test_build_only_uses_real_top_and_strict_optimized_driver():
    script=(ROOT/'chisel/continuous_prefill/scripts/run_host_bf16_attention_core_gate.sh').read_text()
    assert 'EmitHostBf16AttentionCore' in script and '--top-module HostBlockTop' in script
    assert 'host_bf16_attention_core.cpp' in script
    assert 'OPT_FAST=-O2 OPT_SLOW=-O0' in script and '-ffp-contract=off -fno-fast-math' in script
    assert 'numerical_pass=False' in script and 'BUILT_HOST_ATTENTION_CORE_NOT_NUMERICAL_PASS' in script
    assert 'production_source_identity.py" record' in script and 'production_source_identity.py" verify' in script
    assert 'actual_verilator_before.json' in script and 'actual_verilator_after.json' in script
