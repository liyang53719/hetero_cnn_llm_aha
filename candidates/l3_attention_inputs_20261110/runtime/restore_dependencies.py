from pathlib import Path
import json,hashlib,urllib.request,time,subprocess,sys
r=Path(__file__).resolve().parent;lock=json.loads((r/'official_runtime_lock.json').read_text());names={'torch','filelock','typing-extensions','sympy','mpmath','networkx','jinja2','markupsafe','fsspec','numpy'};selected=[a for a in lock['artifacts'] if a['name'] in names];start=time.monotonic()
for a in selected:
 p=r/a['filename']
 if not p.exists():
  with urllib.request.urlopen(a['url'],timeout=45) as response,p.with_suffix('.partial').open('xb') as out:
   count=0
   for b in iter(lambda:response.read(1<<20),b''):
    count+=len(b)
    if count>a['bytes'] or time.monotonic()-start>180:raise ValueError('download budget')
    out.write(b)
  p.with_suffix('.partial').rename(p)
 if p.stat().st_size!=a['bytes'] or hashlib.sha256(p.read_bytes()).hexdigest()!=a['sha256']:raise ValueError('pin mismatch '+a['name'])
 print('verified',a['name'],flush=True)
(r/'DEPENDENCY_PINS.json').write_text(json.dumps(selected,indent=2)+'\n')
subprocess.run([sys.executable,'-m','pip','install','--no-index','--no-deps','--no-compile','--target',str(r/'site'),*[str(r/a['filename']) for a in selected]],check=True,timeout=180)
