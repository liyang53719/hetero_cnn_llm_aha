"""Sampled, inode-deduplicated job-local byte/deadline admission. No cleanup.
Call while holding the SAME exclusive job lock used by the stage supervisor.
Admission reserves a caller-reviewed enforced maximum increment, NOT a predicted
or proven peak. The caller must retain the existing supervisor caps throughout
execution. This census is not an atomic filesystem snapshot or cgroup guarantee.
"""
import math
import os
from pathlib import Path
import shutil
import stat
import time

TREE_CAP = 12_081_306_272
FREE_RESERVE = 1_500_000_000
ACQUISITION_FLOOR = 8 * 1024**3
JOB_SECONDS = 21_000

def need(v, message):
    if not v:
        raise ValueError(message)

def integer(v, name):
    need(type(v) is int and v >= 0, name)
    return v

def finite(v, name):
    need(type(v) in (int, float) and math.isfinite(v) and v >= 0, name)
    return v

def roots_checked(roots):
    need(type(roots) in (tuple, list) and 0 < len(roots) <= 64, 'bounded explicit owned roots')
    values = []
    for raw in roots:
        p = Path(raw)
        need(p.is_absolute() and '..' not in p.parts, 'absolute canonical owned root')
        need(not any(q.is_symlink() for q in (p, *p.parents)), 'root alias forbidden')
        need(p.is_dir(), 'existing owned root required')
        values.append(p)
    result = []
    for p in sorted(set(values), key=lambda q: (len(q.parts), str(q))):
        if not any(p.is_relative_to(q) for q in result):
            result.append(p)
    return result

def census(roots, *, max_entries=100_000, max_seconds=60):
    """No symlink traversal; hardlinks counted once. Special files fail closed.
    A missing/changed entry during traversal fails rather than yielding a partial
    usable snapshot. Directory aliases are counted, not traversed. Their targets
    MUST be covered independently by the calling job's source/runtime contract.
    """
    integer(max_entries, 'max entries'); finite(max_seconds, 'max census seconds')
    need(max_entries > 0 and max_seconds > 0, 'positive census bounds')
    roots = roots_checked(roots)
    started = time.monotonic(); seen = set(); seen_dirs = set()
    count = files = links = total = 0; stack = list(roots)
    while stack:
        need(time.monotonic() - started <= max_seconds, 'census deadline')
        directory = stack.pop()
        ds = directory.lstat(); need(stat.S_ISDIR(ds.st_mode), 'directory changed')
        di = (ds.st_dev, ds.st_ino)
        if di in seen_dirs:
            continue
        seen_dirs.add(di)
        with os.scandir(directory) as entries:
            for entry in entries:
                count += 1
                need(count <= max_entries, 'entry census cap')
                need(time.monotonic() - started <= max_seconds, 'census deadline')
                s = entry.stat(follow_symlinks=False)
                if stat.S_ISLNK(s.st_mode):
                    links += 1
                elif stat.S_ISDIR(s.st_mode):
                    stack.append(Path(entry.path))
                elif stat.S_ISREG(s.st_mode):
                    identity = (s.st_dev, s.st_ino)
                    if identity not in seen:
                        seen.add(identity); files += 1; total += s.st_size
                else:
                    raise ValueError('nonregular owned entry')
    free = min(shutil.disk_usage(p).free for p in roots)
    finished = time.monotonic()
    return dict(schema='SAMPLED_OWNED_LIVE_BYTES_V1', roots=[str(p) for p in roots],
                bytes=total, files=files, entries=count, symlinks_not_followed=links,
                free_bytes=free, started_monotonic=started, finished_monotonic=finished,
                elapsed_seconds=finished-started, complete=True,
                resource_peak_qualification='INCOMPLETE_SAMPLED_NOT_CONTINUOUS')

def admit(snapshot, *, extra_bytes, phase_seconds, job_started, now=None,
          acquisition=False, cleanup_seconds=60, max_snapshot_age=2, job_seconds=JOB_SECONDS):
    """Reserve declared bounded increment and full phase wall+cleanup allowance.
    Caller must supply a fresh locked census. No default per-profile DUT budget:
    no measured DUT rate means no automatic full-five runtime admission.
    """
    need(type(job_seconds)is int and 0<job_seconds<=2**31-1, 'finite separately admitted lifecycle')
    now = time.monotonic() if now is None else now
    finite(now, 'now'); finite(job_started, 'job start')
    integer(extra_bytes, 'reviewed extra byte reservation')
    finite(phase_seconds, 'phase wall'); finite(cleanup_seconds, 'cleanup wall')
    finite(max_snapshot_age, 'snapshot age')
    need(phase_seconds > 0 and cleanup_seconds >= 30, 'finite phase and cleanup reserve')
    need(type(acquisition) is bool, 'acquisition flag')
    need(snapshot.get('schema') == 'SAMPLED_OWNED_LIVE_BYTES_V1' and snapshot.get('complete') is True, 'complete owned census')
    live = integer(snapshot['bytes'], 'live bytes'); free = integer(snapshot['free_bytes'], 'free bytes')
    finished = finite(snapshot['finished_monotonic'], 'census finish')
    need(0 <= now-finished <= max_snapshot_age, 'stale/future census')
    need(0 <= now-job_started <= job_seconds, 'job deadline')
    need(live+extra_bytes <= TREE_CAP, 'owned aggregate allocation exceeds cap')
    need(free-extra_bytes >= FREE_RESERVE, 'disk reserve after allocation')
    if acquisition:
        need(free >= ACQUISITION_FLOOR, 'original 8GiB acquisition floor')
    remaining = job_seconds-(now-job_started)
    need(phase_seconds+cleanup_seconds <= remaining, 'insufficient remaining job wall')
    return dict(schema='PHASE_LIVE_ADMISSION_V1', status='ADMITTED_BOUNDED_PHASE_NOT_PEAK_PROOF',
                live_bytes=live, reserved_increment_bytes=extra_bytes,
                resulting_byte_ceiling=live+extra_bytes, free_before_bytes=free,
                phase_seconds=phase_seconds, cleanup_seconds=cleanup_seconds,
                remaining_job_seconds=remaining, acquisition=acquisition,
                resource_peak_qualification='INCOMPLETE_SAMPLED_NOT_CONTINUOUS')
