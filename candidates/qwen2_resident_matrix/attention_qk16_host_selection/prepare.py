"""Default-off QK-only constructor propagation; writes a fresh overlay only."""
from pathlib import Path
import hashlib,json,argparse
HERE=Path(__file__).resolve().parent

def sha(b):return hashlib.sha256(b).hexdigest()
def load():
 pins=json.loads((HERE/'pins.json').read_text())
 for n,k in [('edits.json','edits_sha256'),('selection.patch','patch_sha256')]:
  if sha((HERE/n).read_bytes())!=pins[k]:raise ValueError('candidate artifact drift: '+n)
 return pins,json.loads((HERE/'edits.json').read_text())
def prepare(source_root,fragment_root,output):
 source_root,fragment_root,output=map(Path,(source_root,fragment_root,output))
 if output.exists() or output.is_symlink():raise ValueError('fresh output required')
 pins,edits=load(); results={}
 for n,h in {**pins['inputs'],**pins['unchanged']}.items():
  if sha((source_root/n).read_bytes())!=h:raise ValueError('original source drift: '+n)
 for n,h in pins['fragment'].items():
  b=(fragment_root/n).read_bytes()
  if sha(b)!=h:raise ValueError('QK-only materialization fragment drift: '+n)
  results[n]=b
 for n,rs in edits.items():
  t=(source_root/n).read_text()
  for a,b in rs:
   if t.count(a)!=1:raise ValueError('source anchor mismatch')
   t=t.replace(a,b)
  if sha(t.encode())!=pins['outputs'][n]:raise ValueError('output drift')
  results[n]=t.encode()
 output.mkdir(parents=True,exist_ok=False)
 for n,b in results.items():
  p=output/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
 return {n:sha(b) for n,b in results.items()}
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 for n in ('source-root','fragment-root','output'):p.add_argument('--'+n,required=True,type=Path)
 a=p.parse_args();print(json.dumps(prepare(a.source_root,a.fragment_root,a.output),indent=2,sort_keys=True))
