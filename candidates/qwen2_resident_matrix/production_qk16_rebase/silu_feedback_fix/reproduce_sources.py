"""Rebuild repaired 92 production sources or 94-source bench closure; no compiler."""
import argparse,hashlib,json,shutil
from pathlib import Path
P=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def inventory(root):
 out={}
 for p in root.rglob('*'):
  if p.is_symlink():raise ValueError('symlink source')
  if p.is_file() and p.suffix=='.scala':out[str(p.relative_to(root))]=sha(p)
 return out
def compose(source,out,bench=False):
 expected=json.loads((P/'PRODUCTION_SOURCE_PINS.json').read_text())
 if inventory(source)!=expected or len(expected)!=92:raise ValueError('exact public production92 required')
 if out.exists() or out.is_symlink():raise ValueError('fresh output')
 rel='candidates/qwen2_resident_matrix/ffn_group/FfnTileSiluBridge.scala'
 old=(source/rel).read_bytes();new=(P/'source/FfnTileSiluBridge.scala').read_bytes()
 if old.count(b'io.tiles.abort:=bad;io.silu.abort:=bad')!=1 or new!=old.replace(b'io.tiles.abort:=bad;io.silu.abort:=bad',b'io.tiles.abort:=bad;io.silu.abort:=io.abort || poison'):raise ValueError('single-expression delta')
 shutil.copytree(source,out);(out/rel).write_bytes(new);expected[rel]=hashlib.sha256(new).hexdigest()
 if bench:
  (out/'bench').mkdir()
  for n in ['ProductionQk16KernelBench.scala','ProductionQk16KernelSpec.scala']:
   shutil.copyfile(P/'source'/n,out/'bench'/n);expected['bench/'+n]=sha(P/'source'/n)
 if inventory(out)!=expected:raise ValueError('postimage mismatch')
 return expected
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--production-source',type=Path,required=True);a.add_argument('--out',type=Path,required=True);a.add_argument('--include-bench',action='store_true');x=a.parse_args();print(json.dumps(compose(x.production_source,x.out,x.include_bench),indent=2))
