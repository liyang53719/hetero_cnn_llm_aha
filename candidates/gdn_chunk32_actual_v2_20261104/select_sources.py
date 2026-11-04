"""Explicit source-only actual-path selector. Never launches or admits hardware.
Default returns unchanged legacy159. Opt-in returns new162 and its own helper.
The original artifact/generation gates are deliberately not bypassed or edited.
"""
from pathlib import Path
import hashlib,json,argparse,os
HERE=Path(__file__).resolve().parent
EXPECTED_GENERATION_SHA256='2b2f02d698f16a57ba696c52c4669a1226a68c5378efdc8ebe392cc1b9098f52'
DEFAULT_BASE=Path(os.environ['GDN32_BASE']).resolve() if 'GDN32_BASE' in os.environ else HERE.parent.parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def need(v,msg):
 if not v:raise ValueError(msg)
def select(base=DEFAULT_BASE,hardware_source='legacy'):
 need(hardware_source in ('legacy','gdn-chunk32-abort-v2'),'unsupported source selector')
 need(sha(HERE/'GENERATION_CONTRACT.json')==EXPECTED_GENERATION_SHA256,'generation contract drift')
 base=Path(base).resolve();legacy=base/'candidates/model_candidate_build_20261101/MODEL_SOURCE_OVERLAY.json'
 overlay=json.loads((HERE/'MODEL_SOURCE_OVERLAY.json').read_text());contract=json.loads((HERE/'GENERATION_CONTRACT.json').read_text())
 need(sha(legacy)==overlay['base_overlay_sha256'],'base overlay drift')
 need(sha(HERE/'MODEL_SOURCE_OVERLAY.json')==contract['source_overlay_sha256'],'candidate overlay drift')
 enabled=hardware_source=='gdn-chunk32-abort-v2'
 rows=overlay['files'] if enabled else json.loads(legacy.read_text())['files'];paths=[]
 for r in rows:
  rel=Path(r['repo_path']);need(not rel.is_absolute() and '..' not in rel.parts,'canonical relative source')
  p=(HERE if enabled and r['root']=='candidate' else base)/rel
  need(p.is_file() and not p.is_symlink() and p.stat().st_size==r['bytes'] and sha(p)==r['sha256'],'source drift: '+r['name']);paths.append(str(p))
 need(len(paths)==(162 if enabled else 159) and len({Path(p).name for p in paths})==len(paths),'unique actual source closure')
 helper=overlay['helper'];hp=HERE/'source'/helper['name'] if enabled else base/helper['base_path']
 need(sum(Path(p).name==hp.name for p in paths)==1,'one helper class definition')
 need(str(hp) in paths,'helper must be actual selected compile input, not side metadata')
 need(sha(hp)==helper['candidate_sha256' if enabled else 'base_sha256'],'constructor helper drift')
 return dict(hardware_source=hardware_source,source_paths=paths,helper=str(hp),helper_sha256=sha(hp),generation_identity=sha(HERE/'GENERATION_CONTRACT.json') if enabled else sha(base/'candidates/model_candidate_build_20261101/GENERATION_CONTRACT.json'),enableChunk32=enabled,profiles=[0,1,2,3,4],numeric_execution_authorized=False,old_artifact_reuse_permitted=not enabled)
def require_new_artifact(candidate_identity,artifact_identity):
 need(candidate_identity==artifact_identity,'new exact hardware identity required; legacy artifact forbidden')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--hardware-source',default='legacy',choices=['legacy','gdn-chunk32-abort-v2']);p.add_argument('--base',type=Path,default=DEFAULT_BASE);a=p.parse_args();print(json.dumps(select(a.base,a.hardware_source),indent=2))
