"""Separate fresh-host entry identity. No numerical execution on import."""
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import subprocess
import time

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
PREFIX = 'candidates/qwen2_resident_matrix/attention_packed_m128_same_host/'
PROFILE = 'qwen2-public-pv16-packed-m128-same-host-v1'
SOURCE_FILE = 'SOURCE_CONTRACT.json'
NUMERIC_SECONDS = 2400
WORK_SECONDS = 2424
CLEANUP_SECONDS = 2429
OUTER_SECONDS = 2430
_ABSENT = object()


def need(value, message):
    if not value:
        raise ValueError(message)


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)+'\n').encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(value):
    return type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def commit(value):
    return type(value) is str and len(value) == 40 and all(c in '0123456789abcdef' for c in value)


def safe(path, *, directory=False):
    path = Path(path)
    need(path.is_absolute() and '..' not in path.parts, 'absolute canonical path required')
    current = Path(path.anchor)
    for component in path.parts[1:]:
        current /= component
        need(not current.is_symlink(), 'symlink path rejected')
    info = path.stat()
    need(stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode) and info.st_nlink == 1,
         'path kind or hardlink alias differs')
    return path.resolve(strict=True)


def read_json(path, expected=None, *, limit=2*1024*1024):
    path = safe(path)
    need(path.stat().st_size <= limit, 'bounded metadata required')
    raw = path.read_bytes()
    need(len(raw) <= limit and (expected is None or digest(expected) and sha(raw) == expected),
         'metadata hash differs')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            need(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    value = json.loads(raw, object_pairs_hook=unique)
    encoded(value)
    return value


def source_contract():
    value = read_json(HERE/SOURCE_FILE)
    need(type(value) is dict and set(value) == {'schema','profile','git_head','sources','scope'},
         'exact fresh-host source contract')
    need(type(value['schema']) is int and value['schema'] == 1 and value['profile'] == PROFILE and
         commit(value['git_head']) and value['scope'] == 'FRESH_M128_ASSIGNED27_ONLY',
         'fresh-host source profile')
    sources = value['sources']
    need(type(sources) is dict and sources and PREFIX+SOURCE_FILE not in sources,
         'acyclic fresh-host source closure')
    for name, expected in sources.items():
        need(type(name) is str and name and '\\' not in name and '\x00' not in name and
             not Path(name).is_absolute() and all(p not in ('','.','..') for p in name.split('/')) and
             digest(expected), 'source entry schema')
    return value


def snapshot():
    value = source_contract()
    sources = dict(value['sources'])
    for name, expected in sources.items():
        need(sha(safe(ROOT/name).read_bytes()) == expected, 'fresh-host source drift: '+name)
    sources[PREFIX+SOURCE_FILE] = sha((HERE/SOURCE_FILE).read_bytes())
    return sources


def modes(*, fresh_profile, enable_raw_kv, enable_packed=_ABSENT, rows=_ABSENT):
    need(fresh_profile is True and enable_raw_kv is True, 'explicit fresh-host raw profile required')
    if enable_packed is not _ABSENT:
        need(enable_packed is True, 'explicit packed profile required')
    if rows is not _ABSENT:
        need(type(rows) is int and rows == 128, 'fresh-host entry is canonical M128 only')
    return snapshot()


def git_context():
    expected = source_contract()['git_head']
    need((ROOT/'.git').exists() and not (ROOT/'.git').is_symlink() and all(k not in os.environ for k in
         ('GIT_DIR','GIT_WORK_TREE','GIT_INDEX_FILE','GIT_OBJECT_DIRECTORY','GIT_ALTERNATE_OBJECT_DIRECTORIES')),
         'genuine Git context without redirection required')
    def git(*args):
        return subprocess.run(['git',*args], cwd=ROOT, capture_output=True, check=True, timeout=5).stdout
    need(Path(git('rev-parse','--show-toplevel').decode().strip()).resolve() == ROOT, 'Git root differs')
    head = git('rev-parse','HEAD').decode().strip()
    need(head == expected, 'fresh invocation Git commit differs')
    name = 'chisel/continuous_prefill/tests/qwen2_block.cpp'
    raw = git('show','HEAD:'+name)
    need(raw == safe(ROOT/name).read_bytes(), 'committed original scalar arithmetic differs')
    return dict(commit=head, arithmetic_sha256=sha(raw))


def authorize_run(context):
    """Check a parent-owned invocation, never infer authority from producer JSON.

    The external reviewed supervisor must authenticate and inject this context;
    this structural guard is not a signature or a replacement for that boundary.
    """
    need(type(context) is dict and set(context) == {'profile','attempt','pid','parent_pid','started',
         'work_deadline','outer_deadline','source_manifest_sha256','producer_receipt_sha256','attempt_nonce','m16_prerequisite_sha256'},
         'exact external execution context required')
    need(context['profile'] == PROFILE and type(context['attempt']) is int and context['attempt'] == 1 and
         type(context['pid']) is int and context['pid'] == os.getpid() and
         type(context['parent_pid']) is int and context['parent_pid'] == os.getppid(),
         'same supervised single-attempt child required')
    need(all(type(context[k]) in (int,float) and math.isfinite(context[k]) and context[k] > 0 for k in
             ('started','work_deadline','outer_deadline')), 'finite monotonic deadlines required')
    need(context['work_deadline'] == context['started']+WORK_SECONDS and
         context['outer_deadline'] == context['started']+OUTER_SECONDS and
         context['started'] <= time.monotonic() < context['work_deadline'], 'original full-M128 budget exhausted')
    need(digest(context['producer_receipt_sha256']) and digest(context['attempt_nonce']) and
         digest(context['m16_prerequisite_sha256']),
         'parent-qualified producer binding required')
    sources = snapshot()
    git_context()
    need(context['source_manifest_sha256'] == sha(encoded(sources)), 'execution/source binding differs')
    need(time.monotonic() < context['work_deadline'], 'source admission exceeded deadline')
    return sources
