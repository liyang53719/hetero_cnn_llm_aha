"""Finite first-N0 adapters. Default import has no network, tensors or native work.
The coordinator owns the original job deadline and every child process group.
"""
from __future__ import annotations
import hashlib,json,math,os,stat,sys,time,types
from pathlib import Path
MIB=1024**2
GIB=1024**3
PREFIX='candidates/host93_ci_recovery/first_n0/'
INPUTS='candidates/host93_first_n0_sources/inputs/'
REFERENCE='candidates/host93_first_n0_sources/reference/'
RUNTIME='candidates/host93_first_n0_sources/runtime/'
COMPARISON='candidates/host93_first_n0_sources/comparison/'
RAW='development_snapshots/canonical_raw_acquisition_source_20261018/acquire_raw.py'
FRONT_STAGES=('n0_wheels_acquire','n0_runtime_install','n0_raw_acquire','n0_inputs_prepare','n0_reference')
FINAL_STAGES=('host93_first_n0','host93_n0_compare')
PRIVATE_STAGES=FRONT_STAGES+FINAL_STAGES
FRONT_COMPONENTS=('n0_runtime','n0_inputs','n0_reference')
BOUNDARIES=('N0_SOURCE','N0_RUNTIME_PREPARE','N0_RUNTIME_TREE','N0_RAW_RECEIPT','N0_INPUT_RECEIPT','N0_REFERENCE_RECEIPT','N0_REFERENCE_RSS','N0_CAPTURE_RECEIPT','N0_CAPTURE_INPUTS','N0_CAPTURE_ELF','N0_COMPARE_RECEIPT','N0_COMPARE_RSS','N0_DEADLINE','N0_PHASE_ORDER')
CODES=('N0_SOURCE','N0_PATH','N0_READ','N0_CHANGED','N0_JSON','N0_INPUTS','N0_RUNTIME','N0_REFERENCE','N0_CAPTURE','N0_COMPARISON','N0_RSS','N0_DEADLINE','N0_FLAGS','N0_OUTPUT','N0_PHASE')
F32={'bytes':786432,'sha256':'3c25077e0b7aa5819df6fb93cbaba6a0d5379ac06b9df468beecd0f259b5cc3f'}
BF16={'bytes':393216,'sha256':'bd41672e6ea7d12746b41e56d21b3309369ecfd87cc26319ae6adbf0874e5cf2'}
class Rejected(ValueError):
 def __init__(self,boundary,code):
  self.safe_contract_boundary=boundary if boundary in BOUNDARIES else 'N0_SOURCE'
  self.safe_contract_code=code if code in CODES else 'N0_SOURCE'
  super().__init__(self.safe_contract_code)
def need(ok,boundary,code):
 if not ok:raise Rejected(boundary,code)
def bounded(boundary,code,fn,*args,**kwargs):
 try:return fn(*args,**kwargs)
 except (TimeoutError,KeyboardInterrupt,SystemExit,MemoryError):raise
 except BaseException as e:raise Rejected(boundary,code) from e
def sha(raw):return hashlib.sha256(raw).hexdigest()
def plain(path):
 p=Path(path);need(p.is_absolute() and '..' not in p.parts and all(not x.is_symlink() for x in (p,*p.parents)),'N0_SOURCE','N0_PATH');return p

def read(path,cap,expected=None):
 p=plain(path);fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 with os.fdopen(fd,'rb') as f:
  before=os.fstat(f.fileno());need(stat.S_ISREG(before.st_mode) and 0<=before.st_size<=cap,'N0_SOURCE','N0_READ')
  raw=f.read(cap+1);after=os.fstat(f.fileno())
 sig=lambda s:(s.st_dev,s.st_ino,s.st_mode,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
 need(sig(before)==sig(after)==sig(p.stat(follow_symlinks=False)) and len(raw)==before.st_size,'N0_SOURCE','N0_CHANGED')
 if expected is not None:need({'bytes':len(raw),'sha256':sha(raw)}==expected,'N0_SOURCE','N0_CHANGED')
 return raw

def decode(raw):
 def pairs(items):
  d={}
  for k,v in items:need(k not in d,'N0_SOURCE','N0_JSON');d[k]=v
  return d
 def invalid(_):raise Rejected('N0_SOURCE','N0_JSON')
 return json.loads(raw,object_pairs_hook=pairs,parse_constant=invalid)

def load(repo,pins,relative):
 p=pins[relative];raw=read(repo/relative,p['bytes'],p);m=types.ModuleType('_n0_'+sha(raw)[:12]);m.__file__=str(repo/relative);sys.modules[m.__name__]=m;exec(compile(raw,str(repo/relative),'exec',dont_inherit=True),m.__dict__);return m

BOOTSTRAP="""import hashlib,os,stat,sys,types
p,n,h=sys.argv[1:4];f=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
with os.fdopen(f,'rb') as s:
 a=os.fstat(s.fileno());b=s.read(int(n)+1);z=os.fstat(s.fileno())
if not(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode and stat.S_ISREG(a.st_mode) and a.st_size==int(n) and len(b)==int(n) and hashlib.sha256(b).hexdigest()==h and (a.st_dev,a.st_ino,a.st_size,a.st_mtime_ns,a.st_ctime_ns)==(z.st_dev,z.st_ino,z.st_size,z.st_mtime_ns,z.st_ctime_ns)):raise SystemExit('N0_SOURCE_REJECTED')
sys.argv=[p]+sys.argv[4:];m=types.ModuleType('_verified_n0_child');m.__file__=p;sys.modules[m.__name__]=m
exec(compile(b,p,'exec',dont_inherit=True),m.__dict__)
raise SystemExit(m.main())
"""
def argv(repo,pins,relative,options):
 pin=pins[relative];return [str(Path(sys.executable).resolve()),'-I','-S','-B','-c',BOOTSTRAP,str(repo/relative),str(pin['bytes']),pin['sha256']]+list(map(str,options))

def limits(total,work,cpu,address,fsize,log=65536):
 return {'total_seconds':total,'work_seconds':work,'cpu_seconds':cpu,'as_bytes':address,'fsize_bytes':fsize,'log_bytes':log,'sample_rows':total+16}

def cap_deadline(bound,stop):
 left=math.floor(stop-time.monotonic());need(left>16,'N0_DEADLINE','N0_DEADLINE')
 result=dict(bound);result['total_seconds']=min(bound['total_seconds'],left);result['work_seconds']=min(bound['work_seconds'],result['total_seconds']-15);result['sample_rows']=result['total_seconds']+16;return result

def native_environment(work,network=False,numeric=False):
 env={'PATH':'/usr/bin:/bin','HOME':str(work/'home'),'TMPDIR':str(work/'tmp'),'LANG':'C','LC_ALL':'C','PYTHONNOUSERSITE':'1','PYTHONDONTWRITEBYTECODE':'1'}
 if network:
  for key in ('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY','http_proxy','https_proxy','all_proxy','no_proxy','SSL_CERT_FILE','SSL_CERT_DIR','REQUESTS_CA_BUNDLE','CURL_CA_BUNDLE'):
   if key in os.environ:env[key]=os.environ[key]
 if numeric:env.update(OMP_NUM_THREADS='4',MKL_NUM_THREADS='4',OPENBLAS_NUM_THREADS='1')
 return env

def rss_observation(evidence):
 raw=read(Path(evidence)/'leader_samples.jsonl',512*1024);rows=[decode(line) for line in raw.splitlines()]
 need(0<len(rows)<=136,'N0_REFERENCE_RSS','N0_RSS')
 values=[]
 for row in rows:
  for key in ('vmrss_kib','vmhwm_kib'):
   v=row.get(key);need(v is None or type(v) is int and 0<=v<=8*1024*1024,'N0_REFERENCE_RSS','N0_RSS')
   if v is not None:values.append(v)
 need(bool(values) and max(values)<=1572864,'N0_REFERENCE_RSS','N0_RSS')
 return {'sampled_leader_max_kib':max(values),'limit_kib':1572864,'os_hard_limit':False,'includes_descendants':False}

def empty_observation():
 return {'state':'NOT_COLLECTED','runtime_ready':False,'inputs_ready':False,'reference_ready':False,'capture_state':'NOT_COLLECTED','capture':None,'comparison_state':'NOT_COLLECTED','comparison':None,'reference_rss':None,'comparison_rss':None,'numeric_window_seconds':3600,'cycle_cap':8000000,'source_reduction_lower_bound':2428928}

def run_frontdoor(repo,work,pins,call_phase,shared_stop,observation,completed):
 """Five fixed native phases; all successful postflights precede next phase."""
 need(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode,'N0_SOURCE','N0_FLAGS')
 repo=plain(repo);work=plain(work);need(not os.path.lexists(work) and work.parent.is_dir(),'N0_SOURCE','N0_PATH');work.mkdir(mode=0o700)
 for name in ('home','tmp'):(work/name).mkdir(mode=0o700)
 stop=min(shared_stop-15,time.monotonic()+1440);wheel_stop=min(stop,time.monotonic()+300)
 runtime=bounded('N0_SOURCE','N0_SOURCE',load,repo,pins,RUNTIME+'runtime_wheel_gate.py')
 bounded('N0_RUNTIME_PREPARE','N0_RUNTIME',runtime.source_preflight,repo/REFERENCE)
 bounded('N0_RUNTIME_PREPARE','N0_RUNTIME',runtime.require_current_python)
 # Fixed child adapter owns explicit network entry, never a downloaded Python module.
 call_phase('n0_wheels_acquire',argv(repo,pins,PREFIX+'stage_entry.py',['--stage','wheels','--repo',repo,'--out',work/'wheels','--deadline',min(wheel_stop,time.monotonic()+180),'--execute']),work,native_environment(work,True),cap_deadline(limits(180,165,120,512*MIB,256*MIB),wheel_stop))
 install=bounded('N0_RUNTIME_PREPARE','N0_RUNTIME',runtime.install_argv,repo/REFERENCE,work/'wheels',work/'runtime')
 call_phase('n0_runtime_install',install,work,native_environment(work),cap_deadline(limits(120,100,90,2*GIB,GIB),wheel_stop))
 bounded('N0_RUNTIME_TREE','N0_RUNTIME',runtime.observe_installed_tree,work/'runtime',work/'wheels')
 need(time.monotonic()<wheel_stop,'N0_DEADLINE','N0_DEADLINE');observation['runtime_ready']=True;observation['state']='COLLECTING';completed.append('n0_runtime')
 call_phase('n0_raw_acquire',argv(repo,pins,PREFIX+'stage_entry.py',['--stage','raw','--repo',repo,'--out',work/'raw','--deadline',min(stop,time.monotonic()+900),'--execute']),work,native_environment(work,True),cap_deadline(limits(900,880,300,512*MIB,128*MIB),stop))
 provider_stop=min(stop,time.monotonic()+120)
 call_phase('n0_inputs_prepare',argv(repo,pins,PREFIX+'prepare_inputs.py',['--repo',repo,'--raw-root',work/'raw','--out',work/'inputs','--shared-stop',provider_stop,'--execute']),work,native_environment(work),cap_deadline(limits(120,100,60,256*MIB,128*MIB),provider_stop))
 receipt=bounded('N0_INPUT_RECEIPT','N0_INPUTS',lambda:decode(read(work/'inputs'/'INPUTS_READY.json',65536)))
 need(type(receipt) is dict and receipt.get('status')=='CANONICAL16_PREPARED_ONLY' and receipt.get('input_bytes')==94920448 and len(receipt.get('inputs',[]))==16 and receipt.get('weights_loaded_into_rtl') is False,'N0_INPUT_RECEIPT','N0_INPUTS')
 observation['inputs_ready']=True;completed.append('n0_inputs')
 reference_stop=min(stop,time.monotonic()+120)
 result=call_phase('n0_reference',argv(repo,pins,REFERENCE+'n0_reference.py',['--repo',repo,'--embedding',work/'raw'/'tensors'/'embed_tokens.rows_0_255.bin','--gamma',work/'raw'/'tensors'/'input_layernorm.weight.bin','--runtime-root',work/'runtime','--python',Path(sys.executable).resolve(),'--python-profile','ci31214','--out',work/'reference','--pins',repo/REFERENCE/'PINS.json','--shared-stop',reference_stop,'--execute']),work,native_environment(work,numeric=True),cap_deadline(limits(120,100,90,8*GIB,4*MIB),reference_stop))
 ref=bounded('N0_REFERENCE_RECEIPT','N0_REFERENCE',lambda:decode(read(work/'reference'/'RECEIPT.json',65536)))
 need(ref.get('status')=='PASS_FROZEN_N0_EXACT' and ref.get('reference_accepted') is True and ref.get('stage')=='COMPLETE' and ref.get('code') is None and ref.get('output')=={'native':BF16,'fp32le':F32,'native_exact':True,'fp32le_exact':True,'accepted':True},'N0_REFERENCE_RECEIPT','N0_REFERENCE')
 bounded('N0_REFERENCE_RECEIPT','N0_REFERENCE',read,work/'reference'/'n0.f32le',F32['bytes'],F32)
 reference_rss=bounded('N0_REFERENCE_RSS','N0_RSS',rss_observation,result['evidence_root'])
 need(time.monotonic()<stop,'N0_DEADLINE','N0_DEADLINE');observation['reference_rss']=reference_rss;observation['reference_ready']=True;completed.append('n0_reference')
 return {'work':work,'inputs':work/'inputs','runtime':work/'runtime','reference':work/'reference'/'n0.f32le'}

def verify_file(path,pin):
 p=plain(path);fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 with os.fdopen(fd,'rb') as f:
  a=os.fstat(f.fileno());need(stat.S_ISREG(a.st_mode) and a.st_size==pin['bytes'],'N0_CAPTURE_INPUTS','N0_INPUTS');h=hashlib.sha256();n=0
  while n<a.st_size:
   b=f.read(min(65536,a.st_size-n));need(bool(b),'N0_CAPTURE_INPUTS','N0_INPUTS');h.update(b);n+=len(b)
  need(not f.read(1),'N0_CAPTURE_INPUTS','N0_INPUTS');z=os.fstat(f.fileno())
 sig=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
 need(sig(a)==sig(z)==sig(p.stat(follow_symlinks=False)) and h.hexdigest()==pin['sha256'],'N0_CAPTURE_INPUTS','N0_INPUTS')
 return {'bytes':n,'sha256':h.hexdigest()}

def canonical_inputs(repo,pins,root):
 spec=decode(read(repo/(INPUTS+'CONVERSION_SPEC.json'),pins[INPUTS+'CONVERSION_SPEC.json']['bytes'],pins[INPUTS+'CONVERSION_SPEC.json']))
 rows=[('metadata/host_commands.bin',{'bytes':384,'sha256':'618cd4db94fbc5f0e3829182a72d5e298b5a42d2a3840ec2b9f9be639cd884c4'}),('metadata/host_descriptors.bin',{'bytes':3456,'sha256':'1e4d35da18b21a4d9de05d2f3129e5bd9717cd923837c83c8d5eb320bfcddb02'})]
 rows += [('providers/'+r['name']+'.bin',{'bytes':r['output_bytes'],'sha256':r['expected_output_sha256']}) for r in spec['providers']]
 need(len(rows)==16 and sum(p['bytes'] for _,p in rows)==94920448,'N0_CAPTURE_INPUTS','N0_INPUTS')
 for name,pin in rows:verify_file(root/name,pin)
 return rows

def natural_exit(row,code):
 return row.get('exit_code')==code and row.get('waitid_code')==1 and row.get('waitid_status')==code and row.get('receipt_timed_out') is False and row.get('cleanup_confirmed') is True and row.get('kill_attempted') is True and row.get('kill_result') in ('SIGNAL_SENT_BEFORE_REAP','GROUP_ALREADY_ABSENT') and row.get('final_reap_signal') is None

def validate_comparison(report,comparator,capture,actual_pin):
 need(type(report) is dict and set(report)==comparator.REPORT_KEYS,'N0_COMPARE_RECEIPT','N0_COMPARISON')
 need(report['schema']==1 and report['scope']=='FIRST_N0_M128_ONLY' and report['stage']=='COMPLETE' and report['code'] is None and report['full_block_pass'] is False and report['reference_hash_accepted'] is True and report['capture_basic_counts_accepted'] is True,'N0_COMPARE_RECEIPT','N0_COMPARISON')
 need(report['shape']==[1,128,1536] and type(report['elements']) is int and report['elements']==196608 and type(report['actual_bytes']) is int and report['actual_bytes']==786432 and type(report['reference_bytes']) is int and report['reference_bytes']==786432,'N0_COMPARE_RECEIPT','N0_COMPARISON')
 need(all(type(report[k]) is str and len(report[k])==64 and all(c in '0123456789abcdef' for c in report[k]) for k in ('source_sha256','contract_sha256','capture_sha256','actual_sha256','reference_sha256')),'N0_COMPARE_RECEIPT','N0_COMPARISON')
 need(report['source_sha256']==comparator.ORIGINAL_SCRIPT['sha256'] and report['contract_sha256']==comparator.ORIGINAL_CONTRACT['sha256'] and report['capture_sha256']==capture['sha256'] and report['actual_sha256']==actual_pin['sha256'] and report['reference_sha256']==F32['sha256'],'N0_COMPARE_RECEIPT','N0_COMPARISON')
 metric=report['metrics'];need(type(metric) is dict and set(metric)==comparator.METRIC_KEYS,'N0_COMPARE_RECEIPT','N0_COMPARISON')
 need(metric['shape']==[1,128,1536] and type(metric['elements']) is int and metric['elements']==196608 and metric['finite'] is True and metric['actual_f32_sha256']==actual_pin['sha256'] and metric['reference_f32_sha256']==F32['sha256'],'N0_COMPARE_RECEIPT','N0_COMPARISON')
 for key in ('max_abs','mean_abs','relative_l2','cosine','normalized_max_abs'):
  need(metric[key] is None or type(metric[key]) is float and math.isfinite(metric[key]),'N0_COMPARE_RECEIPT','N0_COMPARISON')
 need(type(metric['max_abs']) is float and metric['max_abs']>=0 and type(metric['mean_abs']) is float and metric['mean_abs']>=0 and type(metric['different_elements']) is int and 0<=metric['different_elements']<=196608,'N0_COMPARE_RECEIPT','N0_COMPARISON')
 need(report['limits']=={'max_abs':0.03125,'mean_abs':0.005},'N0_COMPARE_RECEIPT','N0_COMPARISON')
 passed=metric['max_abs']<=.03125 and metric['mean_abs']<=.005
 need(type(report['numeric_pass']) is bool and report['numeric_pass']==passed and report['status']==('N0_LIMITED_TOLERANCE_PASS' if passed else 'N0_LIMITED_TOLERANCE_FAIL'),'N0_COMPARE_RECEIPT','N0_COMPARISON')
 need(all(type(report[k]) is bool for k in ('bit_exact','hash_exact')) and type(metric['bit_exact']) is bool and report['bit_exact']==metric['bit_exact']==(metric['different_elements']==0) and report['hash_exact']==(actual_pin['sha256']==F32['sha256']) and report['bit_exact']==report['hash_exact'],'N0_COMPARE_RECEIPT','N0_COMPARISON')
 return passed

def cycle_budget_counts(raw,comparator):
 """Only the fixed full 8M terminal receipt, never an accepted numeric capture."""
 counts=decode(raw);need(type(counts) is dict and set(counts)==comparator.COUNT_KEYS,'N0_CAPTURE_RECEIPT','N0_CAPTURE')
 expected={'scope':'FIRST_N0_M128_ONLY','status':'INCOMPLETE_CYCLE_BUDGET','numeric_comparison':'NOT_RUN','phase':'RTL_N0','code':'CYCLE_BUDGET','full_block_pass':False,'root256_handles':'UNKNOWN','cycle_budget':8000000,'reduction_only_source_floor':2428928,'unproven_overhead_allowance':5571072,'cycles':8000000,'completion_acks':0,'further_eval_calls':0,'actual_values':0,'actual_bytes':0}
 for key,value in expected.items():need(type(counts[key]) is type(value) and counts[key]==value,'N0_CAPTURE_RECEIPT','N0_CAPTURE')
 for key,value in counts.items():
  if key not in expected and key not in comparator.ARRAY_SIZES and key!='axi':need(comparator.nonnegative_int(value),'N0_CAPTURE_RECEIPT','N0_CAPTURE')
 for key,length in comparator.ARRAY_SIZES.items():
  value=counts[key];need(type(value) is list and len(value)==length and all(comparator.nonnegative_int(x) for x in value),'N0_CAPTURE_RECEIPT','N0_CAPTURE')
 axi=counts['axi'];need(type(axi) is dict and set(axi)==comparator.AXI_KEYS and all(comparator.nonnegative_int(x) for x in axi.values()),'N0_CAPTURE_RECEIPT','N0_CAPTURE')
 need(all(counts[key]<=1 for key in ('launches','jobs','owner_dones','post_pc','post_issued_jobs')) and counts['successful_b']==axi['bs']<=12288 and counts['committed_bytes']==axi['strobed_bytes']<=786432 and counts['writeback_bytes']<=786432,'N0_CAPTURE_RECEIPT','N0_CAPTURE')
 need(all(axi[key]<=8000000 for key in ('ar_stall','aw_stall','w_stall','r_stall','b_stall')),'N0_CAPTURE_RECEIPT','N0_CAPTURE')
 return counts

def run_numeric(repo,work,pins,call_phase,shared_stop,front,execution,observation,completed,stages):
 window_stop=min(shared_stop-15,time.monotonic()+3600)
 work=plain(work);need(not os.path.lexists(work) and work.parent.is_dir(),'N0_CAPTURE_RECEIPT','N0_PATH');work.mkdir(mode=0o700)
 for name in ('home','tmp'):(work/name).mkdir(mode=0o700)
 comparator=bounded('N0_SOURCE','N0_SOURCE',load,repo,pins,COMPARISON+'n0_compare.py')
 elf=execution['compiled_executable'];identity={k:elf[k] for k in ('bytes','sha256')}
 bounded('N0_CAPTURE_ELF','N0_CAPTURE',verify_file,Path(elf['path']),identity)
 bounded('N0_CAPTURE_INPUTS','N0_INPUTS',canonical_inputs,repo,pins,front['inputs'])
 capture=work/'capture';observation['capture_state']='READ_ERROR'
 try:
  call_phase('host93_first_n0',[elf['path'],str(front['inputs']),str(capture)],work,native_environment(work),cap_deadline(limits(3540,3510,3540,6*GIB,4*MIB),window_stop-45))
 except BaseException:
  observation['capture_state']='NATIVE_FAILED'
  # Only a natural exit2 plus the exact full fixed cycle-cap receipt may retain
  # finite counters. Missing/invalid counts never replace the native exception.
  try:
   need(stages and stages[-1]['name']=='host93_first_n0' and natural_exit(stages[-1],2),'N0_CAPTURE_RECEIPT','N0_CAPTURE')
   partial=cycle_budget_counts(read(capture/'counts.json',65536),comparator)
   observation['capture_state']='REPORTED';observation['capture']=partial
  except BaseException:pass
  raise
 raw=bounded('N0_CAPTURE_RECEIPT','N0_CAPTURE',read,capture/'counts.json',65536)
 counts=bounded('N0_CAPTURE_RECEIPT','N0_CAPTURE',comparator.capture_gate,raw)
 actual_raw=bounded('N0_CAPTURE_RECEIPT','N0_CAPTURE',read,capture/'actual_n0.f32le',786432)
 need(len(actual_raw)==786432,'N0_CAPTURE_RECEIPT','N0_CAPTURE');actual_pin={'bytes':len(actual_raw),'sha256':sha(actual_raw)}
 bounded('N0_CAPTURE_INPUTS','N0_INPUTS',canonical_inputs,repo,pins,front['inputs'])
 bounded('N0_CAPTURE_ELF','N0_CAPTURE',verify_file,Path(elf['path']),identity)
 observation['capture_state']='AVAILABLE';observation['capture']=counts;completed.append('n0_capture')
 observation['comparison_state']='READ_ERROR';failure=None;result=None
 try:
  result=call_phase('host93_n0_compare',argv(repo,pins,COMPARISON+'n0_compare.py',['--repo',repo,'--reference-worker',repo/REFERENCE/'n0_reference.py','--pins',repo/REFERENCE/'PINS.json','--runtime-root',front['runtime'],'--python',Path(sys.executable).resolve(),'--reference',front['reference'],'--actual',capture/'actual_n0.f32le','--capture',capture/'counts.json','--out',work/'comparison','--shared-stop',min(window_stop,time.monotonic()+30),'--execute']),work,native_environment(work,numeric=True),cap_deadline(limits(30,15,25,8*GIB,4*MIB),window_stop))
 except BaseException as error:failure=error
 try:
  report=bounded('N0_COMPARE_RECEIPT','N0_COMPARISON',lambda:decode(read(work/'comparison'/'RECEIPT.json',65536)))
  passed=validate_comparison(report,comparator,{'bytes':len(raw),'sha256':sha(raw)},actual_pin)
  need(stages and stages[-1]['name']=='host93_n0_compare' and natural_exit(stages[-1],0 if passed else 1),'N0_COMPARE_RECEIPT','N0_COMPARISON')
  need((failure is None)==passed,'N0_COMPARE_RECEIPT','N0_COMPARISON')
  bounded('N0_COMPARE_RECEIPT','N0_COMPARISON',read,capture/'counts.json',len(raw),{'bytes':len(raw),'sha256':sha(raw)})
  bounded('N0_COMPARE_RECEIPT','N0_COMPARISON',verify_file,capture/'actual_n0.f32le',actual_pin)
  bounded('N0_REFERENCE_RECEIPT','N0_REFERENCE',read,front['reference'],F32['bytes'],F32)
  phase_root=Path(result['evidence_root']) if result is not None else work.parent/'phases'/'host93_n0_compare'
  comparison_rss=bounded('N0_COMPARE_RSS','N0_RSS',rss_observation,phase_root)
  need(time.monotonic()<window_stop,'N0_DEADLINE','N0_DEADLINE')
  observation['comparison_rss']=comparison_rss;observation['comparison_state']='AVAILABLE';observation['comparison']=report;observation['state']='COMPLETE';completed.append('n0_comparison');return passed
 except BaseException as post_error:
  if failure is not None:
   if isinstance(post_error,Rejected):
    try:failure.safe_contract_boundary=post_error.safe_contract_boundary;failure.safe_contract_code=post_error.safe_contract_code
    except BaseException:pass
   raise failure
  raise

def fixed_markers(repo,pins,name):
 if name in ('n0_wheels_acquire','n0_raw_acquire'):
  entry=load(repo,pins,PREFIX+'stage_entry.py');runtime=load(repo,pins,RUNTIME+'runtime_wheel_gate.py')
  codes=set(entry.RAW_RULES.values())|set(runtime.CODES)|{'FLAGS','PATH','SOURCE','DEADLINE','RESOURCE','UNEXPECTED','UNMAPPED_RAW'}
  return {'N0_ACQUISITION_FAILED:'+stage+':'+code for stage in ('SOURCE','WHEELS','RAW_SOURCE','RAW_OUTPUT','RAW_ACQUIRE') for code in codes}
 if name=='n0_runtime_install':return set()
 if name=='n0_inputs_prepare':return {'N0_INPUTS_INCOMPLETE:'+code for code in load(repo,pins,PREFIX+'prepare_inputs.py').CODES}
 if name=='n0_reference':
  codes=load(repo,pins,REFERENCE+'n0_reference.py').CODES
  return {status+':'+code for status in ('NOT_COMPLETED','REFERENCE_MISMATCH') for code in codes}
 if name=='host93_n0_compare':
  codes=load(repo,pins,COMPARISON+'n0_compare.py').CODES
  return {'NOT_COMPLETED:'+code for code in codes}|{'N0_LIMITED_TOLERANCE_FAIL'}
 return set()

def private_diagnostics(repo,pins,name,path):
 result={'observations':[],'merged_log_tail':'','truncated':False,'context_state':'READ_ERROR'}
 try:raw=read(path,65536)
 except BaseException:return result
 result['context_state']='AVAILABLE';selected=[]
 try:
  allowed=fixed_markers(repo,pins,name)
  for line in raw.decode('ascii',errors='replace').splitlines():
   if line in allowed:selected.append(line)
  if name=='host93_first_n0':
   relative='candidates/host93_first_n0_sources/bridge/metadata/DIAGNOSTIC_MAP.json';pin=pins[relative]
   table=decode(read(repo/relative,pin['bytes'],pin))
   codes={r['code'] for r in table['messages'].values()}|{'UNMAPPED','CYCLE_BUDGET','ALLOCATION_LIMIT','CLI_ARGUMENT_COUNT','CLI_INPUT_ROOT','CLI_OUTPUT_ROOT','CLI_PARENT_TRAVERSAL','OUTPUT_DIRECTORY','OUTPUT_WRITE','OUTPUT_REPORT'}
   for line in raw.splitlines():
    try:item=decode(line)
    except BaseException:continue
    if type(item) is dict and set(item)=={'scope','status','phase','code','numeric_comparison'} and item['scope']=='FIRST_N0_M128_ONLY' and item['numeric_comparison']=='NOT_RUN' and item['status'] in ('CLI_ERROR','CONTRACT_ERROR','INCOMPLETE_OUTPUT_IO','INCOMPLETE_RESOURCE','INCOMPLETE_CYCLE_BUDGET') and item['phase'] in ('INPUT_LOAD','READY','MODEL_ADMISSION','RTL_N0','OUTPUT') and item['code'] in codes:
     selected.append(item['status']+':'+item['phase']+':'+item['code'])
  result['merged_log_tail']='\n'.join(selected[-4:]) if selected else 'PRIVATE_PHASE_FAILED:NO_FIXED_STATUS_MARKER'
 except BaseException:
  result.update(context_state='SANITIZER_ERROR',merged_log_tail='')
 return result

def validate_public(observation,completed,stages,scope,comparator):
 need(type(observation) is dict and set(observation)==set(empty_observation()),'N0_SOURCE','N0_OUTPUT')
 need(observation['state'] in ('NOT_COLLECTED','COLLECTING','COMPLETE') and observation['cycle_cap']==8000000 and type(observation['cycle_cap']) is int and observation['source_reduction_lower_bound']==2428928 and type(observation['source_reduction_lower_bound']) is int and observation['numeric_window_seconds']==3600 and type(observation['numeric_window_seconds']) is int,'N0_SOURCE','N0_OUTPUT')
 for key,component in (('runtime_ready','n0_runtime'),('inputs_ready','n0_inputs'),('reference_ready','n0_reference')):
  need(type(observation[key]) is bool and observation[key]==(component in completed),'N0_SOURCE','N0_OUTPUT')
 need(observation['state']!='NOT_COLLECTED' or observation==empty_observation(),'N0_SOURCE','N0_OUTPUT')
 for key,component in (('reference_rss','n0_reference'),('comparison_rss','n0_comparison')):
  value=observation[key]
  if component not in completed:need(value is None,'N0_SOURCE','N0_OUTPUT')
  else:
   need(type(value) is dict and set(value)=={'sampled_leader_max_kib','limit_kib','os_hard_limit','includes_descendants'} and type(value['sampled_leader_max_kib']) is int and 0<=value['sampled_leader_max_kib']<=1572864 and type(value['limit_kib']) is int and value['limit_kib']==1572864 and value['os_hard_limit'] is False and value['includes_descendants'] is False,'N0_SOURCE','N0_OUTPUT')
 need(observation['capture_state'] in ('NOT_COLLECTED','READ_ERROR','NATIVE_FAILED','REPORTED','AVAILABLE') and observation['comparison_state'] in ('NOT_COLLECTED','READ_ERROR','AVAILABLE'),'N0_SOURCE','N0_OUTPUT')
 captured='n0_capture' in completed;compared='n0_comparison' in completed
 need((observation['capture_state']=='AVAILABLE')==captured and (observation['comparison_state']=='AVAILABLE')==compared and scope['weights_loaded']==captured,'N0_SOURCE','N0_OUTPUT')
 names=[row['name'] for row in stages]
 if captured:
  raw=(json.dumps(observation['capture'],sort_keys=True,separators=(',',':'))+'\n').encode()
  comparator.capture_gate(raw)
  need('host93_first_n0' in names and natural_exit(stages[names.index('host93_first_n0')],0),'N0_SOURCE','N0_OUTPUT')
 else:
  need(observation['comparison'] is None and not scope['n0_numeric'],'N0_SOURCE','N0_OUTPUT')
  if observation['capture_state']=='REPORTED':
   cycle_budget_counts((json.dumps(observation['capture'],sort_keys=True,allow_nan=False)+'\n').encode(),comparator)
   need(names and names[-1]=='host93_first_n0' and natural_exit(stages[-1],2),'N0_SOURCE','N0_OUTPUT')
  else:need(observation['capture'] is None,'N0_SOURCE','N0_OUTPUT')
 if compared:
  report=observation['comparison'];need(type(report) is dict and type(report.get('capture_sha256')) is str and len(report['capture_sha256'])==64 and all(c in '0123456789abcdef' for c in report['capture_sha256']),'N0_SOURCE','N0_OUTPUT')
  passed=validate_comparison(report,comparator,{'sha256':report['capture_sha256']},{'sha256':report.get('actual_sha256')})
  need(names[-1]=='host93_n0_compare' and natural_exit(stages[-1],0 if passed else 1) and scope['n0_numeric']==passed and observation['state']=='COMPLETE','N0_SOURCE','N0_OUTPUT')
 else:need(observation['comparison'] is None and not scope['n0_numeric'] and observation['state']!='COMPLETE','N0_SOURCE','N0_OUTPUT')
 return True

PARENT_COUNTS={
 'N0_SOURCE':tuple(range(44)), 'N0_RUNTIME_PREPARE':(0,1), 'N0_RUNTIME_TREE':(2,),
 'N0_RAW_RECEIPT':(3,), 'N0_INPUT_RECEIPT':(4,), 'N0_REFERENCE_RECEIPT':(5,43),
 'N0_REFERENCE_RSS':(5,), 'N0_CAPTURE_RECEIPT':(41,42), 'N0_CAPTURE_INPUTS':(41,42),
 'N0_CAPTURE_ELF':(41,42), 'N0_COMPARE_RECEIPT':(43,), 'N0_COMPARE_RSS':(43,),
 'N0_DEADLINE':tuple(range(44)), 'N0_PHASE_ORDER':tuple(range(43))}

def validate_private_diagnostics(repo,pins,name,value):
 need(type(value) is dict and not value['observations'] and value['truncated'] is False,'N0_SOURCE','N0_OUTPUT')
 if value['context_state']!='AVAILABLE':return
 text=value['merged_log_tail'];need(type(text) is str,'N0_SOURCE','N0_OUTPUT')
 if text=='PRIVATE_PHASE_FAILED:NO_FIXED_STATUS_MARKER':return
 allowed=fixed_markers(repo,pins,name)
 if name=='host93_first_n0':
  relative='candidates/host93_first_n0_sources/bridge/metadata/DIAGNOSTIC_MAP.json';p=pins[relative];table=decode(read(repo/relative,p['bytes'],p))
  codes={r['code'] for r in table['messages'].values()}|{'UNMAPPED','CYCLE_BUDGET','ALLOCATION_LIMIT','CLI_ARGUMENT_COUNT','CLI_INPUT_ROOT','CLI_OUTPUT_ROOT','CLI_PARENT_TRAVERSAL','OUTPUT_DIRECTORY','OUTPUT_WRITE','OUTPUT_REPORT'}
  allowed={status+':'+phase+':'+code for status in ('CLI_ERROR','CONTRACT_ERROR','INCOMPLETE_OUTPUT_IO','INCOMPLETE_RESOURCE','INCOMPLETE_CYCLE_BUDGET') for phase in ('INPUT_LOAD','READY','MODEL_ADMISSION','RTL_N0','OUTPUT') for code in codes}
 need(0<len(text.splitlines())<=4 and all(line in allowed for line in text.splitlines()),'N0_SOURCE','N0_OUTPUT')
