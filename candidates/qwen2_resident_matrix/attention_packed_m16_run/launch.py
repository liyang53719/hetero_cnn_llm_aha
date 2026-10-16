"""One explicit, separately reviewed full-M16 attempt. Default is plan-only."""
import argparse,hashlib,importlib,json,math,os,signal,subprocess,sys,time,threading
from contextlib import contextmanager
from pathlib import Path
HERE=Path(__file__).resolve().parent
PREFIX='candidates/qwen2_resident_matrix/attention_packed_m16_entry/'
PROFILE='qwen2-packed-m16-full-run-v1'
MAX_JSON=2*1024*1024
PHASES=('preflight','compose','git_clone','reexec','admission','snapshot','numeric','postflight','complete')
LATER=PHASES
FLAGS=('full_29_node_acceptance','rtl_execution','hardware_recipe_acceptance','useful_wall_mac_90_percent')
OVERRIDES=('ATEN_CPU_CAPABILITY','LD_PRELOAD','LD_LIBRARY_PATH','PYTHONHOME','PYTHONPATH','ONEDNN_MAX_CPU_ISA','DNNL_MAX_CPU_ISA','MKL_CBWR')
def need(ok,message):
 if not ok:raise ValueError(message)
def digest(raw):return hashlib.sha256(raw).hexdigest()
def compact(value):return (json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
def encoded(value):return (json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
def same(left,right):return encoded(strict(encoded(left)))==encoded(strict(encoded(right)))
def strict(raw):
 need(type(raw) is bytes and len(raw)<=MAX_JSON,'bounded metadata')
 def pairs(items):
  out={}
  for key,value in items:
   need(key not in out,'duplicate metadata key');out[key]=value
  return out
 def bad(_):raise ValueError('nonfinite metadata')
 value=json.loads(raw,object_pairs_hook=pairs,parse_constant=bad)
 count=0
 def walk(item,depth=0):
  nonlocal count
  count+=1;need(count<=100000 and depth<=40,'metadata complexity')
  if type(item) is float:need(math.isfinite(item),'finite metadata')
  elif isinstance(item,dict):
   for key,child in item.items():need(type(key) is str and len(key)<=4096,'metadata key');walk(child,depth+1)
  elif isinstance(item,list):
   for child in item:walk(child,depth+1)
  elif isinstance(item,str):need(len(item)<=65536,'metadata string')
 walk(value);return value
def safe(path,directory=False):
 p=Path(path).absolute();need('..' not in p.parts and not p.is_symlink() and p.resolve(strict=True)==p,'canonical path')
 need(p.is_dir() if directory else p.is_file(),'regular path');return p
def sha_file(path):
 p=safe(path);h=hashlib.sha256()
 with p.open('rb') as stream:
  for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
 return h.hexdigest()
def bounded_json(path):
 p=safe(path)
 with p.open('rb') as stream:raw=stream.read(MAX_JSON+1)
 return raw,strict(raw)
def atomic(path,value):
 path=Path(path);raw=encoded(value);need(len(raw)<=MAX_JSON,'bounded atomic metadata')
 temp=path.with_name(path.name+'.tmp')
 with temp.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
 os.replace(temp,path)
def verify_map(root,mapping):
 root=safe(root,True);need(type(mapping) is dict and 0<len(mapping)<=1024,'bounded source map')
 for name,expected in mapping.items():
  need(type(name) is str and name and not name.startswith('/') and '\\' not in name and all(p not in ('','.','..') for p in name.split('/')),'relative source path')
  need(type(expected) is str and len(expected)==64 and all(x in '0123456789abcdef' for x in expected),'source digest')
  need(sha_file(root/name)==expected,'source identity changed')
 return mapping

def load_contract(expected,source_root):
 raw,value=bounded_json(HERE/'contract.json');need(digest(raw)==expected,'reviewed wrapper contract required')
 need(set(value)=={'schema','profile','status','own_sources','support_sources','entry_pins_sha256','origin_commit','python','work_seconds','cleanup_seconds','outer_seconds','numeric_seconds','claims'},'contract schema')
 need(type(value['schema']) is int and value['schema']==1 and value['profile']==PROFILE and value['status']=='REVIEWED_SOURCE_EXECUTION_REQUIRES_ROOT_GATE','contract identity')
 need(all(type(value[k]) is int and value[k]==v for k,v in (('work_seconds',924),('cleanup_seconds',5),('outer_seconds',930),('numeric_seconds',900))),'fixed budgets')
 need(same(value['claims'],{k:False for k in FLAGS}),'contract broad claims')
 need(set(value['own_sources'])=={'launch.py','driver.py','terminal_validator.py','test_launch.py','test_terminal_validator.py','README.md'},'exact wrapper source inventory')
 verify_map(HERE,value['own_sources']);verify_map(source_root,value['support_sources'])
 raw,pins=bounded_json(Path(source_root)/PREFIX/'pins.json')
 need(digest(raw)==value['entry_pins_sha256'],'exact reviewed entry pins')
 need(set(pins)=={'schema','profile','sources','own','generated','inputs','targets','execution_scope'},'entry pins schema')
 need(type(pins['schema']) is int and pins['schema']==1 and pins['profile']=='qwen2-public-pv16-packed-m16-linked-v1' and pins['execution_scope']=='ORIGINAL_M16_PUBLIC21','exact linked entry scope')
 need(pins['inputs']==dict(pins['sources'],**pins['own']),'entry input closure')
 verify_map(source_root,pins['inputs'])
 return value,pins

def runtime_python(origin,argument,contract):
 origin=safe(origin,True);argument=Path(argument).absolute()
 need(argument==origin/'private/assets/venv/bin/python','retained private venv interpreter')
 resolved=safe(argument.resolve(strict=True));expected=contract['python']
 need(set(expected)=={'implementation','version','bytes','sha256'} and expected['implementation']=='CPython' and expected['version']==[3,12,14],'fixed normal CPython version')
 need(resolved.stat().st_size==expected['bytes'] and sha_file(resolved)==expected['sha256'],'fixed interpreter file identity')
 return argument

def support(source_root):
 sys.path.insert(0,str(source_root))
 p=importlib.import_module('candidates.qwen2_resident_matrix.attention_packed_m16_assets.producer')
 s=importlib.import_module('candidates.qwen2_resident_matrix.attention_packed_m16_assets_launch.supervisor')
 need(Path(p.__file__).resolve()==source_root/'candidates/qwen2_resident_matrix/attention_packed_m16_assets/producer.py','producer import path')
 need(Path(s.__file__).resolve()==source_root/'candidates/qwen2_resident_matrix/attention_packed_m16_assets_launch/supervisor.py','supervisor import path')
 return p,s

def clean_environment(control):
 need(not any(os.environ.get(key) for key in OVERRIDES),'unreviewed runtime override')
 return dict(PATH='/usr/bin:/bin',HOME=str(control/'home'),TMPDIR=str(control/'tmp'),HF_HOME=str(control/'hf'),LANG='C.UTF-8',OMP_NUM_THREADS='4',MKL_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4',PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1',GIT_NO_LAZY_FETCH='1')

def safe_progress(path,context):
 raw,value=bounded_json(path)
 need(set(value)=={'schema','phase','ordinal','pid','elapsed_seconds','context_sha256'},'safe progress schema')
 need(type(value['schema']) is int and value['schema']==1 and value['phase'] in PHASES and type(value['ordinal']) is int and value['ordinal']==PHASES.index(value['phase']),'safe phase identity')
 need(type(value['pid']) is int and value['pid']==context['child_pid'] and value['context_sha256']==context['context_sha256'],'safe writer identity')
 elapsed=value['elapsed_seconds'];need(type(elapsed) in (int,float) and math.isfinite(elapsed) and 0<=elapsed<=930,'safe elapsed')
 return value

@contextmanager
def deadline(stop):
 need(threading.current_thread() is threading.main_thread() and signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0),'dedicated timer-free main process')
 need(type(stop) in (int,float) and math.isfinite(stop) and stop>time.monotonic(),'remaining finite deadline')
 old={sig:signal.getsignal(sig) for sig in (signal.SIGALRM,signal.SIGTERM,signal.SIGINT)}
 def expired(_signal,_frame):raise TimeoutError('fixed full-run deadline')
 def terminated(_signal,_frame):raise InterruptedError('full-run cancelled')
 signal.signal(signal.SIGALRM,expired);signal.signal(signal.SIGTERM,terminated);signal.signal(signal.SIGINT,terminated)
 signal.setitimer(signal.ITIMER_REAL,max(0.000001,stop-time.monotonic()))
 try:yield stop
 finally:
  signal.setitimer(signal.ITIMER_REAL,0)
  for sig,handler in old.items():signal.signal(sig,handler)

def launch(args):
 started=time.monotonic();outer=started+930;child=None;libc=None;control=None;code=None;phase='preflight';failure=None;clean=False
 source=safe(args.source_root,True);contract,pins=load_contract(args.contract_sha256,source)
 p,s=support(source)
 with deadline(started+924) as stop:
  try:
   origin=safe(args.origin,True);prepared=safe(args.preparation_workspace,True);compiled=safe(args.compile_receipt);compile_origin=safe(args.compile_origin,True)
   work=Path(args.workspace).absolute();safe(work.parent,True)
   need('..' not in work.parts and not work.exists() and not work.is_symlink(),'one fresh attempt workspace')
   for other in (origin,source,prepared,compile_origin,HERE):need(not work.is_relative_to(other) and not other.is_relative_to(work),'disjoint fresh workspace')
   need(sys.flags.optimize==0,'production wrapper requires normal Python')
   python=runtime_python(origin,args.python,contract)
   runtime_python(origin,sys.executable,contract)
   work.mkdir(mode=0o700)
   with (work/'ATTEMPT_LOCK').open('xb') as lock:
    lock.write(encoded(dict(schema=1,attempt=1,pid=os.getpid(),started=started,contract_sha256=args.contract_sha256)));lock.flush();os.fsync(lock.fileno())
   control=work/'control';control.mkdir(mode=0o700)
   for name in ('home','tmp','hf'):(control/name).mkdir(mode=0o700)
   context=dict(schema=1,profile=PROFILE,source_root=str(source),origin=str(origin),preparation_workspace=str(prepared),compile_receipt=str(compiled),compile_origin=str(compile_origin),workspace=str(work),python=str(python),contract_sha256=args.contract_sha256,started=started,work_deadline=stop,outer_deadline=outer,parent_pid=os.getpid())
   atomic(control/'CONTEXT.json',context);context_sha=sha_file(control/'CONTEXT.json')
   libc=s.enable_subreaper()
   command=[str(python),'-I','-B',str(HERE/'driver.py'),'prepare',str(control/'CONTEXT.json'),context_sha]
   with (control/'stdout.log').open('xb') as stdout,(control/'stderr.log').open('xb') as stderr:
    blocked=signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGALRM,signal.SIGTERM,signal.SIGINT})
    try:
     process=subprocess.Popen(command,cwd=control,env=clean_environment(control),stdout=stdout,stderr=stderr,start_new_session=True)
     child=s.Child(process)
    finally:signal.pthread_sigmask(signal.SIG_SETMASK,blocked)
    phase='child';code=child.wait(stop)
   need(code==0 and child.clean_exit(),'child exit/debt failure')
   phase='postflight'
   load_contract(args.contract_sha256,source);runtime_python(origin,args.python,contract)
   need(sha_file(control/'CONTEXT.json')==context_sha,'parent context overwritten')
   _,done=bounded_json(control/'CHILD_COMPLETE.json')
   need(set(done)=={'schema','status','pid','context_sha256','source_manifest_sha256','result_sha256','snapshot_sha256','public'} and type(done['schema']) is int and done['schema']==1 and done['status']=='VALIDATED_M16_CHILD_COMPLETE' and done['pid']==process.pid and done['context_sha256']==context_sha,'completed child identity')
   from . import terminal_validator as terminal
   _,proof=bounded_json(control/'SOURCE_PROOF.json')
   expected_sources=dict(pins['sources'],**pins['own'],**pins['generated']);expected_sources[PREFIX+'pins.json']=contract['entry_pins_sha256']
   need(set(proof)=={'schema','pid','context_sha256','work_deadline','git_head','committed_cpp_sha256','runtime_sources','source_manifest_sha256'} and type(proof['schema']) is int and proof['schema']==1 and proof['runtime_sources']==expected_sources,'exact frozen source proof')
   need(proof['source_manifest_sha256']==digest(compact(expected_sources))==done['source_manifest_sha256'],'exact source manifest proof')
   need(proof['git_head']==contract['origin_commit'],'original Git proof')
   verify_map(work/'source',expected_sources)
   public=terminal.validate_terminal(work/'actual/summary.json',done['result_sha256'],expected_sources,work/'snapshot/SNAPSHOT.json',done['snapshot_sha256'])
   need(same(public,done['public']) and public['summary_sha256']==done['result_sha256'],'postflight exact result binding')
   need(proof['context_sha256']==context_sha and proof['pid']==process.pid and proof['work_deadline']==stop,'same-PID/deadline source proof')
   s.restore_subreaper(libc);libc=None;clean=True
   summary=dict(schema=1,profile=PROFILE,status='PASS_ASSIGNED_OFFICIAL_OBSERVED_GATES_ONLY',phase='complete',contract_sha256=args.contract_sha256,child_exit_code=0,cleanup_complete=True,elapsed_seconds=round(time.monotonic()-started,6),source_manifest_sha256=done['source_manifest_sha256'],context_sha256=context_sha,validation=public,assigned_official_observed_gates_passed=True,numerical_acceptance=False,numerical_run_started=True,actual_chain_completion_verified=True,actual_chain_executed=True,**{k:False for k in FLAGS})
   atomic(work/'PRIVATE_LAUNCH_RECEIPT.json',dict(context=context,source_proof=proof,child_complete=done,caller_must_observe_launcher_exit=True))
   summary['private_launch_receipt_sha256']=sha_file(work/'PRIVATE_LAUNCH_RECEIPT.json')
  except BaseException as error:
   failure=error
   with p.protected_cleanup():
    clean=True
    if child is not None:
     try:clean=child.terminate(outer)
     except BaseException:clean=False
    if libc is not None and clean:
     try:s.restore_subreaper(libc);libc=None
     except BaseException:clean=False
    if control is not None:
     for target in (control/'CHILD_COMPLETE.json',control.parent/'PRIVATE_LAUNCH_RECEIPT.json'):
      try:target.unlink(missing_ok=True)
      except BaseException:clean=False
   last_phase='unavailable'
   if control is not None and child is not None:
    try:last_phase=safe_progress(control/'progress.json',dict(child_pid=process.pid,context_sha256=context_sha))['phase']
    except BaseException:pass
   numerical_started=(LATER.index(last_phase)>=LATER.index('numeric')) if last_phase in LATER else None
   status='TIMEOUT' if isinstance(error,TimeoutError) else 'CANCELLED' if isinstance(error,(InterruptedError,KeyboardInterrupt)) else 'FAILED'
   summary=dict(schema=1,profile=PROFILE,status=status if clean else 'FAILED_CLEANUP',phase=phase,last_valid_child_phase=last_phase,contract_sha256=args.contract_sha256,child_exit_code=code,cleanup_complete=clean,elapsed_seconds=round(time.monotonic()-started,6),numerical_acceptance=False,numerical_run_started=numerical_started,actual_chain_completion_verified=False,**{k:False for k in FLAGS})
 if control is not None:
  try:
   with deadline(outer):atomic(control.parent/'summary.json',summary)
  except BaseException:
   summary=dict(schema=1,profile=PROFILE,status='FAILED_PUBLICATION',numerical_acceptance=False,numerical_run_started=summary.get('numerical_run_started'),actual_chain_completion_verified=summary.get('actual_chain_completion_verified',False),**{k:False for k in FLAGS})
 return summary

def main(argv=None):
 parser=argparse.ArgumentParser(description=__doc__)
 for key in ('source-root','origin','preparation-workspace','compile-receipt','compile-origin','workspace','python','contract-sha256'):parser.add_argument('--'+key,required=True)
 parser.add_argument('--execute',action='store_true');args=parser.parse_args(argv)
 try:
  if not args.execute:
   load_contract(args.contract_sha256,Path(args.source_root));value=dict(status='PLAN_ONLY_NO_EXECUTION',numeric_seconds=900,work_seconds=924,cleanup_seconds=5,outer_seconds=930)
  else:value=launch(args)
 except BaseException:value=dict(status='FAILED_PREFLIGHT',numerical_acceptance=False,**{k:False for k in FLAGS})
 print(json.dumps(value,sort_keys=True,allow_nan=False),flush=True)
 return 0 if value['status'] in ('PLAN_ONLY_NO_EXECUTION','PASS_ASSIGNED_OFFICIAL_OBSERVED_GATES_ONLY') else 1
if __name__=='__main__':raise SystemExit(main())
