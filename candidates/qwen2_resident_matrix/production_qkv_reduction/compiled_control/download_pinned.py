"""Explicit offline-preparation download only; never installs or runs tools."""
import argparse,hashlib,json,signal,time,urllib.request
from pathlib import Path
HERE=Path(__file__).resolve().parent
TOOLS={'verilator_5.032-1+b2_amd64.deb':('https://deb.debian.org/debian/pool/main/v/verilator/verilator_5.032-1+b2_amd64.deb','238ab4ca84cddd371f113cd549f16f2d65c43e7b4962a763bea1d259158dd3b2'),'llvm-firtool-1.62.1-linux-x64.jar':('https://repo.maven.apache.org/maven2/org/chipsalliance/llvm-firtool/1.62.1/llvm-firtool-1.62.1-linux-x64.jar','63acdcb58ed12d4c1aa0ecdedc6e2425a252e94eefb75df9253c118d7d222039')}
def run(kind,out,download):
 if not download:raise ValueError('explicit --download required')
 if out.exists() or out.is_symlink():raise ValueError('fresh download directory required')
 items=TOOLS
 if kind=='hardfloat':items={'hardfloat.tar.gz':('https://codeload.github.com/ucb-bar/berkeley-hardfloat/tar.gz/c1105e6ac6a0dd90fc80893efc4830ab609005d3','55f9c47f73c5a0ff347ff0ff4fc72b6966ffaa6b6d29998a00b3956dce512de7')}
 if kind=='jars':
  original=json.loads((HERE/'BASELINE_DEPENDENCY_PINS.json').read_text())['jars'];current=json.loads((HERE/'dependency-lock.json').read_text())['jars']
  for n in set(original)&set(current):
   if original[n]!=current[n]:raise ValueError('conflicting fixed jar identity')
  items={n:('https://repo.maven.apache.org/maven2/'+n,h) for n,h in {**original,**current}.items()}
 if signal.getitimer(signal.ITIMER_REAL)!=(0.0,0.0):raise ValueError('existing alarm')
 def timeout(sig,frame):raise TimeoutError('download preparation deadline')
 old=signal.signal(signal.SIGALRM,timeout);signal.setitimer(signal.ITIMER_REAL,600);start=time.monotonic();records={};out.mkdir(parents=True)
 try:
  for n,(url,h) in sorted(items.items()):
   with urllib.request.urlopen(url,timeout=30) as r:
    if r.geturl()!=url:raise ValueError('redirect forbidden')
    b=r.read(64*1024**2+1)
   if len(b)>64*1024**2 or hashlib.sha256(b).hexdigest()!=h:raise ValueError('download hash/size '+n)
   p=out/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b);records[n]=dict(url=url,sha256=h,bytes=len(b))
 finally:
  signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)
  (out/'download_receipt.json').write_text(json.dumps(dict(files=records,elapsed_seconds=time.monotonic()-start,executed=False),indent=2)+'\n')
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--kind',choices=['tools','jars','hardfloat'],required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--download',action='store_true');a=p.parse_args();run(a.kind,a.out,a.download)
