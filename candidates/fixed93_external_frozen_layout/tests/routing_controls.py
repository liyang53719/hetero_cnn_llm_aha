"""Real loader and original function CodeTypes with synthetic route/state fixtures.

No recipe/gates module top level, inherited OracleGate constructor, runtime,
owner, model, native code or real input/reference payload is executed.
"""
import argparse
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import resource
import signal
import stat
import sys
import time
import types

HERE=Path(__file__).resolve().parents[1]

def need(ok,text):
    if not ok:raise AssertionError(text)
def reject(fn):
    try:fn()
    except (ValueError,TypeError,KeyError):return
    raise AssertionError('negative accepted')
def pin(raw):return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
def code_in(code,name):return next(c for c in code.co_consts if type(c) is types.CodeType and c.co_name==name)
def function(code,node,namespace):
    value=types.FunctionType(code,namespace,node.name)
    def default(n):return namespace[n.id] if isinstance(n,ast.Name) else ast.literal_eval(n)
    value.__defaults__=tuple(default(n) for n in node.args.defaults) or None
    value.__kwdefaults__={n.arg:default(v) for n,v in zip(node.args.kwonlyargs,node.args.kw_defaults) if v is not None} or None
    return value

def run(output):
    start=time.monotonic();output=Path(output).absolute()
    need(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode,'isolated flags')
    need(output.resolve()==output and not output.exists(),'fresh output')
    resource.setrlimit(resource.RLIMIT_CPU,(15,15));resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,256*1024**2));signal.alarm(15)
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    denied=[];pyc_reads=[]
    def audit(event,args):
        if event.startswith(('ctypes.','subprocess.','socket.')) or event in ('os.system','os.fork','os.forkpty','os.posix_spawn'):
            denied.append(event);raise RuntimeError('native/process/network denied')
        if event=='import' and args[0].split('.')[0] in {'ctypes','numpy','torch','candidates'}:
            denied.append('import');raise RuntimeError('DUT/native import denied')
        if event=='open' and isinstance(args[0],(str,bytes)):
            p=Path(os.fsdecode(args[0])).absolute();mode,flags=args[1:]
            writing=(type(mode) is str and any(c in mode for c in 'wax+')) or (type(flags) is int and flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND))
            ok=p.is_relative_to(output) if writing else (p.is_relative_to(output) or p.is_relative_to(HERE) or str(p).startswith(sys.base_prefix+'/lib/'))
            if not ok:denied.append('open');raise RuntimeError('foreign file access denied')
            if p.suffix=='.pyc' and p.is_relative_to(output) and not writing:pyc_reads.append(str(p))
    sys.addaudithook(audit);output.mkdir()
    names=('assembly_preflight.py','frozen_layout.py','integration/runtime_support/recipe.py','integration/runtime_support/gates.py','integration/runner.py','admission.py')
    before={n:pin((HERE/'overlay'/n).read_bytes()) for n in names}
    candidate=output/'candidate';source=candidate/'source';inp=output/'inputs';ref=output/'reference'
    for p in (source,candidate/'contract',candidate/'__pycache__',inp/'typed',inp/'raw',ref/'first',ref/'proof'):p.mkdir(parents=True,exist_ok=True)
    prefixes=('work/qwen2_recovered_inputs','work/qwen2_recovered_reference')
    roots=dict(zip(prefixes,(str(inp),str(ref))))
    logicals=([prefixes[0]+'/typed/r'+str(i)+'.bin' for i in range(14)]+[prefixes[0]+'/raw/r'+str(i)+'.bin' for i in range(13)]+
              [prefixes[1]+'/first/r'+str(i)+'.f32le' for i in range(29)]+[prefixes[1]+'/first/mask.bf16le']+
              [prefixes[0]+'/ARTIFACTS.json']+[prefixes[1]+'/first/m'+str(i)+'.json' for i in range(12)]+[prefixes[1]+'/proof/p'+str(i)+'.json' for i in range(6)])
    files={}
    for i,name in enumerate(logicals):
        prefix=next(k for k in prefixes if name.startswith(k+'/'));path=Path(roots[prefix])/name[len(prefix)+1:]
        raw=bytes([i+1])*4;path.write_bytes(raw);files[name]=pin(raw)
    raw=json.dumps(dict(files=files)).encode();(candidate/'contract/FROZEN_DATA_COPIES.json').write_bytes(raw);copy_pin=pin(raw)
    doc=dict(schema='fixed93-readonly-external-frozen-layout-v1',roots=roots,files=files,copy_manifest=copy_pin,read_only=True,copy_payloads=False)
    raw=json.dumps(doc).encode();(candidate/'FROZEN_EXTERNAL_LAYOUT.json').write_bytes(raw);layout_pin=pin(raw)
    resolver_raw=(HERE/'overlay/frozen_layout.py').read_bytes();(candidate/'frozen_layout.py').write_bytes(resolver_raw)
    (candidate/'__pycache__/frozen_layout.cpython-312.pyc').write_bytes(b'UNTRUSTED-BYTECODE-MUST-NOT-OPEN')
    manifest=dict(preparation_files={'frozen_layout.py':pin(resolver_raw),'FROZEN_EXTERNAL_LAYOUT.json':layout_pin,'contract/FROZEN_DATA_COPIES.json':copy_pin})
    (candidate/'SOURCE_MANIFEST.json').write_text(json.dumps(manifest))
    preflight=types.ModuleType('assembly_preflight');preflight.__file__=str(candidate/'assembly_preflight.py')
    raw=(HERE/'overlay/assembly_preflight.py').read_bytes();exec(compile(raw,preflight.__file__,'exec',dont_inherit=True),vars(preflight))
    sys.modules['assembly_preflight']=preflight
    sys.modules['frozen_layout']=types.ModuleType('frozen_layout')
    reject(lambda:preflight.frozen_layout(manifest));del sys.modules['frozen_layout']
    layout=preflight.frozen_layout(manifest)
    need(not pyc_reads and len(layout.files)==76,'raw source loader, not bytecode')
    checks=['canonical_raw_source_loader_rejects_foreign_module_and_ignores_pyc']
    canonical=sys.modules['frozen_layout'];saved=canonical.PREFIXES;canonical.PREFIXES=('foreign',)
    reject(lambda:preflight.frozen_layout(manifest));canonical.PREFIXES=saved
    saved=canonical.FrozenLayout.path;canonical.FrozenLayout.path=lambda *a:None
    reject(lambda:preflight.frozen_layout(manifest));canonical.FrozenLayout.path=saved
    saved=canonical.load.__defaults__;canonical.load.__defaults__=(False,)
    reject(lambda:preflight.frozen_layout(manifest));canonical.load.__defaults__=saved
    saved=canonical.FrozenLayout.read.__kwdefaults__['reference_opened']
    canonical.FrozenLayout.read.__kwdefaults__['reference_opened']=True
    reject(lambda:preflight.frozen_layout(manifest))
    canonical.FrozenLayout.read.__kwdefaults__['reference_opened']=saved
    preflight.frozen_layout(manifest);checks.append('cached_globals_class_members_defaults_and_kwdefaults_drift_rejected')
    # Keep compile context intact, but instantiate only selected original defs.
    recipe_path=HERE/'overlay/integration/runtime_support/recipe.py';raw=recipe_path.read_bytes();tree=ast.parse(raw);code=compile(raw,str(recipe_path),'exec',dont_inherit=True)
    ns=dict(__name__='_synthetic_recipe',ROOT=source,CANDIDATE=candidate,Path=Path,os=os,stat=stat,re=re,sys=sys,types=types,json=json,hashlib=hashlib,
            _LAYOUT=layout,_FROZEN_PREFIXES=prefixes,FROZEN_BINDING='work/qwen2_fixed93_fullblock_binding/FROZEN_BINDING.json',Rejected=ValueError)
    selected=('need','sha','frozen_layout','_relative','_frozen_namespace','frozen_path','frozen_name','safe_path','_local_read','identity','checked','stat_only')
    for name in selected:
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name);ns[name]=function(code_in(code,name),node,ns)
    r=types.SimpleNamespace(**{name:ns[name] for name in selected})
    typed=logicals[0];rawname=logicals[14];reference=logicals[27];meta=prefixes[0]+'/ARTIFACTS.json'
    need(r.frozen_name(r.frozen_path(typed))==typed and r.checked(source,typed,files[typed])==b'\1'*4,'recipe actual read route')
    reject(lambda:r.checked(source,reference,files[reference]));r.stat_only(source,reference,4)
    need(r.checked(source,reference,files[reference],reference_opened=True)==bytes([28])*4,'explicit postseal adapter value')
    for name in ('work/missing','work/qwen2_recovered_inputs/unknown.bin','/absolute','../escape'):
        reject(lambda name=name:r.frozen_path(name))
    checks.append('original_recipe_codetypes_exact_routes_and_no_unknown_work_fallback')
    gates_path=HERE/'overlay/integration/runtime_support/gates.py';raw=gates_path.read_bytes();gtree=ast.parse(raw);gcode=compile(raw,str(gates_path),'exec',dont_inherit=True)
    gns=dict(__name__='_synthetic_gates',R=r,ROOT=source,Path=Path,os=os,re=re,sys=sys,types=types,DATA=inp/'typed',REFERENCE=ref/'first',
             DATA_LOGICAL=prefixes[0]+'/typed',REFERENCE_LOGICAL=prefixes[1]+'/first',OUTPUT_ROOT=candidate/'work/fixed93_fullblock',TAIL_INPUTS=inp/'typed',require=ns['need'])
    for name in ('_canonical','data_path','reference_path','fresh_output'):
        node=next(n for n in gtree.body if isinstance(n,ast.FunctionDef) and n.name==name);gns[name]=function(code_in(gcode,name),node,gns)
    need(gns['data_path'](gns['DATA_LOGICAL'])==inp/'typed' and gns['reference_path'](gns['REFERENCE_LOGICAL'])==ref/'first','logical argv remains exact')
    reject(lambda:gns['data_path'](str(inp/'typed')));reject(lambda:gns['reference_path'](str(ref/'first')))
    out=gns['OUTPUT_ROOT']/'one';gns['fresh_output'](out,inp/'typed');reject(lambda:gns['fresh_output'](inp/'out',inp/'typed'))
    checks.append('original_path_guards_and_external_output_exclusion')
    cls=next(n for n in gtree.body if isinstance(n,ast.ClassDef) and n.name=='OracleGate');ccode=code_in(gcode,'OracleGate')
    gate=types.SimpleNamespace(opened=False,blocked=0,out=out,input_paths={r.frozen_path(typed)},raw_paths={r.frozen_path(rawname)},
       reference_paths={r.frozen_path(reference)},metadata_paths={r.frozen_path(meta)},runtime_paths=set(),artifacts={},input_reads=[],reference_reads=[],provenance_reads=[],
       parent_stat_path=Path('/proc/0/stat'),parent_identity_bound={'pid':0},source_cache_bypasses=[],artifact_reads=[])
    gate._cleanup_directory=lambda *a:None
    for name in ('_readonly','_deny','open_after_seal','audit'):
        node=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name==name);f=function(code_in(ccode,name),node,gns);setattr(gate,name,types.MethodType(f,gate))
    def observe(name,mode='r',flags=os.O_RDONLY):gate.audit('open',(str(r.frozen_path(name)),mode,flags))
    observe(typed);observe(meta);reject(lambda:observe(rawname));reject(lambda:observe(reference));reject(lambda:observe(typed,'w',os.O_WRONLY))
    reject(lambda:gate.audit('open',(str(inp/'unknown'),'r',os.O_RDONLY)))
    need(gate.input_reads==[typed] and not gate.reference_reads,'logical audit labels and preseal zero reference')
    gate.open_after_seal(dict(actual_outputs_sealed=True,finalfence=True,same_live_identity=True,public_completions=21,actual_owner_jobs=17,accepted_launch_results=1,outstanding_debts={}))
    observe(rawname);observe(reference);need(gate.reference_reads==[reference] and gate.provenance_reads==[rawname],'postseal logical logs')
    checks.append('original_oraclegate_open_branch_and_seal_with_explicit_synthetic_state')
    need(before=={n:pin((HERE/'overlay'/n).read_bytes()) for n in names} and not denied,'sources/boundaries')
    result=dict(status='PASS_SOURCE_CODETYPE_SYNTHETIC_ROUTING_ONLY',checks=checks,groups=len(checks),files=before,
      elapsed_seconds=time.monotonic()-start,maxrss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,denied_boundary_attempts=denied,
      pyc_reads=pyc_reads,actual_oraclegate_constructed=False,synthetic_gate_state=True,recipe_module_top_level_executed=False,
      native_executed=False,DUT_executed=False,real_frozen_inputs_read=False,real_preflight_executed=False,actual_authorized=False)
    (output/'RESULT.json').write_text(json.dumps(result,indent=2)+'\n');return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();print(json.dumps(run(a.output),sort_keys=True))
