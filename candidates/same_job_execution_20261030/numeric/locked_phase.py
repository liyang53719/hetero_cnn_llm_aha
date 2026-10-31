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

def main():
 a=argparse.ArgumentParser();a.add_argument('--phase',required=True);a.add_argument('--sha256',required=True);v=a.parse_args()
 if sha(v.phase)!=v.sha256:raise ValueError('admitted phase drift')
 b=json.loads(pathlib.Path(v.phase).read_text())
 if os.getpid()!=os.getpgrp() or os.getpid()!=os.getsid(0):raise ValueError('strict outer session leader required')
 for p,h in b['pins'].items():
  if sha(p)!=h:raise ValueError('phase source drift')
 check_environment(b)
 snapshot=live_budget.census(b['owned_roots'])
 admission=live_budget.admit(snapshot,extra_bytes=b['extra_bytes'],phase_seconds=b['seconds'],job_started=b['job_started'],job_seconds=b.get('job_budget_seconds',21000),acquisition=False)
 with open(b['admission_output'],'x') as f:json.dump(admission,f,indent=2)
 cap=b['write_file_bytes']
 if type(cap)is not int or not 0<cap<=128<<20:raise ValueError('bounded generated output')
 resource.setrlimit(resource.RLIMIT_FSIZE,(cap,cap))
 argv=b['argv']
 if not argv or not pathlib.Path(argv[0]).is_absolute():raise ValueError('absolute exact executable')
 os.execve(argv[0],argv,b['environment'])
if __name__=='__main__':main()
