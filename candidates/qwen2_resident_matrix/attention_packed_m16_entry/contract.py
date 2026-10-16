"""Exact installed linked-M16 source contract; no arithmetic or native loading."""
import hashlib,json,math,os,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
PREFIX='candidates/qwen2_resident_matrix/attention_packed_m16_entry/'
PROFILE='qwen2-public-pv16-packed-m16-linked-v1'
_ABSENT=object()
def need(ok,message):
 if not ok:raise ValueError(message)
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def snapshot():
 path=HERE/'pins.json'
 need(path.is_file() and not path.is_symlink(),'linked source contract is not installed')
 raw=path.read_bytes();need(len(raw)<=2*1024*1024,'bounded source contract')
 pins=json.loads(raw)
 need(set(pins)=={'schema','profile','sources','own','generated','inputs','targets','execution_scope'} and
  type(pins['schema']) is int and pins['schema']==1 and pins['profile']==PROFILE and
  pins['execution_scope']=='ORIGINAL_M16_PUBLIC21','exact linked M16 source contract')
 expected={**pins['sources'],**pins['own'],**pins['generated']}
 need(PREFIX+'pins.json' not in expected,'acyclic linked source contract')
 for name,value in expected.items():
  need(type(name) is str and name and '\\' not in name and not Path(name).is_absolute() and
   all(x not in ('','.','..') for x in name.split('/')) and type(value) is str and len(value)==64 and
   all(c in '0123456789abcdef' for c in value),'canonical source entry')
  target=ROOT/name
  need(target.is_file() and not target.is_symlink() and target.resolve()==target and digest(target)==value,'linked source drift: '+name)
 expected[PREFIX+'pins.json']=hashlib.sha256(raw).hexdigest()
 return expected

def modes(*,fresh_profile,enable_raw_kv,enable_packed=_ABSENT,rows=_ABSENT):
 need(fresh_profile is True and enable_raw_kv is True,'linked entry requires explicit fresh/raw profile')
 if enable_packed is not _ABSENT:need(enable_packed is True,'linked entry requires explicit packed profile')
 if rows is not _ABSENT:need(type(rows) is int and rows==16,'linked entry supports canonical M16 only')
 return snapshot()

def git_context():
 from ..attention_packed_m16_assets import reuse
 expected=reuse.contract()['origin_commit']
 need((ROOT/'.git').is_dir() and not (ROOT/'.git').is_symlink() and
  all(k not in os.environ for k in ('GIT_DIR','GIT_WORK_TREE','GIT_INDEX_FILE','GIT_OBJECT_DIRECTORY','GIT_ALTERNATE_OBJECT_DIRECTORIES')),
  'independent Git checkout without environment redirection required')
 top=subprocess.run(['git','rev-parse','--show-toplevel'],cwd=ROOT,capture_output=True,check=True,timeout=5).stdout.decode('utf-8').strip()
 need(Path(top).resolve()==ROOT,'original Git worktree root mismatch')
 head=subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,check=True,timeout=5).stdout.decode('ascii').strip()
 need(head==expected,'authentic original arithmetic Git context required')
 name='chisel/continuous_prefill/tests/qwen2_block.cpp'
 raw=subprocess.run(['git','show','HEAD:'+name],cwd=ROOT,capture_output=True,check=True,timeout=5).stdout
 need(raw==(ROOT/name).read_bytes(),'committed original scalar arithmetic changed')
 return dict(commit=head,arithmetic_sha256=hashlib.sha256(raw).hexdigest())

def authorize_run(context):
 need(type(context) is dict and set(context)=={'profile','attempt','pid','started','work_deadline','outer_deadline','source_manifest_sha256'},
  'explicit bounded execution context required')
 need(context['profile']==PROFILE and type(context['attempt']) is int and context['attempt']==1 and
  type(context['pid']) is int and context['pid']==os.getpid(),'single local numerical attempt')
 need(all(type(context[k]) in (int,float) and math.isfinite(context[k]) and context[k]>0
  for k in ('started','work_deadline','outer_deadline')),'finite process deadlines')
 need(context['work_deadline']==context['started']+924 and context['outer_deadline']==context['started']+930 and
  context['started']<=time.monotonic()<context['work_deadline'],'fixed 930-second envelope exhausted or changed')
 sources=snapshot();git_context()
 encoded=(json.dumps(sources,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
 need(context['source_manifest_sha256']==hashlib.sha256(encoded).hexdigest(),'execution context/source mismatch')
 need(time.monotonic()<context['work_deadline'],'source preflight exceeded work deadline')
 return sources
