"""Closed, zero-fuzz M16 composition; no producer or native execution."""
import hashlib,json,subprocess
from pathlib import Path
from ..attention_packed_public import prepare as prior
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
PREFIX='candidates/qwen2_resident_matrix/attention_packed_m16/'
TARGETS=('candidates/qwen2_resident_matrix/attention_packed_owner/schedule.py',
 'candidates/qwen2_resident_matrix/raw_kv_public/model.py',
 'candidates/qwen2_resident_matrix/ffn_public/fullgraph_execution.py')
OWN=tuple(PREFIX+n for n in ('m16.patch','profile.py','prepare.py','library.py','test_prepare.py','README.md'))
EXTRA=('candidates/qwen2_resident_matrix/official_bf16/silu_recipe.cpp',
 'candidates/qwen2_resident_matrix/ffn_tiles/silu_recipe.cpp')
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def inputs():
 # Read the frozen predecessor inventory without rerunning its base-only
 # composition verifier on an already overlaid execution tree.
 base=json.loads((prior.HERE/'pins.json').read_bytes())
 return tuple(sorted(set((*base['sources'],*prior.OWN,prior.PREFIX+'pins.json',*EXTRA))))
def snapshot(root=ROOT):return {n:digest(Path(root)/n) for n in (*inputs(),*OWN,PREFIX+'pins.json')}
def check():
 prior.check();p=json.loads((HERE/'pins.json').read_bytes())
 if set(p)!={'schema','sources','own','generated'} or type(p['schema']) is not int or p['schema']!=1:raise ValueError('M16 profile schema')
 if set(p['sources'])!=set(inputs()) or set(p['own'])!=set(OWN):raise ValueError('M16 source inventory')
 for field in ('sources','own'):
  if {n:digest(ROOT/n) for n in p[field]}!=p[field]:raise ValueError('M16 source drift')
 return p

def _compose(destination):
 out=prior.compose(destination)
 for n in (*EXTRA,*OWN,PREFIX+'pins.json'):
  source=ROOT/n
  if source.exists():
   target=out/n;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(source.read_bytes())
 r=subprocess.run(['patch','--batch','--fuzz=0','-p1','-i',str(HERE/'m16.patch')],cwd=out,capture_output=True,timeout=5)
 if r.returncode or any(x in r.stdout+r.stderr for x in (b'offset',b'fuzz')):raise ValueError('M16 zero-fuzz composition')
 return out

def generated_names():
 # Every earlier overlay remains explicitly bound, including native source.
 from ..attention_packed_native import prepare as native
 from ..attention_packed_owner import prepare as owner
 return tuple(sorted(set((*TARGETS,*prior.TARGETS,*owner.TARGETS,*native.TARGETS,prior.ORACLE_COPY))))
def compose(destination):
 p=check();out=_compose(destination)
 if set(p['generated'])!=set(generated_names()) or {n:digest(out/n) for n in p['generated']}!=p['generated']:raise ValueError('M16 generated identity')
 return out

def verify_installed(root=ROOT):
 root=Path(root);p=json.loads((root/PREFIX/'pins.json').read_bytes())
 if set(p)!= {'schema','sources','own','generated'} or type(p['schema']) is not int or p['schema']!=1:raise ValueError('installed M16 schema')
 if set(p['sources'])!=set(inputs()) or set(p['own'])!=set(OWN) or set(p['generated'])!=set(generated_names()):raise ValueError('installed M16 inventory')
 expected={**p['sources'],**p['own'],**p['generated']}
 if any(digest(root/n)!=h for n,h in expected.items()):raise ValueError('installed M16 source drift')
 return expected

def authorize_full_numeric(*args,**kwargs):
 raise ValueError('M16 linked asset/observer/numerical admission is not implemented')
