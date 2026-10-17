#!/usr/bin/python3
"""Pinned firtool only; preserve its stdout/stderr and record argv separately."""
import hashlib,json,os,resource,stat,sys
from pathlib import Path
root=Path(__file__).resolve().parent
config=json.loads((root/'config.json').read_text());tool=Path(config['tool'])
if hashlib.sha256(tool.read_bytes()).hexdigest()!=config['sha256']:raise ValueError('firtool drift')
resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))
os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
fd=os.open(root/'argv.jsonl',os.O_WRONLY|os.O_APPEND|os.O_NOFOLLOW|os.O_CLOEXEC)
try:
 if not stat.S_ISREG(os.fstat(fd).st_mode):raise ValueError('audit not regular')
 line=(json.dumps(dict(argv=[str(tool)]+sys.argv[1:],as_limit=resource.getrlimit(resource.RLIMIT_AS),affinity_count=len(os.sched_getaffinity(0))),separators=(',',':'))+'\n').encode()
 if os.fstat(fd).st_size+len(line)>65536:raise ValueError('audit64KiB cap')
 os.write(fd,line)
finally:os.close(fd)
os.execve(str(tool),[str(tool)]+sys.argv[1:],{'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','LC_ALL':'C.UTF-8','TZ':'UTC'})
