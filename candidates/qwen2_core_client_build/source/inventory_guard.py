"""Stdlib-only endpoint inventory. Never invoke inventoried tools; do not follow directory links."""
import hashlib,os,stat
from pathlib import Path

def require(ok, why):
    if not ok: raise ValueError(why)

def _raise_walk_error(error):
    raise error

def entries(root):
    p=Path(root)
    require(p.is_dir() and not p.is_symlink(), 'inventory root must be canonical directory')
    result=[]
    for here,dirs,files in os.walk(p,followlinks=False,onerror=_raise_walk_error):
        for name in sorted(dirs+files):
            q=Path(here)/name;s=q.lstat();row={'relative':str(q.relative_to(p)),'mode':stat.S_IMODE(s.st_mode)}
            if stat.S_ISLNK(s.st_mode):row.update(kind='symlink',target=os.readlink(q),resolved_path=str(q.resolve()),target_exists=q.exists(),target_is_directory=q.is_dir())
            elif stat.S_ISDIR(s.st_mode):row.update(kind='directory')
            elif stat.S_ISREG(s.st_mode):row.update(kind='regular',bytes=s.st_size)
            else:raise ValueError('special inventory entry: '+str(q))
            result.append(row)
    return sorted(result,key=lambda r:r['relative'])

def verify_inventory(spec):
    require(str(Path(spec['root']).resolve())==spec['root'],'inventory root canonical drift')
    require(entries(spec['root'])==spec['entries'],'exact lstat entry inventory drift')

def verify_pin(p):
    q=Path(p['path']);require(str(q.resolve())==p['resolved_path'],'resolved path drift')
    if 'symlink_target' in p:require(q.is_symlink() and os.readlink(q)==p['symlink_target'],'file link drift')
    else:require(not q.is_symlink(),'unexpected endpoint link')
    h=hashlib.sha256()
    with q.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    require(q.stat().st_size==p['bytes'] and h.hexdigest()==p['sha256'],'file bytes drift')

def verify_absent(paths):
    for path in paths:require(not os.path.lexists(path),'missing slot appeared: '+path)
