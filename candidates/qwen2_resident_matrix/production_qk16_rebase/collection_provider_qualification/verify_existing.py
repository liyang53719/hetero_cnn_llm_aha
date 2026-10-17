"""Read-only exact artifact and optional historical IR/SV replay; never execute EDA."""
import argparse,hashlib,json,signal,sys
from pathlib import Path
P=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def need(ok,msg):
 if not ok:raise ValueError(msg)
def run(a):
 need(signal.getitimer(signal.ITIMER_REAL)==(0.,0.),'preexisting alarm')
 def timeout(s,f):raise TimeoutError('30s offline cap')
 old=signal.signal(signal.SIGALRM,timeout);signal.setitimer(signal.ITIMER_REAL,30)
 try:
  for folder in ['structure','sv','endpoint']:
   root=P/folder;pins=json.loads((root/'MANIFEST.json').read_text());need(all(sha(root/n)==h for n,h in pins.items()),'frozen source drift '+folder)
  result=dict(source_manifests=True,ir_replayed=False,sv_replayed=False,full_bench_lint_pass=False,numerical=False)
  if a.ir:
   need(sha(a.ir)=='db430673f18166b3ce7c8703251b881d5446f71d70ddb29077f004a1db3599ba','historical IR hash');sys.path.insert(0,str(P/'structure'))
   from check_structure import check
   from check_packed import check_packed
   from check_silu import check as check_silu
   check(a.ir);check_packed(a.ir);check_silu(a.ir);result['ir_replayed']=True
  if a.sv:
   need(sha(a.sv)=='53f4f4cb503fc9fd9e7bf72d8e52a6ffc842d70959f847098ea817df11ba933f','historical SV hash');sys.path.insert(0,str(P/'sv'));from check_sv import check
   r=check(a.sv);need(r['definition_count']==56 and len(r['bench_ports'])==76,'historical inventory');result['sv_replayed']=True
  print(json.dumps(result,indent=2))
 finally:signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--ir',type=Path);p.add_argument('--sv',type=Path);run(p.parse_args())
