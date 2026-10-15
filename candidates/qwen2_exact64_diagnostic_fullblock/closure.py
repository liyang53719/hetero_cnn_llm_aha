"""Strict source union. Old source identity does not reuse an old authorization."""
import hashlib
import json
from pathlib import Path
from candidates.qwen2_official_platform_fullblock import closure as original
ROOT=Path(__file__).resolve().parents[2]
PACKAGE='candidates/qwen2_exact64_diagnostic_fullblock'
WORKFLOW='.github/workflows/qwen2-exact64-diagnostic-fullblock.yml'
def source_manifest(root=ROOT):
    if Path(root)!=ROOT:raise ValueError('fixed source root')
    result=original.source_manifest(root)
    doc=json.loads((ROOT/PACKAGE/'SOURCE_MANIFEST.json').read_bytes())
    if type(doc) is not dict or set(doc)!={'schema','files'} or type(doc['schema']) is not int or doc['schema']!=1:raise ValueError('source inventory schema')
    own={str(p.relative_to(ROOT)) for p in (ROOT/PACKAGE).rglob('*') if p.is_file()}
    if own!={p for p in doc['files'] if p.startswith(PACKAGE+'/')}|{PACKAGE+'/SOURCE_MANIFEST.json'}:raise ValueError('exact diagnostic inventory')
    for name,spec in doc['files'].items():
        p=Path(name)
        if p.is_absolute() or '..' in p.parts or name.startswith('work/') or any('authorization' in part for part in p.parts):raise ValueError('source-only relative path')
        target=ROOT/p
        if target.resolve()!=target or any(q.is_symlink() for q in (target,*target.parents)):raise ValueError('source alias')
        raw=target.read_bytes();actual=dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
        if type(spec) is not dict or set(spec)!={'bytes','sha256'} or type(spec['bytes']) is not int or spec!=actual:raise ValueError('source changed')
        if name in result and result[name]!=actual:raise ValueError('source union conflict')
        result[name]=actual
    raw=(ROOT/PACKAGE/'SOURCE_MANIFEST.json').read_bytes()
    result[PACKAGE+'/SOURCE_MANIFEST.json']=dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
    return result
def digest(root=ROOT):
    return hashlib.sha256(json.dumps(source_manifest(root),sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
