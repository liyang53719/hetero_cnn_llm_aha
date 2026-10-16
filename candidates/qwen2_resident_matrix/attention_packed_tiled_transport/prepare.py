"""Closed explicit M17/M32 transport composition, no full program admission."""
import hashlib,json,tempfile
from pathlib import Path
from ..attention_packed_m128 import prepare as prior
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
PREFIX='candidates/qwen2_resident_matrix/attention_packed_tiled_transport/'
TARGET='candidates/qwen2_resident_matrix/raw_kv_public/model.py'
OWN=tuple(PREFIX+n for n in ('prepare.py','profile.py','fixture.py','run_small.py','test_prepare.py','README.md'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def inputs():
 p=prior.check();return {**p['sources'],**p['own'],prior.PREFIX+'pins.json':sha(prior.HERE/'pins.json')}
def upstream_generated():
 return set(prior.prior.generated_names())|{prior.TARGET}
def alter(s):
 old='from ..attention_packed_m16.profile import PackedM16PublicProfile'
 new=old+'\n            from ..attention_packed_tiled_transport.profile import PackedTiledProfile'
 guard='type(packed_profile) in (PackedPublicProfile,PackedM16PublicProfile)'
 if s.count(old)!=1 or s.count(guard)!=1:raise ValueError('exact optional profile selector')
 return s.replace(old,new).replace(guard,'type(packed_profile) in (PackedPublicProfile,PackedM16PublicProfile,PackedTiledProfile)')
def _compose(out):
 prior.compose(out)
 for n in (*OWN,prior.PREFIX+'pins.json'):
  p=out/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((ROOT/n).read_bytes())
 p=out/TARGET;p.write_text(alter(p.read_text()))
 return {n:sha(out/n) for n in sorted(upstream_generated()|{TARGET})}
def check():
 p=json.loads((HERE/'pins.json').read_bytes())
 if set(p)!={'schema','sources','own','generated'} or type(p['schema']) is not int or p['schema']!=1:raise ValueError('profile schema')
 if p['sources']!=inputs() or p['own']!={n:sha(ROOT/n) for n in OWN}:raise ValueError('transport source drift')
 with tempfile.TemporaryDirectory() as d:g=_compose(Path(d)/'source')
 if g!=p['generated']:raise ValueError('generated transport drift')
 return p
def compose(out):
 p=check();out=Path(out)
 if _compose(out)!=p['generated']:raise ValueError('composition drift')
 (out/PREFIX/'pins.json').write_bytes((HERE/'pins.json').read_bytes())
 return out
def verify_installed():
 p=json.loads((HERE/'pins.json').read_bytes());mapping={**p['sources'],**p['own'],**p['generated']}
 for n,h in mapping.items():
  path=ROOT/n
  if path.resolve()!=path or not path.is_file() or sha(path)!=h:raise ValueError('installed transport source drift: '+n)
 mapping[PREFIX+'pins.json']=sha(HERE/'pins.json')
 return mapping
