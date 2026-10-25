"""Exact DUT supervisor. Reviewed PID/birth ownership core retained; no target import."""
import hashlib,json,os,signal,stat,time
from pathlib import Path

def need(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def file_id(path):
    p = Path(path)
    h = hashlib.sha256()
    count = 0
    with p.open('rb') as stream:
        before = os.fstat(stream.fileno())
        need(stat.S_ISREG(before.st_mode), 'not a regular file: ' + str(p))
        while data := stream.read(1048576):
            h.update(data)
            count += len(data)
        after = os.fstat(stream.fileno())
    need((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
         (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns),
         'file changed while hashing: ' + str(p))
    need(count == before.st_size, 'short file read: ' + str(p))
    return {'bytes': count, 'sha256': h.hexdigest()}


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + '\n').encode()


def write_new(path, value):
    raw = encoded(value)
    with Path(path).open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return {'bytes': len(raw), 'sha256': sha(raw)}


def read_checked(path, expected_sha, maximum=33554432):
    with Path(path).open('rb') as stream:
        raw = stream.read(maximum + 1)
    need(len(raw) <= maximum, 'JSON exceeds size boundary')
    need(sha(raw) == expected_sha, 'exact JSON SHA256 mismatch: ' + str(path))
    return json.loads(raw)


def process_stat(pid):
    try:
        raw = Path('/proc/%d/stat' % pid).read_text()
        tail = raw[raw.rfind(')') + 2:].split()
        return {'pid': pid, 'state': tail[0], 'ppid': int(tail[1]),
                'pgrp': int(tail[2]), 'start_ticks': int(tail[19]),
                'rss_bytes': int(tail[21]) * os.sysconf('SC_PAGE_SIZE'),
                'cpu_ticks': int(tail[11]) + int(tail[12])}
    except (FileNotFoundError, ProcessLookupError):
        return None


class OwnedIdentities(dict):
    """Current verified identities plus an append-only rebind audit trail."""
    def __init__(self):
        super().__init__()
        self.rebindings = []


def discover_tree(worker_pid, tracked):
    table = {}
    for entry in Path('/proc').iterdir():
        if entry.name.isdigit():
            try:
                row = process_stat(int(entry.name))
            except (OSError, ValueError, IndexError):
                continue
            if row:
                table[row['pid']] = row
    return expand_owned_tree(table, worker_pid, tracked, os.getpid())


def expand_owned_tree(table, worker_pid, tracked, parent_pid):
    """Never extend ancestry or group ownership through a reused process identity."""
    changed = True
    while changed:
        changed = False
        valid = {pid for pid, start in tracked.items()
                 if pid in table and table[pid]['start_ticks'] == start}
        group_confirmed = any(table[pid]['pgrp'] == worker_pid for pid in valid)
        for pid, row in table.items():
            if pid in valid:
                continue
            # A stale numeric PID is not a permanent tombstone. Rebind only
            # after proving this new identity belongs to the CURRENT owned tree.
            inherited = row['ppid'] in valid
            same_owned_group = group_confirmed and row['pgrp'] == worker_pid
            adopted_direct_child = row['ppid'] == parent_pid
            if inherited or same_owned_group or adopted_direct_child:
                previous = tracked.get(pid)
                if previous is not None and previous != row['start_ticks'] and hasattr(tracked, 'rebindings'):
                    tracked.rebindings.append({
                        'pid': pid, 'old_start_ticks': previous, 'new_start_ticks': row['start_ticks'],
                        'current_ppid': row['ppid'], 'current_pgrp': row['pgrp'],
                        'verified_current_parent': inherited, 'verified_current_group': same_owned_group,
                        'adopted_direct_child': adopted_direct_child})
                tracked[pid] = row['start_ticks']
                changed = True
    return {pid: row for pid, row in table.items()
            if pid in tracked and row['start_ticks'] == tracked[pid] and row['state'] != 'Z'}


def stop_owned(worker_pid, tracked):
    """Never signal a reused PID; group signal only while group leader identity matches."""
    active = discover_tree(worker_pid, tracked)
    leader = process_stat(worker_pid)
    if leader and leader['start_ticks'] == tracked.get(worker_pid) and leader['pgrp'] == worker_pid:
        try:
            os.killpg(worker_pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    for pid, record in active.items():
        current = process_stat(pid)
        if current and current['start_ticks'] == tracked[pid]:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    return sorted(active)


def total_output(out):
    total = 0
    for path in Path(out).rglob('*'):
        entry = path.lstat()
        need(not stat.S_ISLNK(entry.st_mode), 'output symlink forbidden: ' + str(path))
        if stat.S_ISREG(entry.st_mode):
            need(entry.st_nlink == 1, 'output hardlink forbidden: ' + str(path))
            total += entry.st_size
        else:
            need(stat.S_ISDIR(entry.st_mode), 'output special file forbidden: ' + str(path))
    return total


def manifest_postflight(manifest):
    """Independent complete rehash. Keep every difference, not just the first."""
    begin = time.monotonic()
    differences = {}
    checked_bytes = 0
    for path, expected in manifest.items():
        try:
            actual = file_id(path)
            checked_bytes += actual['bytes']
            if actual != expected:
                differences[path] = {'expected': expected, 'actual': actual}
        except (OSError, ValueError) as exc:
            differences[path] = {'expected': expected, 'error': type(exc).__name__ + ': ' + str(exc)}
    return {'passed': not differences, 'files_checked': len(manifest),
            'bytes_checked': checked_bytes, 'differences': differences,
            'wall_seconds': time.monotonic() - begin,
            'scope': 'full sealed file manifest after worker/descendant terminal state; outside worker budget'}




def terminal_output_snapshot(out):
    """Actual full-directory/log sizes, after workers have become terminal."""
    trace = out / 'dut/attention_service_events.q2evt'
    return {'output_bytes': total_output(out),
            'trace_bytes': trace.stat().st_size if trace.exists() else 0,
            'log_bytes': {name: (out / name).stat().st_size if (out / name).exists() else 0
                          for name in ('stdout.log', 'stderr.log')}}


def terminal_limit_reason(snapshot, resources):
    if snapshot['output_bytes'] > resources['output_bytes']:
        return 'terminal_output_limit_exceeded'
    if sum(snapshot['log_bytes'].values()) > resources['log_bytes']:
        return 'terminal_log_limit_exceeded'
    if snapshot['trace_bytes'] > resources['trace_bytes']:
        return 'terminal_trace_limit_exceeded'
    return None


def project_terminal_success(out, receipt, seal_template, resources):
    """Exact encoded receipt + seal sizes; no file writes or authority changes."""
    snapshot = terminal_output_snapshot(out)
    candidate = dict(receipt)
    candidate['terminal_output_budget'] = {
        'limit_bytes': resources['output_bytes'], 'before_parent_terminal_files': snapshot,
        'exact_receipt_and_seal_projection_required': True,
        'actual_staged_bytes_checked_before_success_seal': True,
        'exclusive_directory_assumption': 'Launcher-owned directory; worker and tracked descendants are terminal; no external writers during finalization.',
        'success_seal_publication': 'Byte-preserving atomic rename after complete staged-file size/hash/log checks; no later output-directory writes.',
        'failure_diagnostics_may_exceed_success_limit': True,
    }
    receipt_raw = encoded(candidate)
    receipt_identity = {'bytes': len(receipt_raw), 'sha256': sha(receipt_raw)}
    seal = dict(seal_template, receipt=receipt_identity)
    # Only decimal byte-count lengths are self-referential. Reach an exact
    # fixed point before any candidate terminal output is written.
    seal_bytes = projected_total = 0
    for _ in range(16):
        seal['terminal_output_budget'] = {
            'limit_bytes': resources['output_bytes'], 'base_output_bytes': snapshot['output_bytes'],
            'receipt_bytes': len(receipt_raw), 'completion_seal_bytes': seal_bytes,
            'final_output_bytes': projected_total, 'terminal_log_bytes': snapshot['log_bytes'],
            'terminal_trace_bytes': snapshot['trace_bytes'],
            'actual_staged_bytes_checked_before_success_seal': True,
        }
        seal_raw = encoded(seal)
        actual = (len(seal_raw), snapshot['output_bytes'] + len(receipt_raw) + len(seal_raw))
        if actual == (seal_bytes, projected_total):
            return {'receipt': candidate, 'receipt_identity': receipt_identity,
                    'seal': seal, 'seal_identity': {'bytes': len(seal_raw), 'sha256': sha(seal_raw)},
                    'snapshot': snapshot, 'projected_total_bytes': projected_total}
        seal_bytes, projected_total = actual
    raise ValueError('terminal output byte projection did not converge')


def write_failed_terminal(out, receipt, reason, resources):
    """Retain every candidate/worker artifact; FAIL diagnostics may exceed cap."""
    preserved = {}
    for name in ('RECEIPT.json', 'COMPLETION_SEAL.pending.json'):
        path = out / name
        if path.exists():
            rejected = out / (name + '.REJECTED')
            need(not rejected.exists(), 'rejected candidate target already exists')
            path.rename(rejected)
            preserved[rejected.name] = file_id(rejected)
    # This function never creates or removes a successful completion seal.
    need(not (out / 'COMPLETION_SEAL.json').exists(), 'failure cannot follow success publication')
    failed = dict(receipt, status='FAIL_EXACT_M128_DUT_RETAINED', passed=False,
                  observed_domain_passed=False, full29_numeric_pass=False, hardware_acceptance=False)
    failed['limit_reason'] = failed.get('limit_reason') or reason
    try:
        failure_snapshot = terminal_output_snapshot(out)
    except (OSError, ValueError) as exc:
        failure_snapshot = {'error': type(exc).__name__ + ': ' + str(exc)}
    failed['terminal_output_budget'] = {
        'passed': False, 'limit_bytes': resources['output_bytes'],
        'before_failure_diagnostics': failure_snapshot,
        'failure_reason': reason, 'preserved_rejected_candidates': preserved,
        'failure_diagnostics_may_exceed_success_limit': True,
        'no_artifacts_deleted_to_fit_limit': True,
        'success_seal_created': False,
    }
    write_new(out / 'RECEIPT.json', failed)
    return failed, False


def finalize_terminal_output(out, receipt, resources, seal_template=None, completion_path=None):
    """Close the success output budget before publishing the sole parent seal.

    Precondition: workers/descendants are terminal and this directory has no
    external writers. A pending candidate is not a completion seal. Publishing
    it by rename is the last directory mutation on the successful path.
    """
    if not receipt['passed']:
        return write_failed_terminal(out, receipt, receipt.get('limit_reason') or 'earlier_gate_failed', resources)
    try:
        need(completion_path == out / 'COMPLETION_SEAL.json', 'exact completion seal destination required')
        need(not completion_path.exists(), 'completion seal already exists')
        need(not (out / 'RECEIPT.json').exists() and not (out / 'COMPLETION_SEAL.pending.json').exists(),
             'terminal candidate path already exists')
        projection = project_terminal_success(out, receipt, seal_template, resources)
        reason = terminal_limit_reason(projection['snapshot'], resources)
        need(reason is None, reason or 'terminal limits failed')
        need(projection['projected_total_bytes'] <= resources['output_bytes'],
             'projected_final_output_limit_exceeded')
        receipt_id = write_new(out / 'RECEIPT.json', projection['receipt'])
        pending = out / 'COMPLETION_SEAL.pending.json'
        seal_id = write_new(pending, projection['seal'])
        need(receipt_id == projection['receipt_identity'] and seal_id == projection['seal_identity'],
             'terminal encoded output identity changed')
        actual = terminal_output_snapshot(out)
        reason = terminal_limit_reason(actual, resources)
        need(reason is None, reason or 'terminal limits failed after writes')
        need(actual['output_bytes'] == projection['projected_total_bytes']
             and actual['log_bytes'] == projection['snapshot']['log_bytes']
             and actual['trace_bytes'] == projection['snapshot']['trace_bytes'],
             'terminal output changed after exact projection')
        need(file_id(out / 'RECEIPT.json') == projection['receipt_identity']
             and file_id(pending) == projection['seal_identity'], 'staged terminal bytes changed')
        # No process can write here under the stated ownership precondition.
        # The final path publication changes no byte count and adds no output.
        pending.rename(completion_path)
        return projection['receipt'], True
    except (OSError, ValueError, TypeError) as exc:
        return write_failed_terminal(out, receipt, 'terminal_finalization:' + str(exc), resources)



class TreeCpuSamples:
    """Observed per-birth CPU high-water sum, NOT a kernel tree CPU quota.

    Exited processes missed between polls may be absent. Per-process RLIMIT_CPU
    plus final RUSAGE_CHILDREN supplement this sampled accounting.
    """
    def __init__(self):
        self.ticks = {}
        self.hz = os.sysconf('SC_CLK_TCK')

    def observe(self, tracked):
        for pid, birth in list(tracked.items()):
            row = process_stat(pid)
            if row and row['start_ticks'] == birth:
                key = (pid, birth)
                self.ticks[key] = max(self.ticks.get(key, 0), row['cpu_ticks'])
        return sum(self.ticks.values()) / self.hz

    def report(self):
        return {'sampled_aggregate_cpu_seconds': sum(self.ticks.values()) / self.hz,
                'clock_ticks_per_second': self.hz,
                'identity_high_water_ticks': [dict(pid=p, start_ticks=b, cpu_ticks=t)
                    for (p, b), t in sorted(self.ticks.items())],
                'kernel_aggregate_tree_cpu_hard_cap': False,
                'short_lived_unsampled_processes_may_be_missing': True}


def artifact_manifest(out):
    # Validate every object before opening any evidence file.
    total_output(out)
    return {str(p.relative_to(out)): file_id(p) for p in sorted(Path(out).rglob('*')) if p.is_file()}
