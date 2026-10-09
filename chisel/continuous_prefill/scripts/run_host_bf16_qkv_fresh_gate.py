#!/usr/bin/env python3
"""Fresh representative acceptance on one production Host QKV binary.

Requires the reviewed live independent-reference adapter and serial build
recipe. No saved capture/reference inputs or full128 option are accepted.
Upload only the same two compact JSON files used by the Host-V gate.
"""
from pathlib import Path
import argparse
import contextlib
import hashlib
import json
import os
import subprocess
import time

from pack_host_bf16_v_fixture import ROOT, rebuild_session
from pack_host_bf16_qkv_fixture import pack_fixture
from verify_host_bf16_qkv_fixture import verify
from host_bf16_qkv_execution import BUILD_STATUS, MODES, run_case, verify_all_build_sources
from host_bf16_qkv_reference import generate_projection_references
# Reuse the published Host-V gate's existing compact/failure/tool conventions.
from run_host_bf16_v_fresh_gate import _write_compact, _native_failure_evidence, _preflight, _git_head

SCRIPT_DIR = ROOT / 'chisel/continuous_prefill/scripts'
WINDOWS = (('baseline', 'cold', 0), ('baseline', 'carried', 127),
           ('avx2', 'cold', 0), ('avx2', 'carried', 127))
ENTRY_SOURCES = (
    '.github/workflows/host-bf16-v.yml', 'pyproject.toml', 'scripts/check_git_payloads.py',
    'chisel/continuous_prefill/config/host_bf16_qkv_descriptor_contract.json',
    'chisel/continuous_prefill/config/host_bf16_v_descriptor_contract.json',
    'chisel/continuous_prefill/build.sbt', 'chisel/continuous_prefill/project/build.properties',
    'src/heteronpu/abi_validation.py', 'src/heteronpu/command.py',
    'src/heteronpu/descriptor_chain.py', 'src/heteronpu/gemmini_descriptor_v2.py',
    'src/heteronpu/gemmini_rocc_lowering.py',
) + tuple('chisel/continuous_prefill/scripts/' + name for name in (
    'run_host_bf16_qkv_fresh_gate.py', 'host_bf16_qkv_reference.py',
    'pack_host_bf16_qkv_fixture.py', 'verify_host_bf16_qkv_fixture.py',
    'host_bf16_qkv_descriptor.py', 'host_bf16_qkv_execution.py',
    'run_host_bf16_qkv_gate.sh', 'run_host_bf16_v_fresh_gate.py',
    'pack_host_bf16_v_fixture.py', 'prepare_host_ci_tools.sh',
    'prepare_pinned_idma_sources.py', 'prepare_idma_export.py',
))


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def case_plan():
    # Six modes means normal pass plus five fault/reset modes, not six faults.
    return [(v, p, base, mode) for v, p, base in WINDOWS
            for mode in (MODES if (v, p) == ('baseline', 'cold') else ('pass',))]


def merge_sources(destination, sources):
    for name, digest in sources.items():
        path = ROOT / name
        require(not Path(name).is_absolute() and '..' not in Path(name).parts
                and path.is_file() and not path.is_symlink(), 'invalid source identity path')
        require(name not in destination or destination[name] == digest, 'source identity conflict: ' + name)
        require(sha(path) == digest, 'source changed: ' + name)
        destination[name] = digest


def verify_checkout(head, sources):
    require(_git_head() == head, 'git HEAD changed')
    require(not os.environ.get('GITHUB_SHA') or os.environ['GITHUB_SHA'] == head,
            'checkout HEAD differs from GITHUB_SHA')
    tracked = set(subprocess.check_output(
        ['git', '-C', str(ROOT), 'ls-tree', '-rz', '--name-only', head]).decode().split('\0'))
    require(set(sources) <= tracked, 'source closure contains files absent from exact commit')
    dirty = subprocess.check_output(
        ['git', '-C', str(ROOT), 'status', '--porcelain', '--untracked-files=normal'], text=True)
    require(not dirty.strip(), 'exact-commit CI requires a clean tracked/index/untracked checkout')
    require(all(sha(ROOT / name) == digest for name, digest in sources.items()), 'source closure drift')


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--payload-layer0', type=Path, default=ROOT / 'work/qwen35_layer0_payload')
    p.add_argument('--payload-layer3', type=Path, default=ROOT / 'work/qwen35_layer3_payload')
    p.add_argument('--payload-extra', type=Path, default=ROOT / 'work/qwen35_prefix_payload')
    return p


def run(args):
    original = Path(args.output)
    require(not original.is_symlink(), 'output must not be a symlink')
    out = original.resolve()
    require(out.is_relative_to(ROOT / 'work') and out != ROOT / 'work' and not out.exists(),
            'new output beneath ignored work required')
    out.mkdir(parents=True)
    started = time.monotonic()
    hashes = dict(source_sha256={}, input_sha256={}, output_sha256={})
    summary = dict(status='RUNNING_FRESH_PRODUCTION_HOST_QKV_REPRESENTATIVE', stage='preflight',
        numerical_acceptance=False, scope='PROJECTION_ONLY', actual_host_root=True,
        experimental_default_off=True, norm_supported=False, rope_supported=False,
        full_block_supported=False, full128_requested=False, full128_accepted=False,
        logical_matrix_engines=1, physical_matrix_slices=8, pinned_idma_instances=1,
        cross_host_byte_equivalence_claimed=False, fresh_official_executions=None,
        reused_official_executions=0, planned_actual_invocations=len(case_plan()), cases=[],
        artifact_upload_allowlist=['compact/summary.json', 'compact/source_input_hashes.json'])
    session = references = None
    build = out / 'host_build'

    def checkpoint(stage):
        summary['stage'] = stage
        summary['elapsed_seconds'] = time.monotonic() - started
        _write_compact(out, summary, hashes)

    try:
        merge_sources(hashes['source_sha256'], {name: sha(ROOT / name) for name in ENTRY_SOURCES})
        head = _git_head()
        summary['git_head'] = head
        verify_checkout(head, hashes['source_sha256'])
        env = os.environ.copy()
        env.setdefault('BUILD_JOBS', '1')
        require(env['BUILD_JOBS'] == '1', 'production QKV build must remain serial')
        env['SOURCE_IDENTITY_SCOPE'] = 'full'
        summary['idma_preflight'] = _preflight(env, out)
        checkpoint('fresh_official_prefix_capture')
        with (out / 'pipeline.log').open('w') as log, contextlib.redirect_stdout(log):
            session = rebuild_session(out / 'official_capture', args.payload_layer0,
                                      args.payload_layer3, args.payload_extra)
            summary.update(session.evidence())
            require(session.fresh and summary['fresh_official_executions'] == 2
                    and summary['reused_official_executions'] == 0, 'fresh official session required')
            hashes['official_capture_manifest_sha256'] = session.manifest_sha256
            merge_sources(hashes['source_sha256'], session.verify()['source_sha256'])
            summary['native_full_block_failures'] = _native_failure_evidence(session)
            checkpoint('fresh_representative_integer_c_references')
            references = generate_projection_references(session, out / 'independent_reference',
                                                         variants=('baseline', 'avx2'))
            receipt = references.verify(session=session)
            require(receipt['head_jobs'] == 48 and len(receipt['windows']) == 4,
                    'expected both variants and both representative windows')
            merge_sources(hashes['source_sha256'], receipt['source_sha256'])
            hashes['independent_reference_receipt_sha256'] = references.receipt_sha256
            summary['independent_reference'] = {key: receipt[key] for key in (
                'status', 'origin', 'policy', 'head_jobs', 'matrix_accumulator_steps',
                'elapsed_seconds', 'native_operator_gate_pass', 'native_thresholds',
                'maximum_head_accumulator_bytes', 'persistent_accumulator_traces',
                'full128_reference_generated', 'cross_variant_input_identity_assumed')}
            summary['reference_toolchain'] = receipt['tools']
            require(receipt['native_operator_gate_pass'] is True,
                    'fresh independent terminals failed unchanged native operator thresholds')
            verify_checkout(head, hashes['source_sha256'])
            checkpoint('production_host_build_only')
            with (out / 'host_build.log').open('w') as log:
                subprocess.run(['bash', str(SCRIPT_DIR / 'run_host_bf16_qkv_gate.sh'), str(build), '0'],
                               cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
            summary['toolchain'] = json.loads((build / 'toolchain.json').read_text())
            merge_sources(hashes['source_sha256'], json.loads((build / 'sources.sha256.json').read_text()))
            ready = json.loads((build / 'build_ready.json').read_text())
            require(ready['status'] == BUILD_STATUS and ready['numerical_pass'] is False
                    and ready['initial_verilation_exit'] == 0, 'serial build-only receipt required')
            require(set(ready['actual_verilator']) == {'entrypoint', 'actual_elf'}
                    and ready['actual_verilator']['actual_elf']['kind'] == 'ELF'
                    and len(ready['actual_verilator']['actual_elf']['sha256']) == 64,
                    'actual Verilator ELF identity required')
            summary['build'] = {key: ready[key] for key in
                ('status', 'numerical_pass', 'initial_verilation_exit', 'actual_verilator')}
            hashes.update(binary_sha256=ready['binary_sha256'], rtl_sha256=ready['rtl_sha256'],
                          build_ready_sha256=sha(build / 'build_ready.json'))
            verify_checkout(head, hashes['source_sha256'])
            fixtures = {}
            for variant, phase, base, mode in case_plan():
                key = f'{variant}_{phase}_base{base}_count1'
                label = key + '_' + mode.replace('-', '_')
                checkpoint('actual_host_' + label)
                if key not in fixtures:
                    fixture = out / (key + '_fixture')
                    pack_fixture(fixture, variant=variant, phase=phase, token_base=base, token_count=1,
                                 session=session, reference_session=references)
                    admitted = verify(fixture, session=session, reference_session=references)
                    hashes['input_sha256'][key] = admitted['input_sha256']
                    fixtures[key] = fixture
                case_started = time.monotonic()
                result = run_case(build, fixtures[key], mode, session, label=label,
                                  reference_session=references)
                require(result['status'] == 'PASS_PRODUCTION_HOST_QKV_CASE'
                        and result['actual_dut_identity_verified'] is True
                        and result['numerical_acceptance_eligible'] is True
                        and result['binary_sha256'] == hashes['binary_sha256']
                        and result['rtl_sha256'] == hashes['rtl_sha256'], 'case identity or acceptance drift')
                summary['cases'].append(dict(name=label, variant=variant, phase=phase,
                    token_base=base, token_count=1, mode=mode, status=result['status'],
                    elapsed_seconds=time.monotonic() - case_started, runs=result['runs']))
                hashes['output_sha256'][label] = {
                    str(row['run']): row['actual_sha256'] for row in result['runs']}
                checkpoint('completed_' + label)
            checkpoint('final_source_capture_reference_verification')
            references.verify(session=session)
            verify_all_build_sources(build, 'fresh_final_source_verify.log')
            require(sha(build / 'obj/VHostBlockTop') == hashes['binary_sha256']
                    and sha(build / 'generated/HostBlockTop.sv') == hashes['rtl_sha256']
                    and sha(build / 'build_ready.json') == hashes['build_ready_sha256'], 'final DUT identity drift')
            verify_checkout(head, hashes['source_sha256'])
            summary.update(session.evidence())
            summary['native_full_block_failures'] = _native_failure_evidence(session)
            require(len(summary['cases']) == 9, 'incomplete representative/fault inventory')
            summary.update(git_head_verified_unchanged=True, source_immutability_verified=True,
                status='PASS_FRESH_PRODUCTION_HOST_QKV_REPRESENTATIVE', numerical_acceptance=True)
            checkpoint('complete')
        return summary, 0
    except (Exception, KeyboardInterrupt) as error:
        summary.update(status='FAIL_FRESH_PRODUCTION_HOST_QKV_REPRESENTATIVE', numerical_acceptance=False,
                       error=dict(type=type(error).__name__, message=str(error)))
        if session is not None:
            try:
                summary.update(session.evidence())
                summary['native_full_block_failures'] = _native_failure_evidence(session)
            except Exception as drift:
                summary['final_capture_verification_error'] = str(drift)
        for key, name in (('partial_build_toolchain', 'toolchain_before.json'),
                          ('partial_idma_identity', 'idma_identity.json')):
            path = build / name
            if path.is_file():
                try:
                    summary[key] = json.loads(path.read_text())
                except (ValueError, OSError):
                    pass
        checkpoint(summary['stage'])
        return summary, 1


def main():
    args = parser().parse_args()
    try:
        summary, code = run(args)
    except (ValueError, OSError) as error:
        print(json.dumps(dict(status='FRESH_HOST_QKV_ENTRY_REJECTED', error=str(error))))
        raise SystemExit(2)
    print(json.dumps(summary, sort_keys=True, separators=(',', ':')))
    raise SystemExit(code)


if __name__ == '__main__':
    main()
