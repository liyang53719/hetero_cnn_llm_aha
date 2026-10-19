"""Single fresh PC0->ACK0->PC1->ACK1, using the already qualified ELF."""
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import stat
import sys
import time
import types

MIB = 1024**2
SHARED_SECONDS = 10620
TAIL_SECONDS = 120
CAPTURE_TOTAL = 10410
CAPTURE_WORK = 10395
CONFIG_PIN = (1561, 'c9341bcaf055c0f3bbc5b9d391b8657e6e86aa8b96f6d243cf94fd4c84145776')
RELINK_PIN = (19837, 'd80f19af41760b96f8a8a60d2a45faab21b2addea39bf5e805fe2a2a338e798d')
RELINK_RECEIPT_PIN = (16380, '64831215e25271d0ab4d882b2fea051f2b6ceacb5fe04e6af0f7f201e425f7e1')
ELF_PIN = {'bytes': 13537744, 'sha256': 'cb64b5cf1d5e9c226b9768fb3fdcbb3305bee894b6d904cb4cf29633d10fe5b1'}
MODEL_RECEIPT_PIN = (17596, 'c7367d084b11ecf6a895bd165dd5e3d51dfa3ddbfdb439dce24a4b183659e2e7')
MODEL_RESULT_PIN = (1249, 'ae61290bf5ba0d5ff2f21920c8913a15736c788e3093a06ff2c9e0ba89b586f6')
SPEC_PIN = (17884, 'ab1fabb72d69f0f196dafd19fe7324a1413b000952e0ee04baa3cbaaff4a14ac')
COMPARE_PIN = (15167, 'c8e8026838bc955364ae1c171e9775d7138acff20074fb168dfe3000b2fc4820')
REFERENCE_PINS = {
    'qraw.typed.f32le': {'bytes': 786432, 'sha256': '346b2974824f3e2849206d5ea72f7a066c328439c4faa088bf2a13d742b713f1'},
    'qraw.math.f32le': {'bytes': 786432, 'sha256': '42604d286bb7f237c4dc982b4a65065ea74edec82714a4e0f0ad07fcd6172851'},
    'qraw.math.f64le': {'bytes': 1572864, 'sha256': 'ef5d02aa4b9ad77afdb61eb2842786780d218978bc1dac4641068ec4856710e8'}}

METADATA_PINS = {'metadata/host_commands.bin': {'bytes': 384, 'sha256': '618cd4db94fbc5f0e3829182a72d5e298b5a42d2a3840ec2b9f9be639cd884c4'}, 'metadata/host_descriptors.bin': {'bytes': 3456, 'sha256': '1e4d35da18b21a4d9de05d2f3129e5bd9717cd923837c83c8d5eb320bfcddb02'}}

def need(ok, code='PC01_CAPTURE_CONTRACT'):
    if not ok:
        raise ValueError(code)


def identity(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def read(path, pin):
    p = Path(path)
    need(p.is_absolute() and '..' not in p.parts and p.resolve(strict=True) == p and
         not any(x.is_symlink() for x in (p, *p.parents)), 'SOURCE_CANONICAL')
    size, digest = pin
    need(type(size) is int and 0 <= size <= MIB, 'SOURCE_CAP')
    fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_size == size, 'SOURCE_SIZE')
        raw = bytearray()
        while len(raw) <= size:
            chunk = os.read(fd, min(65536, size + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
        raw = bytes(raw)
        stamp = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        need((len(raw), hashlib.sha256(raw).hexdigest()) == pin and
             stamp(before) == stamp(os.fstat(fd)) == stamp(p.stat(follow_symlinks=False)), 'SOURCE_HASH_OR_DRIFT')
        return raw
    finally:
        os.close(fd)


def module(path, pin, name):
    raw = read(path, pin)
    m = types.ModuleType(name)
    m.__file__ = str(path)
    exec(compile(raw, str(path), 'exec', dont_inherit=True), m.__dict__)
    return m



def supervisor_projection(path, pin):
    raw = read(path, pin)
    old, new = b'SHARED_SECONDS = 6600\n', b'SHARED_SECONDS = 10620\n'
    need(raw.count(old) == 1 and new not in raw, 'SUPERVISOR_BUDGET_ANCHOR')
    derived = raw.replace(old, new)
    need(derived.replace(new, old) == raw, 'SUPERVISOR_INVERSE')
    m = types.ModuleType('pc01_fixed_supervisor')
    m.__file__ = str(path)
    exec(compile(derived, str(path), 'exec', dont_inherit=True), m.__dict__)
    return m, {'original': identity(raw), 'derived': identity(derived),
               'only_change': 'SHARED_SECONDS_6600_TO_10620', 'inverse_exact': True}


def successful_record(stage):
    r, d, u = stage['record'], stage['diagnostics'], stage['usage']
    need(type(r['exit_code']) is int and r['exit_code'] == 0 and r['status'] == 'PASS' and
         r['cleanup_confirmed'] is True and r['timed_out'] is False and r['reaped'] is True and
         r['parent_exception'] is None and r['group_state'] == 'absent' and
         r['exit_observed_while_unreaped']['code'] == 1 and
         r['exit_observed_while_unreaped']['status'] == 0 and
         d['receipt_timed_out'] is False and d['waitid_code'] == 1 and d['waitid_status'] == 0 and
         d['cleanup_confirmed'] is True and d['exit_code'] == 0 and
         d['failure_boundary'] == 'NONE' and d['failure_code'] == 'NONE', 'NATURAL_EXIT_CLEANUP')
    need(type(u['maxrss_kib_cumulative_parent_children']) is int and
         0 <= u['maxrss_kib_cumulative_parent_children'] <= 6 * 1024**2, 'CUMULATIVE_RSS_6G')


def accept_relink(receipt, r, catalog, work, contract):
    need(receipt['schema'] == 1 and receipt['status'] == 'COMPLETE_DRIVER_COMPILE_LINK_ONLY' and
         receipt['scope'] == 'DRIVER_COMPILE_LINK_ONLY' and receipt['rtl_executed'] is False and
         receipt['pc01_executable_invoked'] is False and receipt['full_block_pass'] is False and
         receipt['shared_seconds_cap'] == 180 and receipt['cpu_affinity_count'] == 1 and
         receipt['binary']['identity'] == ELF_PIN and
         [x['name'] for x in receipt['stages']] == ['compile', 'link'], 'RELINK_RECEIPT_SCOPE')
    commands = r.commands(catalog, work, contract)
    for stage in receipt['stages']:
        successful_record(stage)
        need(stage['record']['argv'] == commands[stage['name']] and stage['record']['cwd'] == str(work),
             'RELINK_ACTUAL_ARGV')
    need(receipt['compiler_catalog_identity'] == dict(zip(('bytes', 'sha256'), r.CATALOG_PIN)) and
         receipt['reuse_identity'] == dict(zip(('bytes', 'sha256'), r.REUSE_PIN)), 'RELINK_INPUT_IDENTITY')


def accept_models(receipt):
    need(receipt['schema'] == 1 and receipt['status'] == 'COMPLETE_SUPERVISED_TWO_REFERENCE_MODELS' and
         receipt['full_models_executed'] is True and receipt['rtl_executed'] is False and
         receipt['old_ram_resumed'] is False and receipt['official_raw_numeric_pass'] is None and
         receipt['application_accuracy_pass'] is None and receipt['baseline_adopted'] is False and
         [x['name'] for x in receipt['stages']] == ['compile', 'micro', 'full_models'], 'MODEL_RECEIPT_SCOPE')
    for stage in receipt['stages']:
        successful_record(stage)
    need(receipt['outputs']['outputs'] == REFERENCE_PINS and receipt['outputs']['result_identity'] ==
         dict(zip(('bytes', 'sha256'), MODEL_RESULT_PIN)), 'MODEL_OUTPUT_IDENTITIES')


def input_pins(repo):
    spec = json.loads(read(repo / 'candidates/host93_first_n0_sources/inputs/CONVERSION_SPEC.json', SPEC_PIN))
    pins = {'providers/' + row['output_filename']: {'bytes': row['output_bytes'], 'sha256': row['expected_output_sha256']}
            for row in spec['providers']}
    pins.update(METADATA_PINS)
    need(len(spec['providers']) == 14 and len(pins) == 16 and sum(x['bytes'] for x in pins.values()) == 94920448,
         'CANONICAL16_COUNT')
    return pins


def check_inputs(g, root, pins):
    need(set(pins) == {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()} and
         all(not p.is_symlink() for p in root.rglob('*')), 'CANONICAL16_ENTRIES')
    for rel, pin in pins.items():
        g.checked(root / rel, pin, 32 * MIB, fixed_leaf=Path(rel).name)


def environment(catalog, work):
    libdirs = {str(Path(p).parent) for p in catalog['libraries'].values()}
    need(len(libdirs) == 1, 'FIXED_LIBRARY_DIRECTORY')
    return {'PATH': str(work / 'empty-path'), 'LD_LIBRARY_PATH': next(iter(libdirs)),
            'HOME': str(work / 'home'), 'TMPDIR': str(work / 'tmp'),
            'LC_ALL': 'C', 'LANG': 'C', 'TZ': 'UTC',
            'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1'}


def phase_limits():
    return {'total_seconds': CAPTURE_TOTAL, 'work_seconds': CAPTURE_WORK, 'cpu_seconds': CAPTURE_WORK,
            'as_bytes': 6 * 1024**3, 'fsize_bytes': 16 * MIB, 'tree_bytes': 64 * MIB,
            'log_bytes': MIB, 'sample_rows': CAPTURE_TOTAL + 2, 'file_count': 64, 'entry_count': 128}


def capture_sequence(s, support, base, work, argv, env, stop, owner, preflight, compare, result, admit):
    # Two full-window checks cover all read-only preflight time without resetting t0.
    need(time.monotonic() + CAPTURE_TOTAL <= stop - TAIL_SECONDS - 60, 'INCOMPLETE_CAPTURE_WINDOW')
    preflight()
    result['pre_native_admission'] = admit()
    need(time.monotonic() + CAPTURE_TOTAL <= stop - TAIL_SECONDS - 60, 'INCOMPLETE_CAPTURE_WINDOW')
    stage = {'name': 'fresh_pc0_through_ack1', 'record': None, 'usage': None, 'diagnostics': {}}
    try:
        record, raw, usage = s.run_phase(support, base, 'pc01_capture', argv, work,
            work / 'phases/capture', env, phase_limits(), stop, owner, stage['diagnostics'])
        stage['record'], stage['usage'] = record, usage
        successful_record(stage)
        need(record['argv'] == argv and record['cwd'] == str(work), 'CAPTURE_ACTUAL_ARGV')
    finally:
        result['stages'].append(stage)
    preflight()
    need(time.monotonic() < stop - TAIL_SECONDS, 'INCOMPLETE_COMPARISON_WINDOW')
    observation = compare(stop - TAIL_SECONDS)
    result['comparison'] = observation
    need(observation['status'] == 'COMPLETE_DATA_OBSERVATION_ONLY' and
         observation['typed_reference']['bit_exact'] is True and
         observation['typed_reference']['hash_exact'] is True and
         observation['typed_reference']['mismatch_values'] == 0, 'TYPED_REFERENCE_MISMATCH')
    preflight()
    return observation


def save_tail(h, work, result, failure, stop):
    # Evidence gets at most 120 seconds and never extends the one overall timer.
    report_stop = min(stop, time.monotonic() + TAIL_SECONDS)
    result['report_deadline_monotonic'] = report_stop
    try:
        need(time.monotonic() < report_stop, 'INCOMPLETE_EVIDENCE_WINDOW')
        signal.setitimer(signal.ITIMER_REAL, max(0.001, report_stop - time.monotonic()))
        failure = h.save_preserving_failure(work, result, failure)
    except BaseException as error:
        if failure is None:
            failure = error
    return failure


def run(config_path, execute=False, *, started=None, source_pin=None):
    need(execute and sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode,
         'EXPLICIT_CAPTURE_AND_ISOLATION_REQUIRED')
    need(type(started) is float and 0 <= time.monotonic() - started < 30, 'ENTRY_T0_REQUIRED')
    stop = started + SHARED_SECONDS
    need(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0) and
         signal.SIGALRM not in signal.pthread_sigmask(signal.SIG_BLOCK, []), 'TIMER_OWNERSHIP')
    old_alarm = signal.getsignal(signal.SIGALRM)
    def expired(*unused):
        raise TimeoutError('PC01_CAPTURE_SHARED_DEADLINE')
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, max(0.001, stop - time.monotonic()))
    owner = {'handler': expired, 'deadline': stop}
    result = {'schema': 1, 'status': 'INCOMPLETE', 'scope': 'FRESH_PC0_THROUGH_ACK1_ONLY',
              'stages': [], 'old_process_resumed': False, 'offline_n0_loaded': False,
              'full_block_pass': False, 'baseline_adopted': False,
              'official_raw_numeric_pass': None, 'application_accuracy_pass': None,
              'started_monotonic': started, 'deadline_monotonic': stop,
              'shared_seconds_cap': SHARED_SECONDS, 'tail_reserved_seconds': TAIL_SECONDS,
              'global_main_cycle_cap': 8000000, 'pc1_useful_macs': 301989888, 'fixed_mac_lanes': 4096,
              'independent_prior_relink_cap_seconds': 180, 'combined_authorized_ceiling_seconds': 10800,
              'inter_step_wait_in_native_wall': False}
    failure, work, h = None, None, None
    try:
        for kind, limit in ((resource.RLIMIT_AS, 6 * 1024**3), (resource.RLIMIT_CPU, SHARED_SECONDS),
                            (resource.RLIMIT_FSIZE, 16 * MIB)):
            _, hard = resource.getrlimit(kind)
            need(hard == resource.RLIM_INFINITY or hard >= limit, 'INHERITED_HARD_LIMIT')
            resource.setrlimit(kind, (limit, limit))
        allowed = os.sched_getaffinity(0)
        need(bool(allowed), 'CPU_AFFINITY')
        os.sched_setaffinity(0, {min(allowed)})
        own = read(Path(__file__).resolve(), source_pin)
        config_raw = read(config_path, CONFIG_PIN)
        cfg = json.loads(config_raw)
        need(set(cfg) == {'schema', 'relink_source', 'relink_config', 'inputs', 'reference_root',
                         'model_execution_receipt', 'comparison_source', 'work', 'review_evidence'} and
             cfg['schema'] == 'PC01_CAPTURE_PRIVATE_BINDING_V1', 'FIXED_CONFIG')
        relink_source = Path(cfg['relink_source'])
        r = module(relink_source / 'run_relink.py', RELINK_PIN, 'fixed_relink_readonly_helpers')
        relink_cfg_raw = read(Path(cfg['relink_config']), r.CONFIG_PIN)
        rc = json.loads(relink_cfg_raw)
        repo, source, bdir, prior = Path(rc['repo']), Path(rc['source']), Path(rc['binding_source']), Path(rc['work'])
        h = r.module(repo / 'candidates/host93_first_n0_sources/pc1_reference_execution/run_reference.py', r.HELPER_PIN, 'fixed_evidence_helpers')
        g = h.module(repo / 'candidates/host93_first_n0_sources/local_dependency_bootstrap/bootstrap.py', h.PINS['bootstrap.py'], 'capture_bootstrap')
        o = h.module(bdir / 'binding_observer.py', h.PINS['binding_observer.py'], 'capture_observer')
        l = h.module(bdir / 'local_mount_profile.py', h.PINS['local_mount_profile.py'], 'capture_mount')
        s, result['supervisor_projection'] = supervisor_projection(repo / 'candidates/host93_ci_recovery/ci_support_v3.py', h.PINS['ci_support_v3.py'])
        d = r.module(relink_source / 'dependency_gate.py', r.GATE_PIN, 'capture_dependencies')
        c = module(Path(cfg['comparison_source']) / 'compare.py', COMPARE_PIN, 'capture_three_reference_comparison')
        support, base, support_pins = s.fixed_support(repo)
        binding_raw = g.checked(Path(rc['binding']['path']), rc['binding']['identity'])
        binding = g.binding(binding_raw, rc['binding']['identity'], repo)
        profile = g.decode(g.checked(Path(rc['profile']['path']), rc['profile']['identity']))
        catalog_raw = r.read(Path(rc['dependencies']), r.CATALOG_PIN)
        catalog = json.loads(catalog_raw)
        need(len(catalog['files']) == 39 and catalog['programs']['g++'] == binding['system_programs']['/usr/bin/g++']['path'], 'FIXED_DEPENDENCIES')
        need(str(Path(sys.executable).resolve(strict=True)) == binding['system_programs']['/usr/bin/python3']['path'], 'FIXED_INTERPRETER')
        l.validate(g, o, binding, profile)
        baseline = d.verify(g, o, l, repo, catalog)
        reuse_raw = r.read(Path(rc['reuse_binding']), r.REUSE_PIN)
        reuse = json.loads(reuse_raw)
        buffers = r.input_buffers(g, repo, source, reuse)
        contract_raw = r.read(source / 'RELINK_CONTRACT.json', r.COMMAND_PIN)
        contract = json.loads(contract_raw)
        relink_raw = read(prior / 'EXECUTION_RESULT.json', RELINK_RECEIPT_PIN)
        relink = json.loads(relink_raw)
        accept_relink(relink, r, catalog, prior, contract)
        need(relink['staged_files'] == {rel: identity(raw) for rel, raw in buffers.items()}, 'RELINK_STAGED_IDENTITIES')
        model_raw = read(Path(cfg['model_execution_receipt']), MODEL_RECEIPT_PIN)
        accept_models(json.loads(model_raw))
        refs = g.clean(cfg['reference_root'])
        reference_result = read(refs / 'RESULT.json', MODEL_RESULT_PIN)
        inputs = g.clean(cfg['inputs'])
        pins = input_pins(repo)
        target = g.clean(cfg['work'])
        excluded = (repo, source, bdir, prior, refs, inputs, relink_source, Path(cfg['comparison_source']), g.clean(reuse['old_work_readonly']))
        need(not target.exists() and all(not target.is_relative_to(p) and not p.is_relative_to(target) for p in excluded), 'FRESH_DISJOINT_WORK')
        reviews = {}
        need(len(cfg['review_evidence']) == 3, 'FIXED_REVIEW_COUNT')
        for row in cfg['review_evidence']:
            reviews[row['path']] = read(Path(row['path']), (row['bytes'], row['sha256']))
        result['admission'] = r.resource_gate(target.parent)
        support.fresh_directory(target)
        work = target
        for name in ('home', 'tmp', 'phases', 'empty-path'):
            support.fresh_directory(work / name)
        env = environment(catalog, work)
        argv = [str(prior / 'pc01'), str(inputs), str(work / 'capture')]
        binary_expected = relink['binary']
        def preflight():
            need(time.monotonic() < stop - TAIL_SECONDS, 'INCOMPLETE_WORK_WINDOW')
            need(read(Path(__file__).resolve(), source_pin) == own and read(config_path, CONFIG_PIN) == config_raw, 'CALLER_OR_CONFIG_CHANGED')
            need(read(Path(cfg['relink_config']), r.CONFIG_PIN) == relink_cfg_raw, 'RELINK_CONFIG_CHANGED')
            read(relink_source / 'run_relink.py', RELINK_PIN)
            read(relink_source / 'dependency_gate.py', r.GATE_PIN)
            read(Path(cfg['comparison_source']) / 'compare.py', COMPARE_PIN)
            read(repo / 'candidates/host93_first_n0_sources/pc1_reference_execution/run_reference.py', r.HELPER_PIN)
            for path, pin in ((repo / 'candidates/host93_first_n0_sources/local_dependency_bootstrap/bootstrap.py', h.PINS['bootstrap.py']),
                              (bdir / 'binding_observer.py', h.PINS['binding_observer.py']),
                              (bdir / 'local_mount_profile.py', h.PINS['local_mount_profile.py']),
                              (repo / 'candidates/host93_ci_recovery/ci_support_v3.py', h.PINS['ci_support_v3.py'])):
                read(path, pin)
            for name, raw in reviews.items():
                need(read(Path(name), (len(raw), hashlib.sha256(raw).hexdigest())) == raw, 'REVIEW_CHANGED')
            need(r.read(Path(rc['dependencies']), r.CATALOG_PIN) == catalog_raw and
                 r.read(Path(rc['reuse_binding']), r.REUSE_PIN) == reuse_raw and
                 r.read(source / 'RELINK_CONTRACT.json', r.COMMAND_PIN) == contract_raw, 'RELINK_INPUT_CHANGED')
            need(g.checked(Path(rc['binding']['path']), rc['binding']['identity']) == binding_raw and
                 g.decode(g.checked(Path(rc['profile']['path']), rc['profile']['identity'])) == profile, 'PROFILE_CHANGED')
            l.validate(g, o, binding, profile)
            need(d.verify(g, o, l, repo, catalog) == baseline, 'DEPENDENCY_CHANGED')
            need(r.input_buffers(g, repo, source, reuse) == buffers, 'SOURCE_OR_CACHE_CHANGED')
            r.verify_copies(g, prior, buffers)
            g.checked(prior / 'pc01_main.o', relink['object'], 16 * MIB, fixed_leaf='pc01_main.o')
            need(d.check_binary(g, repo, catalog, prior / 'pc01') == binary_expected, 'QUALIFIED_ELF_CHANGED')
            need(read(prior / 'EXECUTION_RESULT.json', RELINK_RECEIPT_PIN) == relink_raw and
                 read(Path(cfg['model_execution_receipt']), MODEL_RECEIPT_PIN) == model_raw and
                 read(refs / 'RESULT.json', MODEL_RESULT_PIN) == reference_result, 'ACTUAL_RECEIPT_CHANGED')
            for name, pin in REFERENCE_PINS.items():
                g.checked(refs / name, pin, 2 * MIB, fixed_leaf=name)
            need(input_pins(repo) == pins, 'CANONICAL_SPEC_CHANGED')
            check_inputs(g, inputs, pins)
            need(environment(catalog, work) == env and list((work / 'empty-path').iterdir()) == [], 'ENV_CHANGED')
            need(argv == [str(prior / 'pc01'), str(inputs), str(work / 'capture')], 'ARGV_CHANGED')
        def compare(deadline):
            return c.compare(work / 'capture', refs, refs / 'RESULT.json', shared_stop=deadline)
        preflight()
        result['pre_native_admission'] = r.resource_gate(work)
        need(time.monotonic() <= started + 30, 'INCOMPLETE_INITIAL_WINDOW')
        capture_sequence(s, support, base, work, argv, env, stop, owner, preflight, compare, result, lambda: r.resource_gate(work))
        result.update(status='COMPLETE_SUPERVISED_PC01_TYPED_MATCH_AND_MATH_DIAGNOSTICS',
                      seconds=time.monotonic() - started, qualified_binary=binary_expected,
                      prior_relink_receipt_identity=identity(relink_raw), model_receipt_identity=identity(model_raw),
                      input_identities=pins, cpu_affinity_count=1, fresh_reset_native_runs=1,
                      typed_recipe_bit_exact_to_rtl=True, whole_block_utilization=None)
    except BaseException as error:
        failure = error
        result['failure_type'] = type(error).__name__
        result['failure_code'] = safe_failure_code(error)
    finally:
        if h is not None:
            failure = save_tail(h, work, result, failure, stop)
            failure = h.restore_preserving_failure(old_alarm, failure)
        else:
            for fn, args in ((signal.setitimer, (signal.ITIMER_REAL, 0)), (signal.signal, (signal.SIGALRM, old_alarm))):
                try:
                    fn(*args)
                except BaseException as error:
                    if failure is None:
                        failure = error
    if failure is not None:
        raise failure
    return result


SAFE_FAILURE_CODES = ('ACTUAL_RECEIPT_CHANGED', 'ARGV_CHANGED', 'CALLER_OR_CONFIG_CHANGED', 'CANONICAL16_COUNT', 'CANONICAL16_ENTRIES', 'CANONICAL_SPEC_CHANGED', 'CAPTURE_ACTUAL_ARGV', 'CPU_AFFINITY', 'CUMULATIVE_RSS_6G', 'DEPENDENCY_CHANGED', 'ENTRY_T0_REQUIRED', 'ENV_CHANGED', 'EXPLICIT_CAPTURE_AND_ISOLATION_REQUIRED', 'FIXED_CONFIG', 'FIXED_DEPENDENCIES', 'FIXED_INTERPRETER', 'FIXED_LIBRARY_DIRECTORY', 'FIXED_REVIEW_COUNT', 'FRESH_DISJOINT_WORK', 'INCOMPLETE_CAPTURE_WINDOW', 'INCOMPLETE_COMPARISON_WINDOW', 'INCOMPLETE_EVIDENCE_WINDOW', 'INCOMPLETE_INITIAL_WINDOW', 'INCOMPLETE_WORK_WINDOW', 'INHERITED_HARD_LIMIT', 'MODEL_OUTPUT_IDENTITIES', 'MODEL_RECEIPT_SCOPE', 'NATURAL_EXIT_CLEANUP', 'NETWORK_FORBIDDEN', 'PC01_CAPTURE_SHARED_DEADLINE', 'PROFILE_CHANGED', 'QUALIFIED_ELF_CHANGED', 'RELINK_ACTUAL_ARGV', 'RELINK_CONFIG_CHANGED', 'RELINK_INPUT_CHANGED', 'RELINK_INPUT_IDENTITY', 'RELINK_RECEIPT_SCOPE', 'RELINK_STAGED_IDENTITIES', 'REVIEW_CHANGED', 'SOURCE_CANONICAL', 'SOURCE_CAP', 'SOURCE_HASH_OR_DRIFT', 'SOURCE_OR_CACHE_CHANGED', 'SOURCE_SIZE', 'SUPERVISOR_BUDGET_ANCHOR', 'SUPERVISOR_INVERSE', 'TIMER_OWNERSHIP', 'TYPED_REFERENCE_MISMATCH')

def safe_failure_code(error):
    return str(error) if type(error) in (ValueError, TimeoutError, RuntimeError) and str(error) in SAFE_FAILURE_CODES else None


def main(argv=None, *, started=None, source_pin=None):
    import argparse
    p = argparse.ArgumentParser(allow_abbrev=False)
    p.add_argument('--private-config', required=True, type=Path)
    p.add_argument('--execute-reviewed-capture', action='store_true')
    args = p.parse_args(argv)
    def audit(event, unused):
        if event.startswith('socket.') or event == 'urllib.Request':
            raise RuntimeError('NETWORK_FORBIDDEN')
    sys.addaudithook(audit)
    result = run(args.private_config, args.execute_reviewed_capture, started=started, source_pin=source_pin)
    print(json.dumps({'status': result['status'], 'phases': len(result['stages']), 'full_block_pass': False}))
