"""Source-only composition of an explicitly enabled, M16-only numerical entry."""
import ast,copy,hashlib,json,subprocess,tempfile
from pathlib import Path
from ..raw_kv_public_fresh import prepare as fresh
from ..attention_packed_m16 import prepare as packed
from ..attention_packed_observation import prepare as observer
from ..attention_packed_m16_assets import reuse
from . import contract
ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
PREFIX=contract.PREFIX
OWN_NAMES=('admission.py','library_origin.py','views.py','contract.py','cold_construct.py','preparation_receipts.py','provenance.json','prepare.py','entry.patch',
 'test_admission.py','test_library_origin.py','test_views.py','test_preparation_receipts.py','test_prepare.py','README.md')
TARGETS=('candidates/qwen2_resident_matrix/dense_block_reduce/check_public_numeric.py',
 'candidates/qwen2_resident_matrix/official_bf16/check_numeric.py',
 'candidates/qwen2_resident_matrix/ffn_public/check_fullgraph_numeric.py',
 'candidates/qwen2_resident_matrix/attention_packed_m16/profile.py')
OBSERVER_PIN=observer.PREFIX+'pins.json'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def digest(path):return sha(path.read_bytes())
def need(value,message):
 if not value:raise ValueError(message)
def _function(text,name):return next(n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name==name)
def same_ast(left,right):return ast.dump(left,include_attributes=False)==ast.dump(right,include_attributes=False)
def check_scope(before,after):
 need(set(before)==set(after)==set(TARGETS),'exact four linked entry targets')
 # All comparisons, raw input loading, failure preservation and runtime body
 # remain original. The only official compare change is honest reuse metadata.
 official=TARGETS[1];reduced=TARGETS[0];full=TARGETS[2]
 truthful='fresh same-input sequential/block-pair outputs; explicitly reused verified native M16 outputs; original gates retained'
 historical='fresh separately sealed same-input sequential/block-pair and official outputs; original gates retained'
 before=dict(before)
 for target in (reduced,official):before[target]=before[target].replace(historical,truthful)
 for target,names in ((reduced,('compare','independent_bytes')),
  (official,('load_inputs','_reference_bytes','retain_failed_run','prerequisite')),
  (full,('runtime','compare','run','load_inputs','input_spec','binary_identity'))):
  for name in names:need(same_ast(_function(before[target],name),_function(after[target],name)),
   'original numerical/control body changed: '+target+':'+name)
 expected=before[official].replace("new_official_forward_executed=ref.get('fresh_profile') == fresh_assets.PROFILE,",
  'new_official_forward_executed=False, native_execution_reused=True,')
 need(same_ast(_function(expected,'compare'),_function(after[official],'compare')),'official numerical comparator changed')
 # Project only the enumerated selection/guard changes out of the actual
 # Public run. Preserve every other statement, including physical prefix/suffix,
 # terminal ACK fence, reference gate and full numerical comparisons.
 original=_function(before[reduced],'run');projected=copy.deepcopy(_function(after[reduced],'run'))
 need([a.arg for a in projected.args.kwonlyargs][-2:]==['enable_packed','run_context'],'explicit packed run options')
 del projected.args.kwonlyargs[-2:];del projected.args.kw_defaults[-2:]
 need(same_ast(projected.body[0],ast.parse('packed_contract.modes(fresh_profile=fresh_profile,enable_raw_kv=enable_raw_kv,enable_packed=enable_packed,rows=16)').body[0]) and
  same_ast(projected.body[1],ast.parse('packed_contract.authorize_run(run_context)').body[0]),'early linked mode/admission guard')
 del projected.body[:2]
 # The approved M16-specific work ceiling is narrower than the original1800.
 new_budget=ast.parse("require(not out.exists() and type(wall_budget) in (int,float) and 0<wall_budget<=900,'fresh bounded packed M16 run required')").body[0]
 hits=[(i,n) for i,n in enumerate(projected.body) if same_ast(n,new_budget)]
 need(len(hits)==1,'exact narrower M16 budget guard')
 projected.body[hits[0][0]]=copy.deepcopy(original.body[hits[0][0]])
 def capture_branch(node):
  return isinstance(node,ast.If) and same_ast(node.test,ast.Name(id='enable_raw_kv',ctx=ast.Load())) and any(
   isinstance(x,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='capture' for t in x.targets) for x in node.body)
 old_capture=[n for n in ast.walk(original) if capture_branch(n)]
 new_capture=[n for n in ast.walk(projected) if capture_branch(n)]
 need(len(old_capture)==len(new_capture)==1,'single observer selection branch')
 need(len(new_capture[0].body)==4,'exact packed observer/profile construction')
 new_capture[0].body=copy.deepcopy(old_capture[0].body)
 calls=[n for n in ast.walk(projected) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and
  n.func.attr=='execute_public_suffix' and any(k.arg=='packed_profile' for k in n.keywords)]
 need(len(calls)==1 and same_ast(next(k.value for k in calls[0].keywords if k.arg=='packed_profile'),ast.Name(id='packed_profile',ctx=ast.Load())),
  'single typed packed suffix selection')
 calls[0].keywords=[k for k in calls[0].keywords if k.arg!='packed_profile']
 need(same_ast(original,projected),'original Public execution/control or numerical order changed')
 # Other identity-plumbing edits are exact generated-file pins and require
 # direct review; this projection does not establish enabled arithmetic PASS.

def _assemble(out):
 need(not out.exists(),'fresh composition required')
 with tempfile.TemporaryDirectory(prefix='packed-linked-source-') as temporary:
  temp=Path(temporary)
  f=fresh.prepare(temp/'fresh',enable_raw_kv=True)
  p=packed.check();packed.compose(temp/'packed')
  o=observer.check()
  sources={**f['inputs'],**p['sources'],**p['own'],packed.PREFIX+'pins.json':digest(packed.HERE/'pins.json')}
  sources.update({n:digest(ROOT/n) for n in (*observer.EXTRA,*observer.OWN,OBSERVER_PIN)})
  sources.update({'candidates/qwen2_resident_matrix/attention_packed_m16_assets/'+n:h for n,h in reuse.snapshot().items()})
  backend='candidates/qwen2_resident_matrix/raw_kv_public_fresh/setup.py'
  sources[backend]=digest(ROOT/backend)
  validator='candidates/qwen2_resident_matrix/attention_packed_m16_assets_launch/receipt.py'
  sources[validator]=digest(ROOT/validator)
  own={PREFIX+n:digest(HERE/n) for n in OWN_NAMES}
  for name in (*sources,*own):
   target=out/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((ROOT/name).read_bytes())
  for src,names in ((temp/'fresh',f['generated']),(temp/'packed',p['generated'])):
   for name in names:
    target=out/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((src/name).read_bytes())
  before={n:(out/n).read_text() for n in TARGETS}
  patch=(HERE/'entry.patch').read_bytes()
  need([line[6:] for line in patch.decode().splitlines() if line.startswith('--- a/')]==list(TARGETS),'entry patch targets/order')
  subprocess.run(['patch','--batch','--fuzz=0','-p1'],cwd=out,input=patch,capture_output=True,check=True,timeout=10)
  after={n:(out/n).read_text() for n in TARGETS};check_scope(before,after)
  # A separate generated observer pin variant binds the reviewed changed entry
  # identities. Its production capture code and own map remain byte-identical.
  op=json.loads((ROOT/OBSERVER_PIN).read_text())
  op['runtime']={name:digest(out/name) for name in op['runtime']}
  (out/OBSERVER_PIN).write_text(json.dumps(op,sort_keys=True,indent=2)+'\n')
  generated_names=set(f['generated'])|set(p['generated'])|set(TARGETS)|{OBSERVER_PIN}
  generated={n:digest(out/n) for n in sorted(generated_names)}
  return dict(schema=1,profile=contract.PROFILE,sources=sources,own=own,generated=generated,
   inputs=dict(sources,**own),targets=list(TARGETS),execution_scope='ORIGINAL_M16_PUBLIC21')

def check():
 pins=json.loads((HERE/'pins.json').read_text())
 need(pins['execution_scope']=='ORIGINAL_M16_PUBLIC21','exact original M16 execution scope')
 with tempfile.TemporaryDirectory(prefix='linked-m16-check-') as temp:
  actual=_assemble(Path(temp)/'source')
 need(actual==pins,'linked composition/source drift')
 return pins

def compose(out):
 pins=check();out=Path(out)
 actual=_assemble(out);need(actual==pins,'composition identity drift')
 (out/PREFIX/'pins.json').write_bytes((HERE/'pins.json').read_bytes())
 return out
