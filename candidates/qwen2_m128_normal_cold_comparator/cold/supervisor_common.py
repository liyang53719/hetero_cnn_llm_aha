"""Generic evidence/PID supervisor functions copied from reviewed reference r3. No target import."""
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
    raw = Path(path).read_bytes()
    need(len(raw) <= maximum, 'JSON exceeds size boundary')
    need(sha(raw) == expected_sha, 'exact JSON SHA256 mismatch: ' + str(path))
    return json.loads(raw)


def process_stat(pid):
    try:
        raw = Path('/proc/%d/stat' % pid).read_text()
        tail = raw[raw.rfind(')') + 2:].split()
        return {'pid': pid, 'state': tail[0], 'ppid': int(tail[1]),
                'pgrp': int(tail[2]), 'start_ticks': int(tail[19]),
                'rss_bytes': int(tail[21]) * os.sysconf('SC_PAGE_SIZE')}
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
    return sum(p.stat().st_size for p in out.rglob('*') if p.is_file() and not p.is_symlink())


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


