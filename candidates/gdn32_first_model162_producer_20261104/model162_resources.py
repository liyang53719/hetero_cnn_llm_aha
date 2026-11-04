"""Fresh typed resource probe for the owning full same-job controller only."""
import hashlib,importlib.util,json,pathlib
P=pathlib.Path
REL='candidates/gdn32_first_model_execution_20261104/numeric/samejob_gdn32_full.py'
def need(v,m):
 if not v:raise ValueError(m)
def sha(p):
 with P(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def load_controller(row):
 need(type(row)is dict and set(row)=={'path','sha256'},'exact owning controller pin')
 p=P(row['path']);need(p.is_absolute()and p==p.resolve()and all(not q.is_symlink()for q in(p,*p.parents))and p.is_file()and 0<p.stat().st_size<=2<<20 and sha(p)==row['sha256'],'owning controller unchanged before resource probe')
 b=json.loads(p.read_text());need(b.get('schema')=='GDN32_FULL_MODEL_SAME_JOB_BINDING_V1','full actual162 controller resource domain')
 path=P(b['repo'])/REL;need(path.is_file()and path==path.resolve()and all(not q.is_symlink()for q in(path,*path.parents))and b['pins'].get(str(path))==sha(path),'pinned typed resource gate bridge')
 spec=importlib.util.spec_from_file_location('_actual162_resource_bridge',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 return b,m
# Exact original stage wall/RSS requests, never a new resource budget.
STAGE_REQUESTS={
 'jdk':(300,1),'compile_tools':(300,1),'jars':(600,1),'verilator':(300,1),
 'idma':(240,1),'matrix':(300,1),'fresh_host':(300,1),'binding':(300,1),
 'compile_model_sources':(300,3),'helper_compile':(300,3),'original_high':(600,6),
 'canonical_micro':(120,1),'canonical_full':(300,3),'transform_new_toolchain':(300,3),
 'emit_host':(900,6),'sv_identity':(180,1),'emit_fma':(300,3),'subset':(120,2),
 'frontend':(180,7),
 'frontend_native_Vbf16_context_lane_cluster16_rev8b_b_candidate_d':(1800,12),
 'frontend_native_Vqwen2_matrix_command_endpoint_0':(1800,12),
 'frontend_native_VTransposedDenseDownOwner':(1800,12),
 'frontend_native_VHostBlockTopV4':(1800,12),
 'archive_bf16_context_lane_cluster16_rev8b_b_candidate_d':(600,8),
 'archive_qwen2_matrix_command_endpoint_0':(1800,8),
 'archive_TransposedDenseDownOwner':(3600,8),'host_archive':(3600,8),'host_link':(600,8)}
PRE_CODES={'RESOURCE_REQUEST':'INVALID_STAGE_RESOURCE_REQUEST','CONTROLLER_BINDING':'CONTROLLER_BINDING_REJECTED','RESOURCE_GATE':'RESOURCE_GATE_REJECTED','RUNTIME_ALIAS':'RUNTIME_ALIAS_REJECTED','DISK':'DISK_GATE_REJECTED','DEADLINE':'DEADLINE_REJECTED','NATIVE_ENVIRONMENT':'NATIVE_ENVIRONMENT_REJECTED'}
EXCEPTION_CLASSES={'OSError','FileNotFoundError','ProcessLookupError','PermissionError','InterruptedError','TimeoutError','BlockingIOError','ChildProcessError','BrokenPipeError','IsADirectoryError','NotADirectoryError','FileExistsError','ConnectionError','ValueError','RuntimeError','TypeError','KeyError','IndexError','StopIteration','MemoryError','OverflowError','UnicodeDecodeError','SystemExit','KeyboardInterrupt','_Invalid','_Deadline','CleanupFailure'}
SERIAL_CODES={
 'exact R7 four stages required':'PLAN_PREFIX_SET',
 'plan-only unexpectedly generated child files':'PLAN_ONLY_OUTPUT',
 'args symlink':'ARGFILE_SYMLINK','frontend only':'FRONTEND_ONLY_REQUIRED',
 'one Mdir/prefix':'ARGUMENT_CARDINALITY','owned native Mdir':'MDIR_MISMATCH',
 'native prefix drift':'PREFIX_MISMATCH','native child required':'HIERARCHICAL_CHILD_REQUIRED',
 'Host must not respawn scanner':'HOST_RECURSIVE_SCAN',
 'reviewed hierarchical initial argv':'INITIAL_HIERARCHICAL_ARGV',
 'expected owned obj':'OWNED_OBJ_MISMATCH','serial options':'SERIAL_OPTIONS',
 'concrete input symlink':'INPUT_SYMLINK',
 'native stage incomplete or cleanup not proven':'NATIVE_STAGE_INCOMPLETE',
 'plan drift':'PLAN_DRIFT','exactly one native child wrapper':'CHILD_WRAPPER_CARDINALITY',
 'Host header missing':'HOST_HEADER_MISSING','Host cpp missing':'HOST_CPP_MISSING'}
def safe_failure(stage,phase,exc,seconds,rss_gib,kind='PRE'):
 # Fixed fields only. Unknown caller strings/exception text never leave the job.
 if getattr(exc,'_model162_safe_failure_reported',False):return
 cls=type(exc).__name__;cls=cls if cls in EXCEPTION_CLASSES else 'OTHER'
 stage=stage if type(stage)is str and stage in STAGE_REQUESTS else 'UNKNOWN_STAGE'
 seconds=seconds if type(seconds)is int and 0<=seconds<=21000 else None
 rss_gib=rss_gib if type(rss_gib)is int and 0<=rss_gib<=64 else None
 if kind=='PRE':
  need(phase in PRE_CODES,'fixed pre-supervisor failure phase')
  schema='GDN32_MODEL_PRE_SUPERVISOR_DIAGNOSTIC_V1';code=PRE_CODES[phase];native=False
 elif kind=='SUPERVISOR':
  schema='GDN32_MODEL_SUPERVISOR_EXCEPTION_V1';phase='SUPERVISOR';code='SUPERVISOR_EXCEPTION';native=None
 elif kind=='SERIAL':
  schema='GDN32_MODEL_SERIAL_PLAN_DIAGNOSTIC_V1';stage='frontend';phase='SERIAL_PLAN';code=SERIAL_CODES.get(str(exc),'SERIAL_FRONTEND_UNCLASSIFIED');native=None
 else:raise ValueError('fixed safe diagnostic kind')
 print(json.dumps(dict(schema=schema,stage=stage,phase=phase,status='REFUSED',code=code,exception_class=cls,seconds=seconds,rss_gib=rss_gib,native_started=native,numerical_pass=False),sort_keys=True,allow_nan=False),flush=True)
 try:setattr(exc,'_model162_safe_failure_reported',True)
 except Exception:pass

def before_stage(row,seconds,rss_gib,*,stage):
 try:need(type(stage)is str and stage in STAGE_REQUESTS and type(seconds)is int and type(rss_gib)is int and (seconds,rss_gib)==STAGE_REQUESTS[stage],'fixed exact named stage resource request')
 except Exception as exc:safe_failure(stage,'RESOURCE_REQUEST',exc,seconds,rss_gib);raise
 try:b,m=load_controller(row)
 except Exception as exc:safe_failure(stage,'CONTROLLER_BINDING',exc,seconds,rss_gib);raise
 try:return m.resource_gate(b,phase='MODEL_BUILD',min_memory=(rss_gib+1)*1024**3,min_disk=1_500_000_000,stage_seconds=seconds)
 except Exception as exc:safe_failure(stage,'RESOURCE_GATE',exc,seconds,rss_gib);raise
