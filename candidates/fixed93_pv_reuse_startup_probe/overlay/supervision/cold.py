"""Prepared source projection and fully mocked supervision tests. NOT RUN at authoring.

The caller must provide a reviewed budget, source manifest, and a separate fresh
cold-output directory. No actual child, native service, DUT, or network is allowed.
"""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode and not sys.flags.optimize):
    raise SystemExit('python -I -S -B without optimization required')

ATTEMPTS = []


def audit(event, args):
    if event.startswith(('ctypes.', 'subprocess.', 'socket.', 'os.exec', 'os.spawn')) or event in (
            'os.system', 'os.fork', 'os.forkpty', 'os.posix_spawn'):
        ATTEMPTS.append(event)
        raise RuntimeError('cold process/native/network boundary denied: ' + event)
    if event == 'import' and args[0].split('.')[0] in ('numpy', 'ctypes', 'torch', 'candidates'):
        ATTEMPTS.append('import:' + args[0])
        raise RuntimeError('cold DUT/native import denied')


sys.addaudithook(audit)
import argparse
import ast
import copy
import errno
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import types
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from gate import (CANDIDATE, OWNED, need, preflight, read_budget, read_checked,
                  pinned, strict_json, validate_budget, RECEIPT_BYTES, LOG_FILE_BYTES)
import supervisor_adapter as adapter
import launch


def expect_failure(call, message=None):
    try:
        call()
    except BaseException as error:
        if message is not None:
            need(message in str(error), 'wrong mock failure: ' + str(error))
        return error
    raise AssertionError('mock negative did not fail')


def fixture_classes():
    """Use exact 0936 fake classes, not imports of any old actual entry module."""
    pins = strict_json(read_checked(HERE / 'EXTERNAL_PINS.json'))
    raw = pinned(pins['old_mock_fixtures'])
    lines = raw.splitlines(keepends=True)
    selected = {node.name: b''.join(lines[node.lineno - 1:node.end_lineno])
                for node in ast.parse(raw).body
                if isinstance(node, ast.ClassDef) and node.name in ('FakeClock', 'FakeProcess', 'Model')}
    need(tuple(selected) == ('FakeClock', 'FakeProcess', 'Model'), 'exact three old fake classes required')
    namespace = dict(__name__='pinned_0936_mock_fixtures', errno=errno, os=os,
                     signal=signal, subprocess=subprocess, types=types)
    exec(compile(b'\n\n'.join(selected.values()), 'pinned_0936_mock_classes_only', 'exec',
                 dont_inherit=True), namespace)
    return namespace['Model'], namespace['FakeClock']


def safe_order(model):
    signals = [event for event in model.events if event[0] == 'killpg' and event[1] != 0]
    need(all(not event[2] for event in signals), 'signal after reap in mocked public supervisor')
    if model.reaped:
        at = next(i for i, event in enumerate(model.events) if event[0] == 'wait')
        need(not any(event[0] == 'killpg' and event[1] != 0 for event in model.events[at + 1:]),
             'nonzero signal after final reap')


def projection_check(support, base):
    limits = adapter.fixed_limits()
    plan = dict(published_sources=base['published_sources'], phases={'micro': limits}, environment={})
    supervisor, observation = support.projected_sources(plan, 'micro')
    old = copy.deepcopy(plan)
    old['phases']['micro'] = dict(total_seconds=120, work_seconds=105, cpu_seconds=120,
        as_bytes=1073741824, fsize_bytes=134217728, log_bytes=1048576, sample_rows=121)
    old_supervisor, old_observation = support.projected_sources(old, 'micro')
    old_hashes = dict(supervisor=hashlib.sha256(old_supervisor).hexdigest(),
                      observation=hashlib.sha256(old_observation).hexdigest())
    need(old_hashes == dict(
        supervisor='48b3a11d9d8e1ac166c597bf5d6e43205caaec336286658d949c3016132ba12a',
        observation='aa2474102736098963e62c4af73d1e628e4159d2157d1b9bbfa774d0bae7d5cf'),
        'old reviewed projection identity changed')
    before = b'(134217728, 134217728)'
    after = ('(' + str(limits['fsize_bytes']) + ', ' + str(limits['fsize_bytes']) + ')').encode()
    need(old_supervisor.count(before) == 1, 'single file-limit projection anchor')
    expected_supervisor = old_supervisor.replace(before, after, 1)
    before = b"if record['log_bytes'] > 1048576:"
    after = ("if record['log_bytes'] > " + str(limits['log_bytes']) + ':').encode()
    need(expected_supervisor.count(before) == 1, 'single log-limit projection anchor')
    expected_supervisor = expected_supervisor.replace(before, after, 1)
    before = b"state['count']<121"
    after = ("state['count']<" + str(limits['sample_rows'])).encode()
    need(old_observation.count(before) == 1, 'single sample-cap projection anchor')
    need(supervisor == expected_supervisor and observation == old_observation.replace(before, after, 1),
         'public projection changed beyond explicit file/log/row numeric budget deltas')
    need(observation.count(b"state['next']=now+1") == 1,
         'public first-immediate/next=now+1 sampler must remain unchanged')
    return plan, dict(supervisor=hashlib.sha256(supervisor).hexdigest(),
                      observation=hashlib.sha256(observation).hexdigest()), old_hashes


def mock_runner(support, plan, root, model, *, tree=None, sample_error=None, sticky=False):
    runner = support.make_runner(plan, 'micro', root)
    runner['time'] = model.clock
    runner['os'] = types.SimpleNamespace(waitid=model.waitid, killpg=model.killpg,
        P_PID=os.P_PID, WEXITED=os.WEXITED, WNOHANG=os.WNOHANG, WNOWAIT=os.WNOWAIT)
    runner['signal'] = types.SimpleNamespace(SIGKILL=signal.SIGKILL,
        ITIMER_REAL=signal.ITIMER_REAL, setitimer=lambda *_: None)
    runner['subprocess'] = types.SimpleNamespace(Popen=model.popen,
        TimeoutExpired=subprocess.TimeoutExpired, STDOUT=subprocess.STDOUT)
    def published_sample(child):
        model.sample(child)
        if sample_error is not None:
            raise sample_error
    runner['sample_leader'] = published_sample
    state = {'tree': {'ownership_uncertain': sticky}}
    row = tree or dict(pids=[model.child.pid], rss_bytes=0, cpu_seconds=0,
                      leader_state='Z', live_descendant_pids=[])
    adapter.adapt_runner(runner, owned_root=root, stdout=None, stderr=None,
        work_stop=adapter.WORK_SECONDS, cpu_baseline=0, state=state,
        tree_sampler=lambda *_: dict(row))
    return runner, state


def mock_case(support, plan, root, model, **kwargs):
    runner, state = mock_runner(support, plan, root, model, **kwargs)
    error = record = None
    with patch.object(adapter, 'time', model.clock), patch.object(adapter, 'cpu_usage', return_value=0):
        try:
            record, _ = runner['bounded']('native', ['MOCK_NOT_EXECUTED'], root, root,
                                           min(.05, adapter.WORK_SECONDS), adapter.WHOLE_SECONDS)
        except BaseException as failure:
            error = failure
    saved = strict_json(read_checked(root / 'native.json', cap=RECEIPT_BYTES))
    safe_order(model)
    return record, saved, state, error


def run_mocks(support, plan, folder, Model, FakeClock):
    passed = []
    def case(name, model, **kwargs):
        root = folder / name
        root.mkdir()
        result = mock_case(support, plan, root, model, **kwargs)
        passed.append(name)
        return result
    model = Model()
    _, record, state, error = case('immediate_rc0', model)
    need(error is None and record['status'] == 'PASS' and record['cleanup_confirmed'], 'mock immediate exit')
    order = [event[0] for event in model.events]
    need(order.index('sample') < order.index('wait') and state['sample_count'] == 1, 'pre-reap terminal sample')
    for name, kwargs in (
            ('nonzero', dict(exit_code=7)),
            ('timeout', dict(never_exit=True, exit_code=-signal.SIGKILL)),
            ('group_survivor', dict(survivor=True)),
            ('kill_error', dict(kill_error=True)),
            ('unknown_group', dict(unknown_group=True)),
            ('lost_anchor', dict(anchor_error=True)),
            ('reap_error', dict(reap_error=True))):
        model = Model(**kwargs)
        _, record, _, error = case(name, model)
        need(error is not None and record['status'] == 'FAIL', 'negative supervisor case passed: ' + name)
        if name == 'lost_anchor':
            need(not any(e[0] == 'killpg' and e[1] != 0 for e in model.events), 'signal after lost anchor')
    for number, message in enumerate(sorted(adapter.PUBLIC_SAMPLER_CONTRACT_ERRORS)):
        for sticky in (False, True):
            _, record, state, error = case('known_sampler_' + str(number) + '_' + str(sticky), Model(),
                                          sample_error=ValueError(message), sticky=sticky)
            need(error is not None and record['status'] == 'FAIL' and record['cleanup_confirmed'] and
                 state['tree']['ownership_uncertain'] is sticky,
                 'known sampler error invented/cleared ownership uncertainty')
    _, record, state, error = case('unknown_identity_uncertainty', Model(),
        sample_error=ValueError('unknown identity/read failure'))
    need(error is not None and state['tree']['ownership_uncertain'] is True,
         'unknown identity failure must be sticky')
    _, record, state, error = case('natural_rc0_live_descendant', Model(),
        tree=dict(pids=[424242, 424243], rss_bytes=0, cpu_seconds=0,
                  leader_state='Z', live_descendant_pids=[424243]))
    need(error is not None and 'LIVE_DESCENDANT_AT_LEADER_EXIT' in str(error) and
         record['status'] == 'FAIL' and state['terminal_live_descendant_pids'] == [424243],
         'natural rc0 hidden descendant accepted')
    for name, row in (
            ('sampled_rss_limit', dict(rss_bytes=adapter.RSS_BYTES + 1, cpu_seconds=0)),
            ('whole_cpu_limit', dict(rss_bytes=0, cpu_seconds=adapter.WHOLE_SECONDS + 1))):
        _, record, _, error = case(name, Model(), tree=dict(pids=[424242], leader_state='R',
            live_descendant_pids=[], **row))
        need(error is not None and record['status'] == 'FAIL', 'sampled resource excess accepted')
    # Directly exercise the untouched public sampler with fake proc data/clock.
    sample_dir = folder / 'public_sampler'
    sample_dir.mkdir()
    model = Model()
    runner = support.make_runner(plan, 'micro', sample_dir)
    runner['time'] = model.clock
    runner['os'] = types.SimpleNamespace(sysconf=lambda _: 100)
    def proc_bytes(pid, leaf):
        need(pid == model.child.pid, 'mock PID drift')
        if leaf == 'status':
            return b'VmRSS:\t4 kB\nVmHWM:\t4 kB\n'
        fields = ['R'] + ['0'] * 21
        fields[19], fields[21] = '12345', '1'
        return (str(pid) + ' (mock leader) ' + ' '.join(fields)).encode()
    runner['proc_bytes'] = proc_bytes
    for second in range(adapter.fixed_limits()['sample_rows']):
        model.clock.now = float(second)
        runner['sample_leader'](model.child)
    rows = (sample_dir / 'leader_samples.jsonl').read_bytes().splitlines()
    need(len(rows) == adapter.fixed_limits()['sample_rows'] and all(len(row) + 1 <= 2048 for row in rows),
         'closed whole-window first+endpoint sample row capacity')
    model.clock.now += 1
    expect_failure(lambda: runner['sample_leader'](model.child), 'leader sample row cap exceeded')
    passed.append('first_immediate_closed_window_formula_and_row_overflow')
    resource_root = folder / 'stat_only_owned'
    resource_root.mkdir()
    (resource_root / 'payload.bin').write_bytes(b'abc')
    with patch.object(adapter, 'read_checked', side_effect=AssertionError('payload hash/read during scan')):
        need(adapter.owned_inventory(resource_root)['bytes'] == 3, 'owned stat-only inventory')
    expect_failure(lambda: adapter.owned_inventory(resource_root, cap=2), 'OWNED_OUTPUT_LIMIT')
    (resource_root / 'stdout.log').write_bytes(b'x' * (LOG_FILE_BYTES + 1))
    expect_failure(lambda: adapter.owned_inventory(resource_root), '32KiB log cap')
    (resource_root / 'stdout.log').unlink()
    expect_failure(lambda: adapter.checked_save(resource_root / 'oversize.json',
                   dict(text='x' * RECEIPT_BYTES), resource_root), '32KiB cap')
    passed.append('whole_owned_stat_only_and_32kib_log_receipt_caps')
    # Fast-exit peaks and post-receipt checks use terminal aggregate snapshots.
    clock = FakeClock()
    base_rss = dict(supervisor_maxrss_bytes=0, child_cumulative_maxrss_bytes=0)
    with patch.object(launch, 'time', clock), \
            patch.object(adapter, 'owned_inventory', return_value={'bytes': 0}), \
            patch.object(adapter, 'cpu_usage', return_value=0), \
            patch.object(adapter, 'rss_high_water', return_value=base_rss):
        launch.terminal(adapter, {}, {'cleanup_confirmed': True}, 0, adapter.WHOLE_SECONDS)
        expect_failure(lambda: launch.terminal(adapter, {'tree': {'ownership_uncertain': True}},
                       {'cleanup_confirmed': True}, 0, adapter.WHOLE_SECONDS), 'sticky')
        with patch.object(adapter, 'rss_high_water', return_value=dict(base_rss,
                child_cumulative_maxrss_bytes=adapter.RSS_BYTES + 1)):
            expect_failure(lambda: launch.terminal(adapter, {}, {'cleanup_confirmed': True},
                           0, adapter.WHOLE_SECONDS), 'RSS lower-bound')
        with patch.object(adapter, 'cpu_usage', return_value=adapter.WHOLE_SECONDS + 1):
            expect_failure(lambda: launch.terminal(adapter, {}, {'cleanup_confirmed': True},
                           0, adapter.WHOLE_SECONDS), 'CPU/wall')
        clock.now = adapter.WHOLE_SECONDS
        expect_failure(lambda: launch.terminal(adapter, {}, {'cleanup_confirmed': True},
                       0, adapter.WHOLE_SECONDS), 'CPU/wall')
    passed.append('terminal_rss_cpu_wall_and_sticky_uncertainty')
    return passed


def timer_handoff_mocks(manifest, budget, FakeClock):
    """Current worker main + exact original telemetry.start; all boundaries mocked."""
    worker_raw = read_checked(HERE / 'worker.py')
    worker_tree = ast.parse(worker_raw)
    need(not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and
                 isinstance(node.func.value, ast.Name) and node.func.value.id == 'signal'
                 for node in ast.walk(worker_tree)), 'worker must not own or reset a child alarm')
    main_node = next(node for node in worker_tree.body
                     if isinstance(node, ast.FunctionDef) and node.name == 'main')
    main_node = copy.deepcopy(main_node)
    replaced = 0
    for index, node in enumerate(main_node.body):
        if isinstance(node, ast.ImportFrom) and node.module == 'integration.startup_probe':
            need(len(node.names) == 1 and node.names[0].name == 'main' and
                 node.names[0].asname == 'run_main', 'single exact integration handoff import')
            main_node.body[index] = ast.copy_location(ast.Assign(
                targets=[ast.Name(id='run_main', ctx=ast.Store())],
                value=ast.Name(id='_mock_run_main', ctx=ast.Load())), node)
            replaced += 1
    need(replaced == 1, 'mock replaces only the one integration import, never worker gates')
    worker_code = compile(ast.fix_missing_locations(ast.Module(
        body=[main_node], type_ignores=[])), str(HERE / 'worker.py'), 'exec', dont_inherit=True)
    relative = 'candidates/qwen2_live_attention_model_m128_bounded/telemetry.py'
    telemetry_raw = read_checked(CANDIDATE / 'source' / relative,
        manifest['source_sha256'][relative], manifest['source_bytes'][relative])
    cls = next(node for node in ast.parse(telemetry_raw).body
               if isinstance(node, ast.ClassDef) and node.name == 'SparseTelemetry')
    start_node = next(node for node in cls.body
                      if isinstance(node, ast.FunctionDef) and node.name == 'start')
    start_code = compile(ast.Module(body=[start_node], type_ignores=[]),
                         'exact_original_telemetry_start_only', 'exec', dont_inherit=True)
    passed = []
    for label, occupied, expire_at_gate in (
            ('worker_empty_timer_real_telemetry_start', False, False),
            ('real_telemetry_existing_timer_fails_closed', True, False),
            ('worker_original_parent_stop_not_extended', False, True)):
        clock = FakeClock()
        clock.now = 100.0
        work_stop = clock.now + budget['inner_wall_seconds'] / 2
        whole_deadline = clock.now + budget['outer_wall_seconds']
        timer = {'value': (1.0, 0.0) if occupied else (0.0, 0.0), 'calls': []}
        def setitimer(kind, value):
            timer['calls'].append(('setitimer', kind, value))
            timer['value'] = (value, 0.0)
        fake_signal = types.SimpleNamespace(SIGALRM=14, SIGTERM=15, ITIMER_REAL=0,
            getitimer=lambda _: timer['value'], getsignal=lambda _: None,
            signal=lambda *args: timer['calls'].append(('signal', *args)), setitimer=setitimer)
        telemetry_ns = {'signal': fake_signal, 'time': clock}
        exec(start_code, telemetry_ns)
        entered = []
        def run_main(argv):
            entered.append(list(argv))
            need(not timer['calls'], 'worker touched timer before unchanged telemetry.start')
            receiver = types.SimpleNamespace(deadline=clock.now + budget['inner_wall_seconds'],
                _alarm=lambda *_: None, _terminate=lambda *_: None, active=False)
            telemetry_ns['start'](receiver)
            need(receiver.active, 'real telemetry.start did not acquire empty timer')
            return 0
        parent = dict(pid=101, start_ticks=777)
        hashes = dict(manifest='1' * 64, admission='2' * 64, budget='3' * 64)
        lease = dict(parent=parent, source_manifest_sha256=hashes['manifest'],
            admission_sha256=hashes['admission'], budget_sha256=hashes['budget'],
            out=str(OWNED / 'run01'), work_stop=work_stop, whole_deadline=whole_deadline)
        original_lease = copy.deepcopy(lease)
        def mocked_gate(*args, **kwargs):
            if expire_at_gate:
                clock.now = work_stop
        limits = []
        namespace = dict(__doc__='mock current worker handoff', argparse=argparse, math=math,
            os=types.SimpleNamespace(getppid=lambda: 101, sched_getaffinity=lambda _: {0},
                path=types.SimpleNamespace(lexists=lambda _: False),
                environ={'FIXED93_FULLBLOCK_PARENT_PID': '101',
                         'QWEN2_FIXED93_ADMISSION_SHA256': hashes['admission'],
                         'FIXED93_FULLBLOCK_SOURCE_SHA256': hashes['manifest'],
                         'FIXED93_FULLBLOCK_BUDGET_SHA256': hashes['budget']}),
            resource=types.SimpleNamespace(RLIMIT_CPU='CPU', RLIMIT_AS='AS',
                RLIMIT_FSIZE='FSIZE', RLIMIT_CORE='CORE',
                setrlimit=lambda *args: limits.append(args)), time=clock,
            sys=types.SimpleNamespace(path=[]), CANDIDATE=CANDIDATE, OWNED=OWNED,
            OUTPUT=types.SimpleNamespace(exists=lambda: False), need=need,
            read_budget=lambda _: dict(budget), actual_gate=mocked_gate,
            read_checked=lambda *args, **kwargs: json.dumps(lease).encode(),
            strict_json=json.loads, parent_identity=lambda _: dict(parent),
            _mock_run_main=run_main)
        # The source compares str(OUTPUT); use a harmless path with mocked exists.
        class OutputPath:
            def exists(self):
                return False
            def __str__(self):
                return str(OWNED / 'run01')
        namespace['OUTPUT'] = OutputPath()
        exec(worker_code, namespace)
        argv = ['--manifest-sha', hashes['manifest'], '--admission-sha', hashes['admission'],
                '--budget-sha', hashes['budget'], '--deadline', str(work_stop)]
        if occupied:
            expect_failure(lambda: namespace['main'](argv), 'existing timer cannot be replaced')
            need(len(entered) == 1 and not timer['calls'], 'occupied timer was replaced')
        elif expire_at_gate:
            expect_failure(lambda: namespace['main'](argv), 'original parent work deadline exhausted')
            need(not entered and not timer['calls'], 'expired parent lease reached integration')
        else:
            need(namespace['main'](argv) == 0 and len(entered) == 1 and len(limits) == 4,
                 'current worker did not preserve four child RLIMITs and reach telemetry')
            need(timer['calls'][-1][0] == 'setitimer', 'unchanged telemetry timer not installed')
        need(lease == original_lease and lease['work_stop'] == work_stop and
             lease['whole_deadline'] == whole_deadline, 'parent absolute deadlines changed')
        passed.append(label)
    return passed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest-sha', required=True)
    parser.add_argument('--budget-sha', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    need(adapter._BUDGET is None, 'cold starts with an unconfigured canonical adapter')
    prepared, manifest, _, _ = preflight(args.manifest_sha)
    need(adapter._BUDGET is None, 'production preflight consumed actual-only adapter configuration')
    budget = read_budget(args.budget_sha)
    expect_failure(lambda: validate_budget(dict(budget, status='OPEN')), 'not actual authority')
    expect_failure(lambda: validate_budget(dict(budget, rss_bytes=None)), 'positive integer')
    adapter.configure(budget)
    ci, support, base, _ = adapter.load_public()
    plan, hashes, old_hashes = projection_check(support, base)
    production = prepared['production_supervision_preflight']
    need(production['status'] == 'ASSEMBLED_REAL_PUBLIC_PROJECTION_NO_EXECUTION' and
         production['projection_hashes'] == hashes and production['limits'] == adapter.fixed_limits() and
         production['child_created'] is False and production['runtime_output_created'] is False,
         'cold must use the real production preflight projection and budget interface')
    Model, FakeClock = fixture_classes()
    out = Path(args.out).absolute()
    need(out.resolve() == out and not out.is_relative_to(OWNED) and not out.exists(),
         'separate fresh cold-output namespace required')
    out.mkdir(mode=0o700)
    passed = run_mocks(support, plan, out, Model, FakeClock)
    passed.extend(timer_handoff_mocks(manifest, budget, FakeClock))
    need(not ATTEMPTS and not OWNED.exists(), 'cold attempted actual/native boundary')
    result = dict(status='PASS_SOURCE_PROJECTION_AND_MOCK_ONLY',
        source_manifest_sha256=args.manifest_sha, budget_sha256=args.budget_sha,
        preflight=prepared, limits=adapter.fixed_limits(), projection_hashes=hashes,
        old_projection_hashes=old_hashes, projection_delta_verified=True, mock_cases=passed,
        actual_executed=False, real_child_created=False, numpy_imported=False,
        ctypes_imported=False, native_authorized=False, denied_boundary_attempts=ATTEMPTS,
        fullblock=False, M128_executed=False, RTL=False)
    with (out / 'RESULT.json').open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
