#!/usr/bin/env python3
"""Verify exact public text inventory; no model or hardware verification."""
from pathlib import Path
import hashlib,json
HERE=Path(__file__).resolve().parent

def verify():
 doc=json.loads((HERE/'MANIFEST.json').read_text())
 actual=set()
 for p in HERE.rglob('*'):
  if p.is_symlink():raise ValueError('symlink prohibited')
  if not p.is_file() and not p.is_dir():raise ValueError('nonregular file prohibited')
  if p.is_file() and p != HERE/'MANIFEST.json':actual.add(p.relative_to(HERE).as_posix())
 if actual!=set(doc['files']):raise ValueError('file inventory drift')
 for name,entry in doc['files'].items():
  data=(HERE/name).read_bytes();data.decode('utf-8')
  if len(data)!=entry['bytes'] or hashlib.sha256(data).hexdigest()!=entry['sha256']:raise ValueError('hash/size '+name)
 print('PASS exact public text inventory only:',len(actual))
if __name__=='__main__':verify()
