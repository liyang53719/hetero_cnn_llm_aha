"""Three bounded phases: dependency discovery, compile/link, software diagnostic."""
import hashlib
import json
import os
import re
from pathlib import Path
import signal
import stat
import threading
import time
import types

def need(ok, reason):
    if not ok:
        raise ValueError(reason)

def stamp(s):
    return (s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns)

def checked(path, pin, keep=False):
    path = Path(path)
    need(path.is_absolute() and '..' not in path.parts, 'absolute fixed input')
    resolved = str(path.resolve(strict=True))
    need(resolved == pin.get('resolved', str(path)), 'input resolved identity')
    before = path.stat()
    need(stat.S_ISREG(before.st_mode) and before.st_size == pin['bytes'], 'input regular size')
    need(not keep or before.st_size <= 2 * 1024**2, 'small source buffer')
    h, chunks, count = hashlib.sha256(), [], 0
    with path.open('rb') as f:
        need(stamp(before) == stamp(os.fstat(f.fileno())), 'opened input identity')
        while True:
            b = f.read(min(1024**2, pin['bytes'] + 1 - count))
            if not b:
                break
            count += len(b)
            need(count <= pin['bytes'], 'input grew')
            h.update(b)
            if keep:
                chunks.append(b)
        need(stamp(before) == stamp(os.fstat(f.fileno())), 'FD changed during read')
    need(stamp(before) == stamp(path.stat()) and str(path.resolve()) == resolved, 'path changed during read')
    need(count == pin['bytes'] and h.hexdigest() == pin['sha256'], 'input digest')
    return b''.join(chunks) if keep else {'bytes': count, 'sha256': h.hexdigest(), 'stamp': stamp(before)}

def dump(path, value):
    raw = (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()
    need(len(raw) <= 2 * 1024**2, 'small receipt cap')
    with Path(path).open('xb') as f:
        f.write(raw)

def inventory(root, hashes=False):
    total, logs, files = 0, 0, {}
    for n, p in enumerate(root.rglob('*'), 1):
        need(n <= 8192, 'owned entry cap')
        try:
            s = p.lstat()
        except FileNotFoundError:
            need(not hashes, 'terminal file disappeared')
            continue  # A concurrent JVM temporary may have been removed.
        need(not stat.S_ISLNK(s.st_mode), 'owned symlink rejected')
        if stat.S_ISDIR(s.st_mode):
            continue
        need(stat.S_ISREG(s.st_mode) and s.st_nlink == 1, 'owned regular exclusive file')
        need(len(files) < 4096 and s.st_size <= 2 * 1024**2, 'owned file cap')
        rel = p.relative_to(root).as_posix()
        need(p.suffix.lower() not in {'.v', '.sv', '.fir', '.mlir', '.class'}, 'no RTL/JVM artifacts')
        total += s.st_size
        logs += s.st_size if p.suffix == '.log' else 0
        row = {'bytes': s.st_size}
        if hashes:
            h = hashlib.sha256()
            with p.open('rb') as f:
                need(stamp(s) == stamp(os.fstat(f.fileno())), 'owned open identity')
                while b := f.read(65536):
                    h.update(b)
                need(stamp(s) == stamp(os.fstat(f.fileno())), 'owned FD drift')
            need(stamp(s) == stamp(p.lstat()), 'owned path drift')
            row['sha256'] = h.hexdigest()
        files[rel] = row
    return {'bytes': total, 'log_bytes': logs, 'files': files}

def descendant_rss(parent):
    rows = {}
    for n, p in enumerate(Path('/proc').glob('[0-9]*/status'), 1):
        need(n <= 65536, 'bounded process scan')
        try:
            raw = p.read_bytes()
            need(len(raw) <= 65536, 'proc status cap')
            vals = dict(x.split(':', 1) for x in raw.decode().splitlines() if ':' in x)
            rows[int(p.parent.name)] = (int(vals['PPid']), int(vals.get('VmRSS', '0 kB').split()[0]) * 1024)
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
    owned = {parent}
    for _ in range(len(rows) + 1):
        new = {pid for pid, (ppid, _) in rows.items() if ppid in owned}
        if new.issubset(owned):
            break
        owned |= new
    return sum(rows[p][1] for p in owned if p != parent and p in rows)

def natural(record):
    need(record['status'] == 'PASS' and record['exit_code'] == 0 and
         not record['timed_out'] and record['parent_exception'] is None and
         record['anchor_confirmed'] and record['reaped'] and record['cleanup_confirmed'] and
         record['group_state'] == 'absent' and
         record['exit_observed_while_unreaped']['code'] == 1 and
         record['exit_observed_while_unreaped']['status'] == 0,
         'natural phase exit and anchored cleanup')

def terminal_bytes(path, maximum):
    before = path.lstat()
    need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size <= maximum,
         'bounded terminal file')
    with path.open('rb') as f:
        need(stamp(before) == stamp(os.fstat(f.fileno())), 'terminal open identity')
        raw = f.read(maximum + 1)
        need(stamp(before) == stamp(os.fstat(f.fileno())) == stamp(path.lstat()), 'terminal drift')
    need(len(raw) == before.st_size, 'terminal size')
    return raw

def verify_inputs(plan):
    need(len(plan['sources']) == 2 and len(plan['compile_flags']) == 7, 'two complete TUs and original seven flags')
    for p in plan['absent_paths']:
        need(not os.path.lexists(p), 'unexpected compiler/preload/PCH override')
    for p, link in plan['fixed_symlinks'].items():
        need(Path(p).is_symlink() and os.readlink(p) == link['target'] and
             str(Path(p).resolve()) == link['canonical_path'], 'fixed tool/header alias')
    need(not list(Path('/usr/local/include').iterdir()), 'no local include shadow')
    return {p: checked(p, pin) for p, pin in plan['inputs'].items()}


def dependency_rules(raw, plan):
    # GCC -M emits one default basename.o rule per input TU. No make execution.
    text = raw.decode('utf-8').replace('\\\n', ' ')
    rules = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        need(line.count(':') == 1 and '\\' not in line and '$' not in line, 'simple absolute fixed dependency syntax')
        target, body = line.split(':')
        target = target.strip()
        need(target in plan['dependency_targets'] and target not in rules, 'exact two distinct TU targets')
        paths = body.split()
        need(paths and len(paths) <= 4096 and len(paths) == len(set(paths)), 'bounded dependency members')
        need(plan['dependency_targets'][target] in paths, 'correct TU in dependency rule')
        for name in paths:
            need(Path(name).is_absolute() and name in plan['header_or_source_inputs'], 'dependency pre-pinned before scan')
            checked(name, plan['inputs'][name])
        rules[target] = paths
    need(set(rules) == set(plan['dependency_targets']), 'both TU dependency closures')
    return {'rules': rules, 'unique_dependencies': len(set(x for v in rules.values() for x in v)),
            'qualification': 'preprocessor dependency observation only; no numerical execution'}


def main(plan, start, stop, work_stop, deadline_handler):
    work = Path(plan['work'])
    need(plan['schema'] == 'uf-native-diagnostic-bound-v1', 'plan schema')
    expected_flags = ['-std=c++17', '-O2', '-shared', '-fPIC', '-fno-fast-math', '-ffp-contract=off', '-frounding-math']
    need(plan['compile_flags'] == expected_flags, 'unchanged arithmetic flags')
    need(plan['dependency_argv'] == [plan['compiler']] + expected_flags + ['-M'] + plan['sources'], 'fixed dependency only entry')
    need(plan['compile_argv'] == [plan['compiler']] + expected_flags + plan['sources'] +
         ['-o', str(work / 'libuf_diagnostic.so')], 'fixed compile/link entry')
    need(plan['native_argv'] == [plan['python'], '-I', '-S', '-B', '-X',
         'pycache_prefix=' + str(work / 'tmp' / 'pycache'), plan['child_path'], plan['plan_path']], 'fixed software native child')
    need(work.parent == Path('/tmp') and work.parent.resolve() == work.parent and
         not os.path.lexists(work), 'fresh canonical output')
    need(signal.getsignal(signal.SIGALRM) is deadline_handler, 'owned global deadline')
    limits = plan['limits']
    before = verify_inputs(plan)
    mem = int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines()
                   if x.startswith('MemAvailable:'))) * 1024
    fs = os.statvfs(work.parent)
    need(mem >= limits['minimum_host_memavailable_bytes'] and
         fs.f_bavail * fs.f_frsize >= limits['minimum_tmpfs_available_bytes'], 'fresh RAM and tmpfs')
    work.mkdir(mode=0o700)
    for name in ('home', 'tmp', 'phases'):
        (work / name).mkdir(mode=0o700)
    dump(work / 'PLAN_SNAPSHOT.json', plan)
    dump(work / 'BEFORE.json', before)
    watch = {'reason': None, 'peak_sampled_descendant_rss': 0, 'max_owned_bytes': 0,
             'interval_seconds': 0.2, 'aggregate_is_sample_enforced': True}
    done, diagnostics, records, usages, thread = threading.Event(), {}, {}, {}, None
    result = {'status': 'NOT_STARTED', 'native_diagnostic_attempted': False,
              'HardFloat_executed': False, 'RTL_executed': False, 'old_cpp_source_modified': False,
              'future_integration_flags_blocker_remains': True, 'prior_pass_inherited': False}

    def check_owned():
        rss = descendant_rss(os.getpid())
        tree = inventory(work)
        watch['peak_sampled_descendant_rss'] = max(watch['peak_sampled_descendant_rss'], rss)
        watch['max_owned_bytes'] = max(watch['max_owned_bytes'], tree['bytes'])
        need(rss <= limits['aggregate_rss_bytes'], 'aggregate RSS cap')
        need(tree['bytes'] <= limits['owned_output_bytes'] - 2 * 1024**2, 'owned cap with post receipt reserve')
        need(tree['log_bytes'] <= limits['log_bytes'], 'owned log cap')

    def watchdog():
        try:
            while not done.wait(0.2):
                check_owned()
        except BaseException as error:
            watch['reason'] = type(error).__name__ + ': ' + str(error)
            os.kill(os.getpid(), signal.SIGTERM)

    try:
        sp = Path(plan['support_path'])
        raw = checked(sp, plan['inputs'][str(sp)], keep=True)
        module = types.ModuleType('fixed_uf_native_ci_support')
        module.__file__ = str(sp)
        exec(compile(raw, str(sp), 'exec', dont_inherit=True), module.__dict__)
        support, base, _ = module.fixed_support(Path(plan['repository']))
        original_remaining_work = module.remaining_work
        phase_work_stop = [0.0]

        def absolute_remaining_work(*args, **kwargs):
            end = min(original_remaining_work(*args, **kwargs), work_stop, phase_work_stop[0])
            need(end > time.monotonic(), 'absolute work deadline exhausted')
            return end

        module.remaining_work = absolute_remaining_work
        thread = threading.Thread(target=watchdog, daemon=True)
        thread.start()
        library_seal, dependencies = None, None
        compiler_work_stop = min(work_stop, time.monotonic() + 30)
        for name, argv, seconds in [('dependencies', plan['dependency_argv'], 30),
                                    ('compile_link', plan['compile_argv'], 30),
                                    ('native_diagnostic', plan['native_argv'], 10)]:
            need(watch['reason'] is None, 'no previous resource failure')
            phase_work_stop[0] = min(work_stop, time.monotonic() + seconds,
                                     compiler_work_stop if name != 'native_diagnostic' else work_stop)
            remaining = int(phase_work_stop[0] - time.monotonic())
            need(remaining > 0 and time.monotonic() < stop - 20, 'shared absolute work admission')
            if name == 'compile_link':
                need(dependencies is not None and records['dependencies']['cleanup_confirmed'], 'dependency phase complete and reaped')
                for p in set(x for v in dependencies['rules'].values() for x in v):
                    checked(p, plan['inputs'][p])
            if name == 'native_diagnostic':
                result['native_diagnostic_attempted'] = True
                need(library_seal is not None and records['compile_link']['cleanup_confirmed'], 'new compile natural cleanup')
                checked(library_seal['path'], library_seal['pin'])
            cfg = {'total_seconds': int(stop - time.monotonic()), 'work_seconds': remaining,
                   'cpu_seconds': seconds, 'as_bytes': limits['address_space_bytes'],
                   'fsize_bytes': limits['single_file_bytes'], 'log_bytes': limits['log_bytes'], 'sample_rows': 61}
            diag = {}
            diagnostics[name] = diag
            record, _, usage = module.run_phase(support, base, name, argv, work,
                work / 'phases' / name, plan['environment'], cfg, stop,
                owner={'handler': deadline_handler, 'deadline': stop}, diagnostics=diag)
            natural(record)
            records[name], usages[name] = record, usage
            check_owned()
            if name == 'dependencies':
                raw_deps = terminal_bytes(work / 'phases' / name / 'native.log', limits['log_bytes'])
                dependencies = dependency_rules(raw_deps, plan)
                dump(work / 'DEPENDENCIES.json', dependencies)
                need(not (work / 'libuf_diagnostic.so').exists(), '-M did not compile a library')
            elif name == 'compile_link':
                library = work / 'libuf_diagnostic.so'
                raw_library = terminal_bytes(library, limits['single_file_bytes'])
                need(raw_library[:6] == b'\x7fELF\x02\x01' and
                     int.from_bytes(raw_library[16:18], 'little') == 3 and
                     int.from_bytes(raw_library[18:20], 'little') == 62, 'one x86_64 ET_DYN little-endian library')
                library_seal = {'path': str(library), 'pin': {'bytes': len(raw_library),
                    'sha256': hashlib.sha256(raw_library).hexdigest()}, 'compile_natural_cleanup': True,
                    'original_cpp_sha256': plan['inputs'][plan['sources'][0]]['sha256'],
                    'probe_sha256': plan['inputs'][plan['sources'][1]]['sha256'],
                    'plan_sha256': hashlib.sha256((json.dumps(plan, indent=2, sort_keys=True) + '\n').encode()).hexdigest()}
                dump(work / 'LIBRARY_SEAL.json', library_seal)
        done.set()
        thread.join(timeout=1)
        need(not thread.is_alive() and watch['reason'] is None, 'watchdog terminal')
        checked(library_seal['path'], library_seal['pin'])
        raw_result = terminal_bytes(work / 'NATIVE_RESULT.json', 256 * 1024)
        native = json.loads(raw_result)
        need(native['status'] == 'PASS_ORIGINAL_CPP_SOFTWARE_DIAGNOSTIC_ONLY' and
             native['single_lane_cases'] == 24 and native['batch_policy_cases'] == 3 and
             len(native['cases']) == 24 and len(native['batches']) == 3 and
             native['library'] == library_seal and native['flags_difference_case_ids'] == ['01', '02'] and
             native['future_integration_flags_blocker_remains'] is True and
             native['HardFloat_executed'] is False and native['RTL_executed'] is False,
             'limited native software diagnostic postconditions')
        native_lines = terminal_bytes(work / 'phases' / 'native_diagnostic' / 'native.log', limits['log_bytes']).decode().splitlines()
        terminal = json.loads(next(x for x in reversed(native_lines) if x.strip()))
        need(terminal['status'] == native['status'] and terminal['bytes'] == len(raw_result) and
             terminal['sha256'] == hashlib.sha256(raw_result).hexdigest(), 'child report exact final hash')
        after = verify_inputs(plan)
        need(after == before, 'input identity before/after drift')
        dump(work / 'AFTER.json', after)
        dump(work / 'WATCH.json', watch)
        dump(work / 'DIAGNOSTICS.json', diagnostics)
        final_tree = inventory(work, hashes=True)
        final_tree['excludes_self_and_terminal_result'] = True
        dump(work / 'FINAL_INVENTORY.json', final_tree)
        need(inventory(work)['bytes'] <= limits['owned_output_bytes'] - 256 * 1024, 'terminal owned receipt reserve')
        need(time.monotonic() < stop, 'terminal global deadline')
        result.update(status='PASS_ORIGINAL_CPP_SOFTWARE_DIAGNOSTIC_ONLY', records=records, usage=usages,
                      dependency_count=dependencies['unique_dependencies'], input_count=len(before),
                      native_result_sha256=hashlib.sha256(raw_result).hexdigest(),
                      source_count=2, elapsed_seconds=time.monotonic() - start,
                      qualification='Original C++ primitive and independent software Fraction comparison only; HardFloat flags are source spec, not hardware execution')
    except BaseException as error:
        result.update(status='FAIL_OR_UNKNOWN_UF_DIAGNOSTIC_ATTEMPT', exception_type=type(error).__name__,
                      exception=str(error)[:4096], elapsed_seconds=time.monotonic() - start)
        raise
    finally:
        done.set()
        if thread is not None:
            thread.join(timeout=1)
        if not (work / 'WATCH.json').exists():
            dump(work / 'WATCH.json', watch)
        if not (work / 'DIAGNOSTICS.json').exists():
            dump(work / 'DIAGNOSTICS.json', diagnostics)
        result.setdefault('records', records)
        result.setdefault('usage', usages)
        dump(work / 'RESULT.json', result)
    print(json.dumps({'status': result['status'], 'cases': 24, 'batches': 3,
                      'elapsed_seconds': time.monotonic() - start}), flush=True)
