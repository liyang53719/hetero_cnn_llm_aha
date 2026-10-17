"""Separate source composition over the verified complete M16 program.

No setup, library load or numerical execution occurs here.
"""
import hashlib,json,tempfile
from pathlib import Path
from ..attention_packed_m16_host_job import prepare as prior
from ..attention_packed_m128 import prepare as tiled
from ..attention_packed_tiled_observation import prepare as observer
from . import composition,contract
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];PREFIX=contract.PREFIX
OWN_NAMES=('contract.py','profile.py','composition.py','prepare.py','test_composition.py','test_profile.py','cold_construct.py','README.md')
OBSERVER_PIN=observer.PREFIX+'pins.json'
TARGETS=(composition.REDUCED,composition.OFFICIAL,composition.FULL,composition.TRANSPORT,tiled.TARGET)
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def need(v,msg):
 if not v:raise ValueError(msg)
def asset_sources():
 from ..attention_packed_m128_assets import origin
 return origin.source_snapshot()
def _assemble(out):
 need(not out.exists(),'fresh source tree required')
 prior.check();tp=tiled.check();op=observer.check();assets=asset_sources()
 prior.compose(out)
 old=json.loads((out/prior.ENTRY).read_bytes())
 sources={**old['sources'],**old['own'],**old['generated'],prior.ENTRY:digest(out/prior.ENTRY)}
 inputs={**old['inputs'],**{n:digest(ROOT/n) for n in (*prior.OWN,prior.PREFIX+'pins.json')}}
 additions={**tp['own'],tiled.PREFIX+'pins.json':digest(tiled.HERE/'pins.json'),
  **op['own'],**{n:digest(ROOT/n) for n in observer.EXTRA},OBSERVER_PIN:digest(observer.HERE/'pins.json'),**assets}
 inputs.update(additions)
 for n,h in additions.items():
  need(digest(ROOT/n)==h,'M128 input drift')
  p=out/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((ROOT/n).read_bytes());sources[n]=h
 own={PREFIX+n:digest(HERE/n) for n in OWN_NAMES};inputs.update(own)
 for n in own:
  p=out/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((ROOT/n).read_bytes())
 # The exact tiled source is independently composed/pinned, never regenerated
 # by an arithmetic rewrite in this full-program layer.
 with tempfile.TemporaryDirectory() as d:
  t=tiled.compose(Path(d)/'tiled');(out/tiled.TARGET).write_bytes((t/tiled.TARGET).read_bytes())
 for n in (composition.REDUCED,composition.OFFICIAL,composition.FULL):
  p=out/n;p.write_text(composition.entry(p.read_text(),n))
 p=out/composition.TRANSPORT;p.write_text(composition.transport(p.read_text()))
 # New observer identity variant preserves its capture implementation. It
 # explicitly binds each original runtime source to the final composed bytes.
 op['runtime']={n:digest(out/n) for n in op['runtime']}
 (out/OBSERVER_PIN).write_text(json.dumps(op,sort_keys=True,indent=2)+'\n')
 generated={n:digest(out/n) for n in (*TARGETS,OBSERVER_PIN)}
 return dict(schema=1,profile=contract.PROFILE,sources=sources,own=own,generated=generated,
  inputs=inputs,targets=list(TARGETS),execution_scope='ORIGINAL_M128_PUBLIC21')
def check():
 p=json.loads((HERE/'pins.json').read_bytes())
 with tempfile.TemporaryDirectory() as d:actual=_assemble(Path(d)/'source')
 need(actual==p,'M128 full-entry source/composition drift');return p
def compose(out):
 p=check();out=Path(out);need(_assemble(out)==p,'M128 composition drift')
 (out/PREFIX/'pins.json').write_bytes((HERE/'pins.json').read_bytes());return out
