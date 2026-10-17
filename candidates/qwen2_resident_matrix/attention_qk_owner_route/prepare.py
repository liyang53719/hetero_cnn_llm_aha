"""Default-off original core/kernel route overlay; source-only preparation."""
import hashlib,json,subprocess,tempfile
from pathlib import Path
from candidates.qwen2_resident_matrix.attention_packed_stream import prepare as stream
HERE=Path(__file__).resolve().parent;ROOT=stream.ROOT;SCALA=stream.SCALA
TARGETS=tuple(SCALA+n for n in ('Qwen2Block.scala','QwenOwnerProtocol.scala'))
OWN=('owner.patch','model.py','prepare.py','test_route.py','README.md')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def check():
 p=json.loads((HERE/'pins.json').read_bytes())
 if p['own']!={n:sha(HERE/n) for n in OWN}:raise ValueError('own source drift')
 if any(sha(ROOT/n)!=h for n,h in p['sources'].items()):raise ValueError('original source drift')
 stream.check();return p

def compose(out,*,verify=True):
 pins=check() if verify else None
 out=Path(out);stream.compose(out)
 for n in TARGETS:(out/n).write_bytes((ROOT/n).read_bytes())
 subprocess.run(['patch','--batch','--fuzz=0','-p1'],input=(HERE/'owner.patch').read_bytes(),cwd=out,check=True,capture_output=True,timeout=5)
 actual={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file()}
 if verify and actual!=pins['generated']:raise ValueError('generated source drift')
 return actual
