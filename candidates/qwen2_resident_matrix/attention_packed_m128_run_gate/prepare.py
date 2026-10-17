"""Exact successor to the frozen M128 raw-KV run admission gate."""
import hashlib,json,tempfile
from pathlib import Path
from ..attention_packed_m128_entry import prepare as prior
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
PREFIX='candidates/qwen2_resident_matrix/attention_packed_m128_run_gate/'
TARGET='candidates/qwen2_resident_matrix/dense_block_reduce/check_public_numeric.py'
ENTRY=prior.PREFIX+'pins.json'
OBSERVER='candidates/qwen2_resident_matrix/attention_packed_tiled_observation/pins.json'
OWN=tuple(PREFIX+n for n in ('prepare.py','probe.py','test_gate.py','README.md'))
OLD="""        require(validate_rows(pending['rows'])==16,
                'enabled raw KV execution is limited to M16 pending a reviewed same-source M16 receipt')"""
NEW="""        require(validate_rows(pending['rows'])==128,
                'linked packed M128 requires exact M128 snapshot and verified M16 prerequisite')"""
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def repair(text):
 if text.count(OLD)!=1:raise ValueError('exact frozen M16 residual gate required')
 return text.replace(OLD,NEW)
def _compose(out):
 prior.compose(out)
 for n in OWN:
  p=out/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((ROOT/n).read_bytes())
 p=out/TARGET;p.write_text(repair(p.read_text()))
 op=json.loads((out/OBSERVER).read_bytes());op['runtime'][TARGET]=sha(p)
 (out/OBSERVER).write_text(json.dumps(op,sort_keys=True,indent=2)+'\n')
 ep=json.loads((out/ENTRY).read_bytes())
 ep['sources'].update({n:sha(ROOT/n) for n in OWN});ep['inputs'].update({n:sha(ROOT/n) for n in OWN})
 ep['generated'].update({n:sha(out/n) for n in (TARGET,OBSERVER)})
 (out/ENTRY).write_text(json.dumps(ep,sort_keys=True,indent=2)+'\n')
 return {n:sha(out/n) for n in (TARGET,OBSERVER,ENTRY)}
def check():
 p=json.loads((HERE/'pins.json').read_bytes());prior.check()
 if set(p)!={'schema','profile','prior_pins','own','generated'} or type(p['schema']) is not int or p['schema']!=1 or p['profile']!='packed-m128-run-gate-repair-v1':raise ValueError('repair contract schema')
 if p['prior_pins']!=sha(prior.HERE/'pins.json') or p['own']!={n:sha(ROOT/n) for n in OWN}:raise ValueError('repair source drift')
 with tempfile.TemporaryDirectory() as d:g=_compose(Path(d)/'source')
 if g!=p['generated']:raise ValueError('repair generated drift')
 return p
def compose(out):
 p=check();out=Path(out)
 if _compose(out)!=p['generated']:raise ValueError('repair composition drift')
 return out
