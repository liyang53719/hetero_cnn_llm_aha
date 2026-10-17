"""Regenerate real Command128/descriptor bytes using pinned published generator."""
import argparse,hashlib,json,os,subprocess,sys,tempfile,shutil
from pathlib import Path
HERE=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def generate(source_root,out):
 source_root=source_root.resolve(strict=True)
 if out.exists() or out.is_symlink():raise ValueError('fresh fixture output required')
 gate=json.loads((HERE/'fixtures/gate.json').read_text());pins=json.loads((HERE/'FIXTURE_PINS.json').read_text())
 if sha(HERE/'fixtures/gate.json')!=pins['gate.json']:raise ValueError('gate drift')
 def verify_sources():
  for n,h in gate['source_sha256'].items():
   if sha(source_root/n)!=h:raise ValueError('generator source drift '+n)
 verify_sources()
 for n,h in pins.items():
  if not n.endswith('.bin') and sha(HERE/'fixtures'/n)!=h:raise ValueError('metadata fixture drift '+n)
 generator=source_root/'candidates/qwen2_resident_matrix/public_dispatch/generate_contract.py'
 if str(generator.relative_to(source_root)) not in gate['source_sha256']:raise ValueError('generator not externally pinned')
 env=dict(os.environ);env.pop('PYTHONPATH',None);env.pop('PYTHONHOME',None);env['PYTHONDONTWRITEBYTECODE']='1'
 out.parent.mkdir(parents=True,exist_ok=True)
 with tempfile.TemporaryDirectory(dir=out.parent,prefix='qkv_metadata_') as d:
  fresh=Path(d)/'generated'
  subprocess.run([sys.executable,'-B',str(generator),'--out',str(fresh)],check=True,env=env,timeout=30,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  actual={str(f.relative_to(fresh)):sha(f) for f in fresh.rglob('*') if f.is_file()}
  if actual!=pins:raise ValueError('generated fixture inventory or bytes differ')
  verify_sources();shutil.copytree(fresh,out)
 print('PASS_REAL_METADATA_REGENERATION six binary tables verified; no arithmetic')
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source-root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();generate(a.source_root,a.out)
