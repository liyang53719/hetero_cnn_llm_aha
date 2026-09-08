#!/usr/bin/env python3
"""Install exact source bytes, retaining explicitly reviewed concurrent edits."""
from pathlib import Path, PurePosixPath
import base64, hashlib, json, lzma, os, subprocess, uuid
HERE = Path(__file__).resolve().parent
EXPECTED = '4a168e11b4b61df1fc5ad3cddcac9ccb232cb4e389d8a0c682fb1245c1e84078'
def need(ok, text):
    if not ok: raise RuntimeError(text)
def sha(data): return hashlib.sha256(data).hexdigest()
def git(*args, data=None, env=None):
    return subprocess.check_output(['git', *args], input=data, env=env)
def read(ref, name):
    p = subprocess.run(['git', 'show', ref + ':' + name], capture_output=True)
    return p.stdout if p.returncode == 0 else None
def edit(original, edits):
    lines = original.decode('utf-8').splitlines(keepends=True)
    previous = len(lines) + 1
    for begin,end,text in reversed(edits):
        need(type(begin) is int and type(end) is int and 0 <= begin <= end < previous, 'INVALID_EDIT')
        previous = begin + 1
        lines[begin:end] = [text]
    return ''.join(lines).encode('utf-8')
compressed = base64.b64decode(''.join((HERE / ('part%02d.b64' % i)).read_text().strip() for i in range(2)), validate=True)
need(sha(compressed) == EXPECTED, 'CORRUPTED_SOURCE_CAPSULE')
raw = lzma.decompress(compressed, memlimit=128*1024*1024)
need(len(raw) == 51297, 'WRONG_CAPSULE_SIZE')
payload = json.loads(raw); files = payload['files']
merges = json.loads((HERE/'reviewed_merge.json').read_text())
need(len(files) == 18 and set(merges) <= set(files), 'INCOMPLETE_SOURCE_CHANGESET')
expected = {name: merges.get(name, change)['sha256'] for name,change in files.items()}
for name in files:
    p = PurePosixPath(name)
    need(name.startswith('chisel/continuous_prefill/') and not p.is_absolute() and '..' not in p.parts, 'INVALID_PATH')
    need(p.suffix in {'.scala','.py','.sh','.cpp','.inc','.h','.vlt'}, 'NO_DIRECT_RTL_EDITS')
for attempt in range(3):
    subprocess.run(['git','fetch','--no-tags','origin','main'], check=True)
    parent = git('rev-parse','origin/main').decode().strip()
    subprocess.run(['git','merge-base','--is-ancestor',payload['base_commit'],parent], check=True)
    current = {name: read(parent,name) for name in files}
    if all(data is not None and sha(data) == expected[name] for name,data in current.items()):
        commit = parent; break
    materialized = {}
    for name,change in files.items():
        existing = current[name]
        previous = merges[name]['current_sha256'] if name in merges else change['old_sha256']
        need((None if existing is None else sha(existing)) == previous, 'CONCURRENT_TARGET_CHANGE:' + name)
        original = read(payload['base_commit'],change['source']) if change['source'] else b''
        need(original is not None and sha(original) == change['source_sha256'], 'INVALID_FROZEN_SOURCE:' + name)
        data = edit(original,change['edits'])
        need(sha(data) == change['sha256'], 'MATERIALIZATION_MISMATCH:' + name)
        if name in merges:
            merge = merges[name]
            need(sha(data) == merge['input_sha256'], 'MERGE_BASE_MISMATCH:' + name)
            data = edit(data,merge['edits'])
        need(sha(data) == expected[name], 'REVIEWED_MERGE_MISMATCH:' + name)
        materialized[name] = data
    env = dict(os.environ, GIT_INDEX_FILE=str(Path.cwd()/('transport_index_'+uuid.uuid4().hex)),
               GIT_AUTHOR_NAME='heteronpu-verified-transport', GIT_AUTHOR_EMAIL='heteronpu-verified@users.noreply.github.com',
               GIT_COMMITTER_NAME='heteronpu-verified-transport', GIT_COMMITTER_EMAIL='heteronpu-verified@users.noreply.github.com')
    git('read-tree',parent,env=env)
    for name,data in materialized.items():
        blob = git('hash-object','-w','--stdin',data=data).decode().strip()
        git('update-index','--add','--cacheinfo','100644',blob,name,env=env)
        need(git('show',':'+name,env=env) == data, 'INDEX_MISMATCH')
    tree = git('write-tree',env=env).decode().strip()
    commit = git('commit-tree',tree,'-p',parent,'-m','perf(chisel): batch Dense stores and preserve both committed-tail read modes [skip ci]',env=env).decode().strip()
    if subprocess.run(['git','push','origin',commit+':main']).returncode == 0:
        subprocess.run(['git','fetch','--no-tags','origin','main'],check=True)
        subprocess.run(['git','merge-base','--is-ancestor',commit,'origin/main'],check=True)
        for name,data in materialized.items():
            need(git('show','origin/main:'+name) == data, 'REMOTE_BYTE_MISMATCH:' + name)
        break
else:
    raise RuntimeError('FAST_FORWARD_PUBLICATION_FAILED_NO_FORCE')
report = {'status':'SOURCE_BYTES_PUBLISHED_NOT_FULL_PERFORMANCE_ACCEPTANCE','commit':commit,
          'files':expected,'remote_bytes_verified':True,'reviewed_concurrent_edits_preserved':list(merges),
          'full_real16_50_percent_accepted':False}
Path('transport_publication.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
if os.environ.get('GITHUB_OUTPUT'):
    with open(os.environ['GITHUB_OUTPUT'],'a') as f: f.write('commit='+commit+'\n')
