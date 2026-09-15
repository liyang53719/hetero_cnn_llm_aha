"""Apply hash-checked Chisel deltas to main without modifying a checkout."""
from pathlib import Path
import base64, gzip, hashlib, json, os, subprocess, uuid
folder = Path('development_snapshots/read_batch_20260915')
expected = ['7e42e94e511581f87bd543e220db67b3b0a3d36a', '5ca8504b167cfd11a63c3b8c95136311e2cb4759', '2437553089a10004bc65f448e4babc6f0c7c4b79', '4c5e27f3178e8ded7c0171759baf8c4fe6c05f91', 'ed349f3ac81d2bdd17d10934c2f030cfe32ddb69']
parts = []
for i, digest in enumerate(expected):
    data = (folder / ('piece%02d.b64' % i)).read_bytes()
    actual = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
    if actual != digest:
        raise SystemExit('PIECE_HASH_MISMATCH:' + str(i))
    parts.append(data.strip())
# The earlier unsplit changes.b64 is deliberately NOT an input. Its failed
# transport copy remains in Git history; only individually verified pieces apply.
raw = gzip.decompress(base64.b64decode(b''.join(parts), validate=True))
if hashlib.sha256(raw).hexdigest() != '2eef00c60e52259e0fa69b434266220fbfb7273b2ddab69b16f8826187b4d75c':
    raise SystemExit('BAD_PAYLOAD_HASH')
a = json.loads(raw)
entries = a['entries']
if len(entries) != 7 or len({e['path'] for e in entries}) != 7:
    raise SystemExit('BAD_ENTRY_COUNT')
for e in entries:
    p = e['path']
    if '..' in Path(p).parts or p.startswith('/') or p.endswith('.sv') or not p.startswith(('chisel/continuous_prefill/', 'reports/execution/IDMA_READ_BATCH_20260915/')):
        raise SystemExit('BAD_SCOPE:' + p)
def git(*args, env=None, data=None):
    return subprocess.check_output(['git', *args], env=env, input=data)
for attempt in range(3):
    subprocess.run(['git', 'fetch', '--no-tags', 'origin', 'main'], check=True)
    parent = git('rev-parse', 'origin/main').decode().strip()
    env = dict(os.environ, GIT_INDEX_FILE=str(Path.cwd() / ('read_batch_index_' + uuid.uuid4().hex)), GIT_AUTHOR_NAME='heteronpu-chisel-development', GIT_AUTHOR_EMAIL='heteronpu-verified@users.noreply.github.com', GIT_COMMITTER_NAME='heteronpu-chisel-development', GIT_COMMITTER_EMAIL='heteronpu-verified@users.noreply.github.com')
    git('read-tree', parent, env=env)
    changed = False
    for e in entries:
        p = e['path']
        old = subprocess.run(['git', 'show', parent + ':' + p], capture_output=True)
        if old.returncode == 0 and hashlib.sha256(old.stdout).hexdigest() == e['sha256']:
            continue
        if e['old_blob'] is None:
            if old.returncode == 0:
                raise SystemExit('REFUSE_OVERWRITE:' + p)
        elif old.returncode or git('hash-object', '--stdin', data=old.stdout).decode().strip() != e['old_blob']:
            raise SystemExit('BASE_DRIFT:' + p)
        git('apply', '--cached', '--whitespace=nowarn', '-', env=env, data=e['patch'].encode())
        changed = True
        if hashlib.sha256(git('show', ':' + p, env=env)).hexdigest() != e['sha256']:
            raise SystemExit('PATCH_HASH:' + p)
    if changed:
        tree = git('write-tree', env=env).decode().strip()
        commit = git('commit-tree', tree, '-p', parent, '-m', 'perf(chisel): batch checked iDMA reads across 16-beat segments; preserve actual component proof', env=env).decode().strip()
        if subprocess.run(['git', 'push', 'origin', commit + ':main']).returncode:
            continue
    else:
        commit = parent
    subprocess.run(['git', 'fetch', '--no-tags', 'origin', 'main'], check=True)
    subprocess.run(['git', 'merge-base', '--is-ancestor', commit, 'origin/main'], check=True)
    for e in entries:
        if hashlib.sha256(git('show', 'origin/main:' + e['path'])).hexdigest() != e['sha256']:
            raise SystemExit('REMOTE_BYTES:' + e['path'])
    Path('READ_BATCH_PUBLICATION.json').write_text(json.dumps({'commit': commit, 'files': 7, 'remote_bytes_verified': True, 'full_graph_accepted': False}, indent=2) + '\n')
    print('READ_BATCH_PUBLICATION', commit)
    break
else:
    raise SystemExit('FAST_FORWARD_PUSH_FAILED')
