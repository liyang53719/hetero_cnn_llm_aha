"""Verify exact public package files and hashes; not hardware or full reproduction."""
from pathlib import Path
import hashlib,json
R=Path(__file__).resolve().parent
def need(ok,msg):
    if not ok:raise ValueError(msg)
def main():
    manifest=json.loads((R/'MANIFEST.json').read_text())
    rows=manifest['files']; names=[r['path'] for r in rows]
    need(len(names)==len(set(names)), 'duplicate manifest path')
    actual={p.relative_to(R).as_posix() for p in R.rglob('*') if p.is_file()}
    need(actual==set(names)|{'MANIFEST.json'}, 'unexpected or missing package file')
    for p in R.rglob('*'):need(not p.is_symlink(), 'no symlinks')
    for row in rows:
        rel=Path(row['path'])
        need(not rel.is_absolute() and '..' not in rel.parts, 'relative package path')
        data=(R/rel).read_bytes(); data.decode('utf-8')
        need(len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256'], 'hash mismatch '+str(rel))
        need(b'\x00' not in data, 'text only')
    print('PASS exact package hashes; requires-parent, no hardware qualification')
if __name__=='__main__':main()
