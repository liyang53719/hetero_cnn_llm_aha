"""Versioned exact HostControl job-class repair; no numerical execution."""
import hashlib,json,tempfile
from pathlib import Path
from ..attention_packed_m16_entry import prepare as prior
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
PREFIX='candidates/qwen2_resident_matrix/attention_packed_m16_host_job/'
TARGET='candidates/qwen2_resident_matrix/attention_packed_m16/profile.py'
OBSERVER='candidates/qwen2_resident_matrix/attention_packed_observation/pins.json'
ENTRY=prior.PREFIX+'pins.json'
OWN=tuple(PREFIX+n for n in ('prepare.py','test_host_job.py','README.md'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def repair(text):
 old='from ..ffn_public.prefix_owners import Job'
 guard='type(parent) is not ParentLoan or type(job) is not Job or'
 if text.count(old)!=1 or text.count(guard)!=1:raise ValueError('exact original type guard required')
 return text.replace(old,'from ..ffn_public import model as public').replace(guard,'type(parent) is not ParentLoan or type(job) is not public.group.PrefixJob or')
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
 if set(p)!={'schema','prior_pins','own','generated'} or type(p['schema']) is not int or p['schema']!=1 or set(p['generated'])!={TARGET,OBSERVER,ENTRY}:raise ValueError('exact repair contract schema')
 if p['prior_pins']!=sha(prior.HERE/'pins.json') or p['own']!={n:sha(ROOT/n) for n in OWN}:raise ValueError('repair source drift')
 with tempfile.TemporaryDirectory() as d:g=_compose(Path(d)/'source')
 if g!=p['generated']:raise ValueError('repair output drift')
 return p
def compose(out):
 p=check();out=Path(out)
 if _compose(out)!=p['generated']:raise ValueError('repair composition drift')
 return out
