"""Check this small text-only package; no external dependency or compiler needed."""
from pathlib import Path, PurePosixPath
import hashlib,json,re

def verify(root):
    if root.is_symlink() or not root.is_dir():raise ValueError('unsafe root')
    manifest=root/'MANIFEST.json'
    if manifest.is_symlink() or not manifest.is_file():raise ValueError('unsafe manifest')
    if any(p.is_symlink() for p in root.rglob('*')):raise ValueError('symlink entry')
    rows=json.loads((root/'MANIFEST.json').read_text())['files']
    wanted={r['path'] for r in rows}
    if len(wanted)!=len(rows):raise ValueError('duplicate manifest path')
    actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    if actual!=wanted|{'MANIFEST.json'}:raise ValueError('unexpected or missing file')
    for r in rows:
        name=PurePosixPath(r['path'])
        if name.is_absolute() or '..' in name.parts:raise ValueError('unsafe path')
        p=root/r['path']
        if p.is_symlink() or p.suffix not in {'.scala','.cpp','.hpp','.py','.md','.json'}:
            raise ValueError('non-source payload')
        b=p.read_bytes();s=b.decode('utf-8')
        if b'\0' in b or len(b)>100000:raise ValueError('binary or oversized member')
        if len(b)!=r['bytes'] or hashlib.sha256(b).hexdigest()!=r['sha256']:
            raise ValueError('member identity mismatch')
        # Compose forbidden prefixes to avoid embedding them as private locators here.
        if any(x in s for x in ('/'+'workspace/', '/'+'home/agent/', '/'+'usr/lib/', '/'+'tmp/')):
            raise ValueError('private environment locator')
        if re.search(r'[A-Za-z0-9+/]{200,}={0,2}',s):raise ValueError('encoded payload')
    return len(rows)

if __name__=='__main__':print(json.dumps({'verified_members':verify(Path(__file__).resolve().parent),'status':'TEXT_PACKAGE_ONLY'}))
