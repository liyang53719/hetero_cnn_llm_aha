"""Separate schedule-only tiled variant. Full Public admission stays closed."""
import hashlib,json,subprocess,tempfile
from pathlib import Path
from ..attention_packed_m16 import prepare as prior
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
PREFIX='candidates/qwen2_resident_matrix/attention_packed_m128/'
TARGET='candidates/qwen2_resident_matrix/attention_packed_owner/schedule.py'
AUDIT='candidates/qwen2_resident_matrix/attention_bank_m128/controller.py'
OWN=tuple(PREFIX+n for n in ('prepare.py','tiled.patch','test_schedule.py','README.md'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def inputs():
 p=prior.check();return {**p['sources'],**p['own'],prior.PREFIX+'pins.json':sha(prior.HERE/'pins.json'),AUDIT:sha(ROOT/AUDIT)}
def _compose(out):
 prior.compose(out)
 for n in (*OWN,AUDIT):
  t=out/n;t.parent.mkdir(parents=True,exist_ok=True);t.write_bytes((ROOT/n).read_bytes())
 r=subprocess.run(['patch','--batch','--fuzz=0','-p1','-i',str(HERE/'tiled.patch')],cwd=out,capture_output=True,timeout=5)
 if r.returncode or any(v in r.stdout+r.stderr for v in (b'offset',b'fuzz')):raise ValueError('exact tiled schedule patch')
 return sha(out/TARGET)
def check():
 p=json.loads((HERE/'pins.json').read_bytes())
 if set(p)!={'schema','sources','own','generated'} or type(p['schema']) is not int or p['schema']!=1:raise ValueError('tiled profile schema')
 if p['sources']!=inputs() or p['own']!={n:sha(ROOT/n) for n in OWN}:raise ValueError('tiled source drift')
 with tempfile.TemporaryDirectory() as d:h=_compose(Path(d)/'source')
 if p['generated']!={TARGET:h}:raise ValueError('tiled generated source drift')
 return p
def compose(out):
 p=check();out=Path(out)
 if _compose(out)!=p['generated'][TARGET]:raise ValueError('tiled composition drift')
 return out
def authorize_full_public(*a,**kw):raise ValueError('M128 packed Public profile/observer/admission not implemented')
