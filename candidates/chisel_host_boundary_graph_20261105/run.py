"""One source-only structural job. No engine/native, weights, references or IR export."""
import contextlib,gzip,hashlib,importlib.util,json,os,pathlib,re,shutil,subprocess,sys,time,urllib.request,urllib.error,zipfile
P=pathlib.Path;D=P(__file__).resolve().parent;REPO=D.parent.parent
REL='candidates/chisel_host_boundary_graph_20261105';NONCE='ci_launch/chisel_host_boundary_graph_20261105_observed_prepare_measured_scan_quota_once.json'
CAT='candidates/gdn32_first_model_execution_20261104/GDN32_FULL_SOURCE_PINS.json'
CAT_SHA='ad2d4dcaddb213c85fd15adc65f7da5bd74a0d7c3e6c5922c725aa41bdc967cb'
BASE='b0a31279bfd834d33188feb99550abc3f179fdec';BASE_TREE='5f6964896d8a4ae8511b0de48b6044e6ed843f17';TREE=12_081_306_272;RESERVE=8<<30
from witness_record import parse_record as parse_witness_record
from compare_observed_prepare import evidence as parse_observed_evidence, budget_for_provenance as parse_observed_budget, sizing_pair as parse_observed_sizing_pair
from compare_clock_init_results import auxiliary_evidence as parse_auxiliary_evidence, preexisting_evidence as parse_preexisting_evidence
graph_identity={}
differential_identity={};boundary_identity={}
stage_step="NONE";exclusivity_endpoint="NONE";stage_receipt=None
class Stop(Exception):
 def __init__(self,code='GUARD_REJECTED'):self.code=code;super().__init__(code)
def need(x,code='GUARD_REJECTED'):
 if not x:raise Stop(code)
def jdk_location_allowed(path):
 return str(path) in ('/usr/lib/jvm/temurin-21-jdk-amd64','/opt/hostedtoolcache/Java_Temurin-Hotspot_jdk/21.0.13-9/x64')
def sha(p):
 with P(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def regular(p):
 p=P(p);need(p.is_absolute() and p==p.resolve() and p.is_file() and all(not q.is_symlink()for q in(p,*p.parents)));return p
def git(*a):return subprocess.check_output(['git','-C',str(REPO),*a],text=True,stderr=subprocess.DEVNULL,timeout=20).strip()
def load(p,cap=2<<20):
 p=regular(p);need(0<p.stat().st_size<=cap);return json.loads(p.read_text())
def pins_for(rows,root):
 out={}
 for r in rows:
  rel=P(r['path']);need(not rel.is_absolute() and '..'not in rel.parts);p=regular(root/rel)
  need(type(r['bytes'])is int and p.stat().st_size==r['bytes'] and sha(p)==r['sha256'] and str(p)not in out);out[str(p)]=r['sha256']
 return out
def admission():
 mem=int(next(x.split()[1]for x in P('/proc/meminfo').read_text().splitlines()if x.startswith('MemAvailable:')))*1024
 need(mem>=13<<30 and shutil.disk_usage(REPO).free>=TREE+RESERVE)
def remote_exclusive(launch,wait_seconds=90):
 global exclusivity_endpoint
 token=os.environ.get('GITHUB_TOKEN');need(bool(token))
 base='https://api.github.com/repos/liyang53719/hetero_cnn_llm_aha'
 deadline=time.monotonic()+wait_seconds
 retry_available=True # One extra GET total, never a worker-launch retry.
 def get(path,label):
  nonlocal retry_available
  global exclusivity_endpoint
  exclusivity_endpoint=label
  req=urllib.request.Request(base+path,headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json'})
  while True:
   remaining=deadline-time.monotonic();need(remaining>0)
   try:
    response=urllib.request.urlopen(req,timeout=min(20,remaining))
   except BaseException as error:
    if type(error)is not TimeoutError or not retry_available:raise
    retry_available=False
    need(time.monotonic()<deadline)
    continue
   with response as f:data=f.read(1_048_577)
   need(time.monotonic()<deadline)
   need(len(data)<=1_048_576);return json.loads(data)
 while True:
  need(get('/git/ref/heads/main','HEAD')['object']['sha']==launch)
  busy=False
  for status in ('in_progress','queued','waiting','pending','requested'):
   x=get('/actions/runs?status='+status+'&per_page=100','RUNS_'+status.upper());need(x['total_count']<=100)
   busy=busy or any(str(r['id'])!=os.environ['GITHUB_RUN_ID'] for r in x['workflow_runs'])
  if not busy:
   need(time.monotonic()<deadline)
   exclusivity_endpoint="NONE";return
  need(time.monotonic()<deadline);time.sleep(3)

def project(stage,r):
 return {'stage':stage,'status':'COMPLETE' if r.get('status')=='PASS_PROCESS_ONLY' else 'INCOMPLETE','elapsed_seconds':r.get('elapsed_seconds'),'peak_rss':r.get('observed_peak_rss'),'cpu_seconds':r.get('observed_cpu_seconds'),'cleanup_complete':type(r.get('cleanup_proof'))is dict and r['cleanup_proof'].get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'}
# Failure-only finite driver evidence. Never export supervisor messages or paths.
STAGE_STEPS=frozenset({'NONE','ENTER','REMOTE_EXCLUSIVE','DEADLINE','CAPS','SUPERVISOR','RECEIPT','PROJECT','EMIT','POSTCHECK','RETURN'})
EXCLUSIVE_ENDPOINTS=frozenset({'NONE','HEAD','RUNS_IN_PROGRESS','RUNS_QUEUED','RUNS_WAITING','RUNS_PENDING','RUNS_REQUESTED'})
SUPERVISOR_ERROR_CODES={
 'ValueError: locked memory gate':'MEMORY_GATE',
 'ValueError: locked disk gate':'DISK_GATE',
 'ValueError: prelaunch supervisor peak RSS cap':'SUPERVISOR_RSS',
 'ValueError: prelaunch work deadline':'PRELAUNCH_DEADLINE',
 'ValueError: preexisting alarm':'PREEXISTING_ALARM',
 'ValueError: preexec requires no existing reader/background threads':'THREADS',
 'ValueError: sampled observed aggregate RSS cap':'RSS_CAP',
 'ValueError: sampled observed aggregate CPU cap':'CPU_CAP',
 'ValueError: sampled child plus supervisor CPU cap':'COMBINED_CPU_CAP',
 'ValueError: sampled memory reserve':'MEMORY_RESERVE',
 'ValueError: wall cap':'WALL_CAP'}
def supervisor_failure_summary(r):
 try:
  if type(r)is not dict:return {'status':'UNAVAILABLE'}
  errors=r.get('errors');need(type(errors)is list)
  codes=set()
  for error in errors[:16]:
   codes.add(SUPERVISOR_ERROR_CODES.get(error,'OTHER') if type(error)is str and len(error)<=256 else 'OTHER')
  value=r.get('native_exit');exit_code=value if type(value)is int and -255<=value<=255 else None
  started=r.get('worker_started');started=started if type(started)is bool else None
  cleanup=r.get('cleanup_proof');closed=r.get('log_capture')
  return {'status':r.get('status') if r.get('status')in ('PASS_PROCESS_ONLY','FAIL_OR_INCOMPLETE','IN_PROGRESS')else 'OTHER',
   'worker_started':started,'native_exit':exit_code,'cleanup_complete':type(cleanup)is dict and cleanup.get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP',
   'log_finalized':type(closed)is dict and closed.get('gzip_finalized')is True,
   'error_count':min(len(errors),65535),'errors_truncated':len(errors)>16,'error_codes':sorted(codes)}
 except BaseException:return {'status':'UNAVAILABLE'}
def stage_failure_diagnostic(error):
 try:
  http=error.code if type(error)is urllib.error.HTTPError and type(error.code)is int and 100<=error.code<=599 else None
  return {'schema':'STAGE_FAILURE_DIAGNOSTIC_V1','step':stage_step if stage_step in STAGE_STEPS else 'NONE',
   'endpoint':exclusivity_endpoint if exclusivity_endpoint in EXCLUSIVE_ENDPOINTS else 'NONE',
   'exception_class_sha256':hashlib.sha256((type(error).__module__+'.'+type(error).__qualname__).encode()).hexdigest(),
   'http_status':http,'supervisor':stage_receipt if type(stage_receipt)is dict else {'status':'UNAVAILABLE'}}
 except BaseException:return {'schema':'STAGE_FAILURE_DIAGNOSTIC_V1','status':'UNAVAILABLE'}
# Proposal only: fixed-schema diagnostics, never an alternate success oracle.
PHASES=('admission','read','parse','roundtrip','split','official_lower','lower_checks','boundary_split','boundary_checks','get_firrtl_ast','set_implicit_output_info','prepare_ast','prepared_checks','symbol_table','summary_hash')
PHASE_RE='(?:'+'|'.join(PHASES)+')'
METRIC_RE=re.compile(r'GRAPH_PHASE_V1 seq=([0-9]+) kind=(BEGIN|END|SAMPLE|CYCLE_SEEN) phase=('+PHASE_RE+r') wallMs=([0-9]+) cpuMs=([0-9]+) heapUsed=([0-9]+) heapMax=([0-9]+) gcMillis=([0-9]+) gcCount=([0-9]+) cycleSeen=([01])')
PASS_RE=re.compile(r'PASS_DECLARED_CONE_TOPOLOGY_ONLY highSha=([0-9a-f]{64}) annotationsSha=([0-9a-f]{64}) preparedSha=([0-9a-f]{64}) symbols=([0-9]+) leafBindings=17 boundaryInstances=1 boundaryInputFields=26 boundaryAddedPorts=90 nativeInstances=0 evaluatedEdges=0 schedulingQualified=false fullHostAccepted=false suppressedDiagnosticBytes=([0-9]+) cycleSeen=([01])')
BOUNDARY_GUARD_CODES={'TOPOLOGY': frozenset({'TOPOLOGY_LEAF_ABI', 'TOPOLOGY_MODEL_BINDING', 'TOPOLOGY_IDMA_PATH_COUNT', 'TOPOLOGY_STATEMENT_BOUND', 'TOPOLOGY_WRAPPER_IDENTITY', 'TOPOLOGY_INSTANCE_SEGMENT', 'TOPOLOGY_PATH_BOUNDS', 'TOPOLOGY_BINDING_COUNT'}), 'TRANSFORM': frozenset({'MUX_WIDTHS', 'CYCLIC_EXPRESSION_OBJECT', 'ALIAS_CYCLE', 'PRIVATE_FIELD_NAMESPACE', 'CALLER_EXPANSION_BOUND', 'CALLER_STATEMENT_BOUND', 'ALIAS_SINGLE_DRIVER', 'UNCONDITIONAL_LOW_REQUIRED', 'PROJECTION_RANGE', 'SPLIT_LEAF_ABI', 'TRANSPARENT_WRAPPER', 'MODULE_UNIQUENESS', 'WRAPPER_OUTPUT_PACKING', 'ALIAS_PROJECTION_BOUND', 'LAYOUT_BIT_COVERAGE', 'CALLER_POSTORDER', 'WRAPPER_UNIQUE_DRIVERS', 'CALLER_DEPTH_BOUND', 'ALIAS_IMPLICIT_COERCION', 'PACKED_INPUT_SINGLE_DRIVER', 'CALLER_IDENTITY_BOUND', 'WRAPPER_INPUT_SLICE', 'WRAPPER_MODEL_BINDING', 'CALLER_INSTANCE_NAMES', 'PROJECTED_VALID_IF', 'VALIDIF_WIDTHS', 'PROJECTED_SUB_ACCESS', 'PROJECTED_INFO_EXPR', 'PROJECTED_OTHER', 'PROJECTED_V_RANDOM', 'EXPRESSION_RECURSION_BOUND', 'PACKED_INPUT_WIDTH', 'CALLER_OCCURRENCE_BOUND', 'CALLER_CHILDREN_BOUND', 'EXPRESSION_IDENTITY_BOUND', 'PACKED_WRAPPER_ABI', 'UNSIGNED_WIDTH_REQUIRED', 'BOUNDARY_INSTANCE_FIELD_COUNT', 'CONTROL_PASSTHROUGH', 'EXPANDED_EXPRESSION_BOUND', 'UNRESOLVED_PACKED_BOUNDARY', 'WRAPPER_DRIVER_MISSING', 'TOTAL_FIELD_EXPANSION_BOUND'}), 'NONE': frozenset()}
BOUNDARY_GUARD_RE='(?:'+'|'.join(sorted({'UNKNOWN'}|set().union(*BOUNDARY_GUARD_CODES.values())))+')'
FAIL_RE=re.compile(r'FAIL_STRUCTURAL_GRAPH_ONLY stage=('+PHASE_RE+r') exceptionClassSha=([0-9a-f]{64})(?: boundaryStep=(NONE|TOPOLOGY|TRANSFORM) boundaryGuard=('+BOUNDARY_GUARD_RE+r'))?(?: preparedStep=(?P<prepared_step>NONE|STATE|ANNOTATIONS|INIT_REPAIR|TYPES|FLOWS|CLOCK|BINDINGS) clockInitGuard=(?P<clock_init_guard>NONE|UNKNOWN|BOUND|TYPE|INFO|STRUCTURE|DUPLICATE|COUNT|SHAPE|ORIGINAL_MODULE|PREEXISTING|CLOCK|ANNOTATION_TARGET|ANNOTATION_SHAPE|ANNOTATION_PRESET|ANNOTATION_EXTENSION|REFERENCES|DRIVER|CONSUMER|ANCHOR|NONINTERFERENCE) clockInitBound=(?P<clock_init_bound>[A-Z0-9_:]+) clockInitSizing=(?P<clock_init_sizing>[A-Z0-9_:,]+) clockInitAux=(?P<clock_init_aux>[A-Z0-9_:]+) clockInitPreexisting=(?P<clock_init_preexisting>[A-Z0-9_:]+) passAggregate=(?P<pass_aggregate>true|false) passErrorsScanned=(?P<pass_scanned>[0-9]+) passErrorsTruncated=(?P<pass_truncated>true|false) passErrorClasses=(?P<pass_hist>[A-Z0-9_:,]+))? nativeInstances=0 evaluatedEdges=0 schedulingQualified=false fullHostAccepted=false suppressedDiagnosticBytes=(?P<suppressed>[0-9]+) cycleSeen=(?P<cycle>[01])')
PASS_CLASS_HASHES={'T01': '55798a44db78c6aab80261a6a885857f14cfc1ce0073b2b53a9c50f484239751', 'T02': '15f6403ab5b64e42939421b7d3e5d647382eb774981aa4ea920cce93a092561a', 'T03': '61d66402120511aa0eb6ac9b33914e64227ef4c7b937745e747010c5e1e2dfd1', 'T04': '0899f63f4b40d5954568c2db8486c5d252b9d39e3a0f16dabb113957de582411', 'T05': '2748016f6c2552ee805ca4ade2390ec7f05ea28002cf708262dbcba1aed7d564', 'T06': '51fb68974012ffee11a320ac5a9a5de2a01c4efb13951c4e71b5a2047d8f8247', 'T07': '29fc2ca21b85d1225a140f8a003e24d7bda21052691bd7ccc64506f7eabfced1', 'T08': '685fdad6d916225e74101edd084b55ff182ff96b7460a4f46824d82906882b5f', 'T09': 'fa0c112d1da506e0adb11888aca4523d65109b2c277903b4ee6d5e9101e3b8fe', 'T10': '42eb85d8a8723e4f12762f7d092d1a8d8067fa0ae862c56b72d49f64da477e41', 'T11': 'bbc3305f91e129d639b3f2f3e3667e5eca7c41b0c7816fbb27736f2cf475cbac', 'T12': 'ce0827d944715c55300f78749ad55fc536fea76a3f9896b7af4030da5d040318', 'T13': '07368567288e40b02a197c590b238890667ab44e1d813855643b4e4394ff00c2', 'T14': 'b5e1a4edf0b5ea250dfb2ba00d7de9ad84559c1759bc393bc53cb39482f6693f', 'T15': 'f47d7a4f20ff9e197a4c8e44c846c7131b087c924515958218d8be8d12b30a74', 'T16': 'a1892eba49bc551e116f902030c086fcecc2741dec7b5322f443675c7eb19c5b', 'T17': 'e4734c4ebaeb93b393e15948e4a7ea8f69d0c5a68f5b34c2f6e2fbfbdca65893', 'T18': '65e3c1be23f19c99b634667adad7c0da5f00b52b0845c36ad1db4a71212387e4', 'T19': '39195152365eac58862e3a2a390f3be21da5cfc413ec66cc7a2a8fc42458c3a2', 'T20': 'f4f1ec9064e3c1a2b5eed16b171a33f47775377f4f1290426aafc3696e655190', 'T21': '114a5475039b5aa8a979e51aa92939892510436837a279c3514881381fa278be', 'T22': '8a9763a3d26172107b89a6d18d9d1374d3666cdabdeb7df31761fa7604a9b454', 'T23': 'b68761016d4b4546442ede6190810ef493132e6dbbee8402a65bb847b0d808e4', 'T24': 'a8273bf2151fe993f8d53ccd6b8fbd4ffd341d676f6b9ab92feb2825dd6bb379', 'T25': '4e00d9b0cbeb1c10e0d8f086c00cab32c137f8926094df4ff4a0463aa9fbce2f', 'T26': '7a862431e6e9e3087c6a6637c308d82aa090f1f7fbfec68ebafa8f70a6269004', 'T27': '52c60070de0ff1c935357e010e05d1cae4dc8c9e2786c570e00db6560d0254d1', 'T28': 'c9821f372d269ee65250bc54e68ea688e77d494f55562bc8df8cd929bc340264', 'T29': 'f0e83d70271e196ca1197b721f5010d73ab8fda7351c4c2afee5033d5041c641', 'T30': '075594a22ac08cf8449767b50bdc0b460a554813e1b87e5d5dd629de69722bee', 'T31': '1dcd43a78721eb97e90196a26b601e9ddf0ac7e7b6acb5854e751a731e8c041f', 'T32': 'bbb30c18243be20c3f8ab8f172ef70070d33d2a48fa83f837cbfea44a8727f2f', 'F01': '99914bc48af9a0e2d34462f18f8216a168b17a9a1581c5a780ec921fadf0764f', 'BASE_PASS': '892667cf8140b49c85712f16499c40a82f3a47111c56b40c55cfb0f3c0763d7d'}
PASS_AGGREGATE_HASH='f212da272dce0cd568b09ab66e94cd2954cb40108e3641df8f9cea821cf8dccc'
CLOCK_INIT_GUARDS={'ANCHOR','ANNOTATION_EXTENSION','ANNOTATION_PRESET','ANNOTATION_SHAPE','ANNOTATION_TARGET','BOUND','CLOCK','CONSUMER','COUNT','DRIVER','DUPLICATE','INFO','NONINTERFERENCE','ORIGINAL_MODULE','PREEXISTING','REFERENCES','SHAPE','STRUCTURE','TYPE'}
CLOCK_INIT_BOUND_REASONS=frozenset({'GLOBAL_WORK','NAME','TYPE_DEPTH','TYPE_NODES','TYPE_FIELDS','INFO_DEPTH','INFO_NODES','INFO_STRING','INFO_CHILDREN','MODULES','PORTS','STATEMENT_DEPTH','DECLARATIONS','PRINT_STRING','ANNOTATIONS','TARGET_PATH','TARGET_COMPONENT','TARGET_GROUPS','TARGET_MEMBERS','EXPRESSION_DEPTH'})
CLOCK_INIT_BOUND_PHASES=frozenset({'INDEX_BEFORE','INDEX_PREPARED','CANDIDATES','ANNOTATIONS','USES','ANCHORS','MATCHING','REBUILD','NONINTERFERENCE'})
def parse_clock_init_bound(step,guard,record):
 need(type(record)is str and len(record)<=64,'CLOCK_INIT_BOUND_SCHEMA')
 if step!='INIT_REPAIR' or guard!='BOUND':
  need(record=='NONE','CLOCK_INIT_BOUND_WRONG_GUARD');return {'status':'NONE'}
 if record=='UNAVAILABLE':return {'status':'UNAVAILABLE'}
 found=re.fullmatch(r'([A-Z_]+):([A-Z_]+):(0|[1-9][0-9]{0,6})',record)
 need(found is not None,'CLOCK_INIT_BOUND_SCHEMA')
 reason,phase,work=found.groups()
 need(reason in CLOCK_INIT_BOUND_REASONS and phase in CLOCK_INIT_BOUND_PHASES,'CLOCK_INIT_BOUND_ENUM')
 work=int(work)
 need(work==5000001 if reason=='GLOBAL_WORK' else work<=5000000,'CLOCK_INIT_BOUND_WORK')
 return dict(status='AVAILABLE',reason=reason,phase=phase,work=work)
# Counts are raw traversal occurrences, never distinct names or object identities.
INDEX_CENSUS_FIELDS=('modules','roots','ports','statements','named_declarations','namespace_occurrences','max_ports_per_module','max_statements_per_module','max_namespace_per_module','total_name_chars','max_name_length','registers')
def parse_clock_init_sizing(step,guard,bound,record):
 need(type(record)is str and len(record)<=512,'CLOCK_INIT_SIZING_SCHEMA')
 trigger=step=='INIT_REPAIR' and guard=='BOUND' and bound.get('status')=='AVAILABLE' and bound.get('reason')=='DECLARATIONS' and bound.get('phase')=='INDEX_BEFORE'
 if not trigger:
  need(record=='NONE','CLOCK_INIT_SIZING_WRONG_GUARD');return {'status':'NONE'}
 if record=='UNAVAILABLE':return {'status':'UNAVAILABLE'}
 parts=record.split(':')
 need(len(parts)==5,'CLOCK_INIT_SIZING_SCHEMA')
 status,phase,visits,before,prepared=parts
 need((status=='COMPLETE' and phase=='DONE') or (status=='TRUNCATED' and phase in ('BEFORE','PREPARED')),'CLOCK_INIT_SIZING_PHASE')
 def number(raw,cap):
  need(re.fullmatch(r'0|[1-9][0-9]{0,10}',raw)is not None,'CLOCK_INIT_SIZING_COUNT')
  value=int(raw);need(value<=cap,'CLOCK_INIT_SIZING_COUNT');return value
 visits=number(visits,5000000)
 def circuit(raw,complete):
  values=raw.split(',');need(len(values)==12,'CLOCK_INIT_SIZING_SCHEMA')
  values=[number(value,20480000000 if i==9 else 5000000)for i,value in enumerate(values)]
  modules,roots,ports,statements,declarations,namespace,max_ports,max_statements,max_namespace,chars,max_length,registers=values
  need(modules<=4096 and roots<=modules and roots<=statements and declarations<=statements and registers<=declarations,'CLOCK_INIT_SIZING_COHERENCE')
  need(namespace==ports+declarations and max_ports<=250000 and max_length<=4096 and chars<=namespace*4096,'CLOCK_INIT_SIZING_COHERENCE')
  for total,maximum in ((ports,max_ports),(statements,max_statements),(namespace,max_namespace)):
   need(maximum<=total<=modules*maximum and (total==0)==(maximum==0),'CLOCK_INIT_SIZING_COHERENCE')
  need(max_namespace>=max_ports and chars>=namespace and max_length<=chars<=namespace*max_length and (namespace==0)==(max_length==0),'CLOCK_INIT_SIZING_COHERENCE')
  out=dict(zip(INDEX_CENSUS_FIELDS,values))
  if complete:out['estimated_index_ticks']=modules+ports+2*statements-roots
  return out
 before=circuit(before,status=='COMPLETE' or phase=='PREPARED');prepared=circuit(prepared,status=='COMPLETE')
 need(visits==sum(c[k]for c in (before,prepared)for k in ('modules','ports','statements')),'CLOCK_INIT_SIZING_VISITS')
 if status=='TRUNCATED':
  need(visits==5000000,'CLOCK_INIT_SIZING_VISITS')
  if phase=='BEFORE':need(not any(prepared.values()),'CLOCK_INIT_SIZING_PHASE')
 return dict(status=status,phase=phase,visits=visits,before_complete=status=='COMPLETE' or phase=='PREPARED',prepared_complete=status=='COMPLETE',before=before,prepared=prepared)
def parse_prepared_evidence(step,aggregate,scanned,truncated,histogram,exception_sha):
 need(step in ('NONE','STATE','ANNOTATIONS','INIT_REPAIR','TYPES','FLOWS','CLOCK','BINDINGS'),'PREPARED_STEP_SCHEMA')
 need(aggregate in ('true','false') and truncated in ('true','false'),'PREPARED_PASS_SCHEMA')
 need(type(scanned)is str and re.fullmatch(r'0|[1-9][0-9]{0,3}',scanned),'PREPARED_PASS_COUNT')
 n=int(scanned);need(n<=1024 and (truncated=='false' or n==1024),'PREPARED_PASS_COUNT')
 need(type(histogram)is str and len(histogram)<=512,'PREPARED_PASS_HISTOGRAM')
 counts={}
 if histogram!='NONE':
  pairs=histogram.split(',');need(len(pairs)<=35,'PREPARED_PASS_HISTOGRAM')
  previous=''
  for pair in pairs:
   found=re.fullmatch(r'(T[0-9]{2}|F01|BASE_PASS|OTHER):([1-9][0-9]{0,3})',pair);need(found is not None,'PREPARED_PASS_HISTOGRAM')
   code=found[1];count=int(found[2]);need(code in set(PASS_CLASS_HASHES)|{'OTHER'} and code>previous and count<=1024,'PREPARED_PASS_HISTOGRAM')
   counts[code]=count;previous=code
 need(sum(counts.values())==n and (histogram=='NONE')==(n==0),'PREPARED_PASS_COUNT')
 if aggregate=='true':need(exception_sha==PASS_AGGREGATE_HASH,'PREPARED_PASS_EXCEPTION')
 else:
  need(n==1 and truncated=='false' and len(counts)==1,'PREPARED_PASS_SINGLE')
  code=next(iter(counts))
  if code=='OTHER':need(exception_sha not in set(PASS_CLASS_HASHES.values())|{PASS_AGGREGATE_HASH},'PREPARED_PASS_EXCEPTION')
  else:need(exception_sha==PASS_CLASS_HASHES[code],'PREPARED_PASS_EXCEPTION')
 return dict(prepared_step=step,pass_aggregate=aggregate=='true',pass_errors_scanned=n,pass_errors_truncated=truncated=='true',pass_error_classes=counts)
CENSUS_HISTS={
 'regDeclTypes':set('USCRANVBO'),'regInitTypes':set('USCRANVBO'),'regResetTypes':set('USCRANVBO'),
 'regInitExpr':{'REF','ULIT','SLIT','MUX','VALIDIF','PRIM','OTHER'},
 'regInitZero':{'UZERO','SZERO','OTHER'},'regResetZero':{'UZERO','SZERO','OTHER'},
 'regSelf':{'DIRECT','OTHER'},'regOrigin':{'ADDED','PRESENT'},
 'regWidths':{'EQ','NE','UNKNOWN','NA'},
 'regUses':{'PRINT','STOP','VERIFY'},'regUseInfo':{'SAME_PRESENT','SAME_NONE','DIFFERENT'}}
def parse_register_census(line):
 need(type(line)is str and len(line)<=1024,'REGISTER_CENSUS_LIMIT')
 if line=='REG_INIT_CENSUS_V1 regCensus=UNAVAILABLE':return {'status':'UNAVAILABLE'}
 parts=line.split(' ')
 keys=('regCensus','regScanned','regMismatchTotal','regMismatchSampled','regMismatchTruncated',*CENSUS_HISTS)
 need(len(parts)==len(keys)+1 and parts[0]=='REG_INIT_CENSUS_V1','REGISTER_CENSUS_SCHEMA')
 values={}
 for key,part in zip(keys,parts[1:]):
  pair=part.split('=');need(len(pair)==2 and pair[0]==key,'REGISTER_CENSUS_KEYS');values[key]=pair[1]
 need(values['regCensus']=='OK','REGISTER_CENSUS_STATUS')
 def number(value,cap):
  need(re.fullmatch(r'0|[1-9][0-9]{0,6}',value)is not None,'REGISTER_CENSUS_COUNT')
  n=int(value);need(n<=cap,'REGISTER_CENSUS_COUNT');return n
 scanned=number(values['regScanned'],5000000);total=number(values['regMismatchTotal'],5000000);sampled=number(values['regMismatchSampled'],1024)
 need(total<=scanned and sampled==min(total,1024) and values['regMismatchTruncated']==str(total>1024).lower(),'REGISTER_CENSUS_COUNTS')
 histograms={}
 for key,codes in CENSUS_HISTS.items():
  text=values[key];counts={}
  if text!='NONE':
   pairs=text.split(',');need(len(pairs)<=len(codes),'REGISTER_CENSUS_HISTOGRAM')
   for pair in pairs:
    row=pair.split(':');need(len(row)==2 and row[0]in codes and row[0]not in counts,'REGISTER_CENSUS_CODE')
    n=number(row[1],sampled);need(n>0,'REGISTER_CENSUS_COUNT');counts[row[0]]=n
   need(list(counts)==sorted(counts),'REGISTER_CENSUS_ORDER')
  if key not in ('regUses','regUseInfo'):need(sum(counts.values())==sampled,'REGISTER_CENSUS_SUM')
  histograms[key]=counts
 need(bool(histograms['regUses'])==bool(histograms['regUseInfo']),'REGISTER_CENSUS_USE_INFO')
 return dict(status='OK',registers_scanned=scanned,mismatches=total,sampled=sampled,truncated=total>1024,histograms=histograms)

def parse_graph_text(text,receipt,high_sha,annotations_sha,observation_only=False,sizing_diagnostics=False):
 need(type(sizing_diagnostics)is bool and (not sizing_diagnostics or observation_only),'GRAPH_SIZING_MODE')
 need(type(observation_only)is bool,'GRAPH_OBSERVATION_MODE')
 need(type(text)is str and len(text.encode('ascii'))<=32768,'GRAPH_LOG_LIMIT')
 need('\r'not in text and (not text or text.endswith('\n')),'GRAPH_LOG_TRUNCATED_LINE')
 lines=text.splitlines();need(len(lines)<=98,'GRAPH_RECORD_LIMIT')
 rows=[];final=None;active=None;next_phase=0;last=None;last_phase=None;cycle_event_seen=False;witness=None;census=None;provenance=None;observer_budget_raw=None;observer_sizing_raw=None;observer_budget=None;observer_sizing=None
 for line in lines:
  need(final is None,'GRAPH_LOG_TRAILING_OR_LONG')
  if line.startswith('PREPARE_PROVENANCE_V1 '):
   need(observation_only and provenance is None and active is None and last_phase=='prepare_ast' and next_phase==PHASES.index('prepared_checks'),'OBSERVER_RECORD_PHASE')
   try:provenance=parse_observed_evidence(line[len('PREPARE_PROVENANCE_V1 '):],394)
   except (ValueError,TypeError):raise Stop('OBSERVER_RECORD_SCHEMA')
   continue
  if line.startswith('PREPARE_BUDGET_V1 '):
   need(sizing_diagnostics and provenance is not None and observer_budget_raw is None and active is None and last_phase=='prepare_ast','OBSERVER_BUDGET_PHASE')
   need(len(line)<=512,'OBSERVER_BUDGET_LIMIT')
   observer_budget_raw=line[len('PREPARE_BUDGET_V1 '):]
   try:observer_budget=parse_observed_budget(provenance,observer_budget_raw)
   except (ValueError,TypeError):raise Stop('OBSERVER_BUDGET_SCHEMA')
   continue
  if line.startswith('PREPARE_USES_SIZING_V1 '):
   need(sizing_diagnostics and provenance is not None and observer_budget_raw is not None and observer_sizing_raw is None and active is None and last_phase=='prepare_ast','OBSERVER_SIZING_PHASE')
   need(len(line)<=512,'OBSERVER_SIZING_LIMIT')
   observer_sizing_raw=line[len('PREPARE_USES_SIZING_V1 '):]
   try:pair=parse_observed_sizing_pair(provenance,observer_budget_raw,observer_sizing_raw)
   except (ValueError,TypeError):raise Stop('OBSERVER_SIZING_SCHEMA')
   need(len(json.dumps(pair,separators=(',',':')))<=2048,'OBSERVER_SIZING_OUTPUT_CAP')
   observer_sizing=pair['sizing']
   continue
  if line.startswith('REG_INIT_CENSUS_V1 '):
   need(census is None and active=='prepared_checks','REGISTER_CENSUS_PHASE')
   census=parse_register_census(line);continue
  if census is not None:need(line.startswith('FAIL_STRUCTURAL_GRAPH_ONLY '),'REGISTER_CENSUS_FAILURE_REQUIRED')
  if line.startswith('GRAPH_CYCLE_WITNESS '):
   need(witness is None and active=='symbol_table' and not cycle_event_seen,'GRAPH_WITNESS_ORDER')
   try:witness=parse_witness_record(line[len('GRAPH_CYCLE_WITNESS '):])
   except (ValueError,TypeError,KeyError):raise Stop('GRAPH_WITNESS_SCHEMA')
   continue
  need(len(line)<=1024,'GRAPH_LOG_TRAILING_OR_LONG')
  m=METRIC_RE.fullmatch(line)
  if m:
   seq=int(m[1]);kind=m[2];phase=m[3];values=list(map(int,m.groups()[3:]))
   wall,cpu,used,maximum,gc_ms,gc_count,cycle=values
   need(seq==len(rows)+1 and seq<=96 and all(0<=v<1<<63 for v in values),'GRAPH_METRIC_RANGE')
   need(used<=maximum and 0<maximum<=15<<30 and wall<=2400000 and cpu<=2400000,'GRAPH_METRIC_RANGE')
   if last:
    need(all(values[i]>=last[i]for i in (0,1,4,5,6)) and maximum==last[3],'GRAPH_METRIC_REGRESSION')
   if kind=='BEGIN':
    if observation_only and phase=='prepared_checks':need(provenance is not None,'OBSERVER_RECORD_MISSING')
    if sizing_diagnostics and phase=='prepared_checks':need(observer_sizing_raw is not None,'OBSERVER_SIZING_MISSING')
    need(active is None and next_phase<len(PHASES) and phase==PHASES[next_phase],'GRAPH_PHASE_ORDER');active=phase
   else:
    need(active==phase,'GRAPH_PHASE_ORDER')
    if kind=='CYCLE_SEEN':
     need(phase=='symbol_table' and cycle==1 and not cycle_event_seen,'GRAPH_CYCLE_EVENT_INVALID');cycle_event_seen=True
    if kind=='END':active=None;next_phase+=1
   last_phase=phase;last=values
   rows.append(dict(seq=seq,kind=kind,phase=phase,wall_ms=wall,cpu_ms=cpu,heap_used=used,heap_max=maximum,gc_ms=gc_ms,gc_count=gc_count,cycle_seen=bool(cycle)))
   continue
  a=PASS_RE.fullmatch(line);b=FAIL_RE.fullmatch(line)
  need(a is not None or b is not None,'GRAPH_LOG_NOT_WHITELISTED')
  if a:
   need(not observation_only,'OBSERVER_DIAGNOSTIC_CANNOT_PASS')
   need(active is None and next_phase==len(PHASES) and witness is None,'GRAPH_SUCCESS_INCOMPLETE_PHASES')
   need(a[1]==high_sha and a[2]==annotations_sha and a[6]=='0' and (not last or last[6]==0),'GRAPH_SUCCESS_IDENTITY_OR_CYCLE')
   need(int(a[4])>0 and int(a[4])<1<<63 and int(a[5])<=8<<20,'GRAPH_FINAL_RANGE')
   final=dict(kind='success',prepared_sha256=a[3],symbol_count=int(a[4]))
  else:
   need(b[1]==(last_phase or 'admission'),'GRAPH_FAILURE_PHASE_MISMATCH')
   need(int(b['suppressed'])<=8<<20 and int(b['cycle'])>=(last[6]if last else 0),'GRAPH_FINAL_RANGE')
   if b[1]=='boundary_split':
    need(b[3]in BOUNDARY_GUARD_CODES and (b[4]=='UNKNOWN' or b[4]in BOUNDARY_GUARD_CODES[b[3]]),'BOUNDARY_DIAGNOSTIC_SCHEMA')
    need(b[4]=='UNKNOWN' or b[2]=='6757b394f9b99b54cc59cd8f05528b770054c25bc6643d413f1a7337f96614d0','BOUNDARY_DIAGNOSTIC_EXCEPTION')
   else:need(b[3]is None and b[4]is None,'BOUNDARY_DIAGNOSTIC_WRONG_PHASE')
   final=dict(kind='failure',phase=b[1],exception_class_sha256=b[2],cycle_seen=b['cycle']=='1')
   if b[1]=='boundary_split':final.update(boundary_step=b[3],boundary_guard=b[4])
   if b[1]=='prepared_checks':
    if b['prepared_step']=='INIT_REPAIR':
     need(b['clock_init_guard']=='UNKNOWN' or b['clock_init_guard']in CLOCK_INIT_GUARDS,'CLOCK_INIT_GUARD_SCHEMA')
     need(b['clock_init_guard']=='UNKNOWN' or b[2]=='6757b394f9b99b54cc59cd8f05528b770054c25bc6643d413f1a7337f96614d0','CLOCK_INIT_GUARD_EXCEPTION')
     final['clock_init_guard']=b['clock_init_guard']
    else:need(b['clock_init_guard']=='NONE','CLOCK_INIT_GUARD_WRONG_STEP')
    final['clock_init_bound']=parse_clock_init_bound(b['prepared_step'],b['clock_init_guard'],b['clock_init_bound'])
    final['clock_init_sizing']=parse_clock_init_sizing(b['prepared_step'],b['clock_init_guard'],final['clock_init_bound'],b['clock_init_sizing'])
    try:final['clock_init_auxiliary']=parse_auxiliary_evidence(b['clock_init_aux'])
    except ValueError:raise Stop('CLOCK_INIT_AUXILIARY_SCHEMA')
    if not(b['prepared_step']=='INIT_REPAIR' and b['clock_init_guard']=='BOUND' and final['clock_init_bound']['status']=='UNAVAILABLE'):need(final['clock_init_auxiliary']['status']=='NONE','CLOCK_INIT_AUXILIARY_SCOPE')
    try:final['clock_init_preexisting']=parse_preexisting_evidence(b['clock_init_preexisting'])
    except ValueError:raise Stop('CLOCK_INIT_PREEXISTING_SCHEMA')
    if b['prepared_step']=='INIT_REPAIR' and b['clock_init_guard']=='PREEXISTING':need(final['clock_init_preexisting']['status']!='NONE','CLOCK_INIT_PREEXISTING_MISSING')
    else:need(final['clock_init_preexisting']['status']=='NONE','CLOCK_INIT_PREEXISTING_SCOPE')
    final.update(parse_prepared_evidence(b['prepared_step'],b['pass_aggregate'],b['pass_scanned'],b['pass_truncated'],b['pass_hist'],b[2]))
    if b['prepared_step']=='TYPES':
     need(census is not None,'REGISTER_CENSUS_MISSING')
     final['register_init_census']=census
     if census['status']=='OK' and not final['pass_errors_truncated'] and 'OTHER'not in final['pass_error_classes']:
      need(census['mismatches']==final['pass_error_classes'].get('T09',0),'REGISTER_CENSUS_T09_COUNT')
    else:need(census is None,'REGISTER_CENSUS_WRONG_STEP')
   else:need(census is None and all(b[k]is None for k in ('prepared_step','clock_init_guard','clock_init_bound','clock_init_sizing','clock_init_aux','clock_init_preexisting','pass_aggregate','pass_scanned','pass_truncated','pass_hist')),'PREPARED_DIAGNOSTIC_WRONG_PHASE')
 need(census is None or (final is not None and final['kind']=='failure'),'REGISTER_CENSUS_INCOMPLETE')
 clean=receipt.get('status')=='PASS_PROCESS_ONLY' and receipt.get('native_exit')==0 and receipt.get('errors')==[] and receipt.get('worker_started')is True
 if final and final['kind']=='success':need(clean,'GRAPH_FALSE_SUCCESS_RECEIPT')
 # Keep at most last sample/marker per phase in exported JSON, not the full log.
 latest={r['phase']:r for r in rows}
 out=dict(status='INCOMPLETE_STRUCTURAL_GRAPH_ONLY',last_phase=last_phase,metric_records=len(rows),phase_metrics=list(latest.values()),cycle_seen=bool(last and last[6]))
 if final and final['kind']=='success':out.update(status='STRUCTURAL_GRAPH_ONLY_DECLARED_DEPENDENCIES',prepared_sha256=final['prepared_sha256'],symbol_count=final['symbol_count'],leaf_bindings=17,boundary_instances=1,boundary_input_fields=26,boundary_added_ports=90)
 elif final:out.update(status='FAILED_STRUCTURAL_GRAPH_ONLY',phase=final['phase'],exception_class_sha256=final['exception_class_sha256'],cycle_seen=final['cycle_seen'])
 if final and final['kind']=='failure' and final['phase']=='boundary_split':out.update(boundary_step=final['boundary_step'],boundary_guard=final['boundary_guard'])
 if final and final['kind']=='failure' and final['phase']=='prepared_checks':out.update({k:final[k]for k in ('prepared_step','pass_aggregate','pass_errors_scanned','pass_errors_truncated','pass_error_classes')})
 if final and 'clock_init_auxiliary'in final:out['clock_init_auxiliary']=final['clock_init_auxiliary']
 if final and 'clock_init_preexisting'in final:out['clock_init_preexisting']=final['clock_init_preexisting']
 if final and 'clock_init_sizing'in final:out['clock_init_sizing']=final['clock_init_sizing']
 if final and 'clock_init_bound'in final:out['clock_init_bound']=final['clock_init_bound']
 if final and 'clock_init_guard'in final:out['clock_init_guard']=final['clock_init_guard']
 if final and 'register_init_census'in final:out['register_init_census']=final['register_init_census']
 if provenance is not None:out['prepare_provenance']=provenance
 if observer_budget_raw is not None:out['prepare_budget']=observer_budget
 if observer_sizing_raw is not None:out['prepare_uses_sizing']=observer_sizing
 if witness is not None:
  need(final is not None and final['kind']=='failure' and final['cycle_seen'],'GRAPH_WITNESS_WITHOUT_CYCLE_FAILURE')
  out['cycle_witness']=witness
 return out

# BEGIN BOUNDARY COMPILER PARSER
COMPILER_SOURCE_ROLES={
 'IdmaSplitLayout.scala':'LAYOUT',
 'IdmaFieldSplitTransform.scala':'FIELD_SPLIT',
 'IdmaPackedBoundarySplit.scala':'PACKED_SPLIT',
 'BoundarySplitStructuralFixture.scala':'BOUNDARY_FIXTURE',
 'RegisterInitCensus.scala':'REGISTER_CENSUS',
 'ClockInitRepresentationRepair.scala':'CLOCK_REPAIR',
 'ClockInitStructuralFixture.scala':'CLOCK_FIXTURE',
}
COMPILER_CATEGORY_PREFIXES=(
 ('type mismatch','TYPE_MISMATCH'),
 ('not found: value ','NOT_FOUND_VALUE'),
 ('not found: type ','NOT_FOUND_TYPE'),
 ('not found: object ','NOT_FOUND_OBJECT'),
 ('not found: ','NOT_FOUND'),
 ('value ','VALUE_OR_MEMBER'),
 ('overloaded method ','OVERLOAD'),
 ('ambiguous reference','AMBIGUOUS'),
 ('reference to ','REFERENCE'),
 ('too many arguments','ARGUMENT_ARITY'),
 ('not enough arguments','ARGUMENT_ARITY'),
 ('wrong number of arguments','ARGUMENT_ARITY'),
 ('type arguments ','TYPE_ARGUMENTS'),
 ('illegal start','SYNTAX'),
 ('Unmatched closing brace','SYNTAX'),
 ("';' expected",'SYNTAX'),
 ("')' expected",'SYNTAX'),
 ("'}' expected",'SYNTAX'),
 ("']' expected",'SYNTAX'),
 ('identifier expected','SYNTAX'),
)
def compiler_failure_summary(text,sources,input_truncated=False,observed_only=False):
 """Pure lossy compiler-failure metadata; never source text or success evidence."""
 out=dict(schema='COMPILER_DIAGNOSTIC_V1',status='FAILED_COMPILER_DIAGNOSTIC_ONLY',
  parse_status='COMPLETE',rejection='NONE',header_count=0,row_count=0,
  suppressed_count=0,malformed=False,truncated=False,rows=[])
 def reject(reason,truncated=False):
  out.update(parse_status='REJECTED',rejection=reason,truncated=truncated)
  return out
 if type(input_truncated)is not bool:return reject('INPUT_TYPE')
 out['truncated']=input_truncated
 if type(text)is not str:return reject('INPUT_TYPE',input_truncated)
 if len(text)>32768:return reject('INPUT_BYTES',True)
 if not text.isascii() or any(ord(c)<32 and c not in '\n\t\r' for c in text) or '\x7f'in text:
  return reject('INPUT_ASCII',input_truncated)
 if '\r'in text or (text and not text.endswith('\n')):return reject('INPUT_LINE_ENDINGS',input_truncated)
 lines=text.split('\n')
 if any(len(line)>4096 for line in lines):return reject('INPUT_LINE_LENGTH',input_truncated)
 if type(observed_only)is not bool:return reject('SOURCE_MAP',input_truncated)
 source_roles={'ObservedScheduleIdentity.scala':'OBSERVED_IDENTITY','ObservedPrepareAst.scala':'OBSERVED_PHASE','ObservedPrepareStructuralFixture.scala':'OBSERVED_FIXTURE'}if observed_only else COMPILER_SOURCE_ROLES
 if type(sources)is not dict or len(sources)!=len(source_roles):return reject('SOURCE_MAP',input_truncated)
 seen=set()
 for path,entry in sources.items():
  if type(path)is not str or not 1<=len(path)<=4096 or not path.isascii() or any(ord(c)<32 or ord(c)==127 for c in path):
   return reject('SOURCE_MAP',input_truncated)
  basename=path.rsplit('/',1)[-1]
  if basename not in source_roles or basename in seen:return reject('SOURCE_MAP',input_truncated)
  if type(entry)is not dict or set(entry)!={'role','line_count'} or type(entry['role'])is not str or entry['role']!=source_roles[basename]:
   return reject('SOURCE_MAP',input_truncated)
  if type(entry['line_count'])is not int or not 1<=entry['line_count']<=1000000:return reject('SOURCE_MAP',input_truncated)
  seen.add(basename)
 pending=None;after=0
 for line in lines[:-1]:
  header=re.fullmatch(r'(.+):([0-9]+): error: (.*)',line)
  if header is not None or 'error:'in line:
   pending=None;after=0;out['header_count']+=1
   if header is None:
    out['suppressed_count']+=1;out['malformed']=True;continue
   path,number,message=header.groups()
   if path not in sources or len(number)>7 or number.startswith('0'):
    out['suppressed_count']+=1;out['malformed']=True;continue
   number=int(number)
   if not 1<=number<=sources[path]['line_count']:
    out['suppressed_count']+=1;out['malformed']=True;continue
   if len(out['rows'])==32:
    out['suppressed_count']+=1;out['truncated']=True;continue
   category='OTHER'
   for prefix,value in COMPILER_CATEGORY_PREFIXES:
    if message.startswith(prefix):category=value;break
   out['rows'].append(dict(role=sources[path]['role'],line=number,column=None,category=category))
   pending=len(out['rows'])-1
  elif pending is not None:
   after+=1
   # Scala emits the optional caret immediately or after one source excerpt.
   # Only a single ASCII-space-indented caret is recognized; no excerpt is kept.
   caret=re.fullmatch(r'( *)\^ *',line)
   if caret is not None and after<=2:
    out['rows'][pending]['column']=len(caret[1])+1;pending=None
   elif after>=2:pending=None
 out['row_count']=len(out['rows'])
 return out
# END BOUNDARY COMPILER PARSER

def read_closed_log(path,receipt):
 need((receipt.get('cleanup_proof')or{}).get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP','GRAPH_CLEANUP_UNPROVEN')
 barrier=receipt.get('reader_join_barrier')or{};cap=receipt.get('log_capture')or{}
 need(barrier.get('complete')is True and barrier.get('alive')is False and barrier.get('reader_finally_done')is True,'GRAPH_READER_UNCLOSED')
 need(cap.get('pipe_eof_observed')is True and cap.get('gzip_finalized')is True and cap.get('capture_cap_hit')is False,'GRAPH_LOG_UNFINALIZED')
 path=regular(path);need(path.stat().st_size<=65536,'GRAPH_COMPRESSED_LOG_LIMIT')
 need(cap.get('compressed_bytes')==path.stat().st_size and cap.get('compressed_sha256')==sha(path),'GRAPH_COMPRESSED_LOG_IDENTITY')
 with gzip.open(path,'rb')as f:raw=f.read(32769)
 need(len(raw)<=32768 and cap.get('raw_bytes')==len(raw) and cap.get('raw_sha256')==hashlib.sha256(raw).hexdigest(),'GRAPH_RAW_LOG_IDENTITY')
 try:text=raw.decode('ascii')
 except UnicodeError:raise Stop('GRAPH_LOG_ENCODING')
 return text

# BEGIN BOUNDARY COMPILER CLOSED-LOG PROJECTION
BOUNDARY_COMPILER_SOURCES=('IdmaSplitLayout.scala','IdmaFieldSplitTransform.scala','IdmaPackedBoundarySplit.scala','BoundarySplitStructuralFixture.scala','RegisterInitCensus.scala','ClockInitRepresentationRepair.scala','ClockInitStructuralFixture.scala')
def boundary_compiler_failure(path,receipt,pins):
 # This is evidence attached to a failed source-only compiler stage, never a gate.
 try:
  need(phase=='compile_boundary_fixture' and type(receipt)is dict and type(receipt.get('native_exit'))is int and receipt['native_exit']!=0,'COMPILER_DIAGNOSTIC_SCOPE')
  sources={}
  for name in BOUNDARY_COMPILER_SOURCES:
   source=regular(D/'scala'/name);need(source.is_absolute() and str(source)in pins,'COMPILER_SOURCE_IDENTITY')
   need(source.stat().st_size<=262144,'COMPILER_SOURCE_BOUND');need(sha(source)==pins[str(source)],'COMPILER_SOURCE_IDENTITY')
   raw=source.read_bytes();need(b'\r'not in raw and raw.endswith(b'\n'),'COMPILER_SOURCE_LINES')
   count=raw.count(b'\n');need(0<count<=10000,'COMPILER_SOURCE_LINES')
   sources[str(source)]={'role':dict(zip(BOUNDARY_COMPILER_SOURCES,('LAYOUT','FIELD_SPLIT','PACKED_SPLIT','BOUNDARY_FIXTURE','REGISTER_CENSUS','CLOCK_REPAIR','CLOCK_FIXTURE')))[name],'line_count':count}
  text=read_closed_log(path,receipt)
  return compiler_failure_summary(text,sources)
 except BaseException:
  return {'schema':'COMPILER_DIAGNOSTIC_V1','status':'UNAVAILABLE','reason':'CLOSED_LOG_OR_SOURCE_IDENTITY_OR_SCHEMA'}
# END BOUNDARY COMPILER CLOSED-LOG PROJECTION
def observed_compiler_failure(path,receipt,pins):
 try:
  need(phase=='compile_observed_fixture' and type(receipt)is dict and type(receipt.get('native_exit'))is int and receipt['native_exit']!=0,'COMPILER_DIAGNOSTIC_SCOPE')
  sources={}
  for name,role in [('ObservedScheduleIdentity.scala','OBSERVED_IDENTITY'),('ObservedPrepareAst.scala','OBSERVED_PHASE'),('ObservedPrepareStructuralFixture.scala','OBSERVED_FIXTURE')]:
   source=regular(D/'scala'/name);need(str(source)in pins and source.stat().st_size<=262144 and sha(source)==pins[str(source)],'COMPILER_SOURCE_IDENTITY')
   raw=source.read_bytes();need(b'\r'not in raw and raw.endswith(b'\n')and 0<raw.count(b'\n')<=10000,'COMPILER_SOURCE_LINES')
   sources[str(source)]={'role':role,'line_count':raw.count(b'\n')}
  return compiler_failure_summary(read_closed_log(path,receipt),sources,observed_only=True)
 except BaseException:return {'schema':'COMPILER_DIAGNOSTIC_V1','status':'UNAVAILABLE','reason':'CLOSED_LOG_OR_SOURCE_IDENTITY_OR_SCHEMA'}

def read_graph_diagnostics(path,receipt,high_sha,annotations_sha):
 return parse_graph_text(read_closed_log(path,receipt),receipt,high_sha,annotations_sha,observation_only=True,sizing_diagnostics=True)

def reject_fixture_failure(text,label,comparator):
 # Caller must first obtain text through read_closed_log. This path always
 # fails, irrespective of exit status; diagnostic text is never a pass oracle.
 if text.startswith('BOUNDARY_GRAPH_FAILURE_V1'):
  try:failure=comparator.parse_failure(text,label)
  except (ValueError,TypeError):raise Stop('BOUNDARY_FAILURE_SCHEMA_REJECTED')
  boundary_identity['boundary_failure']=failure
  raise Stop('BOUNDARY_FIXTURE_REPORTED_FAILURE')

def stage_cpu_budget(name,seconds):
 # One explicit graph continuation, not a general stage cap relaxation.
 if name=='graph':
  need(seconds==1500,'GRAPH_WALL_CONTRACT');return 1200
 return min(seconds,600)

def main():
 global phase,graph_identity,differential_identity,boundary_identity,stage_step,exclusivity_endpoint,stage_receipt
 graph_identity={};differential_identity={};boundary_identity={}
 stage_step="NONE";exclusivity_endpoint="NONE";stage_receipt=None
 phase='identity';need(os.environ.get('GITHUB_REPOSITORY')=='liyang53719/hetero_cnn_llm_aha' and os.environ.get('GITHUB_REF')=='refs/heads/main' and os.environ.get('GITHUB_EVENT_NAME')=='push' and os.environ.get('GITHUB_RUN_ATTEMPT')=='1')
 launch=git('rev-parse','HEAD');need(launch==os.environ.get('GITHUB_SHA'));source=git('rev-parse','HEAD^');need(git('rev-parse',BASE+'^{tree}')==BASE_TREE and git('rev-parse',source+'^')==BASE)
 need(git('diff','--name-only','HEAD^','HEAD')==NONCE and not git('status','--porcelain'))
 nonce=load(REPO/NONCE,4096);need(nonce=={'schema':'ONE_OBSERVED_PREPARE_DIAGNOSTIC_V1','source_commit':source,'base_commit':BASE,'attempts':1,'numerical_execution':False,'native_execution':False,'artifact_upload':False})
 own=load(D/'SOURCE_PINS.json')
 expected_files={'.github/workflows/chisel-host-boundary-graph-once.yml',*[REL+'/'+p for p in ('run.py', 'prepare_jars.py', 'compare_fixture_results.py', 'compare_boundary_results.py', 'witness_record.py', 'modulecache/BoundedCycleWitness.scala', 'modulecache/CycleWitnessFixture.scala', 'modulecache/StructuralDifferential.scala', 'modulecache/SymbolTable.scala', 'scala/CycleWitnessRoles.scala', 'scala/IdmaFieldSplitTransform.scala', 'scala/IdmaSplitLayout.scala', 'scala/IdmaPackedBoundarySplit.scala', 'scala/BoundarySplitStructuralFixture.scala', 'scala/OriginalHostStructuralGraph.scala', 'scala/StructuralMetadataFactory.scala', 'scala/BoundaryIntegrationGuards.scala', 'scala/RegisterInitCensus.scala', 'scala/ClockInitRepresentationRepair.scala', 'scala/ClockInitStructuralFixture.scala', 'compare_clock_init_results.py','compare_schedule_probe.py','scala/ScheduleProbe.scala','compare_observed_prepare.py','scala/ObservedScheduleIdentity.scala','scala/ObservedPrepareAst.scala','scala/ObservedPrepareStructuralFixture.scala') ]}
 need(set(own)=={'schema','files','publication_delta'} and own['schema']=='HOST_BOUNDARY_GRAPH_SOURCE_PINS_V1')
 need(len(own['files'])==len(expected_files) and {row['path']for row in own['files']}==expected_files)
 pins=pins_for(own['files'],REPO);pins[str(D/'SOURCE_PINS.json')]=sha(D/'SOURCE_PINS.json')
 changed=set(git('diff','--name-only',BASE,source).splitlines())
 expected_delta={'.github/workflows/chisel-host-boundary-graph-once.yml', 'candidates/chisel_host_boundary_graph_20261105/SOURCE_PINS.json', 'candidates/chisel_host_boundary_graph_20261105/compare_observed_prepare.py', 'candidates/chisel_host_boundary_graph_20261105/run.py', 'candidates/chisel_host_boundary_graph_20261105/scala/ObservedPrepareAst.scala', 'candidates/chisel_host_boundary_graph_20261105/scala/ObservedPrepareStructuralFixture.scala'}
 need(len(own['publication_delta'])==len(expected_delta) and changed==set(own['publication_delta'])==expected_delta)
 catalog=regular(REPO/CAT);need(sha(catalog)==CAT_SHA);doc=load(catalog);need(doc['schema']=='REVIEWED_RELATIVE_SOURCE_CLOSURE_V1'and len(doc['files'])==1211);pins.update(pins_for(doc['files'],REPO));pins[str(catalog)]=CAT_SHA
 phase='admission';remote_exclusive(launch);admission();work=P(os.environ['RUNNER_TEMP'])/'chisel-host-boundary-graph';need(work.is_absolute()and not work.exists()and all(not p.is_symlink()for p in(work,*work.parents)));work.mkdir()
 contract={'schema':'BOUNDED_FRESH_HOST_V1','run_id':int(os.environ['GITHUB_RUN_ID']),'source_commit':source,'launch_commit':launch};contractPath=work/'fresh-host.json';contractPath.write_text(json.dumps(contract));pins[str(contractPath)]=sha(contractPath)
 material=REPO/'candidates/ci_frontend_materialization_r2_20261029';sys.path.insert(0,str(material));import fresh_host
 fresh_host.reject_injection(os.environ);fresh_host.validate_contract(contract)
 supdir=REPO/'candidates/ci_frontend_pipeline_r2_20261029';sys.path.insert(0,str(supdir));import supervise_multiroot as supervisor
 started=time.monotonic();reports=[];aliases=[]
 env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','LC_ALL':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1','GITHUB_RUN_ID':os.environ['GITHUB_RUN_ID'],'GITHUB_SHA':launch,'GITHUB_RUN_ATTEMPT':'1','ImageVersion':os.environ.get('ImageVersion',''),'ImageOS':os.environ.get('ImageOS','')}
 py=str(P('/usr/bin/python3').resolve());pins[py]=sha(py)
 def stage(name,args,seconds,rss):
  global phase,stage_step,exclusivity_endpoint,stage_receipt
  phase=name;stage_step="ENTER";exclusivity_endpoint="NONE";stage_receipt=None
  if args and args[0].endswith('/bin/java'):args=[args[0],'-Djava.io.tmpdir='+str(work/name/'tmp'),*args[1:]]
  stage_step="REMOTE_EXCLUSIVE";remote_exclusive(launch)
  stage_step="DEADLINE";need(time.monotonic()-started+seconds+90<2400)
  stage_step="CAPS"
  cap=dict(wall_seconds=seconds,cleanup_seconds=30,cpu_seconds=stage_cpu_budget(name,seconds),per_process_cpu_seconds=stage_cpu_budget(name,seconds),rss_bytes=rss<<30,per_process_as_bytes=15<<30,file_bytes=536870912,tree_bytes=3<<30,watch_tree_bytes=TREE,max_entries=150000,log_bytes=16<<20,raw_log_bytes=32<<20,min_free_disk_bytes=RESERVE,extra_watch_roots=[str(REPO),str(work)],jdk_aliases=aliases)
  stage_env=dict(env)
  if name=='jdk_inventory':stage_env['JAVA_TOOL_OPTIONS']='-Djava.io.tmpdir='+str(work/name/'tmp')+' -XX:-UsePerfData -XX:-HeapDumpOnOutOfMemoryError -XX:ErrorFile=/dev/null'
  stage_step="SUPERVISOR"
  with open(os.devnull,'w')as muted,contextlib.redirect_stdout(muted),contextlib.redirect_stderr(muted):
   r=supervisor.execute(args,str(work/name),str(work/'owner.lock'),cap,stage_env,dict(pins),resource_gate={'min_available_memory':13<<30,'min_disk_free':TREE+RESERVE})
  stage_step="RECEIPT";stage_receipt=supervisor_failure_summary(r)
  stage_step="PROJECT";reports.append(project(name,r))
  stage_step="EMIT";print(json.dumps({'schema':'STRUCTURAL_GRAPH_PROGRESS_V1',**reports[-1],'numerical_pass':False}),flush=True)
  stage_step="POSTCHECK"
  # BEGIN BOUNDARY COMPILER FAILURE HOOK
  if name=='compile_observed_fixture' and type(r.get('native_exit'))is int and r['native_exit']!=0:
   boundary_identity['observed_compiler_failure']=observed_compiler_failure(work/name/'frontend.log.gz',r,pins)
  if name=='compile_boundary_fixture' and type(r.get('native_exit'))is int and r['native_exit']!=0:
   boundary_identity['boundary_compiler_failure']=boundary_compiler_failure(work/name/'frontend.log.gz',r,pins)
  # END BOUNDARY COMPILER FAILURE HOOK
  if name in ('graph','diff_official','diff_cached','witness_fixture','boundary_official','boundary_cached','register_census_fixture','clock_init_official','clock_init_cached','observed_official','observed_cached'):
   stage_step="RETURN";return work/name,r # Parse only after independent cleanup/log-finalization gates.
  need(r.get('native_exit')in ((0,1)if name=='jdk_inventory'else(0,)) and not r.get('errors') and reports[-1]['cleanup_complete'])
  stage_step="RETURN";return work/name
 phase='jdk_location'
 need(bool(os.environ.get('JAVA_HOME_21_X64')),'JDK_ENVIRONMENT_MISSING')
 rawhome=P(os.environ['JAVA_HOME_21_X64']);need(rawhome.is_absolute(),'JDK_HOME_NOT_ABSOLUTE');need(rawhome.is_dir(),'JDK_HOME_MISSING');home=rawhome.resolve(strict=True);need(jdk_location_allowed(home),'JDK_HOME_LOCATION_REJECTED')
 inv=stage('jdk_inventory',[py,str(material/'inventory_runner_jdk.py'),'--java-home',str(home),'--output',str(work/'jdk_inventory.json'),'--fresh-host-contract',str(contractPath),'--fresh-host-contract-sha256',sha(contractPath)],300,1)
 jdk=load(work/'jdk_inventory.json',4<<20)
 if jdk.get('status')=='FAIL_JDK_INVENTORY':
  code=jdk.get('failure_code');allowed={'JDK_UNKNOWN_EXTERNAL_ALIAS','JDK_EXTERNAL_TARGET_NOT_BOUNDED_REGULAR','JDK_RELEASE_IDENTITY_MISMATCH','JDK_ARCH_MISMATCH','RUNNER_IMAGE_MISMATCH','JDK_PROBE_LOG_CAP','JDK_RUNTIME_IDENTITY_MISMATCH','JDK_TREE_BUDGET','JDK_PROBE_TIMEOUT','JDK_PROBE_NONZERO','JDK_FILESYSTEM_ERROR','JDK_UNCLASSIFIED_FAILURE'}
  need(code in allowed);raise Stop(code)
 need(jdk.get('status')=='NEW_TOOLCHAIN_INVENTORY_ONLY_PENDING_FRESH_QUALIFICATION','JDK_INVENTORY_SCHEMA_REJECTED')
 for row in jdk['files']:
  p=home/row['path']
  if 'symlink'in row:
   aliases.append({'path':str(p),'link':row['symlink'],'target':row['resolved_target']})
   if 'external_dependency'in row:
    dep=row['external_dependency'];pins[dep['resolved_target']]=dep['sha256']
  else:pins[str(p)]=row['sha256']
 java=str(home/'bin/java');need(java in pins)
 phase='jars';stage('jars',[py,str(D/'prepare_jars.py'),str(REPO)],300,1)
 original=REPO/'candidates/fresh_original_top_recovery_20261028';m=load(original/'SOURCE_AND_TOOLCHAIN_PINS.json');jars=[];plugin=None
 for row in m['jars']:
  p=regular(original/'cache'/row['maven_path']);need(sha(p)==row['sha256']);pins[str(p)]=row['sha256']
  if row['role']=='plugin':plugin=str(p)
  else:jars.append(str(p))
 need(len(jars)==106 and plugin is not None);cp=':'.join(jars)
 def jvm(heap,classpath,main,args=()):return [java,'-XX:-UsePerfData','-XX:ActiveProcessorCount=1','-XX:ReservedCodeCacheSize=128m','-Xss4m','-Xmx'+heap,'-XX:-HeapDumpOnOutOfMemoryError','-XX:ErrorFile=/dev/null','-cp',classpath,main,*args]
 # Compile a narrowly patched official SymbolTable and one common fixture.
 # No JVM simulation engine or native library is constructed by either.
 patch_source=regular(D/'modulecache/SymbolTable.scala');fixture_source=regular(D/'modulecache/StructuralDifferential.scala')
 need(sha(patch_source)=='363cfcbc9df17d340580b2308551a83877ab91637c42bda3a6351e2b9fd22fc3')
 witness_source=regular(D/'modulecache/BoundedCycleWitness.scala')
 official_jars=[p for p in jars if P(p).name=='chiseltest_2.13-6.0.0.jar'];need(len(official_jars)==1)
 official_jar=official_jars[0]
 with zipfile.ZipFile(official_jar)as z:
  official_pins={'source_sha256':'9d8cf72aa1efb8c7ebd3e174da99e509bd7d44aec60a1c391b0dfc6f7b453bab','class_sha256':hashlib.sha256(z.read('treadle2/executable/SymbolTable.class')).hexdigest(),'companion_sha256':hashlib.sha256(z.read('treadle2/executable/SymbolTable$.class')).hexdigest()}
 patchclasses=stage('compile_modulecache',jvm('2g',cp,'scala.tools.nsc.Main',['-classpath',cp,'-d','.',str(patch_source),str(witness_source)]),90,3)
 for p in patchclasses.rglob('*.class'):pins[str(p)]=sha(p)
 cached_pins={'source_sha256':sha(patch_source),'class_sha256':sha(regular(patchclasses/'treadle2/executable/SymbolTable.class')),'companion_sha256':sha(regular(patchclasses/'treadle2/executable/SymbolTable$.class'))}
 need(cached_pins['companion_sha256']!=official_pins['companion_sha256'])
 fixtureclasses=stage('compile_fixture',jvm('2g',cp,'scala.tools.nsc.Main',['-classpath',cp,'-d','.',str(fixture_source)]),90,3)
 for p in fixtureclasses.rglob('*.class'):pins[str(p)]=sha(p)
 need(not (fixtureclasses/'treadle2/executable/SymbolTable.class').exists() and not (fixtureclasses/'treadle2/executable/SymbolTable$.class').exists())
 compare_spec=importlib.util.spec_from_file_location('strict_fixture_compare',D/'compare_fixture_results.py');comparator=importlib.util.module_from_spec(compare_spec);compare_spec.loader.exec_module(comparator)
 differential_identity={'differential_status':'PENDING','official_symbol_table':official_pins,'patched_symbol_table':cached_pins,'fixture_source_sha256':sha(fixture_source),'interpreter_bookkeeping_modified':True}
 results=[]
 for label,expected,location,classpath in [('official',official_pins,official_jar,str(fixtureclasses)+':'+cp),('cached',cached_pins,str(patchclasses),str(patchclasses)+':'+str(fixtureclasses)+':'+cp)]:
  folder,receipt=stage('diff_'+label,jvm('1g',classpath,'treadle2.executable.StructuralDifferential',[label,expected['source_sha256'],expected['class_sha256'],expected['companion_sha256'],location]),45,2)
  text=read_closed_log(folder/'frontend.log.gz',receipt)
  need(receipt.get('status')=='PASS_PROCESS_ONLY' and receipt.get('worker_started')is True,'DIFFERENTIAL_PROCESS_FAILED')
  # These booleans are derived from the actual closed-log checks above, not a synthetic receipt.
  process={'exit':receipt.get('native_exit'),'errors':receipt.get('errors'),'cleanup_complete':(receipt.get('cleanup_proof')or{}).get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP','log_finalized':(receipt.get('log_capture')or{}).get('gzip_finalized')is True}
  results.append((text,process))
 differential=comparator.compare(results[0][0],results[1][0],official_pins,cached_pins,results[0][1],results[1][1])
 differential_identity.update(differential_status=differential['status'],differential_cases=differential['cases'])
 # Qualify the exact witness implementation before any large original graph.
 witness_fixture=regular(D/'modulecache/CycleWitnessFixture.scala')
 witnessclasses=stage('compile_witness_fixture',jvm('2g',cp,'scala.tools.nsc.Main',['-classpath',str(patchclasses)+':'+cp,'-d','.',str(witness_fixture)]),90,3)
 for p in witnessclasses.rglob('*.class'):pins[str(p)]=sha(p)
 wf,wr=stage('witness_fixture',jvm('1g',str(patchclasses)+':'+str(witnessclasses)+':'+cp,'treadle2.executable.CycleWitnessFixture'),45,2)
 wt=read_closed_log(wf/'frontend.log.gz',wr)
 cases=('self_loop','multi_loop','acyclic','reachable_other_cycle','node_cap','edge_cap','output_cap','time_cap','reverse_edge','invalid_role','name_cap','lazy_edges','callback_error','malformed_record','record_disclosure','reverse_asymmetric','reverse_direction_mismatch','forward_fanout_reverse_cycle','exception_noninterference')
 expected=''.join('CYCLE_FIXTURE_V1 case='+c+' outcome=PASS\n'for c in cases)+'CYCLE_FIXTURE_FINAL_V1 cases=19 status=PASS\n'
 need(wt==expected and wr.get('status')=='PASS_PROCESS_ONLY' and wr.get('native_exit')==0 and not wr.get('errors'),'WITNESS_FIXTURE_FAILED')
 differential_identity.update(witness_fixture_status='PASS_19_SMALL_CASES_ONLY',witness_source_sha256=sha(witness_source),witness_fixture_source_sha256=sha(witness_fixture))
 boundary_fixture_source=regular(D/'scala/BoundarySplitStructuralFixture.scala')
 need(sha(boundary_fixture_source)=='d4f17a1ac12ed62ebb26f63135c13752a1ff0142097f05d7b907491309c5bce0','CANDIDATE_FIXTURE_SOURCE_CHANGED')
 need(sha(D/'scala/IdmaPackedBoundarySplit.scala')=='27bf9a87064eb66342f2d18b7b268249f7f4c20795f3ea8a31a33f299909e3ee','CANDIDATE_TRANSFORM_SOURCE_CHANGED')
 helpers=[str(regular(D/'scala'/n))for n in ('IdmaSplitLayout.scala','IdmaFieldSplitTransform.scala','IdmaPackedBoundarySplit.scala','BoundarySplitStructuralFixture.scala','RegisterInitCensus.scala','ClockInitRepresentationRepair.scala','ClockInitStructuralFixture.scala')]
 boundaryclasses=stage('compile_boundary_fixture',jvm('2g',cp,'scala.tools.nsc.Main',['-classpath',cp,'-d','.',*helpers]),180,3)
 for p in boundaryclasses.rglob('*.class'):pins[str(p)]=sha(p)
 need(not (boundaryclasses/'treadle2/executable/SymbolTable.class').exists() and not (boundaryclasses/'treadle2/executable/SymbolTable$.class').exists())
 boundary_compare_spec=importlib.util.spec_from_file_location('strict_boundary_compare',D/'compare_boundary_results.py');boundary_comparator=importlib.util.module_from_spec(boundary_compare_spec);boundary_compare_spec.loader.exec_module(boundary_comparator)
 boundary_identity={'boundary_status':'PENDING','official_symbol_table':official_pins,'patched_symbol_table':cached_pins,'boundary_fixture_source_sha256':sha(boundary_fixture_source),'boundary_transform_source_sha256':sha(D/'scala/IdmaPackedBoundarySplit.scala'),'interpreter_bookkeeping_modified':True}
 results=[]
 for label,expected,location,classpath in [('official',official_pins,official_jar,str(boundaryclasses)+':'+cp),('cached',cached_pins,str(patchclasses),str(patchclasses)+':'+str(boundaryclasses)+':'+cp)]:
  folder,receipt=stage('boundary_'+label,jvm('1g',classpath,'chiseltest.simulator.BoundarySplitStructuralFixture',[label,expected['class_sha256'],expected['companion_sha256'],location]),120,2)
  text=read_closed_log(folder/'frontend.log.gz',receipt)
  need(receipt.get('worker_started')is True,'BOUNDARY_PROCESS_NOT_STARTED')
  reject_fixture_failure(text,label,boundary_comparator)
  need(receipt.get('status')=='PASS_PROCESS_ONLY' and receipt.get('worker_started')is True,'BOUNDARY_PROCESS_FAILED')
  process={'exit':receipt.get('native_exit'),'errors':receipt.get('errors'),'cleanup_complete':(receipt.get('cleanup_proof')or{}).get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP','log_finalized':(receipt.get('log_capture')or{}).get('gzip_finalized')is True}
  results.append((text,process))
 boundary_result=boundary_comparator.compare(results[0][0],results[1][0],official_pins,cached_pins,results[0][1],results[1][1])
 need(boundary_result['status']=='PASS_ISOLATED_BOUNDARY_FIXTURE_ONLY','BOUNDARY_PREFLIGHT_FAILED')
 need(boundary_result['cases']==18 and boundary_result['negative_guard_cases']==29 and boundary_result['validity_mask_cases']==6 and boundary_result['bit_equation_phases']==2 and boundary_result['vectors_per_phase']=={'default':3730,'boundary_registered':3731,'unequal_mux':3794,'mux_boundary_registered':3795,'validity_default':6892,'validity_registered':6894},'BOUNDARY_EXTENDED_COVERAGE_REQUIRED')
 boundary_identity.update(boundary_status=boundary_result['status'],boundary_cases=boundary_result['cases'],boundary_negative_guard_cases=boundary_result['negative_guard_cases'],boundary_validity_mask_cases=boundary_result['validity_mask_cases'],boundary_transform_qualification='CURRENT_RUN_PAIRED_FIXTURE_ONLY')
 census_companion_sha=sha(regular(boundaryclasses/'chiseltest/simulator/RegisterInitCensus$.class'))
 censusfolder,censusreceipt=stage('register_census_fixture',jvm('1g',str(boundaryclasses)+':'+cp,'chiseltest.simulator.RegisterInitCensus',[census_companion_sha,str(boundaryclasses)]),30,2)
 census_text=read_closed_log(censusfolder/'frontend.log.gz',censusreceipt)
 need(census_text=='REGISTER_INIT_CENSUS_FIXTURE_V1 status=PASS\n' and censusreceipt.get('status')=='PASS_PROCESS_ONLY' and censusreceipt.get('native_exit')==0 and censusreceipt.get('errors')==[] and censusreceipt.get('worker_started')is True,'REGISTER_CENSUS_PREREQUISITE_FAILED')
 boundary_identity['register_census_fixture_status']='PASS_SYNTHETIC_ONLY'
 repair_companion_sha=sha(regular(boundaryclasses/'chiseltest/simulator/ClockInitRepresentationRepair$.class'))
 clock_spec=importlib.util.spec_from_file_location('strict_clock_init_compare',D/'compare_clock_init_results.py');clock_comparator=importlib.util.module_from_spec(clock_spec);clock_spec.loader.exec_module(clock_comparator)
 clock_results=[]
 for label,expected,location,classpath in [('official',official_pins,official_jar,str(boundaryclasses)+':'+cp),('cached',cached_pins,str(patchclasses),str(patchclasses)+':'+str(boundaryclasses)+':'+cp)]:
  folder,receipt=stage('clock_init_'+label,jvm('1g',classpath,'chiseltest.simulator.ClockInitStructuralFixture',[label,expected['class_sha256'],expected['companion_sha256'],location,repair_companion_sha,str(boundaryclasses)]),120,2)
  text=read_closed_log(folder/'frontend.log.gz',receipt)
  need(receipt.get('worker_started')is True,'CLOCK_INIT_PROCESS_NOT_STARTED')
  if text.startswith('CLOCK_INIT_FAILURE_V1 '):
   try:detail=clock_comparator.failure(text,label)
   except (ValueError,TypeError,KeyError):raise Stop('CLOCK_INIT_FAILURE_SCHEMA')
   boundary_identity['clock_init_failure']=dict(label=label,**detail)
   raise Stop('CLOCK_INIT_FIXTURE_FAILED')
  process={'exit':receipt.get('native_exit'),'errors':receipt.get('errors'),'cleanup_complete':(receipt.get('cleanup_proof')or{}).get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP','log_finalized':(receipt.get('log_capture')or{}).get('gzip_finalized')is True}
  need(receipt.get('status')=='PASS_PROCESS_ONLY','CLOCK_INIT_PROCESS_FAILED')
  clock_results.append((text,process))
 try:clock_result=clock_comparator.compare(clock_results[0][0],clock_results[1][0],clock_results[0][1],clock_results[1][1])
 except (ValueError,TypeError,KeyError):raise Stop('CLOCK_INIT_COMPARATOR_REJECTED')
 need(clock_result=={'status':'PASS_CLOCK_INIT_STRUCTURAL_EQUATIONS_ONLY','cases':3,'block_shape_cases':3,'driver_diagnostic_cases':9,'bound_diagnostic_cases':27,'index_sizing_cases':39,'streaming_cases':186,'legacy_differential_cases':21,'preexisting_diagnostic_cases':72,'negative_guards':27,'equation_vectors_per_case':512,'interpreter_executed':False},'CLOCK_INIT_COVERAGE_REQUIRED')
 boundary_identity['clock_init_qualification']=clock_result
 # Qualify diagnostic observation before any original Host compilation.
 observed_sources=[str(regular(D/'scala'/n))for n in ('ObservedScheduleIdentity.scala','ObservedPrepareAst.scala','ObservedPrepareStructuralFixture.scala')]
 provenanceclasses=stage('compile_observed_fixture',jvm('2g',cp,'scala.tools.nsc.Main',['-classpath',str(boundaryclasses)+':'+cp,'-d','.',*observed_sources]),180,3)
 observed_files=list(provenanceclasses.rglob('*.class'));need(1<=len(observed_files)<=512,'OBSERVER_CLASS_COUNT')
 for path in observed_files:pins[str(regular(path))]=sha(path)
 need(not ({str(p.relative_to(provenanceclasses))for p in observed_files}&{str(p.relative_to(boundaryclasses))for p in boundaryclasses.rglob('*.class')}),'OBSERVER_CLASS_SHADOWING')
 observer_class_sha=sha(regular(provenanceclasses/'chiseltest/simulator/ObservedPrepareAst.class'))
 observer_companion_sha=sha(regular(provenanceclasses/'chiseltest/simulator/ObservedPrepareAst$.class'))
 observed_identity_sha=sha(regular(provenanceclasses/'chiseltest/simulator/ObservedScheduleIdentity$.class'))
 observed_spec=importlib.util.spec_from_file_location('strict_observed_prepare',D/'compare_observed_prepare.py');observed_comparator=importlib.util.module_from_spec(observed_spec);observed_spec.loader.exec_module(observed_comparator)
 observed_results=[]
 for label,expected,location,classpath in [('official',official_pins,official_jar,str(provenanceclasses)+':'+str(boundaryclasses)+':'+cp),('cached',cached_pins,str(patchclasses),str(patchclasses)+':'+str(provenanceclasses)+':'+str(boundaryclasses)+':'+cp)]:
  folder,receipt=stage('observed_'+label,jvm('1g',classpath,'chiseltest.simulator.ObservedPrepareStructuralFixture',[label,str(provenanceclasses),observer_class_sha,observer_companion_sha,observed_identity_sha,location,expected['class_sha256'],expected['companion_sha256']]),120,2)
  text=read_closed_log(folder/'frontend.log.gz',receipt)
  need(receipt.get('worker_started')is True,'OBSERVER_PROCESS_NOT_STARTED')
  if text.startswith('OBSERVED_PREPARE_FAILURE_V1'):
   try:boundary_identity['observed_prepare_failure']=dict(label=label,**observed_comparator.failure(text,label))
   except (ValueError,TypeError,KeyError):raise Stop('OBSERVER_FAILURE_SCHEMA')
   raise Stop('OBSERVER_FIXTURE_REPORTED_FAILURE')
  need(receipt.get('status')=='PASS_PROCESS_ONLY','OBSERVER_PROCESS_FAILED')
  process={'exit':receipt.get('native_exit'),'errors':receipt.get('errors'),'cleanup_complete':(receipt.get('cleanup_proof')or{}).get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP','log_finalized':(receipt.get('log_capture')or{}).get('gzip_finalized')is True}
  observed_results.append((text,process))
 try:observed_result=observed_comparator.compare(observed_results[0][0],observed_results[1][0],observed_results[0][1],observed_results[1][1])
 except (ValueError,TypeError,KeyError):raise Stop('OBSERVER_COMPARATOR_REJECTED')
 need(observed_result=={'status':'PASS_OBSERVED_PREPARE_FIXTURE_ONLY','cases':9,'parity_cases':9,'suffix_checks':12,'graph_checks':12,'observer_checks':69,'parity_checks':11,'failure_parity_cases':3,'sizing_checks':56,'quota_checks':6,'state_fields':3,'form_absent_in_pinned_api':True,'renames_none':True,'diagnostic_only':True,'interpreter_executed':False,'full_host_accepted':False},'OBSERVER_COVERAGE_REQUIRED')
 boundary_identity['observed_prepare_qualification']=observed_result
 gatepath=REPO/'candidates/gdn32_first_model162_producer_20261104/candidate_generation_gate.py';spec=importlib.util.spec_from_file_location('reviewed_graph_inputs',gatepath);gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
 selection=gate.selected_inputs(REPO,gate.MODEL162_SOURCE);sources=gate.checked_paths(REPO,selection['overlay'],m,selection['contract']);need(len(sources)==162)
 # The live 2400-second gate remains authoritative before every later stage.
 classes=stage('compile_original',jvm('2g',cp,'scala.tools.nsc.Main',['-classpath',cp,'-Xplugin:'+plugin,'-language:reflectiveCalls','-d','.',*sources]),300,3)
 for p in classes.rglob('*.class'):pins[str(p)]=sha(p)
 basecp=str(classes)+':'+cp
 helpers=[str(regular(D/'scala'/n))for n in ('OriginalHostStructuralGraph.scala','StructuralMetadataFactory.scala','CycleWitnessRoles.scala','BoundaryIntegrationGuards.scala')]
 hclasses=stage('compile_graph',jvm('2g',cp,'scala.tools.nsc.Main',['-classpath',str(patchclasses)+':'+str(provenanceclasses)+':'+str(boundaryclasses)+':'+basecp,'-d','.',*helpers]),300,3)
 for p in hclasses.rglob('*.class'):pins[str(p)]=sha(p)
 need(not ({str(p.relative_to(hclasses))for p in hclasses.rglob('*.class')}&({str(p.relative_to(boundaryclasses))for p in boundaryclasses.rglob('*.class')}|{str(p.relative_to(provenanceclasses))for p in provenanceclasses.rglob('*.class')})),'QUALIFIED_CLASS_SHADOWING')
 boundary_companion_sha=sha(regular(boundaryclasses/'heteronpu/continuous/model/IdmaPackedBoundarySplit$.class'))
 highdir=stage('original_high',jvm('4g',basecp,'chiseltest.simulator.DiagnoseOriginalHostMoePhaseV5'),600,6)/'host-diagnostic'
 high=regular(highdir/'original-high.fir');ann=regular(highdir/'high-annotations.json');ext=regular(highdir/'high-extmodules.fir')
 need(high.stat().st_size<=512<<20 and ann.stat().st_size<=16<<20 and ext.stat().st_size<=1<<20)
 # Separate inventory emitted by the unchanged original diagnostic is cross-bound
 # to the complete freshly generated high by the structural helper's own parser.
 blocks=re.split(r'(?m)(?=^extmodule )',ext.read_text());matches=[b for b in blocks if b.startswith('extmodule idma_backend_rw_axi_flat_wrap :')];need(len(matches)==1)
 need(matches[0].endswith('\n'));exttext=matches[0][:-1];extsha='85b299b3b237b70a8450315f887a2f8aad53bd86c95fb8d9a2ff943173cb4193';need(hashlib.sha256(exttext.encode()).hexdigest()==extsha)
 for p in (high,ann,ext):pins[str(p)]=sha(p)
 highsha=sha(high);annsha=sha(ann)
 need(highsha=='9130abce09a3ca5b27e4b92eadfa3b2a133d9d17825009f5b5d0ef673b97390f' and annsha=='2bea49e84f2ca30a5409e33c33ae71772f67772269851ae271137feb55bf9303','ORIGINAL_HOST_INPUT_IDENTITY')
 need(high.stat().st_size==117714131 and ann.stat().st_size==1379743,'ORIGINAL_HOST_INPUT_SIZE')
 identity={'high_sha256':highsha,'high_bytes':high.stat().st_size,'annotations_sha256':annsha,'annotations_bytes':ann.stat().st_size}
 graph_identity=dict(identity)
 graphdir,graphreceipt=stage('graph',jvm('4g',str(patchclasses)+':'+str(hclasses)+':'+str(provenanceclasses)+':'+str(boundaryclasses)+':'+basecp,'chiseltest.simulator.OriginalHostStructuralGraph',[str(high),highsha,str(ann),annsha,extsha,cached_pins['class_sha256'],cached_pins['companion_sha256'],str(patchclasses),boundary_companion_sha,str(boundaryclasses),census_companion_sha,repair_companion_sha,observer_class_sha,observer_companion_sha,observed_identity_sha,str(provenanceclasses)]),1500,6)
 # Budget failures may yield useful diagnostics ONLY after closed/finalized log
 # and complete process cleanup. Never promote markers to numerical/graph PASS.
 try:diagnostics=read_graph_diagnostics(graphdir/'frontend.log.gz',graphreceipt,highsha,annsha)
 except BaseException as error:
  diagnostics={'status':'FAIL_OR_INCOMPLETE','reason':error.code if isinstance(error,Stop)else'GRAPH_DIAGNOSTIC_REJECTED'}
 need(shutil.disk_usage(work).free>=RESERVE)
 need(diagnostics['status']!='STRUCTURAL_GRAPH_ONLY_DECLARED_DEPENDENCIES','OBSERVER_DIAGNOSTIC_CANNOT_PASS')
 for path,digest in pins.items():need(sha(path)==digest)
 return {'schema':'STRUCTURAL_GRAPH_ONLY_V1',**diagnostics,**identity,**differential_identity,**boundary_identity,'full_host_accepted':False,'final_reserve_preserved':True,'owned_process_cleanup_complete':all(r['cleanup_complete']for r in reports),'private_job_files_exported':False,'source_commit':source,'launch_commit':launch,'catalog_sha256':CAT_SHA,'jdk_inventory_sha256':sha(work/'jdk_inventory.json'),'helper_manifest_sha256':sha(D/'SOURCE_PINS.json'),'expected_leaf_bindings':17,'dut_provider_native_loaded':False,'dut_evaluated':False,'weights_read':False,'numerical_pass':False,'stages':reports}
if __name__=='__main__':
 phase='startup';ok=False
 try:result=main();ok=False # Observation-only candidate never declares graph acceptance.
 except BaseException as error:result={'schema':'STRUCTURAL_GRAPH_ONLY_V1',**graph_identity,**differential_identity,**boundary_identity,'full_host_accepted':False,'status':'FAIL_OR_INCOMPLETE','stage':phase,'reason':error.code if isinstance(error,Stop)else'UNCLASSIFIED_FAILURE','stage_diagnostic':stage_failure_diagnostic(error),'dut_provider_native_loaded':False,'dut_evaluated':False,'weights_read':False,'numerical_pass':False}
 encoded=json.dumps(result,separators=(',',':'));need(len(encoded)<=16384);print(encoded,flush=True)
 sys.exit(0 if ok else 2)
