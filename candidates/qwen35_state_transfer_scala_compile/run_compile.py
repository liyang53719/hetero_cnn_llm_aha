"""One fresh compile-only JVM; original WNOWAIT cleanup, no hardware entry."""
import hashlib
import json
import os
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
        need(len(files) < 4096 and s.st_size <= 4 * 1024**2, 'owned file cap')
        rel = p.relative_to(root).as_posix()
        need(p.suffix.lower() not in {'.v', '.sv', '.fir', '.mlir'}, 'RTL or elaboration output forbidden')
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


def verify_inputs(plan):
    need(len(plan['tool_paths']) == 314 and len(plan['sources']) == 4 and len(plan['inputs']) == 326, 'fixed tool and source closure')
    return {p: checked(p, pin) for p, pin in plan['inputs'].items()}


def main(plan, start, stop, work_stop, deadline_handler):
    work = Path(plan['work'])
    need(plan['schema'] == 'qwen35-chunk-state-transfer-scala-compile-bound-v1', 'plan schema')
    need(plan['runtime_entry'] == 'scala.tools.nsc.Main' and plan['argv'].count('scala.tools.nsc.Main') == 1,
         'compile-only entry')
    need(len(plan['argv'][-4:]) == len(set(plan['argv'][-4:])) == 4 and
         set(plan['argv'][-4:]) == set(plan['sources']) and
         plan['argv'][plan['argv'].index('-d') + 1] == str(work / 'classes'), 'exact compile source/output')
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
    for name in ('classes', 'home', 'tmp', 'phases'):
        (work / name).mkdir(mode=0o700)
    dump(work / 'PLAN_SNAPSHOT.json', plan)
    dump(work / 'BEFORE.json', before)
    watch = {'reason': None, 'peak_sampled_descendant_rss': 0, 'max_owned_bytes': 0,
             'interval_seconds': 0.2, 'aggregate_is_sample_enforced': True}
    done, diagnostics, thread = threading.Event(), {}, None
    result = {'status': 'NOT_STARTED', 'RTL_generated': False, 'elaboration_executed': False,
              'numerical_tested': False, 'prior_pass_inherited': False}

    def check_owned():
        rss = descendant_rss(os.getpid())
        tree = inventory(work)
        watch['peak_sampled_descendant_rss'] = max(watch['peak_sampled_descendant_rss'], rss)
        watch['max_owned_bytes'] = max(watch['max_owned_bytes'], tree['bytes'])
        need(rss <= limits['aggregate_rss_bytes'], 'aggregate RSS cap')
        # Reserve 4 MiB for final inventories/failure receipts, within the total cap.
        need(tree['bytes'] <= limits['owned_output_bytes'] - 4 * 1024**2, 'owned output cap')
        need(tree['log_bytes'] <= limits['log_bytes'], 'owned log cap')

    def watchdog():
        try:
            while not done.wait(0.2):
                check_owned()
        except BaseException as error:
            watch['reason'] = type(error).__name__ + ': ' + str(error)
            os.kill(os.getpid(), signal.SIGTERM)  # Our coordinator only, never an unrelated PID.

    try:
        sp = Path(plan['support_path'])
        raw = checked(sp, plan['inputs'][str(sp)], keep=True)
        module = types.ModuleType('fixed_chunk_compile_ci_support')
        module.__file__ = str(sp)
        exec(compile(raw, str(sp), 'exec', dont_inherit=True), module.__dict__)
        support, base, _ = module.fixed_support(Path(plan['repository']))
        # The old helper also uses now+work_seconds; clamp its absolute return
        # so preparation/thread-start delay cannot consume the 25s post window.
        original_remaining_work = module.remaining_work

        def absolute_remaining_work(*args, **kwargs):
            end = min(original_remaining_work(*args, **kwargs), work_stop)
            need(end > time.monotonic(), 'absolute work deadline exhausted')
            return end

        module.remaining_work = absolute_remaining_work
        remaining = int(work_stop - time.monotonic())
        need(remaining > 0 and time.monotonic() < stop - 30, 'work admission deadline')
        cfg = {'total_seconds': int(stop - time.monotonic()), 'work_seconds': remaining,
               'cpu_seconds': limits['child_cpu_seconds'], 'as_bytes': limits['address_space_bytes'],
               'fsize_bytes': limits['single_file_bytes'], 'log_bytes': limits['log_bytes'],
               'sample_rows': 181}
        thread = threading.Thread(target=watchdog, daemon=True)
        thread.start()
        record, _, usage = module.run_phase(support, base, 'compile_chunk_state_transfer', plan['argv'], work,
            work / 'phases' / 'compile_chunk_state_transfer', plan['environment'], cfg, stop,
            owner={'handler': deadline_handler, 'deadline': stop}, diagnostics=diagnostics)
        done.set()
        thread.join(timeout=1)
        need(not thread.is_alive() and watch['reason'] is None, 'watchdog terminal')
        need(record['status'] == 'PASS' and record['exit_code'] == 0 and
             not record['timed_out'] and record['parent_exception'] is None and
             record['anchor_confirmed'] and record['reaped'] and record['cleanup_confirmed'] and
             record['group_state'] == 'absent' and
             record['exit_observed_while_unreaped']['code'] == 1 and
             record['exit_observed_while_unreaped']['status'] == 0, 'natural compile and anchored cleanup')
        after = verify_inputs(plan)
        need(after == before, 'input identity before/after drift')
        dump(work / 'AFTER.json', after)
        check_owned()
        tree = inventory(work, hashes=True)
        classes = {k: v for k, v in tree['files'].items() if k.startswith('classes/')}
        need(classes and all(k.endswith('.class') for k in classes), 'class-only output')
        need(all('classes/' + k in classes and classes['classes/' + k]['bytes'] > 0
                 for k in plan['expected_classes']), 'all required contract/protocol/transfer classes present')
        dump(work / 'OUTPUT_MANIFEST.json', classes)
        dump(work / 'WATCH.json', watch)
        dump(work / 'DIAGNOSTICS.json', diagnostics)
        final_tree = inventory(work, hashes=True)
        final_tree['excludes_self_and_terminal_result'] = True
        dump(work / 'FINAL_INVENTORY.json', final_tree)
        need(inventory(work)['bytes'] <= limits['owned_output_bytes'] - 2 * 1024**2,
             'final owned cap with terminal receipt reserve')
        need(time.monotonic() < stop, 'terminal global deadline')
        result.update(status='PASS_QWEN35_CHUNK_STATE_TRANSFER_SCALA_COMPILE_ONLY', source_count=4,
                      tool_count=314, class_count=len(classes), record=record, usage=usage,
                      elapsed_seconds=time.monotonic() - start,
                      qualification='Compilation only; no constructor/elaboration/RTL/handshake/numerical execution')
    except BaseException as error:
        result.update(status='FAIL_OR_UNKNOWN_COMPILE_ATTEMPT', exception_type=type(error).__name__,
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
        dump(work / 'RESULT.json', result)
    print(json.dumps({'status': result['status'], 'classes': result['class_count'],
                      'elapsed_seconds': time.monotonic() - start}), flush=True)
