#!/usr/bin/env python3
"""Fresh raw-hidden Attention block, two same-DUT two-launch cases.

Capture baseline/AVX2 exactly once, retain live independent reference authority,
then use only actual predecessor writes and actual retained prefix KV. Acceptance
is frozen-recipe full-block equality; native full-block and M128 stay open.
Only compact summary and source/input/output hashes are uploadable artifacts.
"""
from pathlib import Path
import argparse
import contextlib
import json
import os
import re
import signal
import subprocess
import sys
import time

# Fixture first: all imports resolve to the production v2 descriptor enum.
import host_bf16_attention_block_fixture as fixture
from host_bf16_attention_block_prefix import run_pair as run_deterministic_prefixes, STATUS as PREFIX_STATUS
from host_block_mac_profile import collect as collect_mac_profile
from heteronpu.qwen35_arch_utilization import report as gdn_architecture_bound
from host_bf16_attention_block_live_gate import (
    BUILD_STATUS, CASE_STATUS, MODES, SCOPE, generate_block_reference,
    pack_fixture, admit_fixture, run_case, build_identity, verify_all_build_sources, verify_case_outputs,
)
from host_bf16_attention_core_reference import WINDOWS
# Preserve the existing production process-group supervisor, without a second
# implementation of signal masking, descendant cleanup or timer behavior.
from run_host_bf16_attention_core_fresh_gate import (
    total_budget, supervise_process, RUNNER_BUDGET_SECONDS, FAILURE_RESERVE_SECONDS,
    GROUP_TERMINATION_GRACE_SECONDS,
)
from pack_host_bf16_v_fixture import ROOT, rebuild_session
from host_bf16_qkv_reference import generate_projection_references
from host_bf16_qk_rope_reference import generate_attention_references
from run_host_bf16_qkv_fresh_gate import require, sha, merge_sources, verify_checkout
from run_host_bf16_v_fresh_gate import _write_compact, _native_failure_evidence, _preflight, _git_head

SCRIPT_DIR = ROOT/'chisel/continuous_prefill/scripts'
SPLIT_RUNNER_BUDGET_SECONDS = 12000
SPLIT_CASE_BUDGET_SECONDS = 10800
BUILD_RUNNER_BUDGET_SECONDS = 6300
# Exact production emission from 79bbe; scheduling changes do not change RTL.
EXPECTED_RTL_SHA256 = 'e8b6ab6640ef0b932a0fc976b00b64998094d692698b4f8e134ead0911611510'
ENTRY_SOURCES = (
    '.github/workflows/host-bf16-attention-block.yml',
    '.github/workflows/host-bf16-attention-core.yml', 'pyproject.toml',
    'chisel/continuous_prefill/scripts/run_host_bf16_attention_block_fresh_gate.py',
    'chisel/continuous_prefill/scripts/run_host_bf16_attention_block_gate.sh',
    'chisel/continuous_prefill/scripts/host_bf16_attention_block_live_gate.py',
    'chisel/continuous_prefill/scripts/host_bf16_attention_block_prefix.py',
    'chisel/continuous_prefill/scripts/host_bf16_attention_block_build_artifact.py',
    '.github/scripts/verify_attention_block_split.py',
    'chisel/continuous_prefill/scripts/host_block_mac_profile.py',
    'src/heteronpu/qwen35_arch_utilization.py',
    'chisel/continuous_prefill/scripts/host_bf16_attention_block_reference.py',
    'chisel/continuous_prefill/scripts/host_bf16_attention_block_fixture.py',
    'chisel/continuous_prefill/scripts/host_bf16_attention_block_execution.py',
    'chisel/continuous_prefill/scripts/host_bf16_attention_block_descriptor.py',
    'chisel/continuous_prefill/tests/host_bf16_attention_block.cpp',
    'chisel/continuous_prefill/tests/host_attention_block_prefix.h',
    'chisel/continuous_prefill/scripts/attention_sigmoid_reference.py',
    # Reused supervisor imports the full stable core closure. The live fixture
    # source identity also binds all production scripts and Python ABI sources.
    'chisel/continuous_prefill/scripts/run_host_bf16_attention_core_fresh_gate.py',
    'chisel/continuous_prefill/scripts/host_bf16_attention_core_live_gate.py',
    'chisel/continuous_prefill/scripts/host_bf16_attention_core_reference.py',
    'chisel/continuous_prefill/scripts/host_bf16_attention_core_fixture.py',
    'chisel/continuous_prefill/scripts/host_bf16_attention_core_execution.py',
    'chisel/continuous_prefill/scripts/run_host_bf16_qkv_fresh_gate.py',
    'chisel/continuous_prefill/scripts/run_host_bf16_v_fresh_gate.py',
    'scripts/check_git_payloads.py',
)


def case_plan():
    return MODES



def invocation_policy(args):
    """Public, bounded scheduling choices; never change a DUT launch or oracle."""
    build_only = getattr(args, 'build_only', False)
    require(type(build_only) is bool, 'invalid build-only policy')
    values = [getattr(args, name, None) for name in
              ('archive', 'expected_sha256', 'expected_commit', 'mode')]
    split = any(value is not None for value in values)
    require(not (build_only and split), 'build and transferred case are exclusive')
    if split:
        archive, digest, commit, mode = values
        require(all(value is not None for value in values), 'complete trusted transfer arguments required')
        require(isinstance(digest, str) and re.fullmatch('[0-9a-f]{64}', digest)
                and isinstance(commit, str) and re.fullmatch('[0-9a-f]{40}', commit)
                and mode in MODES, 'invalid trusted transfer identity/mode')
    return dict(build_only=build_only, split=split,
        modes=(values[3],) if split else case_plan(),
        runner_seconds=(BUILD_RUNNER_BUDGET_SECONDS if build_only else
                        SPLIT_RUNNER_BUDGET_SECONDS if split else RUNNER_BUDGET_SECONDS),
        case_seconds=SPLIT_CASE_BUDGET_SECONDS if split else 3600)


def _new_output(original):
    original = Path(original)
    require(not original.is_symlink(), 'output symlink')
    out = original.resolve()
    require(out.is_relative_to(ROOT/'work') and out != ROOT/'work' and not out.exists(),
            'new output beneath ignored work required')
    out.mkdir(parents=True)
    return out


def run_build(args):
    """One normal production build; the artifact contains no model payloads."""
    from host_bf16_attention_block_build_artifact import seal
    policy = invocation_policy(args)
    require(policy['build_only'], 'explicit build-only policy required')
    out = _new_output(args.output)
    hashes = dict(source_sha256={}, input_sha256={}, output_sha256={})
    summary = dict(status='RUNNING_HOST_ATTENTION_BLOCK_BUILD_ONLY', stage='preflight',
        numerical_acceptance=False, frozen_recipe_block_acceptance=False,
        native_full_block_acceptance=False, full128_executed=False, overall_pass=False,
        runner_budget_seconds=policy['runner_seconds'],
        artifact_upload_allowlist=['host_attention_block_build.tar.gz',
                                  'compact/summary.json','compact/source_input_hashes.json'])
    started = time.monotonic()
    try:
        with total_budget(policy['runner_seconds'] - FAILURE_RESERVE_SECONDS):
            head = _git_head()
            hashes['source_sha256'] = {name:sha(ROOT/name) for name in ENTRY_SOURCES}
            verify_checkout(head, hashes['source_sha256'])
            summary['git_head'] = head
            env = os.environ.copy(); env.setdefault('BUILD_JOBS', '1')
            require(env['BUILD_JOBS'] == '1', 'serial production build required')
            env['SOURCE_IDENTITY_SCOPE'] = 'full'
            summary['idma_preflight'] = _preflight(env, out)
            summary['stage'] = 'production_attention_block_build_only'
            _write_compact(out, summary, hashes)
            build = out/'host_build'
            with (out/'host_build.log').open('w') as log:
                subprocess.run(['bash',str(SCRIPT_DIR/'run_host_bf16_attention_block_gate.sh'),str(build),'0'],
                    cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,check=True,
                    timeout=policy['runner_seconds']-FAILURE_RESERVE_SECONDS)
            ready = json.loads((build/'build_ready.json').read_text())
            require(ready['status'] == BUILD_STATUS and ready['numerical_pass'] is False,
                    'build-only receipt must not claim numerical acceptance')
            require(ready['rtl_sha256'] == EXPECTED_RTL_SHA256, 'unchanged production RTL identity drift')
            merge_sources(hashes['source_sha256'], json.loads((build/'sources.sha256.json').read_text()))
            receipt = seal(build, out/'host_attention_block_build.tar.gz', head)
            verify_checkout(head, hashes['source_sha256'])
            summary.update(status='PASS_HOST_ATTENTION_BLOCK_BUILD_ONLY', stage='complete',
                           build=ready, build_transfer=receipt, source_immutability_verified=True)
            hashes.update({key:receipt[key] for key in ('package_sha256','binary_sha256','rtl_sha256',
                           'build_ready_sha256','source_manifest_sha256','toolchain_sha256')})
        code = 0
    except (Exception, KeyboardInterrupt) as error:
        summary.update(status='FAIL_HOST_ATTENTION_BLOCK_BUILD_ONLY',
                       error=dict(type=type(error).__name__,message=str(error)))
        log = out/'host_build.log'
        if log.exists(): summary['diagnostic_log_tail'] = log.read_text(errors='replace')[-12000:]
        code = 1
    summary['elapsed_seconds'] = time.monotonic()-started
    _write_compact(out, summary, hashes)
    return summary, code


def run(args):
    policy = invocation_policy(args)
    require(not policy['build_only'], 'build-only invocation cannot execute a numerical case')
    out = _new_output(args.output)
    hashes = dict(source_sha256={}, input_sha256={}, output_sha256={})
    summary = dict(status='RUNNING_FRESH_HOST_ATTENTION_BLOCK_M1', stage='preflight', scope=SCOPE,
        numerical_acceptance=False, frozen_recipe_block_acceptance=False, native_context_acceptance=False,
        native_full_block_acceptance=False, actual_host_root=True, experimental_default_off=True,
        representative_tokens_per_launch=1, source_tokens=[0,1], source_phase='cold_m128',
        host_phases=['cold0','carried1'], commands_per_launch=22, descriptors_per_launch=296, owner_jobs_per_successful_launch=19,
        acknowledged_bytes_per_successful_launch=68608, shared_trig_shape=[256,64], raw_hidden_input=True,
        same_dut_launches_per_case=2, resets_between_launches=0, actual_prior_prefix_cache_required=True,
        reference_injection=False, intermediate_preload=False, prior_cache_preload=False,
        logical_matrix_engines=1, physical_matrix_slices=8, pinned_idma_instances=1, scalar_service_shared=True,
        frozen_norm_recipe='C1', frozen_rope_recipe='B1', gqa_recipe='sequential_fma_shared_exp7_v1',
        native_context_gate='UNASSIGNED_DIAGNOSTIC_ONLY_NOT_NATIVE_ACCEPTANCE',
        max_declared_rows=128, full128_executed=False, input_norm_dut=True, sigmoid_gate_dut=True,
        output_projection_dut=True, ffn_supported=True, full_block_supported=True, fault_restore_supported=False,
        overall_pass=False, timing_signoff=False, qor_signoff=False,
        upstream_gdn_decode_executed=False, cross_host_byte_equivalence_claimed=False,
        fresh_official_executions=None, reused_official_executions=0,
        planned_actual_invocations=len(policy['modes']), planned_actual_launches=2*len(policy['modes']), cases=[],
        requested_mode=getattr(args, 'mode', None), transferred_build=policy['split'],
        paired_identical_stimulus_fault_comparison=not policy['split'],
        artifact_upload_allowlist=['compact/summary.json','compact/source_input_hashes.json'])
    started = time.monotonic()
    deadline = started + policy['runner_seconds']
    session = projection = attention = block = None
    build = out/'host_build'

    def remaining(cap):
        seconds = int(deadline-time.monotonic()-FAILURE_RESERVE_SECONDS)
        require(seconds > 0, 'runner total budget exhausted; preserve failure artifact before workflow timeout')
        return min(cap, seconds)

    def checkpoint(stage):
        summary.update(stage=stage, elapsed_seconds=time.monotonic()-started,
                       runner_budget_seconds=policy['runner_seconds'],
                       remaining_budget_seconds=max(0,int(deadline-time.monotonic())))
        _write_compact(out, summary, hashes)

    try:
        with total_budget(policy['runner_seconds']-FAILURE_RESERVE_SECONDS):
            merge_sources(hashes['source_sha256'], {name:sha(ROOT/name) for name in ENTRY_SOURCES})
            head = _git_head(); summary['git_head'] = head
            verify_checkout(head, hashes['source_sha256'])
            # A source-derived GDN M1 bound is distinct from this Attention
            # execution's measured counters. It is not an RTL cycle prediction.
            summary['source_only_gdn_m1_architectural_bound'] = gdn_architecture_bound(repo=ROOT)
            env = os.environ.copy(); env.setdefault('BUILD_JOBS','1')
            require(env['BUILD_JOBS'] == '1', 'serial production build required')
            env['SOURCE_IDENTITY_SCOPE'] = 'full'
            summary['idma_preflight'] = _preflight(env,out)
            checkpoint('fresh_official_prefix_capture')
            with (out/'pipeline.log').open('w') as pipeline, contextlib.redirect_stdout(pipeline):
                session = rebuild_session(out/'official_capture',args.payload_layer0,args.payload_layer3,args.payload_extra)
                summary.update(session.evidence())
                require(session.fresh and summary['fresh_official_executions'] == 2 and
                        summary['reused_official_executions'] == 0, 'one fresh baseline/AVX2 capture required')
                hashes['official_capture_manifest_sha256'] = session.manifest_sha256
                merge_sources(hashes['source_sha256'], session.verify()['source_sha256'])
                summary['native_full_block_failures'] = _native_failure_evidence(session)
                checkpoint('fresh_adjacent_projection_integer_c_reference')
                projection = generate_projection_references(session,out/'projection_reference',variants=('baseline',),windows=WINDOWS)
                receipt = projection.verify(session=session)
                require(receipt['requested_windows'] == [list(w) for w in WINDOWS] and
                        receipt['head_jobs'] == 24 and receipt['matrix_accumulator_steps'] == 10485760,
                        'two adjacent M1 full Q8/K2/V2 reference inventory')
                require(receipt['native_operator_gate_pass'] is True, 'unchanged native projection operator gate failed')
                hashes['projection_reference_receipt_sha256'] = projection.receipt_sha256
                merge_sources(hashes['source_sha256'], receipt['source_sha256'])
                summary['projection_reference'] = {key:receipt[key] for key in (
                    'status','origin','requested_windows','head_jobs','matrix_accumulator_steps','native_operator_gate_pass',
                    'native_thresholds','full128_reference_generated','cross_variant_input_identity_assumed')}
                checkpoint('fresh_frozen_norm_rope_integer_c_reference')
                attention = generate_attention_references(session,projection,out/'attention_reference',variants=('baseline',))
                attention_receipt = attention.verify(session=session,projection_reference_session=projection)
                require(attention_receipt['original_operator_gate_pass'] is True,
                        'frozen Norm/RoPE native operator gate failed; original limits retained')
                hashes['attention_reference_receipt_sha256'] = attention.receipt_sha256
                merge_sources(hashes['source_sha256'], attention_receipt['source_sha256'])
                summary['attention_reference'] = attention_receipt
                checkpoint('fresh_raw_hidden_full_block_reference_and_live_admission')
                block = generate_block_reference(session,projection,attention,out/'block_reference')
                authorities = dict(block_session=block,session=session,projection_session=projection,attention_session=attention)
                block_receipt = block.verify(session=session,projection_session=projection,attention_session=attention)
                summary['block_reference'] = block_receipt
                hashes['block_reference_receipt_sha256'] = block.receipt_sha256
                merge_sources(hashes['source_sha256'],block_receipt['source_sha256_after'])
                fixture_path = out/'pair_fixture'
                admitted = pack_fixture(fixture_path,**authorities)
                require(admitted['live_authorities_verified'] is True, 'live pack admission required')
                hashes['input_sha256'] = admitted['input_sha256']
                merge_sources(hashes['source_sha256'],admitted['source_sha256'])
                verify_checkout(head,hashes['source_sha256'])
                if policy['split']:
                    from host_bf16_attention_block_build_artifact import restore
                    require(head == args.expected_commit, 'transferred source commit differs from exact checkout')
                    checkpoint('restore_exact_production_attention_block_build')
                    summary['build_transfer'] = restore(args.archive, build, args.expected_sha256, args.expected_commit)
                else:
                    checkpoint('production_attention_block_build_only')
                    with (out/'host_build.log').open('w') as log:
                        subprocess.run(['bash',str(SCRIPT_DIR/'run_host_bf16_attention_block_gate.sh'),str(build),'0'],
                            cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=remaining(7200))
                ready = json.loads((build/'build_ready.json').read_text())
                require(ready['status'] == BUILD_STATUS and ready['numerical_pass'] is False,
                        'build-only receipt must not claim numerical acceptance')
                initial_identity = build_identity(build,admitted['source_sha256'])
                merge_sources(hashes['source_sha256'],json.loads((build/'sources.sha256.json').read_text()))
                hashes.update(binary_sha256=ready['binary_sha256'],rtl_sha256=ready['rtl_sha256'],
                              build_ready_sha256=sha(build/'build_ready.json'),build_identity_sha256=initial_identity)
                summary['build'] = ready
                if policy['split']:
                    require(ready['rtl_sha256'] == EXPECTED_RTL_SHA256, 'unchanged production RTL identity drift')
                summary['toolchain'] = json.loads((build/'toolchain.json').read_text())
                checkpoint('actual_bounded_full_block_prefixes')
                prefix_result = run_deterministic_prefixes(build, fixture_path,
                    timeout_seconds=remaining(240), **authorities)
                require(prefix_result['status'] == PREFIX_STATUS and
                        prefix_result['numerical_acceptance'] is False and
                        prefix_result['binary_sha256'] == hashes['binary_sha256'] and
                        prefix_result['rtl_sha256'] == hashes['rtl_sha256'] and
                        prefix_result['build_ready_sha256'] == hashes['build_ready_sha256'],
                        'bounded prefixes must use the actual unchanged numerical DUT')
                summary['deterministic_prefixes'] = prefix_result
                checkpoint('completed_bounded_full_block_prefixes')
                for mode in policy['modes']:
                    checkpoint('actual_two_launch_'+mode.replace('-','_'))
                    result = run_case(build,fixture_path,mode,timeout_seconds=remaining(policy['case_seconds']),**authorities)
                    require(result['status'] == CASE_STATUS and result['actual_dut_identity_verified'] is True and
                            result['live_authorities_verified'] is True and result['same_dut_launches'] == 2 and
                            result['resets_between_launches'] == 0 and result['numerical_acceptance_eligible'] is (mode == 'pass'),
                            'actual case scope/authority mismatch')
                    require(result['binary_sha256'] == hashes['binary_sha256'] and result['rtl_sha256'] == hashes['rtl_sha256'] and
                            result['build_ready_sha256'] == hashes['build_ready_sha256'] and
                            result['block_reference_receipt_sha256'] == hashes['block_reference_receipt_sha256'],
                            'case DUT/reference identity drift')
                    require(len(result['runs']) == 2 and set(result['actual_sha256']) == set(fixture.PHASES) and
                            all(set(row) == set(fixture.NAMES) for row in result['actual_sha256'].values()),
                            'missing per-launch actual output identity')
                    profile_log = build/(mode.replace('-', '_')+'.log')
                    profile = collect_mac_profile(profile_log, mode)
                    require(profile['log_sha256'] == result['log_sha256'],
                            'MAC profile and actual numerical audit used different logs')
                    summary.setdefault('measured_mac_profiles', {})[mode] = dict(profile,
                        actual_dut_identity_verified=True, binary_sha256=result['binary_sha256'],
                        rtl_sha256=result['rtl_sha256'], build_ready_sha256=result['build_ready_sha256'])
                    summary['cases'].append(dict(mode=mode,result=result))
                    hashes['output_sha256'][mode] = result['actual_sha256']
                    checkpoint('completed_'+mode.replace('-','_'))
                checkpoint('final_live_authority_and_dut_verification')
                require(block.verify(session=session,projection_session=projection,attention_session=attention) == block_receipt,
                        'full-block reference changed before final acceptance')
                require(admit_fixture(fixture_path,**authorities) == admitted, 'final live fixture admission changed')
                for row in summary['cases']:
                    verify_case_outputs(build,row['result'])
                verify_all_build_sources(build,'fresh_final_source_verify.log')
                require(build_identity(build,admitted['source_sha256']) == initial_identity, 'final DUT/build/tool identity drift')
                verify_checkout(head,hashes['source_sha256'])
                summary.update(session.evidence())
                summary['native_full_block_failures'] = _native_failure_evidence(session)
                require([row['mode'] for row in summary['cases']] == list(policy['modes']), 'incomplete actual mode inventory')
                numerical = not policy['split'] or args.mode == 'pass'
                summary.update(status=('PASS_FRESH_HOST_ATTENTION_BLOCK_CASE_M1' if policy['split'] else
                                       'PASS_FRESH_HOST_ATTENTION_BLOCK_M1_FROZEN_RECIPE'),
                    numerical_acceptance=numerical, frozen_recipe_block_acceptance=numerical,
                    git_head_verified_unchanged=True, source_immutability_verified=True)
                checkpoint('complete')
        return summary,0
    except (Exception,KeyboardInterrupt) as error:
        summary.update(status='FAIL_FRESH_HOST_ATTENTION_BLOCK_M1',numerical_acceptance=False,frozen_recipe_block_acceptance=False,
                       error=dict(type=type(error).__name__,message=str(error)))
        # Previously verified original failures remain visible even if the fresh
        # capture has changed; final evidence failure cannot erase them.
        if session is not None:
            try:
                summary.update(session.evidence())
                summary['native_full_block_failures'] = _native_failure_evidence(session)
            except Exception as drift:
                summary['final_capture_verification_error'] = str(drift)
        candidates = [out/'host_build.log',out/'pipeline.log']
        if build.is_dir(): candidates += list(build.glob('*.log'))
        latest = sorted((p for p in candidates if p.is_file() and not p.is_symlink()),key=lambda p:p.stat().st_mtime)[-4:]
        summary['diagnostic_log_tail'] = {str(p.relative_to(out)):p.read_text(errors='replace')[-12000:] for p in latest}
        # Preserve public counter records when the numerical auditor has no
        # terminal pair. These are incomplete observations, never utilization.
        partial = {}
        for mode in policy['modes']:
            path = build/(mode.replace('-', '_')+'.log')
            if path.is_file() and not path.is_symlink():
                records, count = [], 0
                with path.open(errors='replace') as stream:
                    for line in stream:
                        if line.startswith('HOST_MAC_PROFILE_'):
                            count += 1
                            if len(records) < 48:
                                records.append(line.rstrip('\n')[:1024])
                partial[mode] = dict(log_sha256=sha(path), complete=False,
                    numerical_acceptance=False, useful_utilization=None,
                    records=records, records_truncated=count>48)
        summary['partial_mac_profile_observations'] = partial
        checkpoint(summary['stage'])
        return summary,1


def _supervisor_failure(out, outcome):
    """Preserve the worker's last evidence and revoke any partial success."""
    out = Path(out)
    require(out.is_relative_to(ROOT/'work') and out != ROOT/'work' and not out.is_symlink(),
            'supervisor output outside ignored work')
    out.mkdir(parents=True,exist_ok=True)
    def existing(name):
        path = out/'compact'/name
        require(not path.is_symlink(), 'supervisor evidence symlink')
        if path.is_file():
            try:
                value = json.loads(path.read_text())
                if type(value) is dict:
                    return value
            except (ValueError,OSError):
                pass
        return {}
    summary = existing('summary.json')
    hashes = existing('source_input_hashes.json')
    summary.setdefault('stage','supervised_worker_start')
    if outcome['forced_shutdown'] or 'error' not in summary:
        if 'error' in summary:
            summary['worker_error'] = summary['error']
        summary['error'] = dict(type='ProcessGroupSupervisor',message=outcome['reason'])
    summary.update(status='FAIL_FRESH_HOST_ATTENTION_BLOCK_M1',scope=SCOPE,
                   numerical_acceptance=False,frozen_recipe_block_acceptance=False,native_full_block_acceptance=False,overall_pass=False,
                   supervisor=outcome,
                   artifact_upload_allowlist=['compact/summary.json','compact/source_input_hashes.json'])
    _write_compact(out,summary,hashes)
    return summary


def _arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--build-only',action='store_true')
    parser.add_argument('--archive',type=Path)
    parser.add_argument('--expected-sha256')
    parser.add_argument('--expected-commit')
    parser.add_argument('--mode',choices=MODES)
    parser.add_argument('--github-output',type=Path)
    for name,default in (('layer0','qwen35_layer0_payload'),('layer3','qwen35_layer3_payload'),('extra','qwen35_prefix_payload')):
        parser.add_argument('--payload-'+name,type=Path,default=ROOT/'work'/default)
    return parser.parse_args()


def publish_ci_outputs(args, summary):
    """Emit digests only after a live producer finished and sealed its compact."""
    target = getattr(args, 'github_output', None)
    if target is None:
        return
    out = Path(args.output).resolve()
    compact = out/'compact'
    values = dict(source_commit=summary['git_head'],
        summary_sha256=sha(compact/'summary.json'),
        hashes_sha256=sha(compact/'source_input_hashes.json'))
    if summary.get('build_transfer'):
        values.update({key:summary['build_transfer'][key] for key in
            ('package_sha256','binary_sha256','rtl_sha256','build_ready_sha256',
             'source_manifest_sha256','toolchain_sha256')})
    require(all(re.fullmatch('[0-9a-f]{40}' if key=='source_commit' else '[0-9a-f]{64}', value)
                for key,value in values.items()), 'invalid producer output digest')
    with Path(target).open('a') as output:
        output.write(''.join(key+'='+value+'\n' for key,value in values.items()))


def _worker_main():
    # Internal module entry only; no CLI switch or saved trust input exists.
    signal.pthread_sigmask(signal.SIG_UNBLOCK, (signal.SIGINT,signal.SIGTERM))
    args = _arguments()
    try:
        policy = invocation_policy(args)
        summary,code = run_build(args) if policy['build_only'] else run(args)
        if code == 0:
            publish_ci_outputs(args, summary)
    except (ValueError,OSError) as error:
        print(json.dumps(dict(status='HOST_ATTENTION_BLOCK_ENTRY_REJECTED',error=str(error))))
        raise SystemExit(2)
    print(json.dumps(summary,sort_keys=True,separators=(',',':')))
    raise SystemExit(code)


def main():
    args = _arguments()
    try:
        policy = invocation_policy(args)
        original = Path(args.output)
        require(not original.is_symlink(), 'output symlink')
        out = original.resolve()
        require(out.is_relative_to(ROOT/'work') and out != ROOT/'work' and not out.exists(),
                'new output beneath ignored work required')
        # The same entry source runs in a separate interpreter/session. All
        # factories and their authorities remain together inside that worker.
        entry = ('import sys; sys.path.insert(0,sys.argv.pop(1)); '
                 'from run_host_bf16_attention_block_fresh_gate import _worker_main; _worker_main()')
        # Resolve paths before the supervised child changes its cwd to ROOT.
        worker_args = ['--output', str(out)]
        for name in ('layer0', 'layer3', 'extra'):
            worker_args += ['--payload-'+name, str(getattr(args, 'payload_'+name).resolve())]
        if policy['build_only']:
            worker_args += ['--build-only']
        for name in ('archive','expected_sha256','expected_commit','mode','github_output'):
            value = getattr(args, name, None)
            if value is not None:
                worker_args += ['--'+name.replace('_','-'), str(value.resolve()) if isinstance(value,Path) else value]
        outcome = supervise_process([sys.executable,'-c',entry,str(SCRIPT_DIR),*worker_args],
            timeout_seconds=policy['runner_seconds']-2*GROUP_TERMINATION_GRACE_SECONDS)
        if outcome['forced_shutdown'] or outcome['returncode'] != 0:
            print(json.dumps(_supervisor_failure(out,outcome),sort_keys=True,separators=(',',':')))
        raise SystemExit(outcome['returncode'])
    except (ValueError,OSError) as error:
        print(json.dumps(dict(status='HOST_ATTENTION_BLOCK_ENTRY_REJECTED',error=str(error))))
        raise SystemExit(2)


if __name__ == '__main__':
    main()
