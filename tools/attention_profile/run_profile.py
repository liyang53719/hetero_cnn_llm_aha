#!/usr/bin/env python3
"""Bounded timing of the unchanged 695981 production top; never numerical acceptance."""
from pathlib import Path
import argparse
import contextlib
import hashlib
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import time

PIN = '6959810545203d5f9508075b311dba52f1bee0c9'
RTL_SHA256 = '4f061c48397979339ff97bef5a5e9f9dee2bd4a0dec7a5637f8a95b5de2e45f9'
BUDGET_SECONDS = 7800
BUILD_SECONDS = 6000
PREFIX_SECONDS = 240
CYCLES = 4096
HERE = Path(__file__).resolve().parent
DIAGNOSTIC_ROOT = HERE.parents[1]


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def source_environment(current, diagnostic_commit, source_commit):
    """Bind both checkouts before adapting the frozen runner's one-root CI check."""
    require(source_commit == PIN, 'wrong production source identity')
    require(not current.get('GITHUB_SHA') or current['GITHUB_SHA'] == diagnostic_commit,
            'diagnostic checkout differs from triggering GITHUB_SHA')
    result = dict(current)
    result['ATTENTION_PROFILE_DIAGNOSTIC_SHA'] = diagnostic_commit
    result['GITHUB_SHA'] = source_commit
    return result


def frozen_file(root, name):
    raw = subprocess.check_output(['git', '-C', str(root), 'show', PIN + ':' + name])
    p = root / name
    require(p.is_file() and not p.is_symlink() and p.read_bytes() == raw,
            'frozen source differs: ' + name)
    return raw


def relocated_builder(raw, source_root, driver):
    """Only relocate script ROOT and the compiled diagnostic C++ translation unit."""
    text = raw.decode()
    old_root = 'ROOT=$(cd "$(dirname "$0")/../../.." && pwd);P="$ROOT/chisel/continuous_prefill"'
    old_driver = '"$P/tests/host_bf16_attention_core.cpp"'
    require(text.count(old_root) == text.count(old_driver) == 1, 'frozen build anchors changed')
    text = text.replace(old_root, 'ROOT=' + shlex.quote(str(source_root)) + ';P="$ROOT/chisel/continuous_prefill"', 1)
    text = text.replace(old_driver, shlex.quote(str(driver)), 1)
    require('OPT_FAST=-O2 OPT_SLOW=-O0' in text and '-ffp-contract=off -fno-fast-math' in text,
            'original strict floating-point/build policy missing')
    return text


def compiler_evidence(build):
    """Retain actual emitted compile policy and bounded-build stage durations."""
    groups = {}
    for path in sorted((build / 'bounded_build').glob('*.log')):
        for line in path.read_text(errors='replace').splitlines():
            if not re.search(r'(?:^|\s)(?:\S*/)?(?:g\+\+|c\+\+)(?:\s|$)', line) or ' -c ' not in line:
                continue
            argv = shlex.split(line)
            source = next((x for x in reversed(argv) if x.endswith('.cpp')), None)
            if source is None:
                continue
            flags = [x for x in argv if re.fullmatch(r'-O(?:[0123sgz]|fast)', x)]
            kind = 'profile_driver' if source.endswith('profile_driver.cpp') else 'generated_slow' if '__Slow.cpp' in source else 'other_cpp'
            key = (kind, tuple(flags), '-fno-fast-math' in argv, '-ffp-contract=off' in argv)
            groups[key] = groups.get(key, 0) + 1
    rows = [dict(kind=k[0], optimization_flags=list(k[1]), effective_optimization=k[1][-1] if k[1] else None,
                 no_fast_math=k[2], fp_contract_off=k[3], compile_commands=count)
            for k, count in sorted(groups.items())]
    require(any(r['kind'] == 'profile_driver' for r in rows), 'profile driver actual compile command absent')
    require(all(r['no_fast_math'] and r['fp_contract_off'] for r in rows), 'effective strict FP compile flags absent')
    return dict(commands=rows, bounded_build=json.loads((build/'bounded_build/result.json').read_text()))


def check_profiles(first, second, first_events_sha, second_events_sha):
    for p in (first, second):
        require(p.get('numerical_acceptance') is False and p.get('prefix_reached') is True,
                'prefix not reached or wrong acceptance claim')
        require(p.get('cycle_limit') == p.get('cycles') == CYCLES and p.get('eval_calls') == 3*CYCLES,
                'fixed cycle/eval inventory changed')
        require(type(p.get('eval_ns')) is int and p['eval_ns'] > 0 and
                p.get('step_elapsed_ns', -1) >= p['eval_ns'] and
                p.get('driver_excluding_eval_ns') == p['step_elapsed_ns']-p['eval_ns'], 'timing inventory')
        require(type(p.get('deterministic')) is dict and p['deterministic'], 'missing semantic prefix counters')
        counters = p['deterministic']
        terminal = counters.get('terminal_event', {})
        require(counters.get('ar_handshakes', 0) > 0 and counters.get('r_handshakes', 0) > 0 and
                terminal.get('end_issued_jobs', 0) > 0 and terminal.get('end_pipeline_issues', 0) > 0,
                'prefix did not reach actual Dense/Matrix and AXI progress')
        require(terminal.get('end_run') == 0 and terminal.get('end_pc') == 0 and
                terminal.get('end_reset_required') == 0, 'prefix no longer samples the original pc0 scope')
    require(first['deterministic'] == second['deterministic'] and first_events_sha == second_events_sha,
            'same-source deterministic prefix differs')


def arguments():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    return p.parse_args()


def imports(source):
    sys.path[:0] = [str(source/'chisel/continuous_prefill/scripts'), str(source/'src')]
    import run_host_bf16_attention_core_fresh_gate as frozen
    require(frozen.ROOT.resolve() == source, 'imported a different production checkout')
    return frozen


def checked_paths(args):
    require(args.source_root.is_absolute() and not args.source_root.is_symlink(), 'absolute nonsymlink source required')
    source = args.source_root.resolve()
    require(git(source, 'rev-parse', 'HEAD') == PIN, 'diagnostic requires exact failing source commit')
    require(args.output.is_absolute() and not args.output.is_symlink(), 'absolute fresh output required')
    out = args.output.resolve()
    require(out.is_relative_to(source/'work') and out != source/'work' and not out.exists(), 'fresh source/work output required')
    return source, out


def run_worker(args):
    source, out = checked_paths(args)
    frozen = imports(source)
    out.mkdir(parents=True)
    diagnostic_commit = git(DIAGNOSTIC_ROOT, 'rev-parse', 'HEAD')
    trigger_sha = os.environ.get('GITHUB_SHA')
    bound_environment = source_environment(os.environ, diagnostic_commit, git(source, 'rev-parse', 'HEAD'))
    # This is the separate source worker only; the supervising process and
    # GitHub workflow keep the real triggering SHA unchanged.
    os.environ['GITHUB_SHA'] = bound_environment['GITHUB_SHA']
    os.environ['ATTENTION_PROFILE_DIAGNOSTIC_SHA'] = diagnostic_commit
    started = time.monotonic()
    deadline = started+BUDGET_SECONDS
    summary = dict(status='RUNNING_BOUNDED_FULL_TOP_PROFILE', numerical_acceptance=False,
                   production_source_commit=PIN, diagnostic_source_commit=diagnostic_commit,
                   github_trigger_sha=trigger_sha, frozen_worker_github_sha=PIN,
                   original_failure_rtl_sha256=RTL_SHA256, functional_rtl_changed=False,
                   hierarchy_changed=False, source_profile='EmitHostBf16AttentionCore',
                   intended_cycles_per_prefix=CYCLES, prefix_timeout_seconds=PREFIX_SECONDS,
                   prefixes=[], stage='preflight', phase_seconds={}, full_command_chain_completed=False,
                   instrumentation_overhead_included=True, speedup_claimed=False,
                   artifact_upload_allowlist=['compact/summary.json', 'compact/source_input_hashes.json'])
    hashes = dict(source_sha256={}, diagnostic_source_sha256={}, instrumented_source_sha256={}, input_sha256={}, output_sha256={})
    from run_host_bf16_v_fresh_gate import _write_compact

    def checkpoint(stage):
        summary.update(stage=stage, elapsed_seconds=time.monotonic()-started,
                       remaining_budget_seconds=max(0, int(deadline-time.monotonic())))
        _write_compact(out, summary, hashes)

    def remaining(cap):
        left = int(deadline-time.monotonic()-120)
        require(left > 0, 'diagnostic budget exhausted')
        return min(cap, left)

    @contextlib.contextmanager
    def phase(name):
        checkpoint(name)
        begin = time.monotonic()
        try:
            yield
        finally:
            summary['phase_seconds'][name] = time.monotonic()-begin
            checkpoint(name)

    def run_to_log(argv, path, cap, env=None):
        with path.open('w') as log:
            subprocess.run(argv, cwd=source, env=env, stdout=log, stderr=subprocess.STDOUT,
                           check=True, timeout=remaining(cap))

    try:
        with frozen.total_budget(BUDGET_SECONDS-120):
            diag_files = sorted(p for p in HERE.iterdir() if p.is_file()) + [DIAGNOSTIC_ROOT/'.github/workflows/attention-top-profile.yml']
            for p in diag_files:
                name = str(p.relative_to(DIAGNOSTIC_ROOT))
                require(p.read_bytes() == subprocess.check_output(['git','-C',str(DIAGNOSTIC_ROOT),'show','HEAD:'+name]),
                        'uncommitted diagnostic source: '+name)
                hashes['diagnostic_source_sha256'][name] = sha(p)
            env = bound_environment
            require(env.get('BUILD_JOBS', '1') == '1', 'one compiler slot required')
            env['BUILD_JOBS'] = '1'
            summary['idma_preflight'] = frozen._preflight(env, out)
            with (out/'reference.log').open('w') as log, contextlib.redirect_stdout(log):
                with phase('fresh_original_capture'):
                    session = frozen.rebuild_session(out/'official_capture',source/'work/qwen35_layer0_payload',
                        source/'work/qwen35_layer3_payload',source/'work/qwen35_prefix_payload')
                    summary.update(session.evidence())
                    require(session.fresh and summary['fresh_official_executions'] == 2 and summary['reused_official_executions'] == 0,
                            'fresh source capture required')
                    summary['native_full_block_failures'] = frozen._native_failure_evidence(session)
                    hashes['official_capture_manifest_sha256'] = session.manifest_sha256
                with phase('original_projection_reference'):
                    projection = frozen.generate_projection_references(session,out/'projection_reference',variants=('baseline',),windows=frozen.WINDOWS)
                    pr = projection.verify(session=session)
                    require(pr['head_jobs'] == 24 and pr['matrix_accumulator_steps'] == 10485760 and pr['native_operator_gate_pass'], 'original projection gate')
                    hashes['projection_reference_receipt_sha256'] = projection.receipt_sha256
                with phase('original_norm_rope_reference'):
                    attention = frozen.generate_attention_references(session,projection,out/'attention_reference',variants=('baseline',))
                    ar = attention.verify(session=session,projection_reference_session=projection)
                    require(ar['original_operator_gate_pass'], 'original Norm/RoPE gate')
                    hashes['attention_reference_receipt_sha256'] = attention.receipt_sha256
                with phase('original_core_reference_and_fixture'):
                    core = frozen.generate_core_reference(session,projection,attention,out/'core_reference')
                    hashes['core_reference_receipt_sha256'] = core.receipt_sha256
                    authorities = dict(core_session=core, session=session, projection_session=projection, attention_session=attention)
                    fixture = out/'pair_fixture'
                    admitted = frozen.pack_fixture(fixture, **authorities)
                    require(admitted['live_authorities_verified'], 'live fixture admission')
                    hashes['input_sha256'] = admitted['input_sha256']
                    hashes['source_sha256'].update(admitted['source_sha256'])
                    frozen.verify_checkout(PIN, hashes['source_sha256'])
            instrumentation = out/'instrumentation'
            run_to_log([sys.executable,str(HERE/'generate_profile.py'),'--repo',str(source),'--output',str(instrumentation),'--cycles',str(CYCLES)],out/'instrumentation.log',30)
            raw = frozen_file(source,'chisel/continuous_prefill/scripts/run_host_bf16_attention_core_gate.sh')
            builder = out/'diagnostic_build.sh'
            builder.write_text(relocated_builder(raw,source,instrumentation/'profile_driver.cpp'))
            tracked = [builder]+sorted(p for p in instrumentation.rglob('*') if p.is_file())
            hashes['instrumented_source_sha256'] = {str(p.relative_to(out)):sha(p) for p in tracked}
            summary['instrumentation'] = json.loads((instrumentation/'transformation_receipt.json').read_text())
            summary['build_transformation'] = dict(original_script_sha256=hashlib.sha256(raw).hexdigest(),
                modified_script_sha256=sha(builder), replacements=['script ROOT relocation','diagnostic driver translation unit'],
                rtl_or_compile_flag_replacements=0)
            build = out/'host_build'
            with phase('unchanged_full_top_build'):
                run_to_log(['bash',str(builder),str(build),'0'],out/'build.log',BUILD_SECONDS,env)
            ready = json.loads((build/'build_ready.json').read_text())
            require(ready['rtl_sha256'] == RTL_SHA256 and ready['numerical_pass'] is False and
                    ready['source_base_commit'] == PIN and ready['status'] == frozen.BUILD_STATUS,
                    'generated RTL/source/build scope differs from original failed full top')
            summary['build'] = ready
            summary['compiler_evidence'] = compiler_evidence(build)
            hashes['source_sha256'].update(json.loads((build/'sources.sha256.json').read_text()))
            hashes.update(binary_sha256=sha(build/'obj/VHostBlockTop'), rtl_sha256=sha(build/'generated/HostBlockTop.sv'), build_ready_sha256=sha(build/'build_ready.json'))
            initial_identity = frozen.build_identity(build, admitted['source_sha256'])
            for index in range(2):
                require(frozen.admit_fixture(fixture,**authorities) == admitted, 'live fixture changed before profile')
                require(frozen.build_identity(build,admitted['source_sha256']) == initial_identity, 'build identity changed before profile')
                prefix = out/('prefix'+str(index))
                with phase('actual_bounded_prefix_'+str(index)):
                    run_to_log([str(build/'obj/VHostBlockTop'),str(fixture),str(prefix),'pass'],out/('prefix'+str(index)+'.log'),PREFIX_SECONDS)
                report = json.loads((prefix/'attention_profile.json').read_text())
                summary['prefixes'].append(report)
                hashes['output_sha256'][str(index)] = dict(profile_json=sha(prefix/'attention_profile.json'),
                    events=sha(prefix/'prefix_events.jsonl'), original_driver_log=sha(out/('prefix'+str(index)+'.log')))
                require(frozen.admit_fixture(fixture,**authorities) == admitted, 'live fixture changed after profile')
            check_profiles(*summary['prefixes'],hashes['output_sha256']['0']['events'],hashes['output_sha256']['1']['events'])
            require(hashes['output_sha256']['0']['original_driver_log'] == hashes['output_sha256']['1']['original_driver_log'], 'original deterministic visible event log differs')
            frozen.verify_all_build_sources(build,'profile_final_source_verify.log')
            require(frozen.build_identity(build,admitted['source_sha256']) == initial_identity, 'final build identity changed')
            require(all(sha(out/name) == digest for name,digest in hashes['instrumented_source_sha256'].items()), 'instrumented source changed')
            frozen.verify_checkout(PIN,hashes['source_sha256'])
            summary.update(status='COMPLETE_BOUNDED_FULL_TOP_PROFILE_NOT_NUMERICAL_ACCEPTANCE', deterministic_prefix_equal=True)
            checkpoint('complete')
            return 0
    except (Exception, KeyboardInterrupt) as error:
        summary.update(status='INCOMPLETE_BOUNDED_FULL_TOP_PROFILE', error=dict(type=type(error).__name__, message=str(error)))
        partials = []
        for p in sorted(out.glob('prefix*/attention_profile.json')):
            try:
                partials.append(json.loads(p.read_text()))
            except (OSError, ValueError):
                partials.append(dict(path=str(p.relative_to(out)), readable_complete_json=False))
        summary['partial_profiles'] = partials
        summary['diagnostic_log_tail'] = {str(p.relative_to(out)):p.read_text(errors='replace')[-4000:] for p in sorted(out.glob('*.log'))[-4:]}
        checkpoint(summary['stage'])
        return 1


def worker_entry():
    signal.pthread_sigmask(signal.SIG_UNBLOCK, (signal.SIGINT, signal.SIGTERM))
    raise SystemExit(run_worker(arguments()))


def finalize_supervision(out, outcome):
    """Keep an honest compact receipt even if a worker dies during JSON output."""
    require(not out.is_symlink(), 'supervisor output symlink')
    out.mkdir(parents=True, exist_ok=True)
    compact = out/'compact'
    require(not compact.is_symlink(), 'supervisor compact symlink')
    compact.mkdir(exist_ok=True)
    def read(name):
        p = compact/name
        require(not p.is_symlink(), 'supervisor receipt symlink')
        if not p.exists():
            return {}, False
        raw = p.read_bytes()
        try:
            value = json.loads(raw)
            require(type(value) is dict, 'worker receipt must be an object')
            return value, True
        except ValueError:
            preserved = out/('supervisor_previous_'+name+'.partial')
            require(not preserved.exists(), 'preserve earlier supervisor evidence')
            preserved.write_bytes(raw)
            return {'incomplete_worker_receipt_sha256':hashlib.sha256(raw).hexdigest()}, False
    summary, valid_summary = read('summary.json')
    hashes, valid_hashes = read('source_input_hashes.json')
    outcome = dict(outcome)
    if not valid_summary or not valid_hashes:
        outcome['returncode'] = 1
        outcome['missing_or_malformed_worker_receipt'] = True
    summary.update(supervisor=outcome, numerical_acceptance=False)
    summary.setdefault('production_source_commit', PIN)
    summary.setdefault('stage', 'supervised_worker_start')
    summary.setdefault('artifact_upload_allowlist', ['compact/summary.json','compact/source_input_hashes.json'])
    if outcome['returncode'] or outcome['forced_shutdown']:
        summary['status'] = 'INCOMPLETE_BOUNDED_FULL_TOP_PROFILE'
    for name, value in [('summary.json',summary),('source_input_hashes.json',hashes)]:
        temporary = compact/(name+'.tmp')
        temporary.write_text(json.dumps(value,sort_keys=True,indent=2)+'\n')
        temporary.replace(compact/name)
    (out/'summary.json').write_bytes((compact/'summary.json').read_bytes())
    return outcome['returncode']


def main():
    args = arguments()
    source, out = checked_paths(args)
    frozen = imports(source)
    entry = 'import sys;sys.path.insert(0,sys.argv.pop(1));from run_profile import worker_entry;worker_entry()'
    result = frozen.supervise_process([sys.executable,'-c',entry,str(HERE),'--source-root',str(source),'--output',str(out)], timeout_seconds=BUDGET_SECONDS)
    raise SystemExit(finalize_supervision(out, result))


if __name__ == '__main__':
    main()
