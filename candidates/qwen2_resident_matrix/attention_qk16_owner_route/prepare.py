"""Exact default-off 16-key route overlay; source preparation only."""
import hashlib,json,subprocess
from pathlib import Path
from candidates.qwen2_resident_matrix.attention_qk_owner_route import prepare as previous
HERE=Path(__file__).resolve().parent;ROOT=previous.ROOT;TARGETS=previous.TARGETS
OWN=('owner.patch','model.py','prepare.py','test_route.py','README.md')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def check():
 p=json.loads((HERE/'pins.json').read_bytes())
 if p['own']!={n:sha(HERE/n) for n in OWN}:raise ValueError('own source drift')
 if any(sha(ROOT/n)!=h for n,h in p['sources'].items()):raise ValueError('dependency drift')
 previous.check();return p

def compose(out,*,verify=True):
 pins=check() if verify else None;out=Path(out);previous.compose(out)
 subprocess.run(['patch','--batch','--fuzz=0','-p1'],input=(HERE/'owner.patch').read_bytes(),cwd=out,check=True,capture_output=True,timeout=5)
 actual={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file()}
 if verify and actual!=pins['generated']:raise ValueError('generated source drift')
 return actual
