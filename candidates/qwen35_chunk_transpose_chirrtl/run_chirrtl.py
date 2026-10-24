"""Two fresh JVMs: compile one emitter, then elaborate one owner to CHIRRTL only."""
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
        need(len(files) < 4096 and s.st_size <= 4 * 1024**2, 'owned file cap')
        rel = p.relative_to(root).as_posix()
        need(p.suffix.lower() not in {'.v', '.sv', '.fir', '.mlir'} or
             (p.suffix == '.fir' and rel == 'ir/GdnChunkTransposeOwner.fir'),
             'only the fixed CHIRRTL artifact, no RTL/other IR')
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
         len(plan['input_classes']) == 146 and len(plan['inputs']) == 501,
         'fixed tools, one emitter source and original 146-class closure')
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


def validate_loaded_classes(raw, plan, compiled):
    """Pure postcondition over bounded log text. Never imports or executes logged classes."""
    available = {x[:-6].replace('/', '.') for x in plan['input_class_relatives']}
    original = set(plan['allowed_input_classes'])
    need(len(original) == len(plan['allowed_input_classes']) == 17 and original <= available,
         'exact allowed frontend subset of compiled inputs')
    need(set(compiled) == set(plan['expected_emitter_classes']), 'exact fixed emitter class set')
    emitted = {x[:-6].replace('/', '.') for x in compiled}
    expected = {x: 'file:' + Path(plan['input_class_root']).as_posix() + '/' for x in original}
    expected.update({x: 'file:' + (Path(plan['work']) / 'classes').as_posix() + '/' for x in emitted})
    loaded, ordinary, hidden, hosts = [], [], [], set()
    for line in raw.decode('utf-8').splitlines():
        if '[class,load]' not in line:
            continue
        row = line.split('[class,load]', 1)[1].strip()
        need(' source:' in row, 'class-load source missing')
        name, source = row.split(' source:', 1)
        source = source.strip()
        need(name and source, 'class-load name/source missing')
        loaded.append(name)
        need(not name.startswith(('hardfloat.', 'gemmini.')), 'arithmetic implementation class forbidden')
        if not name.startswith('heteronpu.'):
            continue
        if name in expected:
            need(source == expected[name], 'fixed candidate class root mismatch')
            hosts.add(name)
            ordinary.append(name)
            continue
        match = re.fullmatch(r'(.+)\$\$Lambda(?:\$[0-9]+)?/0x[0-9a-fA-F]+', name)
        need(match is not None, 'unknown candidate class or hidden-lambda spelling')
        host = match.group(1)
        need(host in plan['allowed_hidden_hosts'] and host in expected and host in hosts and source == host,
             'hidden lambda exact pinned and already loaded host/source')
        hidden.append({'name': name, 'host': host})
    need(loaded and set(plan['required_elaboration_classes']).issubset(loaded),
         'required elaboration classes missing')
    return {'required': plan['required_elaboration_classes'], 'loaded_count': len(loaded),
            'candidate_classes': [x for x in loaded if x.startswith('heteronpu.')],
            'ordinary_candidate_count': len(ordinary), 'hidden_lambda_count': len(hidden),
            'hidden_host_names': sorted({x['host'] for x in hidden}),
            'hardware_class_loaded': True, 'source': 'elaboration-class-load.log',
            'scope': 'one frontend owner only; class loading is not simulation'}


def main(plan, start, stop, work_stop, deadline_handler):
    work = Path(plan['work'])
    need(plan['schema'] == 'qwen35-chunk-transpose-chirrtl-bound-v1', 'plan schema')
    need(plan['compile_argv'].count('scala.tools.nsc.Main') == 1 and
         plan['compile_argv'][-1:] == list(plan['sources']) and
         plan['compile_argv'][plan['compile_argv'].index('-d') + 1] == str(work / 'classes'),
         'exact emitter-only compilation')
    need(plan['elaborate_argv'][-1] == 'heteronpu.continuous.contracttests.GdnChunkTransposeChirrtl' and
         plan['elaborate_argv'][plan['elaborate_argv'].index('-cp') + 1].split(':') ==
         [str(work / 'classes'), plan['input_class_root']] + plan['jar_paths'] and
         '-Djava.security.manager=allow' in plan['elaborate_argv'] and
         len(plan['jar_paths']) == len(set(plan['jar_paths'])) == 87,
         'fixed emitter/class/tool roots and required child guard')
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
    for name in ('classes', 'home', 'tmp', 'phases', 'ir'):
        (work / name).mkdir(mode=0o700)
    dump(work / 'PLAN_SNAPSHOT.json', plan)
    dump(work / 'BEFORE.json', before)
    watch = {'reason': None, 'peak_sampled_descendant_rss': 0, 'max_owned_bytes': 0,
             'interval_seconds': 0.2, 'aggregate_is_sample_enforced': True}
    done, diagnostics, records, usages, thread = threading.Event(), {}, {}, {}, None
    result = {'status': 'NOT_STARTED', 'RTL_generated': False, 'elaboration_attempted': False, 'elaboration_completed': False,
              'owner_constructor_completed': None, 'actual_handshake_tested': False,
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
        module = types.ModuleType('fixed_chunk_chirrtl_ci_support')
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
        for name, argv, seconds in [('compile_emitter', plan['compile_argv'], 120),
                                    ('elaborate', plan['elaborate_argv'], 30)]:
            need(watch['reason'] is None, 'no previous resource failure')
            phase_work_stop[0] = min(work_stop, time.monotonic() + seconds)
            remaining = int(phase_work_stop[0] - time.monotonic())
            need(remaining > 0 and time.monotonic() < stop - 30, 'shared phase admission deadline')
            if name == 'elaborate':
                result['elaboration_attempted'] = True
                need(compiled is not None and records['compile_emitter']['cleanup_confirmed'],
                     'emitter compiled and cleaned before elaboration')
                need(inventory(work / 'classes', hashes=True)['files'] == compiled,
                     'new emitter classes exact before elaboration')
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
            if name == 'compile_emitter':
                compiled = inventory(work / 'classes', hashes=True)['files']
                need(compiled and all(k.endswith('.class') and
                     k.startswith('heteronpu/continuous/contracttests/GdnChunkTransposeChirrtl')
                     for k in compiled), 'only emitter class output, no production recompilation')
                need(set(plan['expected_emitter_classes']) == set(compiled), 'exact emitter main/object/guard compiled')
                dump(work / 'COMPILED_EMITTER_CLASSES.json', compiled)
        done.set()
        thread.join(timeout=1)
        need(not thread.is_alive() and watch['reason'] is None, 'watchdog terminal')
        need(inventory(work / 'classes', hashes=True)['files'] == compiled, 'emitter class drift after elaboration')
        log = terminal_bytes(work / 'phases' / 'elaborate' / 'native.log', limits['log_bytes']).decode()
        lines = [x for x in log.splitlines() if x.strip()]
        need(lines and lines[-1].startswith('{'), 'terminal elaboration JSON')
        elaboration = json.loads(lines[-1])
        need(elaboration['status'] == 'PASS_OWNER_CHIRRTL_FRONTEND_ONLY' and
             type(elaboration['constructors']) is int and elaboration['constructors'] == 1 and
             type(elaboration['io_leaf_checks']) is int and elaboration['io_leaf_checks'] == 109 and
             elaboration['sources_bound'] is True and elaboration['guard_locked'] is True and
             all(type(elaboration[k]) is int and elaboration[k] == 0 for k in
                 ('external_exec_attempts', 'network_attempts', 'guard_replacement_attempts', 'instances')) and
             elaboration['modules'] == 1 and elaboration['RTL_generated'] is False and
             elaboration['actual_handshake_tested'] is False and elaboration['numerical_tested'] is False,
             'one real frontend elaboration and child guard checks completed')
        fir_raw = terminal_bytes(work / 'ir' / 'GdnChunkTransposeOwner.fir', 2 * 1024**2)
        fir = fir_raw.decode('utf-8')
        need(type(elaboration['fir_bytes']) is int and len(fir_raw) == elaboration['fir_bytes'] and
             hashlib.sha256(fir_raw).hexdigest() == elaboration['fir_sha256'], 'CHIRRTL exact digest/bytes')
        fir_lines = [x.strip() for x in fir.splitlines()]
        need(fir_lines and fir_lines[0].startswith('FIRRTL version ') and
             sum(x.startswith('circuit GdnChunkTransposeOwner :') for x in fir_lines) == 1 and
             sum(x.startswith('module ') for x in fir_lines) == 1 and
             sum(x.startswith('module GdnChunkTransposeOwner :') for x in fir_lines) == 1 and
             not any(x.startswith(('extmodule ', 'inst ', 'mem ', 'cmem ', 'smem ')) for x in fir_lines),
             'single owner CHIRRTL circuit without instances/memories/external modules')
        need(elaboration.get('register_tile_rows') == 16 and elaboration.get('register_tile_row_bits') == 512 and
             elaboration.get('register_tile_payload_bytes') == 1024,
             'real bound 1024-byte register tile checks completed')
        tile_lines = [x for x in fir_lines if x.startswith(('regreset tile :', 'reg tile :'))]
        need(len(tile_lines) == 1 and tile_lines[0].startswith('regreset tile : UInt<512>[16], clock, reset, '),
             'exact reset register tile declaration in sole owner, not memory')
        need({p.name for p in (work / 'ir').iterdir()} == {'GdnChunkTransposeOwner.fir'}, 'one IR artifact')
        loaded_raw = terminal_bytes(work / 'elaboration-class-load.log', limits['log_bytes'])
        class_scope = validate_loaded_classes(loaded_raw, plan, compiled)
        after = verify_inputs(plan)
        need(after == before, 'input identity before/after drift')
        dump(work / 'AFTER.json', after)
        dump(work / 'ELABORATION_RESULT.json', elaboration)
        dump(work / 'CLASS_LOADING_SCOPE.json', class_scope)
        dump(work / 'WATCH.json', watch)
        dump(work / 'DIAGNOSTICS.json', diagnostics)
        final_tree = inventory(work, hashes=True)
        final_tree['excludes_self_and_terminal_result'] = True
        dump(work / 'FINAL_INVENTORY.json', final_tree)
        need(inventory(work)['bytes'] <= limits['owned_output_bytes'] - 2 * 1024**2,
             'final owned cap with terminal receipt reserve')
        need(time.monotonic() < stop, 'terminal global deadline')
        result.update(status='PASS_OWNER_CHIRRTL_FRONTEND_ONLY', emitter_source_count=1,
                      original_class_count=146, emitter_class_count=len(compiled), tool_count=314,
                      records=records, usage=usages, elaboration=elaboration,
                      elaboration_completed=True, owner_constructor_completed=True,
                      elapsed_seconds=time.monotonic() - start,
                      qualification='One owner Chisel frontend/109 declared IO checks/CHIRRTL only; no firtool inference, RTL, handshake or numerical test')
    except BaseException as error:
        result.update(status='FAIL_OR_UNKNOWN_OWNER_CHIRRTL_ATTEMPT', exception_type=type(error).__name__,
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
    print(json.dumps({'status': result['status'], 'io_leaf_checks': result['elaboration']['io_leaf_checks'],
                      'elapsed_seconds': time.monotonic() - start}), flush=True)
