"""Two fresh JVMs: compile one test, then evaluate existing Scala address methods. No hardware entry."""
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
    need(len(plan['tool_paths']) == 314 and len(plan['sources']) == 1 and
         len(plan['input_classes']) == 27 and len(plan['inputs']) == 354,
         'fixed tools, one test source and original class closure')
    tree = inventory(Path(plan['input_class_root']))
    need(set(tree['files']) == set(plan['input_class_relatives']), 'exact original class directory')
    return {p: checked(p, pin) for p, pin in plan['inputs'].items()}


def natural(record):
    need(record['status'] == 'PASS' and record['exit_code'] == 0 and
         not record['timed_out'] and record['parent_exception'] is None and
         record['anchor_confirmed'] and record['reaped'] and record['cleanup_confirmed'] and
         record['group_state'] == 'absent' and
         record['exit_observed_while_unreaped']['code'] == 1 and
         record['exit_observed_while_unreaped']['status'] == 0,
         'natural JVM exit and anchored cleanup')


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


def main(plan, start, stop, work_stop, deadline_handler):
    work = Path(plan['work'])
    need(plan['schema'] == 'qwen35-chunk-address-jvm-behavior-bound-v1', 'plan schema')
    need(plan['compile_argv'].count('scala.tools.nsc.Main') == 1 and
         plan['compile_argv'][-1:] == list(plan['sources']) and
         plan['compile_argv'][plan['compile_argv'].index('-d') + 1] == str(work / 'classes'),
         'exact test-only compilation')
    need(plan['behavior_argv'][-1] == 'heteronpu.continuous.contracttests.GdnChunkAddressPlanBehavior' and
         plan['behavior_argv'][plan['behavior_argv'].index('-cp') + 1].split(':') ==
         [str(work / 'classes'), plan['input_class_root'], plan['scala_library']],
         'behavior classpath excludes Chisel and all other tools')
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
    done, diagnostics, records, usages, thread = threading.Event(), {}, {}, {}, None
    result = {'status': 'NOT_STARTED', 'RTL_generated': False, 'elaboration_executed': False,
              'Bundle_instantiated': False, 'actual_handshake_tested': False,
              'numerical_tested': False, 'prior_pass_inherited': False}

    def check_owned():
        rss = descendant_rss(os.getpid())
        tree = inventory(work)
        watch['peak_sampled_descendant_rss'] = max(watch['peak_sampled_descendant_rss'], rss)
        watch['max_owned_bytes'] = max(watch['max_owned_bytes'], tree['bytes'])
        need(rss <= limits['aggregate_rss_bytes'], 'aggregate RSS cap')
        need(tree['bytes'] <= limits['owned_output_bytes'] - 4 * 1024**2, 'owned output cap')
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
        module = types.ModuleType('fixed_chunk_behavior_ci_support')
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
        compiled = None
        for name, argv, seconds in [('compile_test', plan['compile_argv'], 120),
                                    ('behavior', plan['behavior_argv'], 30)]:
            need(watch['reason'] is None, 'no previous resource failure')
            phase_work_stop[0] = min(work_stop, time.monotonic() + seconds)
            remaining = int(phase_work_stop[0] - time.monotonic())
            need(remaining > 0 and time.monotonic() < stop - 30, 'shared phase admission deadline')
            if name == 'behavior':
                need(compiled is not None and records['compile_test']['cleanup_confirmed'],
                     'test compile completed and cleaned before behavior')
                need(inventory(work / 'classes', hashes=True)['files'] == compiled,
                     'new test classes exact before behavior')
                need(set(inventory(Path(plan['input_class_root']))['files']) ==
                     set(plan['input_class_relatives']), 'no extra input classes')
                for p, pin in plan['input_classes'].items():
                    checked(p, pin)
            cfg = {'total_seconds': int(stop - time.monotonic()), 'work_seconds': remaining,
                   'cpu_seconds': seconds, 'as_bytes': limits['address_space_bytes'],
                   'fsize_bytes': limits['single_file_bytes'], 'log_bytes': limits['log_bytes'],
                   'sample_rows': 181}
            diag = {}
            diagnostics[name] = diag
            record, _, usage = module.run_phase(support, base, name, argv, work,
                work / 'phases' / name, plan['environment'], cfg, stop,
                owner={'handler': deadline_handler, 'deadline': stop}, diagnostics=diag)
            natural(record)
            records[name], usages[name] = record, usage
            check_owned()
            if name == 'compile_test':
                compiled = inventory(work / 'classes', hashes=True)['files']
                need(compiled and all(k.endswith('.class') and
                     k.startswith('heteronpu/continuous/contracttests/GdnChunkAddressPlanBehavior')
                     for k in compiled), 'only test class output, no production recompilation')
                need(set(plan['expected_test_classes']).issubset(compiled), 'test main/object compiled')
                dump(work / 'COMPILED_TEST_CLASSES.json', compiled)
        done.set()
        thread.join(timeout=1)
        need(not thread.is_alive() and watch['reason'] is None, 'watchdog terminal')
        need(inventory(work / 'classes', hashes=True)['files'] == compiled, 'test class drift after behavior')
        log = terminal_bytes(work / 'phases' / 'behavior' / 'native.log', limits['log_bytes']).decode()
        lines = [x for x in log.splitlines() if x.strip()]
        need(lines and lines[-1].startswith('{'), 'terminal behavior JSON')
        behavior = json.loads(lines[-1])
        need(behavior['status'] == 'PASS_SCALA_ADDRESS_PLAN_BEHAVIOR_ONLY' and
             type(behavior['checks']) is int and behavior['checks'] > 0 and
             behavior['sources_bound'] is True, 'real Scala method checks completed')
        loaded_raw = terminal_bytes(work / 'behavior-class-load.log', limits['log_bytes'])
        loaded = []
        for line in loaded_raw.decode().splitlines():
            if '[class,load]' in line and ' source:' in line:
                loaded.append(line.split('[class,load]', 1)[1].strip().split(' source:', 1)[0])
        need(loaded and not any(x.startswith(('chisel3.', 'firrtl.', 'circt.', 'hardfloat.')) or
             x in plan['forbidden_candidate_classes'] for x in loaded),
             'no hardware or Bundle class loaded during behavior')
        need(set(plan['required_behavior_classes']).issubset(loaded), 'actual production plan classes loaded')
        after = verify_inputs(plan)
        need(after == before, 'input identity before/after drift')
        dump(work / 'AFTER.json', after)
        dump(work / 'BEHAVIOR_RESULT.json', behavior)
        dump(work / 'CLASS_LOADING_SCOPE.json', {'required': plan['required_behavior_classes'],
             'loaded_count': len(loaded), 'candidate_classes': [x for x in loaded if x.startswith('heteronpu.')],
             'hardware_class_loaded': False, 'source': 'behavior-class-load.log'})
        dump(work / 'WATCH.json', watch)
        dump(work / 'DIAGNOSTICS.json', diagnostics)
        final_tree = inventory(work, hashes=True)
        final_tree['excludes_self_and_terminal_result'] = True
        dump(work / 'FINAL_INVENTORY.json', final_tree)
        need(inventory(work)['bytes'] <= limits['owned_output_bytes'] - 2 * 1024**2,
             'final owned cap with terminal receipt reserve')
        need(time.monotonic() < stop, 'terminal global deadline')
        result.update(status='PASS_SCALA_ADDRESS_PLAN_BEHAVIOR_ONLY', test_source_count=1,
                      original_class_count=27, test_class_count=len(compiled), tool_count=314,
                      records=records, usage=usages, behavior=behavior,
                      elapsed_seconds=time.monotonic() - start,
                      qualification='Real Scala address/byte-obligation methods only; no Bundle/Module/RTL/handshake/arithmetic')
    except BaseException as error:
        result.update(status='FAIL_OR_UNKNOWN_ADDRESS_BEHAVIOR_ATTEMPT', exception_type=type(error).__name__,
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
    print(json.dumps({'status': result['status'], 'checks': result['behavior']['checks'],
                      'elapsed_seconds': time.monotonic() - start}), flush=True)
