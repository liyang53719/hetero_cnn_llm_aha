"""Exactly three supervised native phases; no action on import."""
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import sys
import time
import types

CONFIG_PIN = (2633, '4187aaa36b89a2acd1a6bfb355ec48cc29afe9942d645885fe6e2aa2eb446985')
DEPENDENCY_PIN = (17181, 'eb96b59bacab297190a7cf84157f26612d91d8e8c85b333707122a037a32a18d')
GATE_PIN = (5104, '57207b29c56024c2288afe9faffbc81bd2bd921868dc44badc428fd03673554c')
MODEL_PREPARE_PIN = (8378, '3a52a7ec16680ea6b9e0553563ab51d1415ae0f703cb1916abbe0748bd495167')
PINS = {
    'bootstrap.py': (25509, 'c2a7ca58d8fba3df8b76071e25ad740386ab5113a59897181b39b4d303e50ea8'),
    'binding_observer.py': (11781, '62a7f5b4f9250f66e5c62ed9d8b6a486642e135e5e934fc505ae2dfadc850904'),
    'local_mount_profile.py': (7087, 'cdbe1030e3bf2a9b2222836f7f594b4800c4315dfb31a4438a8b76c07cd18c8f'),
    'ci_support_v3.py': (16348, '653de8cdfbdbb5ffe9b3725467ee0f44c98da353e1d680fec4f282d2b73d00d1'),
}
SHARED_SECONDS = 210
TAIL_SECONDS = 25
FLAGS = ('-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror', '-ffp-contract=off',
         '-fno-fast-math', '-frounding-math')


def need(ok, code='PC1_EXECUTION_CONTRACT'):
    if not ok:
        raise ValueError(code)


def read(path, pin):
    # The unchanged bootstrap reader is not yet available at the first load.
    p = Path(path)
    need(p.is_absolute() and '..' not in p.parts and p.resolve(strict=True) == p,
         'SOURCE_CANONICAL')
    need(not any(x.is_symlink() for x in (p, *p.parents)) and p.is_file(), 'SOURCE_REGULAR')
    size, digest = pin
    need(type(size) is int and 0 <= size <= 1024**2 and p.stat().st_size == size, 'SOURCE_SIZE')
    data = p.read_bytes()
    need(len(data) == size and hashlib.sha256(data).hexdigest() == digest, 'SOURCE_HASH')
    return data


def module(path, pin, name):
    raw = read(path, pin)
    m = types.ModuleType(name)
    m.__file__ = str(path)
    exec(compile(raw, str(path), 'exec', dont_inherit=True), m.__dict__)
    return m


def phase_limits(name):
    total, work, cpu = {'compile': (45, 30, 30), 'micro': (20, 5, 3), 'full_models': (120, 105, 100)}[name]
    return {'total_seconds': total, 'work_seconds': work, 'cpu_seconds': cpu,
            'as_bytes': 512 * 1024**2, 'fsize_bytes': 16 * 1024**2,
            'tree_bytes': 32 * 1024**2, 'log_bytes': 65536,
            'sample_rows': total + 2, 'file_count': 32, 'entry_count': 64}


def compiler_argv(catalog, search, model):
    return [catalog['programs']['g++'], '-B', str(search) + '/', *FLAGS,
            str(model / 'source/pc1_reference_main.cpp'), '-o', str(model / 'pc1_reference'), '-lm']


def check_prior(g, cfg):
    raws = {}
    for name, row in cfg['prior_receipts'].items():
        raws[name] = g.checked(Path(row['path']), row['identity'], 1024**2)
    prior = g.decode(raws['accepted_run'])
    n = prior['n0_observation']
    c, r = n['capture'], n['comparison']
    need(prior['status'] == 'PASS_FIRST_N0_LIMITED_TOLERANCE_ONLY' and
         prior['full_block_pass'] is False and c['status'] == 'ACK0_ACTUAL_CAPTURED' and
         c['committed_bytes'] == 786432 and c['completion_acks'] == 1 and
         c['successful_b'] == 12288 and c['actual_values'] == 196608 and
         r['bit_exact'] is True and r['hash_exact'] is True and r['numeric_pass'] is True and
         r['actual_sha256'] == '3c25077e0b7aa5819df6fb93cbaba6a0d5379ac06b9df468beecd0f259b5cc3f',
         'PRIOR_N0_SCOPE')
    need(g.decode(raws['capture']) == c and g.decode(raws['comparison']) == r, 'PRIOR_RECEIPT_BINDING')
    return {k: g.pin(v) for k, v in raws.items()}


def write_result(path, value):
    raw = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    need(len(raw) <= 1024**2 and not path.exists(), 'FINAL_RECEIPT_SIZE_OR_EXISTS')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        written = 0
        while written < len(raw):
            n = os.write(fd, raw[written:])
            need(n > 0, 'FINAL_RECEIPT_WRITE')
            written += n
        os.fsync(fd)
    finally:
        os.close(fd)


def save_preserving_failure(work, result, failure):
    if work is not None:
        try:
            write_result(work / 'EXECUTION_RESULT.json', result)
        except BaseException as receipt_error:
            if failure is None:
                failure = receipt_error
    return failure


def restore_preserving_failure(old_alarm, failure):
    for action, args in ((signal.setitimer, (signal.ITIMER_REAL, 0)),
                         (signal.signal, (signal.SIGALRM, old_alarm))):
        try:
            action(*args)
        except BaseException as restore_error:
            if failure is None:
                failure = restore_error
    return failure


def supervised_sequence(supervisor, support, base, catalog, model, search, work, env,
                        stop, owner, preflight, binary_check, stages, result):
    binary = None
    for name in ('compile', 'micro', 'full_models'):
        limits = phase_limits(name)
        need(time.monotonic() + limits['total_seconds'] <= stop - TAIL_SECONDS, 'INCOMPLETE_PHASE_WINDOW')
        preflight()
        if name != 'compile':
            observed = binary_check()
            need(observed == binary, 'BINARY_CHANGED')
        argv = compiler_argv(catalog, search, model) if name == 'compile' else (
            [str(model / 'pc1_reference'), '--micro'] if name == 'micro' else
            [str(model / 'pc1_reference'), '--full', str(model / 'inputs'), str(model / 'outputs')])
        need(time.monotonic() + limits['total_seconds'] <= stop - TAIL_SECONDS, 'INCOMPLETE_PHASE_WINDOW')
        stage = {'name': name, 'record': None, 'usage': None, 'diagnostics': {}}
        if name == 'full_models':
            result['full_models_executed'] = None  # Requested; failure may leave extent unknown.
        try:
            record, raw, usage = supervisor.run_phase(
                support, base, 'pc1_reference_' + name, argv, model,
                work / 'phases' / name, env, limits, stop, owner, stage['diagnostics'])
            stage['record'], stage['usage'] = record, usage
            need(type(record['exit_code']) is int and record['exit_code'] == 0 and
                 record['cleanup_confirmed'] is True, 'PHASE_EXIT_OR_CLEANUP')
            need(type(usage['maxrss_kib_cumulative_parent_children']) is int and
                 usage['maxrss_kib_cumulative_parent_children'] <= 393216, 'SAMPLED_USAGE_RSS_GATE')
            if name == 'compile':
                binary = binary_check()
                result['binary'] = binary
            elif name == 'micro':
                need(json.loads(raw) == {'status': 'PASS_NATIVE_MICRO', 'full_arrays_read': False,
                                        'official_raw_numeric_pass': None}, 'NATIVE_MICRO_RESULT')
            else:
                result['full_models_executed'] = True
                need(json.loads(raw) == {'status': 'COMPLETE_TWO_MODEL_DIAGNOSTIC', 'elements': 196608},
                     'FULL_MODEL_RESULT')
        finally:
            stages.append(stage)
        preflight()
        if name != 'compile':
            need(binary_check() == binary, 'BINARY_CHANGED_POSTFLIGHT')
    return binary


def run(config_path, execute=False):
    need(execute and sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode,
         'REQUIRE_EXPLICIT_EXECUTION_AND_ISOLATION')
    need(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0) and
         signal.SIGALRM not in signal.pthread_sigmask(signal.SIG_BLOCK, []), 'TIMER_OWNERSHIP')
    started = time.monotonic()
    stop = started + SHARED_SECONDS
    old_alarm = signal.getsignal(signal.SIGALRM)
    def expired(*unused):
        raise TimeoutError('PC1_SHARED_DEADLINE')
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, SHARED_SECONDS)
    owner = {'handler': expired, 'deadline': stop}
    result = {'schema': 1, 'status': 'INCOMPLETE', 'official_raw_numeric_pass': None,
              'application_accuracy_pass': None, 'rtl_executed': False, 'stages': [],
              'full_models_executed': False, 'baseline_adopted': False}
    failure, work = None, None
    try:
        for kind, limit in ((resource.RLIMIT_AS, 512 * 1024**2),
                            (resource.RLIMIT_CPU, 210), (resource.RLIMIT_FSIZE, 16 * 1024**2)):
            _, hard = resource.getrlimit(kind)
            need(hard == resource.RLIM_INFINITY or hard >= limit, 'INHERITED_HARD_LIMIT')
            resource.setrlimit(kind, (limit, limit))
        allowed = os.sched_getaffinity(0)
        need(bool(allowed), 'CPU_AFFINITY')
        os.sched_setaffinity(0, {min(allowed)})
        cfg_raw = read(config_path, CONFIG_PIN)
        cfg = json.loads(cfg_raw)
        repo = Path(cfg['repo'])
        g = module(repo / 'candidates/host93_first_n0_sources/local_dependency_bootstrap/bootstrap.py', PINS['bootstrap.py'], 'pc1_bootstrap')
        bdir = Path(cfg['binding_source'])
        o = module(bdir / 'binding_observer.py', PINS['binding_observer.py'], 'pc1_observer')
        l = module(bdir / 'local_mount_profile.py', PINS['local_mount_profile.py'], 'pc1_mount')
        source = Path(cfg['model_source'])
        p = module(source / 'prepare_reference.py', MODEL_PREPARE_PIN, 'pc1_models')
        d = module(Path(__file__).resolve().parent / 'dependency_gate.py', GATE_PIN, 'pc1_dependencies')
        s = module(repo / 'candidates/host93_ci_recovery/ci_support_v3.py', PINS['ci_support_v3.py'], 'pc1_supervisor')
        support, base, support_pins = s.fixed_support(repo)
        binding_raw = g.checked(Path(cfg['binding']['path']), cfg['binding']['identity'])
        binding = g.binding(binding_raw, cfg['binding']['identity'], repo)
        profile = g.decode(g.checked(Path(cfg['profile']['path']), cfg['profile']['identity']))
        catalog = g.decode(g.checked(Path(cfg['dependencies']), {'bytes': DEPENDENCY_PIN[0], 'sha256': DEPENDENCY_PIN[1]}))
        need(catalog['programs']['g++'] == binding['system_programs']['/usr/bin/g++']['path'], 'ORIGINAL_COMPILER_BINDING')
        for key in ('bytes', 'sha256', 'mode'):
            need(catalog['files'][catalog['programs']['g++']][key] == binding['system_programs']['/usr/bin/g++'][key], 'ORIGINAL_COMPILER_IDENTITY')
        l.validate(g, o, binding, profile)
        baseline = d.verify(g, o, l, repo, catalog)
        prior = check_prior(g, cfg)
        result['prior_receipt_identities'] = prior
        result['compiler_dependency_catalog'] = {'bytes': DEPENDENCY_PIN[0], 'sha256': DEPENDENCY_PIN[1]}
        target = g.clean(cfg['work'])
        need(not target.exists() and not target.is_relative_to(repo) and not repo.is_relative_to(target), 'FRESH_PRIVATE_WORK')
        support.fresh_directory(target)
        work = target
        for name in ('home', 'tmp', 'phases', 'compiler-search'):
            support.fresh_directory(work / name)
        model = work / 'model'
        prepared = p.prepare(repo, source, cfg['independent_n0'], cfg['accepted_n0'], cfg['wq'], model)
        result['prepared'] = prepared
        search = work / 'compiler-search'
        for name in ('cc1plus', 'collect2', 'as', 'ld'):
            (search / name).symlink_to(catalog['programs'][name])
        libdirs = {str(Path(x).parent) for x in catalog['libraries'].values()}
        need(len(libdirs) == 1, 'FIXED_LIBRARY_DIRECTORY')
        env = {'PATH': str(search), 'LD_LIBRARY_PATH': next(iter(libdirs)), 'HOME': str(work/'home'),
               'TMPDIR': str(work/'tmp'), 'LC_ALL': 'C', 'LANG': 'C', 'TZ': 'UTC'}
        def preflight():
            need(time.monotonic() < stop - TAIL_SECONDS, 'INCOMPLETE_TAIL_RESERVE')
            need(read(config_path, CONFIG_PIN) == cfg_raw, 'CONFIG_CHANGED')
            read(source / 'prepare_reference.py', MODEL_PREPARE_PIN)
            read(Path(__file__).resolve().parent / 'dependency_gate.py', GATE_PIN)
            need(d.verify(g, o, l, repo, catalog) == baseline, 'DEPENDENCY_CHANGED')
            l.validate(g, o, binding, profile)
            need(check_prior(g, cfg) == prior, 'PRIOR_CHANGED')
            local, originals = p.verify_repository(repo, source)
            need({k: p.identity(v) for k, v in originals.items()} == prepared['repository_identities'], 'MODEL_SOURCE_CHANGED')
            for name in p.NATIVE_FILES:
                need((model/'source'/name).read_bytes() == local[name], 'COMPILE_BUFFER_CHANGED')
            need(sorted(x.name for x in search.iterdir()) == ['as', 'cc1plus', 'collect2', 'ld'], 'SEARCH_ENTRIES')
            for name in ('cc1plus', 'collect2', 'as', 'ld'):
                need((search/name).is_symlink() and str((search/name).resolve(strict=True)) == catalog['programs'][name], 'SEARCH_TARGET')
        binary_check = lambda: d.check_binary(g, repo, catalog, model/'pc1_reference')
        supervised_sequence(s, support, base, catalog, model, search, work, env, stop, owner,
                            preflight, binary_check, result['stages'], result)
        need(time.monotonic() < stop - TAIL_SECONDS, 'INCOMPLETE_POSTFLIGHT_WINDOW')
        result['outputs'] = p.verify_complete_outputs(model/'outputs')
        for name, path in (('independent_n0', cfg['independent_n0']), ('accepted_n0_identity_only', cfg['accepted_n0']), ('wq', cfg['wq'])):
            p.fixed_bytes(path, p.INPUTS[name])
        preflight()
        result.update(status='COMPLETE_SUPERVISED_TWO_REFERENCE_MODELS', full_models_executed=True,
                      seconds=time.monotonic()-started, shared_seconds_cap=SHARED_SECONDS,
                      tail_reserved_seconds=TAIL_SECONDS, cpu_affinity_count=1,
                      accepted_n0_used_as_reference=False, old_ram_resumed=False)
    except BaseException as error:
        failure = error
        result['failure_type'] = type(error).__name__
    finally:
        # A receipt failure cannot replace the original native/preflight failure.
        failure = save_preserving_failure(work, result, failure)
        failure = restore_preserving_failure(old_alarm, failure)
    if failure is not None:
        raise failure
    return result


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--private-config', type=Path, required=True)
    parser.add_argument('--execute-reviewed-models', action='store_true')
    args = parser.parse_args(argv)
    def audit(event, unused):
        if event.startswith('socket.') or event == 'urllib.Request':
            raise RuntimeError('NETWORK_FORBIDDEN')
    sys.addaudithook(audit)
    result = run(args.private_config, args.execute_reviewed_models)
    print(json.dumps({'status': result['status'], 'phases': len(result['stages']), 'official_raw_numeric_pass': None}))
