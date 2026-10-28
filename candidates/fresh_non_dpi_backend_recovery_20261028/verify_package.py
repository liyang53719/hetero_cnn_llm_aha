#!/usr/bin/env python3
"""Verify only the explicit text package; no execution of build/test stages."""
from pathlib import Path
import hashlib,json
P=Path(__file__).resolve().parent
m=json.loads((P/'MANIFEST.json').read_text());seen=set()
for r in m['files']:
 n=r['path'];q=Path(n)
 if q.is_absolute() or '..' in q.parts or n in seen:raise ValueError('invalid/duplicate manifest path')
 seen.add(n);p=P/q
 if p.is_symlink() or not p.is_file():raise ValueError('missing/linked package file '+n)
 b=p.read_bytes()
 if len(b)!=r['bytes'] or hashlib.sha256(b).hexdigest()!=r['sha256']:raise ValueError('package byte mismatch '+n)
 b.decode('utf-8')
print(json.dumps({'status':'PASS_TEXT_PACKAGE_IDENTITY_ONLY','files':len(seen),'no_numerical_or_build_claim':True}))
