"""Execute exact admitted argv in outer-owned process after locked disk admission.
No setsid/fork/group change. Outer strict supervisor holds lock before this starts.
"""
import argparse,hashlib,json,os,pathlib,resource,sys
import live_budget

def sha(p):
 with open(p,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
CACHE_NAMES=('HOME','HF_HOME','HF_HUB_CACHE','TRANSFORMERS_CACHE','XDG_CACHE_HOME','TORCH_HOME','NUMBA_CACHE_DIR','MPLCONFIGDIR','TMPDIR')
def check_environment(b):
 root=pathlib.Path(b['cache_root']);roots=live_budget.roots_checked(b['owned_roots'])
 if not root.is_absolute() or not root.is_dir() or any(p.is_symlink()for p in (root,*root.parents)) or not any(root.is_relative_to(p)for p in roots):raise ValueError('cache root must be actual watched job subtree')
 for name in CACHE_NAMES:
  p=pathlib.Path(b['environment'][name])
  if p!=root/name.lower() or not p.is_dir() or p.is_symlink():raise ValueError('explicit owned cache mapping drift')
 for key in ('HF_HUB_OFFLINE','TRANSFORMERS_OFFLINE','PYTHONDONTWRITEBYTECODE','PYTHONNOUSERSITE'):
  if b['environment'].get(key)!='1':raise ValueError('offline provider/reference environment')
 for key in ('LD_PRELOAD','LD_LIBRARY_PATH','PYTHONPATH','PYTHONHOME','GH_TOKEN','GITHUB_TOKEN'):
  if key in b['environment']:raise ValueError('unsafe inherited execution variable')


# Source-only safe failure projection; diagnostics never admit execution.
_DIAGNOSTIC_COMPONENT='LOCKED_PHASE'
_DIAGNOSTIC_PHASES=('CLI', 'PHASE_PIN', 'PHASE_JSON', 'SESSION', 'SOURCE_PINS', 'ENVIRONMENT', 'CENSUS', 'LIVE_ADMISSION', 'ADMISSION_RECEIPT', 'FILE_LIMIT', 'ARGV', 'EXECVE')
_DIAGNOSTIC_CLASSES=('ValueError', 'TypeError', 'KeyError', 'IndexError', 'OSError', 'FileNotFoundError', 'PermissionError', 'JSONDecodeError', 'UnicodeDecodeError', 'UnicodeEncodeError', 'TimeoutExpired', 'SystemExit', 'OverflowError', 'MemoryError', 'RuntimeError', 'IsADirectoryError', 'NotADirectoryError', 'FileExistsError', 'error', 'OTHER')
_diagnostic_phase=['CLI']
def diagnostic_phase(value):
 if value not in _DIAGNOSTIC_PHASES:raise ValueError('unknown internal startup diagnostic phase')
 _diagnostic_phase[0]=value
def startup_failure(exc):
 phase=_diagnostic_phase[0]
 name=type(exc).__name__
 return dict(schema='GDN32_STARTUP_DIAGNOSTIC_V1',component=_DIAGNOSTIC_COMPONENT,stage='UNVERIFIED'if _DIAGNOSTIC_COMPONENT=='LOCKED_PHASE'else'startup_abi',phase=phase,status='FAILED',code=phase+'_REJECTED',exception_class=name if name in _DIAGNOSTIC_CLASSES else 'OTHER',native_started=None,dut_started=None if _DIAGNOSTIC_COMPONENT=='LOCKED_PHASE'else False,numerical_pass=False)

def _main_impl():
 a=argparse.ArgumentParser();a.add_argument('--phase',required=True);a.add_argument('--sha256',required=True);v=a.parse_args()
 diagnostic_phase('PHASE_PIN')
 if sha(v.phase)!=v.sha256:raise ValueError('admitted phase drift')
 diagnostic_phase('PHASE_JSON')
 b=json.loads(pathlib.Path(v.phase).read_text())
 diagnostic_phase('SESSION')
 if os.getpid()!=os.getpgrp() or os.getpid()!=os.getsid(0):raise ValueError('strict outer session leader required')
 diagnostic_phase('SOURCE_PINS')
 for p,h in b['pins'].items():
  if sha(p)!=h:raise ValueError('phase source drift')
 diagnostic_phase('ENVIRONMENT')
 check_environment(b)
 diagnostic_phase('CENSUS')
 snapshot=live_budget.census(b['owned_roots'])
 diagnostic_phase('LIVE_ADMISSION')
 if 'preserve_free_8gib'in b:
  if b['preserve_free_8gib']is not True or type(b['extra_bytes'])is not int or snapshot['free_bytes']-b['extra_bytes']<8<<30:raise ValueError('finite FULL phase preserves8GiB after allocation')
 admission=live_budget.admit(snapshot,extra_bytes=b['extra_bytes'],phase_seconds=b['seconds'],job_started=b['job_started'],job_seconds=b.get('job_budget_seconds',21000),acquisition=False,tree_cap=b.get('tree_cap',live_budget.TREE_CAP))
 diagnostic_phase('ADMISSION_RECEIPT')
 with open(b['admission_output'],'x') as f:json.dump(admission,f,indent=2)
 diagnostic_phase('FILE_LIMIT')
 cap=b['write_file_bytes']
 if type(cap)is not int or not 0<cap<=128<<20:raise ValueError('bounded generated output')
 resource.setrlimit(resource.RLIMIT_FSIZE,(cap,cap))
 diagnostic_phase('ARGV')
 argv=b['argv']
 if not argv or not pathlib.Path(argv[0]).is_absolute():raise ValueError('absolute exact executable')
 diagnostic_phase('EXECVE')
 os.execve(argv[0],argv,b['environment'])
def main():
 diagnostic_phase('CLI')
 try:return _main_impl()
 except SystemExit as exc:
  if exc.code not in (0,None):print(json.dumps(startup_failure(exc),sort_keys=True),flush=True)
  raise
 except Exception as exc:
  print(json.dumps(startup_failure(exc),sort_keys=True),flush=True)
  raise
if __name__=='__main__':main()
