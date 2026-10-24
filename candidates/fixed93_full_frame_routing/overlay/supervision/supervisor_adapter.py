"""0936 resource adapter copied for a NEW explicitly reviewed fullblock budget.

Import is stdlib-only and does not load public code, spawn, or run numerical work.
The public projected bounded/observe_exit/group_state code is never rewritten here.
"""
import copy
import json
import math
import os
from pathlib import Path
import resource
import signal
import stat
import subprocess
import time
import types

from gate import (HERE, SUPPORT, need, read_checked, validate_budget,
                  fixed_limits as budget_limits, RECEIPT_BYTES, LOG_FILE_BYTES,
                  SAMPLE_LINE_BYTES)

SUPPORT_ROOT = SUPPORT
CI_RELATIVE = 'ci_support_v3_long.py'
CI_BYTES = 16349
CI_SHA = '1c48470e6571dc425f7aee7c5e9f1153272d9cbd63b8cf6bfa60f5a7d30d6986'
WHOLE_SECONDS = None
WORK_SECONDS = None
CLEANUP_SECONDS = 5
POST_SECONDS = 10
RSS_BYTES = None
OUTPUT_BYTES = None
FILE_BYTES = None
RECEIPT_RESERVE_BYTES = None
LOG_BYTES = None
_BUDGET = None
# Pinned public sampler: first row immediately, then next = now + 1.
# No catch-up or additional forced terminal row is emitted. In a closed window
# of T seconds, at most floor(T / interval) + 1 leader rows can be written.
LEADER_SAMPLE_INTERVAL_SECONDS = 1
PUBLIC_SAMPLER_CONTRACT_ERRORS = frozenset((
    'sample sink required',
    'leader sample row cap exceeded',
    'leader sample line cap',
))

def configure(budget):
    """Install a validated reviewed budget exactly once; no historical fallback."""
    global WHOLE_SECONDS, WORK_SECONDS, RSS_BYTES, OUTPUT_BYTES, FILE_BYTES
    global RECEIPT_RESERVE_BYTES, LOG_BYTES, _BUDGET
    need(_BUDGET is None, 'supervisor budget is one-use')
    value = validate_budget(budget)
    WHOLE_SECONDS, WORK_SECONDS = value['outer_wall_seconds'], value['inner_wall_seconds']
    RSS_BYTES, OUTPUT_BYTES = value['rss_bytes'], value['output_bytes']
    FILE_BYTES, LOG_BYTES = value['file_bytes'], value['log_bytes']
    RECEIPT_RESERVE_BYTES = value['supervisor_receipt_reserve_bytes']
    _BUDGET = value


def load_public():
    raw = read_checked(HERE / CI_RELATIVE, CI_SHA, CI_BYTES)
    module = types.ModuleType('pinned_public_ci_support_v3')
    module.__file__ = str(HERE / CI_RELATIVE)
    exec(compile(raw, module.__file__, 'exec', dont_inherit=True), module.__dict__)
    support, base, pins = module.fixed_support(SUPPORT_ROOT)
    return module, support, base, pins


def fixed_limits():
    need(_BUDGET is not None, 'no reviewed wholeblock supervisor budget installed')
    return budget_limits(_BUDGET)


def cpu_usage():
    own = resource.getrusage(resource.RUSAGE_SELF)
    children = resource.getrusage(resource.RUSAGE_CHILDREN)
    return own.ru_utime + own.ru_stime + children.ru_utime + children.ru_stime


def rss_high_water():
    # RUSAGE maxrss is a cumulative per-process maximum lower bound, not
    # concurrent whole-tree RSS. It still catches a quick-exit RSS excess.
    own = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
    children = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss * 1024
    need(all(type(value) in (int, float) and math.isfinite(value) and value >= 0
             for value in (own, children)), 'invalid final maxrss')
    return dict(supervisor_maxrss_bytes=own, child_cumulative_maxrss_bytes=children,
                scope='cumulative per-process maximum lower bound; not concurrent tree peak')


def owned_inventory(root, *, cap=None, reserve=0, live=False):
    """Stat-only whole-owned accounting, including receipt temporaries and logs.

    Never hash/read growing model payloads during the public observation loop.
    """
    fixed_limits()
    cap = OUTPUT_BYTES if cap is None else cap
    root = Path(root)
    need(0 <= reserve < cap, 'invalid owned reserve')
    need(not any(p.is_symlink() for p in (root, *root.parents)), 'owned path alias')
    need(root.is_dir(), 'owned root required')
    total = logs = entries = files = 0
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            scan = os.scandir(directory)
        except FileNotFoundError:
            if live:
                continue
            raise
        with scan:
            for entry in scan:
                entries += 1
                need(entries <= 8192, 'owned entry cap')
                try:
                    info = entry.stat(follow_symlinks=False)
                except FileNotFoundError:
                    if live:
                        continue
                    raise
                need(not entry.is_symlink(), 'owned symlink refused')
                if stat.S_ISDIR(info.st_mode):
                    pending.append(Path(entry.path))
                    continue
                need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1,
                     'owned special/hardlinked file refused')
                files += 1
                need(files <= 4096, 'owned regular file cap')
                need(0 <= info.st_size <= FILE_BYTES, 'owned single file cap')
                total += info.st_size
                if entry.name.endswith('.log'):
                    need(info.st_size <= LOG_FILE_BYTES, 'owned individual 32KiB log cap')
                    logs += info.st_size
                if entry.name == 'leader_samples.jsonl':
                    need(info.st_size <= fixed_limits()['sample_rows'] * SAMPLE_LINE_BYTES,
                         'leader sample whole-file cap')
                need(total <= cap - reserve, 'OWNED_OUTPUT_LIMIT')
                need(logs <= LOG_BYTES, 'WHOLE_LOG_LIMIT')
    return dict(bytes=total, log_bytes=logs, files=files, entries=entries)


def checked_save(path, value, owned_root, *, live=False):
    """Account for the temporary and final receipt before and after writing."""
    path = Path(path)
    need(path.is_relative_to(owned_root), 'receipt outside owned root')
    raw = (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()
    need(len(raw) <= RECEIPT_BYTES, 'supervisor receipt 32KiB cap')
    temporary = path.with_name(path.name + '.tmp')
    need(not os.path.lexists(temporary), 'receipt temporary already exists')
    current = owned_inventory(owned_root, live=live)
    need(current['bytes'] + len(raw) <= OUTPUT_BYTES, 'receipt temporary whole cap')
    with temporary.open('xb') as stream:
        stream.write(raw)
        stream.flush()
    temporary.replace(path)
    owned_inventory(owned_root, live=live)


def _proc_row(raw, expected_pid):
    text = raw.decode('ascii')
    prefix, sep, rest = text.rpartition(') ')
    fields = rest.split()
    need(sep and prefix.split(' ', 1)[0] == str(expected_pid) and len(fields) >= 22,
         'proc stat shape')
    row = dict(pid=expected_pid, state=fields[0], ppid=int(fields[1]),
               pgrp=int(fields[2]), session=int(fields[3]),
               ticks=sum(int(fields[i]) for i in (11, 12, 13, 14)),
               start=int(fields[19]), rss_pages=int(fields[21]))
    need(row['ticks'] >= 0 and row['start'] >= 0 and row['rss_pages'] >= 0,
         'negative proc metric')
    return row


def tree_stats(root_pid, state, proc_root=Path('/proc')):
    """Sample group plus descendant identities, retaining earlier owned rows.

    Missing raced-away /proc entries are normal; unreadable/invalid samples fail.
    CPU includes waited children counters, not only currently live child CPU.
    """
    rows = {}
    with os.scandir(proc_root) as scan:
        for entry in scan:
            if not entry.name.isdecimal():
                continue
            pid = int(entry.name)
            try:
                raw = (Path(entry.path) / 'stat').read_bytes()
            except (FileNotFoundError, ProcessLookupError):
                continue
            rows[pid] = _proc_row(raw, pid)
    need(root_pid in rows, 'unreaped leader missing from sampled tree')
    leader = rows[root_pid]
    identity = (root_pid, leader['start'])
    if state.get('leader') is None:
        state['leader'] = identity
    need(identity == state['leader'], 'sampled leader identity changed')
    need(leader['pgrp'] == root_pid and leader['session'] == root_pid,
         'leader is not owned process-group/session anchor')
    prior = state.setdefault('owned', {})
    owned = {pid for pid, row in rows.items()
             if row['pgrp'] == root_pid or row['session'] == root_pid or
             prior.get(pid) == row['start']}
    owned.add(root_pid)
    while True:
        added = {pid for pid, row in rows.items() if row['ppid'] in owned}
        if added <= owned:
            break
        owned.update(added)
    for pid in owned:
        row = rows[pid]
        if row['pgrp'] != root_pid or row['session'] != root_pid:
            state['ownership_uncertain'] = True
            raise ValueError('OWNED_PROCESS_GROUP_ESCAPE')
        prior[pid] = row['start']
    # Recheck the anchor after the entire scan, without consuming its wait status.
    after = _proc_row((proc_root / str(root_pid) / 'stat').read_bytes(), root_pid)
    need((after['pid'], after['start']) == identity, 'tree scan anchor changed')
    page = os.sysconf('SC_PAGE_SIZE')
    hz = os.sysconf('SC_CLK_TCK')
    need(type(page) is int and page > 0 and type(hz) is int and hz > 0,
         'proc unit contract')
    # The supervisor is included too, tightening the prior child-only RSS bound.
    parent = rows.get(os.getpid())
    need(parent is not None, 'supervisor memory sample missing')
    rss = sum(rows[pid]['rss_pages'] for pid in owned) + parent['rss_pages']
    live_descendants = sorted(pid for pid in owned if pid != root_pid and
                              rows[pid]['state'] not in ('Z', 'X'))
    return dict(pids=sorted(owned), rss_bytes=rss * page,
                cpu_seconds=sum(rows[pid]['ticks'] for pid in owned) / hz,
                leader_state=after['state'], live_descendant_pids=live_descendants)


def adapt_runner(runner, *, owned_root, stdout, stderr, work_stop,
                 cpu_baseline, state, tree_sampler=tree_stats):
    """Adapters change dependencies only; public supervisory functions stay exact."""
    published_sample = runner['sample_leader']
    published_popen = runner['subprocess'].Popen
    process_api = runner['subprocess']
    state.setdefault('tree', {})
    state.setdefault('peak_rss_bytes', 0)
    state.setdefault('sample_count', 0)
    state.setdefault('peak_owned_bytes', 0)

    def sample(child):
        # Public WNOWAIT observation checks identity before calling this adapter,
        # including when the leader has exited before its very first sample.
        try:
            published_sample(child)
        except BaseException as error:
            # A known row/sink/line-cap failure still fails the invocation, but
            # does not prove a process escaped or invalidate anchored cleanup.
            # Identity changes and unknown read/parse errors remain fail-closed.
            if not (isinstance(error, ValueError) and
                    str(error) in PUBLIC_SAMPLER_CONTRACT_ERRORS):
                state['tree']['ownership_uncertain'] = True
            raise
        try:
            current = tree_sampler(child.pid, state['tree'])
        except BaseException:
            state['tree']['ownership_uncertain'] = True
            raise
        state['sample_count'] += 1
        state['peak_rss_bytes'] = max(state['peak_rss_bytes'], current['rss_bytes'])
        # A successful leader may not hide an unreaped live compiler/worker.
        # This admission failure is independent of subsequent safe cleanup.
        if current['leader_state'] in ('Z', 'X') and current['live_descendant_pids']:
            state['terminal_live_descendant_pids'] = list(current['live_descendant_pids'])
            raise ValueError('LIVE_DESCENDANT_AT_LEADER_EXIT')
        need(current['rss_bytes'] <= RSS_BYTES, 'SAMPLED_TREE_RSS_LIMIT')
        need(cpu_usage() - cpu_baseline + current['cpu_seconds'] <= WHOLE_SECONDS,
             'WHOLE_CPU_LIMIT')
        totals = owned_inventory(owned_root, reserve=RECEIPT_RESERVE_BYTES, live=True)
        state['peak_owned_bytes'] = max(state['peak_owned_bytes'], totals['bytes'])
        need(time.monotonic() < work_stop, 'WHOLE_ENTRY_WORK_LIMIT')

    def popen(*args, **kwargs):
        # Keep the existing launcher stdout/stderr file interface. The public
        # native.log remains an empty owned file, rather than duplicating logs.
        kwargs = dict(kwargs)
        kwargs['stdout'], kwargs['stderr'] = stdout, stderr
        return published_popen(*args, **kwargs)

    runner['sample_leader'] = sample
    runner['subprocess'] = types.SimpleNamespace(
        Popen=popen, STDOUT=process_api.STDOUT, TimeoutExpired=process_api.TimeoutExpired)
    runner['save'] = lambda path, value: checked_save(path, value, owned_root, live=True)
    return runner


def run_admitted(command, cwd, evidence, environment, owned_root, stdout, stderr,
                 shared_stop, owner, cpu_baseline, state, diagnostics, *, work_stop):
    ci, support, base, pins = load_public()
    need(time.monotonic() < work_stop <= shared_stop - CLEANUP_SECONDS - POST_SECONDS,
         'same whole-entry work deadline required')
    state['work_stop'] = work_stop
    state['source_pins'] = pins
    original_make_runner = support.make_runner

    def make_runner(plan, phase, output):
        runner = original_make_runner(plan, phase, output)
        state['projection_hashes'] = dict(runner['projection_hashes'])
        need(state['projection_hashes'] == state.get('reviewed_projection_hashes'),
             'actual supervisor projection differs from same-budget reviewed cold')
        return adapt_runner(runner, owned_root=owned_root, stdout=stdout, stderr=stderr,
                            work_stop=work_stop, cpu_baseline=cpu_baseline, state=state)

    # The copied public support is an ephemeral module, not the pinned source.
    support.make_runner = make_runner
    return ci.run_phase(support, base, 'micro', list(command), Path(cwd),
                        Path(evidence), dict(environment), fixed_limits(), shared_stop,
                        owner=owner, diagnostics=diagnostics)
