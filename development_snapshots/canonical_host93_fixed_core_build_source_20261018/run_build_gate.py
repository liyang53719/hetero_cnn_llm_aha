"""Three fixed Verilator core phases. Candidate actual bindings are PENDING."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import stat
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
PLAN_BYTES = 160737
PLAN_SHA = 'cd489d6530321fa95b79fc1d0e82d5599d358a1cb882165e44805dcafb98bd42'
PHASES = ('autoconf', 'configure', 'optimized_backend')
FUNCTIONS = ('require', 'save', 'group_state', 'observe_exit', 'bounded')
OBSERVERS = ('proc_bytes', 'proc_stat', 'sample_leader', 'usage')
DEADLINE_PHASE = 'unarmed'


def require(ok, why):
    if not ok:
        raise ValueError(why)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def safe_path(value):
    path = Path(value)
    require(path.is_absolute() and '..' not in path.parts, 'fixed absolute path required')
    return path


def directory_fd(path):
    path = safe_path(path)
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parts[1:]:
            newer = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = newer
        return fd
    except BaseException:
        os.close(fd)
        raise


def stamp(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def regular_fd(path):
    path = safe_path(path)
    parent = directory_fd(path.parent)
    try:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
        try:
            info = os.fstat(fd)
            require(stat.S_ISREG(info.st_mode), 'regular file required')
            require(stamp(info) == stamp(os.stat(path.name, dir_fd=parent, follow_symlinks=False)),
                    'opened file identity mismatch')
            return parent, fd, info
        except BaseException:
            os.close(fd)
            raise
    except BaseException:
        os.close(parent)
        raise


def checked_read(path, size, expected):
    require(type(size) is int and 0 <= size <= 4 * 1024 * 1024, 'small fixed read bound')
    parent, fd, before = regular_fd(path)
    try:
        require(before.st_size == size, 'fixed input size')
        data = bytearray()
        while len(data) <= size:
            part = os.read(fd, min(65536, size + 1 - len(data)))
            if not part:
                break
            data.extend(part)
        raw = bytes(data)
        require(len(raw) == size and sha(raw) == expected, 'fixed input SHA')
        require(stamp(os.fstat(fd)) == stamp(before) ==
                stamp(os.stat(Path(path).name, dir_fd=parent, follow_symlinks=False)),
                'input changed during read')
        return raw
    finally:
        os.close(fd)
        os.close(parent)


def fixed(pin):
    return checked_read(pin['path'], pin['bytes'], pin['sha256'])


def load_plan():
    return json.loads(checked_read(HERE / 'GATE_PLAN.json', PLAN_BYTES, PLAN_SHA))


def identity(path, cap, git=False):
    parent, fd, before = regular_fd(path)
    try:
        size = before.st_size
        require(0 <= size <= cap, 'file identity byte cap')
        digest = hashlib.sha256()
        blob = hashlib.sha1(b'blob ' + str(size).encode('ascii') + b'\0') if git else None
        count = 0
        while True:
            part = os.read(fd, min(65536, size - count + 1))
            if not part:
                break
            count += len(part)
            require(count <= size, 'file grew during hash')
            digest.update(part)
            if blob is not None:
                blob.update(part)
        require(count == size and stamp(os.fstat(fd)) == stamp(before) ==
                stamp(os.stat(Path(path).name, dir_fd=parent, follow_symlinks=False)),
                'file changed during hash')
        result = {'bytes': count, 'sha256': digest.hexdigest(), 'mode': oct(stat.S_IMODE(before.st_mode))}
        if blob is not None:
            result['git_blob'] = blob.hexdigest()
        return result
    finally:
        os.close(fd)
        os.close(parent)


def relative_name(value):
    require(type(value) is str and value and not value.startswith('/'), 'relative member path')
    parts = value.split('/')
    require(all(x not in ('', '.', '..') for x in parts), 'safe member components')
    return parts


def copy_member(source, root, relative, pin, mode):
    require(mode in (0o600, 0o700), 'fixed copy mode')
    parts = relative_name(relative)
    raw = checked_read(source, pin['bytes'], pin['sha256'])
    fd = directory_fd(root)
    try:
        for part in parts[:-1]:
            try:
                os.mkdir(part, 0o700, dir_fd=fd)
            except FileExistsError:
                pass
            newer = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            require(stat.S_IMODE(os.fstat(newer).st_mode) == 0o700, 'copy directory mode')
            os.close(fd)
            fd = newer
        target = os.open(parts[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=fd)
        try:
            count = 0
            while count < len(raw):
                amount = os.write(target, raw[count:])
                require(amount > 0, 'short output write')
                count += amount
            os.fchmod(target, mode)
        finally:
            os.close(target)
    finally:
        os.close(fd)
    found = identity(Path(root) / relative, pin['bytes'])
    require(found == {'bytes': pin['bytes'], 'sha256': pin['sha256'], 'mode': oct(mode)},
            'copied file readback')


def tree_inventory(root, byte_cap, file_cap=4096, entry_cap=8192, single_cap=1024**3):
    root = safe_path(root)
    fd = directory_fd(root)
    try:
        require(stat.S_IMODE(os.fstat(fd).st_mode) == 0o700, 'private tree root mode')
    finally:
        os.close(fd)
    entries = {}
    stack = [root]
    total = 0
    files = 0
    while stack:
        folder = stack.pop()
        with os.scandir(folder) as scan:
            for entry in scan:
                require(len(entries) < entry_cap, 'tree entry cap')
                path = Path(entry.path)
                rel = path.relative_to(root).as_posix()
                info = entry.stat(follow_symlinks=False)
                require(not entry.is_symlink(), 'tree symlink refused')
                if stat.S_ISDIR(info.st_mode):
                    require(stat.S_IMODE(info.st_mode) == 0o700, 'private tree directory mode')
                    entries[rel] = {'kind': 'directory', 'mode': '0o700'}
                    stack.append(path)
                else:
                    require(stat.S_ISREG(info.st_mode), 'tree special file refused')
                    files += 1
                    require(files <= file_cap, 'tree regular-file cap')
                    total += info.st_size
                    require(total <= byte_cap, 'tree aggregate acceptance byte cap')
                    entries[rel] = dict(kind='regular', **identity(path, single_cap))
    return {'root': str(root), 'files': files, 'bytes': total,
            'entries': dict(sorted(entries.items()))}


def review_shape(binding, label):
    require(type(binding) is dict, label + ' actual PENDING')
    require(set(binding) == {'manifest', 'summary', 'summary_claims'}, 'fixed review binding shape')
    claims = binding['summary_claims']
    exit_key = 'original_outer_exit' if label == 'stage' else 'outer_exit'
    require(type(claims) is dict and type(claims.get(exit_key)) is int and claims[exit_key] == 0 and
            type(claims.get('verdict')) is str and claims['verdict'].startswith('PASS_'),
            label + ' terminal actual acceptance claims')
    for pin in (binding['manifest'], binding['summary']):
        require(type(pin) is dict and set(pin) == {'path', 'bytes', 'sha256'}, 'review file pin shape')
        require(type(pin['bytes']) is int and 0 < pin['bytes'] <= 4 * 1024 * 1024,
                label + ' fixed review size PENDING')
        require(type(pin['sha256']) is str and len(pin['sha256']) == 64 and
                all(c in '0123456789abcdef' for c in pin['sha256']), label + ' fixed review SHA PENDING')
        safe_path(pin['path'])


def validate_bindings(plan, phase):
    require(phase in PHASES, 'three fixed phases only')
    for label in ('stage', 'versions', 'tiny'):
        review_shape(plan['required_actual'][label], label)
    require(type(plan['stage_report']) is dict, 'stage report actual PENDING')
    require(plan['stage_report'].get('path') == str(Path(plan['dependency_stage_root']) / 'STAGING_REPORT.json'),
            'fixed accepted stage report path')
    if phase != 'autoconf':
        previous = 'autoconf' if phase == 'configure' else 'configure'
        binding = plan['previous_actual'][previous]
        require(type(binding) is dict and set(binding) == {'review', 'inventory', 'result'},
                previous + ' previous generated actual identity PENDING')
        review_shape(binding['review'], previous)
        for name in ('inventory', 'result'):
            require(type(binding[name]) is dict and set(binding[name]) == {'path', 'bytes', 'sha256'},
                    previous + ' generated identity pin PENDING')
            expected = 'BUILD_TREE.json' if name == 'inventory' else 'RESULT.json'
            require(binding[name]['path'] == str(Path(plan['phases'][previous]['evidence_root']) / expected),
                    'fixed previous generated evidence path')


def manifest_member(manifest, summary_pin):
    names = manifest.get('files')
    if type(names) is dict:
        row = names.get('SUMMARY.json')
    elif type(names) is list:
        found = [r for r in names if r.get('path') == 'SUMMARY.json']
        require(len(found) == 1, 'unique manifest summary member')
        row = found[0]
    else:
        raise ValueError('review manifest member shape')
    require(type(row) is dict and row.get('bytes') == summary_pin['bytes'] and
            row.get('sha256') == summary_pin['sha256'], 'review summary manifest binding')


def verify_review(binding):
    manifest = json.loads(fixed(binding['manifest']))
    summary = json.loads(fixed(binding['summary']))
    manifest_member(manifest, binding['summary'])
    require(all(summary.get(k) == v for k, v in binding['summary_claims'].items()),
            'exact reviewed acceptance claims')
    return summary


def verify_reviews(plan, phase):
    q = plan['source_qualification']
    source_summary = verify_review(dict(manifest=q['manifest'], summary=q['summary'],
                                      summary_claims={'verdict': q['verdict'], 'outer_exit': 0}))
    require(source_summary['selected_count'] == 473 and source_summary['selected_bytes'] == 11747893
            and source_summary['original_acquisition_fail_preserved'] is True,
            'qualified473 scope and original FAIL retained')
    for label in ('stage', 'versions', 'tiny'):
        verify_review(plan['required_actual'][label])
    fixed(plan['stage_report'])
    if phase != 'autoconf':
        previous = 'autoconf' if phase == 'configure' else 'configure'
        binding = plan['previous_actual'][previous]
        summary = verify_review(binding['review'])
        previous_result = json.loads(fixed(binding['result']))
        require(summary.get('build_tree_inventory_sha256') == binding['inventory']['sha256'],
                'previous actual review binds generated tree inventory')
        require(previous_result.get('phase') == previous and
                previous_result.get('status') == 'BUILD_PHASE_EVIDENCE_PENDING_PARENT_ACCEPTANCE' and
                previous_result.get('terminal_success') is False and
                previous_result.get('cleanup_confirmed') is True and
                previous_result.get('build_tree_inventory_sha256') == binding['inventory']['sha256'],
                'previous phase nonterminal receipt/accepted inventory binding')
        old = json.loads(fixed(binding['inventory']))
        current = tree_inventory(plan['build_root'], plan['phases'][previous]['tree_bytes'])
        require(current == old, 'previous accepted generated tree drift')


def verify_payload(plan, include_copy):
    originals = Path(plan['source_root'])
    wanted = set()
    for row in plan['source_members']:
        relative_name(row['path'])
        wanted.add(row['path'])
        actual = identity(originals / row['path'], row['bytes'], git=True)
        require(actual == {k: row[k] for k in ('bytes', 'sha256', 'git_blob')} |
                {'mode': row['actual_mode']}, 'original473 identity/mode drift')
        if include_copy:
            actual = identity(Path(plan['build_root']) / 'verilator' / row['path'], row['bytes'], git=True)
            require(actual == {k: row[k] for k in ('bytes', 'sha256', 'git_blob')} |
                    {'mode': '0o700' if row['git_mode'] == '100755' else '0o600'}, 'copy473 identity/mode drift')
    original_tree = tree_inventory(originals, 11747893, 473, 1024, 4*1024**2)
    require({k for k, v in original_tree['entries'].items() if v['kind'] == 'regular'} == wanted,
            'exact original473 path set')
    stage = Path(plan['dependency_stage_root'])
    expected_stage = {'STAGING_REPORT.json'}
    for row in plan['dependency_members']:
        expected_stage.add(Path(row['source']).relative_to(stage).as_posix())
        actual = identity(row['source'], row['bytes'])
        require(actual == {'bytes': row['bytes'], 'sha256': row['sha256'], 'mode': '0o600'},
                'original dependency identity/mode drift')
        if include_copy:
            actual = identity(Path(plan['build_root']) / row['destination_relative_to_fresh_build_root'], row['bytes'])
            require(actual == {'bytes': row['bytes'], 'sha256': row['sha256'], 'mode': row['copy_mode']},
                    'copied dependency identity/mode drift')
    stage_tree = tree_inventory(stage, 8*1024**2, 69, 256, 4*1024**2)
    require({k for k, v in stage_tree['entries'].items() if v['kind'] == 'regular'} == expected_stage,
            'exact accepted stage69 path set')
    fixed(plan['stage_report'])


def fresh_directory(path):
    path = safe_path(path)
    fd = directory_fd(path.parent)
    try:
        os.mkdir(path.name, 0o700, dir_fd=fd)
    finally:
        os.close(fd)


def materialize(plan):
    root = Path(plan['build_root'])
    fresh_directory(root)
    for name in ('verilator', 'tools', 'home', 'tmp'):
        fresh_directory(root / name)
    for row in plan['source_members']:
        copy_member(Path(plan['source_root']) / row['path'], root / 'verilator', row['path'], row,
                    0o700 if row['git_mode'] == '100755' else 0o600)
    for row in plan['dependency_members']:
        rel = row['destination_relative_to_fresh_build_root']
        copy_member(row['source'], root, rel, row, int(row['copy_mode'], 8))


def pristine_config(plan, phase):
    root = Path(plan['build_root'])
    for rel in ('home/.autom4te.cfg', 'verilator/.autom4te.cfg', 'verilator/aclocal.m4', 'verilator/.git'):
        require(not os.path.lexists(root / rel), 'unreviewed user/project configuration')
    if phase == 'configure':
        for folder in plan['environment']['PATH'].split(':'):
            require(not os.path.lexists(Path(folder) / 'ccache'), 'unreviewed configure ccache discovery')
    require(plan['environment']['CONFIG_SITE'] == '/dev/null', 'fixed empty CONFIG_SITE')


def project_functions(raw, pin, wanted):
    require(len(raw) == pin['bytes'] and sha(raw) == pin['sha256'], 'raw source before AST projection')
    lines = raw.splitlines(keepends=True)
    selected = {}
    for node in ast.parse(raw).body:
        if isinstance(node, ast.FunctionDef) and node.name in wanted:
            require(node.name not in selected, 'duplicate projected function')
            fragment = b''.join(lines[node.lineno-1:node.end_lineno])
            expected = pin['functions'][node.name]
            require(len(fragment) == expected['bytes'] and sha(fragment) == expected['sha256'],
                    'original function raw identity')
            selected[node.name] = fragment
    require(tuple(selected) == wanted, 'exact original function order')
    return selected


def replacement(raw, edits):
    after = raw
    for old, new in edits:
        require(after.count(old) == 1, 'single exact projection anchor')
        after = after.replace(old, new, 1)
    reverse = after
    for old, new in reversed(edits):
        require(reverse.count(new) == 1, 'single inverse projection anchor')
        reverse = reverse.replace(new, old, 1)
    require(reverse == raw, 'exact projection reverse')
    return after


def projected_sources(plan, phase):
    cfg = plan['phases'][phase]
    sup_pin = plan['published_sources']['supervisor']
    obs_pin = plan['published_sources']['observation']
    sup = project_functions(fixed(sup_pin), sup_pin, FUNCTIONS)
    obs = project_functions(fixed(obs_pin), obs_pin, OBSERVERS)
    sup['bounded'] = replacement(sup['bounded'], [
        (b'(4 * 1024 * 1024, 4 * 1024 * 1024)', ('('+str(cfg['fsize_bytes'])+', '+str(cfg['fsize_bytes'])+')').encode()),
        (b'        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))',
         b'        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))\n        allowed = os.sched_getaffinity(0)\n        require(bool(allowed), "empty inherited CPU affinity")\n        os.sched_setaffinity(0, {min(allowed)})'),
        (b"env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'}", b'env=BUILD_ENV'),
        (b'        finally:\n            if child is not None:', b'        finally:\n            signal.setitimer(signal.ITIMER_REAL, 0)\n            if child is not None:'),
        (b"if record['log_bytes'] > 65536:", ("if record['log_bytes'] > "+str(cfg['log_bytes'])+':').encode()),
        (b'isinstance(error, subprocess.TimeoutExpired)', b'isinstance(error, (subprocess.TimeoutExpired, TimeoutError))')])
    anchor = b'        if event is not None:\n'
    sup['observe_exit'] = replacement(sup['observe_exit'], [(anchor,
        b"        require(event is None or event.si_pid == child.pid, 'sample WNOWAIT anchor mismatch')\n        sample_leader(child)\n"+anchor)])
    obs['sample_leader'] = replacement(obs['sample_leader'], [
        (b"state['count']<340", ("state['count']<"+str(cfg['sample_rows'])).encode())])
    return (b'\n\n'.join(sup[n] for n in FUNCTIONS)+b'\n',
            b'\n\n'.join(obs[n] for n in OBSERVERS)+b'\n')


def make_runner(plan, phase, evidence):
    sup, obs = projected_sources(plan, phase)
    cfg = plan['phases'][phase]
    namespace = {'__builtins__': __builtins__, 'os': os, 'resource': resource,
                 'signal': signal, 'subprocess': subprocess, 'time': time, 'json': json,
                 'AS_LIMIT': cfg['as_bytes'], 'BUILD_ENV': dict(plan['environment']), 'require': require}
    exec(compile(obs, 'fixed_four_observer_projection', 'exec', dont_inherit=True), namespace)
    sample = namespace['sample_leader']
    state = {'path': evidence / 'leader_samples.jsonl', 'identity': None,
             'count': 0, 'next': None, 'start': None}
    namespace['sample_leader'] = lambda child: sample(child, state)
    exec(compile(sup, 'fixed_five_WNOWAIT_projection', 'exec', dont_inherit=True), namespace)
    namespace['projection_hashes'] = {'supervisor': sha(sup), 'observation': sha(obs)}
    return namespace


def arm(deadline, label):
    global DEADLINE_PHASE
    DEADLINE_PHASE = label
    remaining = deadline - time.monotonic()
    require(remaining > 0, 'fixed phase deadline exhausted')
    signal.setitimer(signal.ITIMER_REAL, remaining)


def expired(_signal, _frame):
    raise TimeoutError(DEADLINE_PHASE + ' deadline')


def evidence_shape(evidence, success, sample_required):
    wanted = {'INPUTS.json', 'CHILD_USAGE.json', 'native.json', 'native.log'}
    if sample_required:
        wanted.add('leader_samples.jsonl')
    if success:
        wanted |= {'BUILD_TREE.json', 'RESULT.json'}
    else:
        wanted.add('FAILURE.json')
    files = {p.name for p in evidence.iterdir()}
    require(files == wanted, 'exact phase evidence file set')


def execute(phase, entry):
    require(sys.platform == 'linux', 'Linux WNOWAIT/RUSAGE units required')
    require(signal.SIGALRM not in signal.pthread_sigmask(signal.SIG_BLOCK, []), 'blocked alarm refused')
    require(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), 'existing timer refused')
    require(phase in PHASES, 'three fixed phases only')
    stop = entry + (3600 if phase == 'optimized_backend' else 180)
    pre_stop = entry + 10
    evidence = None
    previous = signal.signal(signal.SIGALRM, expired)
    old_umask = os.umask(0o077)
    created = False
    runner = None
    try:
        arm(pre_stop, phase + '_preflight')
        plan = load_plan()
        validate_bindings(plan, phase)  # PENDING rejects before source/copy/native/output activity.
        cfg = plan['phases'][phase]
        require(cfg['total_seconds'] == (3600 if phase == 'optimized_backend' else 180) and cfg['preflight_seconds'] == 10, 'fixed total/preflight bounds')
        evidence = Path(cfg['evidence_root'])
        verify_own_sources(plan)
        verify_reviews(plan, phase)
        verify_payload(plan, phase != 'autoconf')
        runner = make_runner(plan, phase, evidence)
        before = runner['usage']()
        require(before['user_cpu_seconds'] == 0 and before['system_cpu_seconds'] == 0 and
                before['maxrss_kib'] == 0, 'dedicated process already has child usage')
        require(not os.path.lexists(evidence), 'fresh phase evidence required')
        if phase == 'autoconf':
            require(not os.path.lexists(plan['build_root']), 'fresh build root required')
        fresh_directory(evidence)
        created = True
        if phase == 'autoconf':
            materialize(plan)
        verify_payload(plan, True)
        pristine_config(plan, phase)
        runner['save'](evidence / 'INPUTS.json', {
            'status': 'PREPARED_NOT_EXECUTED', 'phase': phase, 'plan_sha256': PLAN_SHA,
            'argv': cfg['argv'], 'cwd': cfg['cwd'], 'environment': plan['environment'],
            'limits': cfg, 'projection_sha256': runner['projection_hashes'],
            'source_qualification_manifest_sha256': plan['source_qualification']['manifest']['sha256'],
            'scope': 'three-stage fixed core build only; no backend execution or Host93'})
        require(time.monotonic() < pre_stop, 'preflight10s exhausted')
        work_stop = min(entry + cfg['work_latest_offset_seconds'], time.monotonic() + cfg['work_max_seconds'])
        arm(work_stop, phase + '_work')
        failure = None
        record = None
        try:
            record, _ = runner['bounded']('native', cfg['argv'], Path(cfg['cwd']), evidence,
                                           work_stop - time.monotonic(), cfg['cpu_seconds'])
        except BaseException as error:
            failure = error
        # bounded has finished its anchored cleanup before cumulative child usage is sampled.
        after = runner['usage']()
        arm(stop, phase + '_postflight')
        runner['save'](evidence / 'CHILD_USAGE.json', {
            'status': 'OBSERVATION_NOT_BUILD_PASS', 'before': before, 'after': after,
            'failure_type': None if failure is None else type(failure).__name__,
            'maxrss_is_cumulative_peak_not_difference': True, 'linux_maxrss_unit': 'KiB',
            'scope': 'RUSAGE_CHILDREN of this dedicated Python phase process after bounded cleanup attempt; inspect native.json cleanup_confirmed; not a sampled subtree peak',
            'leader_scope': 'one original PID/starttime only; commonly make, not its compiler descendants',
            'cleanup_receipt': 'native.json'})
        if failure is not None:
            raise failure
        require(record['cleanup_confirmed'] is True, 'terminal child-group cleanup required')
        verify_payload(plan, True)
        verify_reviews_stable(plan, phase)
        verify_own_sources(plan)
        pristine_config(plan, phase)
        tree = tree_inventory(plan['build_root'], cfg['tree_bytes'], cfg['file_count'],
                              cfg['entry_count'], cfg['fsize_bytes'])
        for name in cfg['required_outputs']:
            row = tree['entries'].get(name)
            require(row is not None and row['kind'] == 'regular' and row['bytes'] > 0,
                    'required generated output absent/empty')
        require(identity(evidence / 'native.log', cfg['log_bytes'])['bytes'] <= cfg['log_bytes'],
                'phase log acceptance cap')
        samples = identity(evidence / 'leader_samples.jsonl', cfg['sample_rows'] * 2048)
        require(samples['bytes'] > 0, 'leader sample evidence missing')
        runner['save'](evidence / 'BUILD_TREE.json', tree)
        inv_pin = identity(evidence / 'BUILD_TREE.json', 4*1024**2)
        result = {'status': 'BUILD_PHASE_EVIDENCE_PENDING_PARENT_ACCEPTANCE', 'terminal_success': False,
                  'phase': phase, 'cleanup_confirmed': True, 'native_exit': record['exit_code'],
                  'build_tree_inventory_sha256': inv_pin['sha256'],
                  'entry_to_postflight_seconds': time.monotonic()-entry,
                  'argv': cfg['argv'], 'required_output_identity': {x: tree['entries'][x] for x in cfg['required_outputs']},
                  'backend_executed': False, 'host93_executed': False,
                  'correctness_or_performance_qualified': False,
                  'acceptance_requires': 'separate observed outer exit0/elapsed and independent exact-phase actual review'}
        runner['save'](evidence / 'RESULT.json', result)
        evidence_shape(evidence, True, True)
        require(time.monotonic() < stop, 'final receipt deadline')
        return result
    except BaseException as error:
        if created and runner is not None:
            try:
                arm(stop, phase + '_failure_record')
                runner['save'](evidence / 'FAILURE.json', {'status': 'FAILED_BUILD_PHASE',
                    'phase': phase, 'error_type': type(error).__name__, 'message': str(error),
                    'terminal_success': False})
            except BaseException:
                pass
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
        os.umask(old_umask)


def verify_own_sources(plan):
    require(type(globals().get('__verified_runner_pin__')) is dict, 'pinned loader identity missing')
    fixed(__verified_runner_pin__)
    checked_read(HERE / 'GATE_PLAN.json', PLAN_BYTES, PLAN_SHA)
    fixed(plan['base_plan'])
    for pin in plan['published_sources'].values():
        fixed(pin)


def verify_reviews_stable(plan, phase):
    # Previous generated tree legitimately changes in this phase. Rehash its immutable
    # acceptance records, not that now-modified tree, after execution.
    q = plan['source_qualification']
    fixed(q['manifest'])
    fixed(q['summary'])
    for binding in plan['required_actual'].values():
        verify_review(binding)
    fixed(plan['stage_report'])
    if phase != 'autoconf':
        previous = 'autoconf' if phase == 'configure' else 'configure'
        binding = plan['previous_actual'][previous]
        verify_review(binding['review'])
        fixed(binding['inventory'])
        fixed(binding['result'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=PHASES, required=True)
    parser.add_argument('--execute-reviewed', action='store_true')
    args = parser.parse_args()
    entry = globals().get('__entry_monotonic__', time.monotonic())
    if args.execute_reviewed:
        result = execute(args.phase, entry)
    else:
        plan = load_plan()
        sup, obs = projected_sources(plan, args.phase)
        result = {'status': 'SOURCE_ONLY_NO_NATIVE_OR_COPY', 'phase': args.phase,
                  'required_actual': 'PENDING', 'supervisor_projection_sha256': sha(sup),
                  'observation_projection_sha256': sha(obs)}
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    require(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode,
            'use pinned loader under python -I -S -B')
    raise SystemExit('Use the separately pinned load_build_gate.py entrypoint; no direct unverified load.')
