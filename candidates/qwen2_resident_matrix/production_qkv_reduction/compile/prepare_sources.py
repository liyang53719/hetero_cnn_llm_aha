"""Copy exact 71 candidate + 20 HardFloat Scala files; no compiler execution."""
import argparse,hashlib,json,shutil
from pathlib import Path
HERE=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def run(source_root,hardfloat_root,out):
 source_root=source_root.resolve(strict=True);hardfloat_root=hardfloat_root.resolve(strict=True)
 if out.exists() or out.is_symlink():raise ValueError('fresh output required')
 pins=json.loads((HERE/'SOURCE_PINS.json').read_text());post=json.loads((HERE.parent/'MANIFEST.json').read_text())['post_sha256']
 actual={str(p.relative_to(source_root)):sha(p) for p in source_root.rglob('*') if p.is_file()}
 if actual!=post:raise ValueError('exact candidate 77-file source inventory required')
 sources={}
 for n,h in pins.items():
  p=(hardfloat_root/n.removeprefix('hardfloat_snapshot/hardfloat/src/main/scala/')) if n.startswith('hardfloat_snapshot/') else source_root/n
  if not p.is_file() or p.is_symlink() or sha(p)!=h:raise ValueError('source identity mismatch: '+n)
  sources[n]=p
 out.mkdir(parents=True,exist_ok=False)
 for n,p in sources.items():
  q=out/n;q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,q)
 if {str(p.relative_to(out)):sha(p) for p in out.rglob('*.scala')}!=pins:raise ValueError('copy identity mismatch')
 print('PASS_EXACT_91_SOURCE_COPY_ONLY')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source-root',required=True,type=Path);p.add_argument('--hardfloat-root',required=True,type=Path,help='directory containing AddRecFN.scala etc.');p.add_argument('--out',required=True,type=Path);a=p.parse_args();run(a.source_root,a.hardfloat_root,a.out)
