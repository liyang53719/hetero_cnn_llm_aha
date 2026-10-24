"""One bounded software-wrapper child; exact original WNOWAIT cleanup, no compiler."""
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
    for p in plan['absent_paths']:
        need(not os.path.lexists(p), 'unexpected loader override')
    for p, link in plan['fixed_symlinks'].items():
        need(Path(p).is_symlink() and os.readlink(p) == link['target'] and
             str(Path(p).resolve()) == link['canonical_path'], 'fixed runtime alias')
    return {p: checked(p, pin) for p, pin in plan['inputs'].items()}


def main(plan, start, stop, work_stop, deadline_handler):
    work = Path(plan['work'])
    need(plan['schema'] == 'strict-reference-wrapper-bound-v1', 'plan schema')
    need(plan['native_argv'] == [plan['python'], '-I', '-S', '-B', '-X',
         'pycache_prefix=' + str(work / 'tmp' / 'pycache'), plan['child_path'], plan['plan_path']], 'one fixed child')
    need(work.parent == Path('/tmp') and work.parent.resolve() == work.parent and
         not os.path.lexists(work), 'fresh canonical output')
    need(signal.getsignal(signal.SIGALRM) is deadline_handler, 'global deadline owner')
    limits = plan['limits']
    before = verify_inputs(plan)
    library = plan['library_path']
    seal = json.loads(checked(plan['library_seal_path'], plan['inputs'][plan['library_seal_path']], keep=True))
    need(seal['path'] == library and seal['compile_natural_cleanup'] is True and
         seal['pin'] == {k: plan['inputs'][library][k] for k in ('bytes', 'sha256')} and
         seal['candidate_cpp_sha256'] == plan['inputs'][plan['candidate_cpp_path']]['sha256'] and
         seal['plan_sha256'] == plan['prior_compile_plan_sha256'], 'existing repaired ELF provenance')
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
    watch = dict(reason=None, peak_sampled_descendant_rss=0, max_owned_bytes=0,
                 interval_seconds=0.2, aggregate_is_sample_enforced=True)
    done, diagnostics, records, usages, thread = threading.Event(), {}, {}, {}, None
    result = dict(status='NOT_STARTED', native_wrapper_attempted=False,
                  compiled_or_rebuilt=False, HardFloat_executed=False, RTL_executed=False,
                  old_cpp_or_model_modified=False, hardware_flags_gate_remains=True,
                  prior_pass_inherited=False)
    def check_owned():
        rss = descendant_rss(os.getpid())
        tree = inventory(work)
        watch['peak_sampled_descendant_rss'] = max(watch['peak_sampled_descendant_rss'], rss)
        watch['max_owned_bytes'] = max(watch['max_owned_bytes'], tree['bytes'])
        need(rss <= limits['aggregate_rss_bytes'], 'aggregate RSS cap')
        need(tree['bytes'] <= limits['owned_output_bytes'] - 2 * 1024**2, 'owned cap with post reserve')
        need(tree['log_bytes'] <= limits['log_bytes'], 'log cap')
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
        module = types.ModuleType('fixed_strict_reference_ci_support')
        module.__file__ = str(sp)
        exec(compile(raw, str(sp), 'exec', dont_inherit=True), module.__dict__)
        support, base, _ = module.fixed_support(Path(plan['repository']))
        original_remaining_work = module.remaining_work
        phase_stop = min(work_stop, time.monotonic() + 10)
        def absolute_remaining_work(*args, **kwargs):
            end = min(original_remaining_work(*args, **kwargs), work_stop, phase_stop)
            need(end > time.monotonic(), 'absolute work exhausted')
            return end
        module.remaining_work = absolute_remaining_work
        thread = threading.Thread(target=watchdog, daemon=True)
        thread.start()
        remaining = int(phase_stop - time.monotonic())
        need(remaining > 0 and time.monotonic() < stop - 20, 'one child within shared deadline')
        cfg = {'total_seconds': int(stop - time.monotonic()), 'work_seconds': remaining,
               'cpu_seconds': 10, 'as_bytes': limits['address_space_bytes'],
               'fsize_bytes': limits['single_file_bytes'], 'log_bytes': limits['log_bytes'], 'sample_rows': 61}
        result['native_wrapper_attempted'] = True
        diag = {}
        diagnostics['native_wrapper'] = diag
        record, _, usage = module.run_phase(support, base, 'native_wrapper', plan['native_argv'], work,
            work / 'phases' / 'native_wrapper', plan['environment'], cfg, stop,
            owner={'handler': deadline_handler, 'deadline': stop}, diagnostics=diag)
        natural(record)
        records['native_wrapper'], usages['native_wrapper'] = record, usage
        check_owned()
        raw_result = terminal_bytes(work / 'WRAPPER_RESULT.json', 192 * 1024)
        child = json.loads(raw_result)
        need(child['status'] == 'PASS_ISOLATED_STRICT_REFERENCE_WRAPPER_SOFTWARE_ONLY' and
             child['policy'] == plan['policy_id'] and child['native_requests'] == 52 and
             len(child['cases']) == 52 and len(child['nonfinite_prechecks']) == 12 and
             52 <= child['native_trace_calls'] <= 104 and child['lane_count'] == 1 and
             child['compiled_or_rebuilt'] is False and child['HardFloat_executed'] is False and
             child['RTL_executed'] is False and child['G11_hardware_group_regression_executed'] is False and
             child['library'] == seal, 'exact finite wrapper result scope')
        after = verify_inputs(plan)
        need(before == after, 'all pinned source/runtime/ELF identity unchanged')
        dump(work / 'AFTER.json', after)
        result.update(status='PASS_SINGLE_STRICT_REFERENCE_WRAPPER_SOFTWARE_ONLY',
                      native_requests=52, native_trace_calls=child['native_trace_calls'],
                      protocol_controls=child['protocol_controls'], nonfinite_prechecks=12,
                      wrapper_result={'bytes':len(raw_result),'sha256':hashlib.sha256(raw_result).hexdigest()},
                      records=records, usages=usages, policy=plan['policy_id'])
    except BaseException as error:
        result.update(status='FAIL', error_type=type(error).__name__, error=str(error),
                      records=records, usages=usages)
        raise
    finally:
        done.set()
        if thread is not None:
            thread.join(timeout=min(1.0, max(0.0, stop-time.monotonic())))
        dump(work / 'DIAGNOSTICS.json', diagnostics)
        dump(work / 'WATCH.json', watch)
        result['elapsed_seconds'] = time.monotonic() - start
        result['plan_sha256'] = hashlib.sha256(Path(plan['plan_path']).read_bytes()).hexdigest()
        dump(work / 'RESULT.json', result)
        tree = inventory(work, hashes=True)
        need(tree['bytes'] <= limits['owned_output_bytes'], 'final owned cap')
        dump(work / 'FINAL_INVENTORY.json', tree)
    need(time.monotonic() < stop and watch['reason'] is None, 'completed within total/resource gate')
    print(json.dumps({'status':result['status'], 'native_requests':52,
                      'native_trace_calls':result['native_trace_calls'], 'elapsed_seconds':result['elapsed_seconds']}),flush=True)
