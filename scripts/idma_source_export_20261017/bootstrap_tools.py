#!/usr/bin/env python3
"""Download fixed official source-generation helpers only; no EDA."""
import argparse, hashlib, io, json, tarfile, urllib.request, signal, time, stat
from pathlib import Path
ASSETS={
'bender':('https://github.com/pulp-platform/bender/releases/download/v0.32.0/bender-x86_64-unknown-linux-gnu.tar.xz','05c2c9c82ddc0b3f45141a1e30dbcfba3b9a98a7d2ad0f9003651c0655c7a2fe'),
'uv':('https://github.com/astral-sh/uv/releases/download/0.8.17/uv-x86_64-unknown-linux-gnu.tar.gz','920cbcaad514cc185634f6f0dcd71df5e8f4ee4456d440a22e0f8c0f142a8203')}
def main(out):
 def expired(sig,frame):raise TimeoutError("bootstrap total wall deadline")
 signal.signal(signal.SIGALRM,expired);signal.setitimer(signal.ITIMER_REAL,180)
 out=Path(out);out.mkdir(parents=True,exist_ok=False);identity={}
 for name,(url,digest) in ASSETS.items():
  with urllib.request.urlopen(url,timeout=60) as r:data=r.read(64*1024*1024+1)
  if len(data)>64*1024*1024:raise ValueError('tool archive exceeds 64MiB')
  if hashlib.sha256(data).hexdigest()!=digest:raise ValueError('official tool archive drift')
  target=out/name;target.mkdir()
  with tarfile.open(fileobj=io.BytesIO(data)) as t:
   members=t.getmembers()
   if len(members)>1000 or sum(m.size for m in members)>128*1024*1024:raise ValueError('expanded tool archive cap')
   if any(not(m.isfile() or m.isdir()) or m.size>64*1024*1024 for m in members):raise ValueError('tool nonregular/member cap')
   t.extractall(target,filter='data')
  matches=[p for p in target.rglob(name) if p.is_file()]
  if len(matches)!=1:raise ValueError('ambiguous tool binary')
  binary=matches[0].resolve();binary.chmod(0o755)
  identity[name]={'path':str(binary),'sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'archive_sha256':digest,'url':url}
 (out/'TOOLS.json').write_text(json.dumps(identity,indent=2)+'\n');signal.setitimer(signal.ITIMER_REAL,0)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('out');main(p.parse_args().out)
