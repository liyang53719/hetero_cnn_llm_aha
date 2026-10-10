#!/usr/bin/env python3
"""One new frozen-98 Attention M1 pair and same-input official measurements.

Restores the single authenticated original build; never compiles or retries a
pair. Live production authorities stay in this supervised worker. The native
helper and retained archives remain offline claims, never hardware authorities.
Only the explicit small artifact allowlist may leave the runner.
"""
from __future__ import annotations

import argparse
import contextlib
from datetime import datetime
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import re
import signal
import stat
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[2]
PIN = '98c7d80f65c5f05b55726c5239a6e9ec15d1b53f'
ARCHIVE_SHA256 = '1cfaf045ca58704016bfecff3f079b7fa708d1d7f7043b0fb014b5da61b7bfb1'
BASELINE_RUN_ID = '38015586840'
BINARY_SHA256 = 'f0f194342fe9ab70290069441f48b9863c6ed9ab9bcd5f3991c7f60168073263'
RTL_SHA256 = 'e8b6ab6640ef0b932a0fc976b00b64998094d692698b4f8e134ead0911611510'
RUNNER_SECONDS, JOB_SECONDS = 12000, 13200
FAILURE_RESERVE_SECONDS = UPLOAD_RESERVE_SECONDS = 180
PAIR_SECONDS, MIN_PAIR_SECONDS = 10800, 9000
DRIVER = 'chisel/continuous_prefill/tests/host_bf16_attention_block.cpp'
WRAPPER_SOURCES = ('tools/attention_native/run_native_pair.py',
    'tools/attention_native/pack_replay.py', 'tools/attention_threads/run_diagnostic.py',
    'scripts/verify_attention_native_m1.py', '.github/workflows/attention-native-m1-pair.yml',
    'config/upstream/qwen3_5_0p8b/layer3_bf16_contract.json',
    'config/upstream/qwen3_5_0p8b/layer3_payload_pin.json')
UPLOAD_LIMITS = {'compact/summary.json': 8 * 1024 * 1024,
    'compact/source_input_hashes.json': 8 * 1024 * 1024,
    'official_m1_preflight.json': 2 * 1024 * 1024,
    'official_m1_actual.json': 2 * 1024 * 1024,
    'input_replay.zip': 16 * 1024, 'replay_pack.zip': 256 * 1024,
    'pack_summary.json': 64 * 1024, 'diagnostic_tail.txt': 12 * 1024}


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


diagnostic = load_module('attention_native_diagnostic_support',
                         ROOT / 'tools/attention_threads/run_diagnostic.py')
require, sha, read_json = diagnostic.require, diagnostic.sha, diagnostic.read_json


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()


def write_json(path, value, limit):
    raw = encoded(value)
    require(len(raw) <= limit, 'compact JSON exceeds artifact limit')
    require(not path.exists() and not any(p.is_symlink() for p in (path, *path.parents)),
            'fresh nonsymlink report required')
    with path.open('xb') as stream:
        stream.write(raw)


def checked_paths(args):
    require(args.expected_sha256 == ARCHIVE_SHA256 and args.baseline_run_id == BASELINE_RUN_ID,
            'only the exact original successful build archive/run is allowed')
    return diagnostic.checked_paths(args)


class Budget:
    """The upload and failure reserves are distinct, inside the 220-minute job."""
    def __init__(self, args, *, wall=time.time, monotonic=time.monotonic):
        require(all(isinstance(value, str) and re.fullmatch('[1-9][0-9]*', value)
                    for value in (args.run_id, args.job_id)), 'numeric current run/job IDs required')
        for key, value in (('GITHUB_RUN_ID', args.run_id), ('CURRENT_JOB_ID', args.job_id),
                           ('CURRENT_JOB_STARTED_AT', args.job_started_at)):
            require(not os.environ.get(key) or os.environ[key] == value, 'trusted workflow identity mismatch: ' + key)
        require(isinstance(args.job_started_at, str) and re.fullmatch(
            r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?Z', args.job_started_at),
            'UTC API job started_at required')
        began = datetime.fromisoformat(args.job_started_at.replace('Z', '+00:00')).timestamp()
        elapsed = wall() - began
        require(math.isfinite(elapsed) and 0 <= elapsed < JOB_SECONDS,
                'job started_at is future or outside the job window')
        self.monotonic, self.started = monotonic, monotonic()
        self.job_elapsed = elapsed
        self.outer_seconds = min(RUNNER_SECONDS, JOB_SECONDS - elapsed - UPLOAD_RESERVE_SECONDS)
        require(self.outer_seconds > FAILURE_RESERVE_SECONDS, 'job budget exhausted before worker start')
        self.active_deadline = self.started + self.outer_seconds - FAILURE_RESERVE_SECONDS

    def remaining(self):
        seconds = self.active_deadline - self.monotonic()
        require(seconds > 0, 'total native-pair budget exhausted')
        return seconds

    def pair_timeout(self):
        seconds = self.remaining()
        require(seconds >= MIN_PAIR_SECONDS, 'fewer than 9000 active seconds remain; actual pair not started')
        return min(PAIR_SECONDS, int(seconds))

    def receipt(self):
        return dict(runner_budget_seconds=self.outer_seconds, job_timeout_seconds=JOB_SECONDS,
            job_elapsed_at_admission_seconds=self.job_elapsed,
            upload_reserve_seconds=UPLOAD_RESERVE_SECONDS,
            failure_reserve_seconds=FAILURE_RESERVE_SECONDS,
            active_remaining_seconds=max(0, self.active_deadline - self.monotonic()))


def wrapper_identity(commit, expected=None):
    require(diagnostic.git(ROOT, 'rev-parse', 'HEAD') == commit and
            diagnostic.git(ROOT, 'rev-parse', '--show-toplevel') == str(ROOT) and
            not diagnostic.git(ROOT, 'status', '--porcelain', '--untracked-files=normal'),
            'wrapper checkout identity drift')
    tracked = set(diagnostic.git(ROOT, 'ls-tree', '-r', '--name-only', commit).splitlines())
    require(set(WRAPPER_SOURCES) <= tracked, 'wrapper source is absent from exact commit')
    actual = {name: sha(diagnostic.regular(ROOT / name)) for name in WRAPPER_SOURCES}
    require(expected is None or actual == expected, 'wrapper source hash drift')
    return actual


@contextlib.contextmanager
def production_environment(trigger):
    """Call only after independently verifying both Git roots and trigger."""
    require(os.environ.get('GITHUB_SHA') == trigger, 'trigger changed before production worker')
    os.environ.pop('GITHUB_SHA', None)
    try:
        yield
    finally:
        if trigger is None:
            os.environ.pop('GITHUB_SHA', None)
        else:
            os.environ['GITHUB_SHA'] = trigger


def helper_modules(source):
    # Production imports must already exist. Never add current src/scripts to
    # sys.path or rewrite ROOT on an imported production module.
    helper = load_module('attention_native_current_helper', ROOT / 'scripts/verify_attention_native_m1.py')
    helper.configure_production_source_root(source)
    packer = load_module('attention_native_current_packer', ROOT / 'tools/attention_native/pack_replay.py')
    return helper, packer


def configure_baseline_cpu():
    cached = sys.modules.get('torch')
    before = os.environ.get('ATEN_CPU_CAPABILITY')
    if cached is not None:
        require(cached.backends.cpu.get_cpu_capability() == 'DEFAULT',
                'already initialized Torch runtime is not baseline DEFAULT')
    os.environ['ATEN_CPU_CAPABILITY'] = 'default'
    return dict(requested='default', previous_setting=before, torch_preimported=cached is not None)


def source_preflight(source, build):
    """Read-only import/inventory check; no runtime, capture, model or simulator.

    Useful before committing the wrapper: it does not admit a dirty wrapper to
    execution or create live authorities. The production root must be exact and
    clean; all 658 source bytes must match its Git-tracked closure.
    """
    source, build = Path(source).absolute(), Path(build).absolute()
    require(not any(p.is_symlink() for p in (source, *source.parents)) and
            diagnostic.git(source, 'rev-parse', 'HEAD') == PIN and
            diagnostic.git(source, 'rev-parse', '--show-toplevel') == str(source) and
            not diagnostic.git(source, 'status', '--porcelain', '--untracked-files=normal'),
            'read-only preflight requires exact clean production checkout')
    diagnostic.imports(source)
    build_sources = diagnostic.source_map(read_json(build / 'sources.sha256.json'))
    stages = diagnostic.source_stage_snapshots(source, build_sources)
    union = diagnostic.source_union(build_sources, *stages.values())
    tracked = set(diagnostic.git(source, 'ls-tree', '-r', '--name-only', PIN).splitlines())
    require(len(build_sources) == 655 and len(union) == 658 and set(union) <= tracked,
            'original complete source inventory required')
    require(all(sha(diagnostic.regular(source / name)) == digest for name, digest in union.items()),
            'production source bytes differ from source inventory')
    return dict(status='READ_ONLY_SOURCE_INVENTORY_VERIFIED', production_source_commit=PIN,
        build_files=655, union_files=658,
        build_source_map_sha256=diagnostic.object_sha(build_sources),
        union_source_map_sha256=diagnostic.object_sha(union),
        reference_only_paths=sorted(set(union) - set(build_sources)),
        stages={name: dict(files=len(value), source_map_sha256=diagnostic.object_sha(value))
                for name, value in stages.items()}, actual_execution=False, native_full_block_acceptance=False)


def pack_inputs(fixture, out, admitted, args, wrapper_commit):
    """Retain the exact small stimulus even if official preflight cannot run."""
    members, records = {}, {}
    for name, expected_bytes, retained_bytes in (('cold0_hidden.bf16le', 2048, 2048),
            ('cold1_hidden.bf16le', 2048, 2048), ('trig.bf16le', 32768, 256)):
        path = diagnostic.regular(fixture / 'input' / name)
        require(path.stat().st_size == expected_bytes, 'raw input size changed: ' + name)
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        require(digest == admitted['input_sha256'][name], 'live raw input identity changed: ' + name)
        target = 'input/' + ('trig_first_two_rows.bf16le' if name == 'trig.bf16le' else name)
        members[target] = raw[:retained_bytes]
        records[target] = dict(bytes=retained_bytes, sha256=hashlib.sha256(members[target]).hexdigest(),
            source_file='input/' + name, source_bytes=expected_bytes, source_sha256=digest, source_offset=0)
    manifest = dict(schema='ATTENTION_M1_INPUT_REPLAY_V1', status='PREPARED_INPUT_ONLY_NOT_EXECUTED',
        production_source_commit=PIN, wrapper_source_commit=wrapper_commit, run_id=args.run_id,
        job_id=args.job_id, original_build_archive_sha256=ARCHIVE_SHA256,
        binary_sha256=BINARY_SHA256, rtl_sha256=RTL_SHA256,
        fixture_manifest_sha256=admitted['manifest_sha256'],
        reference_receipt_sha256=admitted['block_reference_receipt_sha256'],
        reference_receipt_file_sha256=sha(diagnostic.regular(fixture / 'reference_receipt.json')),
        input_sha256={name: admitted['input_sha256'][name] for name in
                      ('cold0_hidden.bf16le', 'cold1_hidden.bf16le', 'trig.bf16le')},
        files=records, raw_bytes=4352, actual_execution_included=False,
        hardware_authority_verified=False, native_full_block_acceptance=False,
        privacy_description='Fixed artificial-token model-derived inputs; authorized CI artifacts only; no weights, NPZ, gold, DDR or trace.')
    members['input_manifest.json'] = encoded(manifest)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_STORED) as archive:
        for name, raw in sorted(members.items()):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, raw)
    raw = buffer.getvalue()
    require(len(raw) <= UPLOAD_LIMITS['input_replay.zip'], 'input replay exceeds compact byte bound')
    path = out / 'input_replay.zip'
    require(not path.exists() and not any(p.is_symlink() for p in (path, *path.parents)), 'fresh input replay required')
    with path.open('xb') as stream:
        stream.write(raw)
    require(path.read_bytes() == raw, 'input replay changed while writing')
    with zipfile.ZipFile(path) as archive:
        require(set(archive.namelist()) == set(members) and all(archive.read(k) == v for k, v in members.items()),
                'input replay verification failed')
    return dict(status=manifest['status'], archive_sha256=sha(path), archive_bytes=len(raw),
                raw_bytes=4352, actual_execution_included=False, native_full_block_acceptance=False)


def validate_report(report, *, actual):
    require(all(report[key] is False for key in ('hardware_authority_verified',
        'hardware_authority_upgrade_supported', 'native_full_block_acceptance', 'overall_pass')),
        'offline helper cannot issue hardware or full native acceptance')
    modes = {'official_own_cache', 'canonical_prior_cache'}
    if actual:
        modes.add('retained_snapshot_prior_cache')
    require(set(report['modes']) == modes, 'official M1 trajectory inventory changed')
    for name, mode in report['modes'].items():
        rows = mode['cases']
        require(len(rows) == 2 and [(r['host_phase'], r['absolute_position'], r['query_tokens'])
            for r in rows] == [('cold0', 0, 1), ('carried1', 1, 1)] and
            all(r['original_trig_bit_identity'] is True for r in rows),
            'official preflight does not describe the exact adjacent two-M1 inputs/trig')
        if actual:
            require(all(r['hardware_authority_verified'] is False and
                        r['receipt_hashed_terminal_comparisons'] and
                        set(r['retained_cache_comparisons']) == {'k', 'v'} for r in rows),
                    'actual terminal measurements missing or authority inflated')
    if actual:
        require(report['retained_replay_pack']['hardware_authority_verified'] is False and
                report['retained_replay_pack']['old_pass_revalidated'] is False,
                'retained claim authority must stay separate from live wrapper')


def numeric_outcome(report):
    """Report unchanged per-operator and block-output gates independently."""
    modes = {}
    for name, mode in report['modes'].items():
        rows = mode['cases']
        modes[name] = dict(operator_limits_pass=all(metric['pass'] is True for row in rows
            for metric in row['receipt_hashed_terminal_comparisons'].values()),
            retained_cache_limits_pass=all(metric['pass'] is True for row in rows
                for metric in row['retained_cache_comparisons'].values()),
            block_output_limits_pass=all(row['receipt_hashed_output_comparison']['pass'] is True for row in rows),
            failed_operators={row['host_phase']: [name for name, metric in
                row['receipt_hashed_terminal_comparisons'].items() if metric['pass'] is not True] for row in rows},
            failed_cache_roles={row['host_phase']: [role for role, metric in
                row['retained_cache_comparisons'].items() if metric['pass'] is not True] for row in rows})
    return dict(modes=modes,
        measured_terminal_and_output_limits_pass=all(row['operator_limits_pass'] and row['retained_cache_limits_pass'] and
            row['block_output_limits_pass'] for row in modes.values()),
        missing_actual_internal_gqa_producers=report['missing_actual_internal_gqa_producers'],
        conditioned_gqa_acceptance=dict(status='UNASSIGNED_DIAGNOSTIC_ONLY',
            excluded_from_acceptance_reason='unassigned_stage_contract'),
        native_full_block_acceptance=False)


def validate_case(frozen, result, built, admitted):
    require(result['status'] == frozen.CASE_STATUS and result['mode'] == 'pass' and
            result['same_dut_launches'] == 2 and result['resets_between_launches'] == 0 and
            all(result[k] is True for k in ('actual_dut_identity_verified', 'live_authorities_verified',
                'source_immutability_verified', 'full_block_m1_executed', 'full_block_artifact_consistency',
                'frozen_recipe_block_acceptance', 'numerical_acceptance_eligible')) and
            all(result[k] is False for k in ('native_full_block_acceptance', 'intermediate_preload',
                'prior_cache_preload')), 'actual one-pair production gates/scope changed')
    require((result['binary_sha256'], result['rtl_sha256'], result['build_ready_sha256']) ==
            (built['obj/VHostBlockTop'], built['generated/HostBlockTop.sv'], built['build_ready.json']) and
            result['fixture_sha256'] == admitted['manifest_sha256'] and
            result['block_reference_receipt_sha256'] == admitted['block_reference_receipt_sha256'] and
            result['input_sha256'] == admitted['input_sha256'], 'actual source/build/fixture identity changed')


def perform_pair(args, out, build, frozen, helper, packer, authorities, admitted,
                 built, budget, summary, hashes, checkpoint, postcheck):
    fixture = out / 'pair_fixture'
    checkpoint('official_m1_runtime_schema_trig_preflight')
    bundle = helper.load_bundle(fixture, sha(fixture / 'reference_receipt.json'),
                                authorities['block_session'].receipt_sha256)
    require(bundle['receipt']['variant'] == 'baseline', 'baseline live fixture required')
    official = helper.OfficialM1(bundle)
    require(official.metadata['torch_cpu_capability'] == 'DEFAULT' and
            os.environ.get('ATEN_CPU_CAPABILITY') == 'default', 'official baseline runtime changed')
    summary['official_cpu_runtime'] = dict(requested='default', actual_capability='DEFAULT')
    preflight = helper.audit(bundle, official)
    validate_report(preflight, actual=False)
    write_json(out / 'official_m1_preflight.json', preflight, UPLOAD_LIMITS['official_m1_preflight.json'])
    hashes['official_m1_preflight_sha256'] = sha(out / 'official_m1_preflight.json')
    # Numerical preflight differences are retained. Unsupported runtime,
    # schema or trig instead raises above, before the expensive actual pair.
    summary['official_preflight_compatible'] = True
    postcheck()
    timeout = budget.pair_timeout()
    summary.update(actual_pair_invocations=1, actual_timeout_seconds=timeout)
    checkpoint('one_actual_pass_pair')
    result = frozen.run_case(build, fixture, 'pass', timeout_seconds=timeout, **authorities)
    validate_case(frozen, result, built, admitted)
    frozen.verify_case_outputs(build, result)
    postcheck()
    summary.update(full_block_m1_executed=True, live_physical_authority_verified=True,
                   frozen_recipe_block_acceptance=True, actual_result=result)
    hashes['output_sha256']['pass'] = result['actual_sha256']
    checkpoint('seal_actual_replay_before_native_comparison')
    archive = ROOT / 'work/attention_native_pair_retained' / (args.run_id + '-' + args.job_id) / 'replay_pack.zip'
    packed = packer.pack_verified_case(build, fixture, archive, result=result, original_commit=PIN,
        run_id=args.run_id, job_id=args.job_id, authorities=authorities)
    # Packer intentionally only writes beneath its own checkout's ignored work.
    # Copy the already-verified exact ZIP into the frozen output allowlist.
    manifest = packer.verify_pack(archive, packed['archive_sha256'], expected_commit=PIN,
        expected_run_id=args.run_id, expected_job_id=args.job_id,
        expected_reference_sha256=admitted['block_reference_receipt_sha256'])
    raw = diagnostic.regular(archive).read_bytes()
    require(len(raw) <= UPLOAD_LIMITS['replay_pack.zip'] and
            hashlib.sha256(raw).hexdigest() == packed['archive_sha256'], 'sealed replay changed before copy')
    with (out / 'replay_pack.zip').open('xb') as stream:
        stream.write(raw)
    require(sha(out / 'replay_pack.zip') == packed['archive_sha256'], 'replay copy changed')
    packer.verify_pack(out / 'replay_pack.zip', packed['archive_sha256'], expected_commit=PIN,
        expected_run_id=args.run_id, expected_job_id=args.job_id,
        expected_reference_sha256=admitted['block_reference_receipt_sha256'])
    write_json(out / 'pack_summary.json', packed, UPLOAD_LIMITS['pack_summary.json'])
    summary.update(replay_pack_sealed=True, replay_pack=packed)
    hashes['replay_pack_sha256'] = packed['archive_sha256']
    checkpoint('actual_replay_preserved')
    profile = frozen.collect_mac_profile(build / 'pass.log', 'pass')
    require(profile['log_sha256'] == result['log_sha256'], 'MAC profile did not use actual audited log')
    summary['measured_mac_profile'] = dict(profile, actual_dut_identity_verified=True,
        binary_sha256=result['binary_sha256'], rtl_sha256=result['rtl_sha256'],
        build_ready_sha256=result['build_ready_sha256'],
        qualification='Host testbench counter window including scripted DDR backpressure and completion holds; not isolated hardware throughput or timing/QoR signoff.')
    retained = helper.load_replay_pack(out / 'replay_pack.zip', packed['archive_sha256'], bundle,
        expected_commit=PIN, expected_run_id=args.run_id, expected_job_id=args.job_id)
    require(retained['hardware_authority_verified'] is False and
            retained['replay_manifest'] == manifest, 'offline retained authority/identity changed')
    checkpoint('same_input_actual_official_comparison')
    actual = helper.audit(bundle, official, retained)
    validate_report(actual, actual=True)
    for phase in actual['conditioned_gqa'].values():
        phase.update(acceptance_status='UNASSIGNED_DIAGNOSTIC_ONLY',
                     excluded_from_acceptance_reason='unassigned_stage_contract')
    write_json(out / 'official_m1_actual.json', actual, UPLOAD_LIMITS['official_m1_actual.json'])
    hashes['official_m1_actual_sha256'] = sha(out / 'official_m1_actual.json')
    summary['native_measurements'] = numeric_outcome(actual)
    frozen.verify_case_outputs(build, result)
    postcheck()
    summary.update(status=('TERMINAL_NATIVE_COMPARISONS_PASS' if
        summary['native_measurements']['measured_terminal_and_output_limits_pass'] else
        'COMPLETE_NATIVE_LIMITS_FAILED'), official_comparison_completed=True)


def run_worker(args):
    budget = Budget(args)
    source, out, wrapper_commit = checked_paths(args)
    trigger = os.environ.get('GITHUB_SHA')
    wrapper_sources = wrapper_identity(wrapper_commit)
    cpu_setup = configure_baseline_cpu()
    frozen, artifact = diagnostic.imports(source)
    out.mkdir(parents=True)
    summary = dict(status='RUNNING_NATIVE_M1_PAIR', stage='restore_original_build',
        production_source_commit=PIN, wrapper_source_commit=wrapper_commit, github_trigger_sha=trigger,
        run_id=args.run_id, job_id=args.job_id, job_started_at=args.job_started_at,
        trusted_baseline_run_id=BASELINE_RUN_ID, baseline_rebuilt=False, scala_executed=False,
        candidate_builds=0, actual_pair_invocations=0, planned_actual_pair_invocations=1,
        same_fresh_fixture=True, old_pass_revalidated=False, reference_injection=False,
        intermediate_preload=False, prior_cache_preload=False, full_block_m1_executed=False,
        live_physical_authority_verified=False, frozen_recipe_block_acceptance=False,
        native_full_block_acceptance=False, numerical_acceptance=False, overall_pass=False,
        full128_executed=False, timing_signoff=False, qor_signoff=False,
        whole_layer_speedup_claimed=False, replay_pack_sealed=False,
        official_cpu_setup=cpu_setup,
        artifact_upload_allowlist=list(UPLOAD_LIMITS), artifact_byte_limits=UPLOAD_LIMITS,
        **budget.receipt())
    hashes = dict(source_sha256={}, input_sha256={}, output_sha256={},
        wrapper_source_sha256=wrapper_sources, baseline_archive_sha256=ARCHIVE_SHA256)
    build = out / 'baseline'
    inventory = authorities = admitted = built = tools_before = None
    code = 1

    def checkpoint(stage):
        summary.update(stage=stage, elapsed_seconds=budget.monotonic() - budget.started, **budget.receipt())
        diagnostic.write_compact(out, summary, hashes)

    def postcheck():
        wrapper_identity(wrapper_commit, wrapper_sources)
        require(sha(diagnostic.regular(args.archive)) == ARCHIVE_SHA256, 'original archive changed')
        frozen.verify_checkout(PIN, hashes['source_sha256'])
        if inventory is not None:
            inventory.verify(hashes, read_json(build / 'sources.sha256.json'))
        if built is not None:
            frozen.verify_all_build_sources(build, 'native_pair_final_source_verify.log')
            require(frozen.build_identity(build, dict(inventory.build)) == built, 'original build/driver/source identity drift')
            require(diagnostic.selected_tools(build) == tools_before, 'selected toolchain drift')
        if authorities is not None:
            require(frozen.admit_fixture(out / 'pair_fixture', **authorities) == admitted, 'same live fixture changed')
            summary.update(authorities['session'].evidence())
            summary['original_m128_native_failures'] = frozen._native_failure_evidence(authorities['session'])

    # Frozen verify_checkout legitimately pins the production root, whereas
    # GITHUB_SHA describes this separately checked wrapper. Never forge it as 98.
    with production_environment(trigger):
        try:
            with frozen.total_budget(budget.remaining()):
                checkpoint('restore_original_build')
                require(os.environ.get('OFFLINE_TOOLS'), 'original compiler JAR runtime required')
                summary['compiler_jars'] = artifact.prepare_compiler_jars(args.archive,
                    Path(os.environ['OFFLINE_TOOLS']), ARCHIVE_SHA256, PIN)
                summary['build_transfer'] = artifact.restore(args.archive, build, ARCHIVE_SHA256, PIN)
                build_sources = read_json(build / 'sources.sha256.json')
                require(len(build_sources) == 655, 'complete original 655-file build inventory required')
                inventory = diagnostic.SourceInventory(frozen, build_sources,
                    diagnostic.source_stage_snapshots(source, build_sources), hashes)
                require(len(inventory.full) == 658, 'complete original 658-file source union required')
                built = frozen.build_identity(build, dict(inventory.build))
                require(built['obj/VHostBlockTop'] == BINARY_SHA256 and
                        built['generated/HostBlockTop.sv'] == RTL_SHA256, 'exact original production ELF/SV required')
                require(sha(diagnostic.regular(source / DRIVER)) == inventory.build[DRIVER], 'production driver source changed')
                hashes.update(baseline_identity=built, driver_source_sha256=inventory.build[DRIVER])
                tools_before = diagnostic.selected_tools(build)
                summary['selected_tools'] = tools_before
                helper, packer = helper_modules(source)
                for name in WRAPPER_SOURCES[-2:]:
                    require(sha(ROOT / name) == sha(source / name), 'packer/frozen model contract differs')
                postcheck()
                checkpoint('one_fresh_capture_and_live_fixture')
                with (out / 'pipeline.log').open('x') as pipeline, contextlib.redirect_stdout(pipeline):
                    authorities, admitted = diagnostic.fresh_fixture(frozen, args, out, summary, hashes, inventory)
                inventory.require_complete(hashes)
                summary['original_m128_native_failures'] = summary.pop('native_full_block_failures')
                postcheck()
                summary['input_replay'] = pack_inputs(out / 'pair_fixture', out, admitted, args, wrapper_commit)
                hashes['input_replay_sha256'] = summary['input_replay']['archive_sha256']
                checkpoint('exact_new_inputs_retained')
                perform_pair(args, out, build, frozen, helper, packer, authorities, admitted,
                    built, budget, summary, hashes, checkpoint, postcheck)
                code = 0 if summary['native_measurements']['measured_terminal_and_output_limits_pass'] else 2
        except (Exception, KeyboardInterrupt) as error:
            summary.update(status='FAILED_NATIVE_M1_PAIR', error=dict(type=type(error).__name__, message=str(error)))
            try:
                postcheck()
                summary['post_failure_identity_verified'] = True
            except Exception as drift:
                summary['post_failure_identity_error'] = str(drift)
        finally:
            summary['input_retention_gap'] = 'input_replay.zip' not in [p.name for p in out.iterdir()]
            summary['full_actual_replay_unavailable'] = not summary['replay_pack_sealed']
            checkpoint('complete' if code in (0, 2) else summary['stage'])
    return code


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source-root', 'output', 'archive', 'payload-layer0', 'payload-layer3', 'payload-extra'):
        parser.add_argument('--' + name, type=Path, required=True)
    for name in ('expected-sha256', 'expected-commit', 'baseline-run-id', 'run-id', 'job-id', 'job-started-at'):
        parser.add_argument('--' + name, required=True)
    return parser.parse_args(argv)


def worker_entry():
    signal.pthread_sigmask(signal.SIG_UNBLOCK, (signal.SIGINT, signal.SIGTERM))
    def interrupted(signum, frame):
        raise KeyboardInterrupt('supervisor cancellation ' + str(signum))
    signal.signal(signal.SIGTERM, interrupted)
    raise SystemExit(run_worker(arguments()))


def finalize_supervision(out, outcome):
    out.mkdir(parents=True, exist_ok=True)
    try:
        summary = read_json(out / 'compact/summary.json', UPLOAD_LIMITS['compact/summary.json'])
        hashes = read_json(out / 'compact/source_input_hashes.json', UPLOAD_LIMITS['compact/source_input_hashes.json'])
    except (ValueError, OSError):
        summary, hashes = {}, {}
        outcome = dict(outcome, returncode=1, missing_or_invalid_worker_evidence=True)
    summary.update(supervisor=outcome, native_full_block_acceptance=False, numerical_acceptance=False,
        overall_pass=False, timing_signoff=False, qor_signoff=False, whole_layer_speedup_claimed=False,
        artifact_upload_allowlist=list(UPLOAD_LIMITS), artifact_byte_limits=UPLOAD_LIMITS)
    if outcome['forced_shutdown'] or outcome['returncode'] not in (0, 2) or (
            outcome['returncode'] == 2 and summary.get('status') != 'COMPLETE_NATIVE_LIMITS_FAILED'):
        summary['status'] = 'FAILED_NATIVE_M1_PAIR'
    diagnostic.write_compact(out, summary, hashes)
    # Never publish a raw pipeline/DDR/trace tail, even on an unexpected error.
    # This diagnostic contains only bounded stage/lifecycle metadata.
    tail = encoded({key: summary.get(key) for key in ('status', 'stage', 'actual_pair_invocations',
        'full_block_m1_executed', 'official_comparison_completed', 'replay_pack_sealed', 'supervisor')})
    tail = tail[-UPLOAD_LIMITS['diagnostic_tail.txt']:]
    path = out / 'diagnostic_tail.txt'
    require(not path.exists() and not path.is_symlink(), 'fresh diagnostic tail required')
    path.write_bytes(tail)
    for name in ('compact/summary.json', 'compact/source_input_hashes.json',
                 'official_m1_preflight.json', 'official_m1_actual.json', 'pack_summary.json'):
        path = out / name
        if path.exists():
            # Print validated compact JSON only. Archives/inputs are never log fallbacks.
            value = read_json(path, UPLOAD_LIMITS[name])
            print('BEGIN_ATTENTION_NATIVE_COMPACT ' + name, flush=True)
            print(json.dumps(value, sort_keys=True, allow_nan=False), flush=True)
            print('END_ATTENTION_NATIVE_COMPACT ' + name, flush=True)
    return outcome['returncode']


def main():
    args = arguments()
    out = None
    try:
        budget = Budget(args)
        source, out, _ = checked_paths(args)
        frozen, _ = diagnostic.imports(source)
        entry = 'import sys;sys.path.insert(0,sys.argv.pop(1));from run_native_pair import worker_entry;worker_entry()'
        argv = [sys.executable, '-c', entry, str(Path(__file__).resolve().parent)]
        for name, value in vars(args).items():
            argv.extend(('--' + name.replace('_', '-'), str(value.resolve() if isinstance(value, Path) else value)))
        # Reuse the exact production process-group cleanup implementation.
        seconds = budget.outer_seconds - (budget.monotonic() - budget.started) - 10
        require(seconds > FAILURE_RESERVE_SECONDS, 'budget exhausted before supervisor')
        outcome = frozen.supervise_process(argv, timeout_seconds=seconds)
    except (Exception, KeyboardInterrupt) as error:
        outcome = dict(returncode=1, forced_shutdown=False, reason='pre_supervisor_validation_failed',
                       error_type=type(error).__name__)
        if out is None:
            # No output path has been admitted. Do not create files from failed
            # caller arguments; still provide bounded JSON in Actions logs.
            print('BEGIN_ATTENTION_NATIVE_COMPACT compact/summary.json', flush=True)
            print(json.dumps(dict(status='FAILED_NATIVE_M1_PAIR', supervisor=outcome,
                native_full_block_acceptance=False, actual_pair_invocations=0)), flush=True)
            print('END_ATTENTION_NATIVE_COMPACT compact/summary.json', flush=True)
            raise SystemExit(1)
    raise SystemExit(finalize_supervision(out, outcome))


if __name__ == '__main__':
    main()
