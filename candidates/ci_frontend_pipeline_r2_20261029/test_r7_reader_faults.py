"""Fault injections only, NOT performance evidence. Isolated small subprocesses."""
from pathlib import Path
import sys,subprocess,tempfile,json
HERE=Path(__file__).resolve().parent
if len(sys.argv)>1:
 import os,time,fcntl
 import supervise_multiroot as m
 root=Path(sys.argv[2]);mode=sys.argv[1];original=m.lossless_log.Capture
 class FaultCapture(original):
  def drain(self):
   if mode=='join_timeout':time.sleep(3)
   raise OSError('injected capture reader fault')
 m.lossless_log.Capture=FaultCapture
 c=dict(wall_seconds=.2,cleanup_seconds=1,file_bytes=1048576,tree_bytes=4194304,log_bytes=1048576,raw_log_bytes=1048576,max_entries=1000,per_process_as_bytes=192*1024**2,per_process_cpu_seconds=10,rss_bytes=64*1024**2,cpu_seconds=10)
 r=m.execute([sys.executable,'-c','import time;time.sleep(5)'],root/'run',root/'lock',c,{'PATH':'/usr/bin:/bin'}, {})
 if r['status']!='FAIL_OR_INCOMPLETE' or r['cleanup_proof']['status']!='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP':raise RuntimeError('fault passed or cleanup failed')
 if mode=='join_timeout':
  if r['reader_join_barrier']['complete']:raise RuntimeError('join timeout not observed')
  fd=os.open(root/'lock',os.O_RDWR)
  try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:pass
  else:raise RuntimeError('lock released with reader alive')
  os.close(fd)
 else:
  if not r['reader_join_barrier']['complete'] or r['log_capture']['pipe_eof_observed']:raise RuntimeError('missing EOF fault not detected')
 print(json.dumps({'mode':mode,'status':r['status'],'errors':r['errors'],'cleanup':r['cleanup_proof']['status'],'reader_join_barrier':r['reader_join_barrier'],'elapsed':r['elapsed_seconds']}),flush=True)
else:
 rows=[]
 for mode in ['reader_error','join_timeout']:
  with tempfile.TemporaryDirectory(prefix='bounded_reader_fault_') as t:
   p=subprocess.run([sys.executable,str(Path(__file__).resolve()),mode,t],capture_output=True,text=True,timeout=15)
   if p.returncode:raise RuntimeError(p.stdout+p.stderr)
   row=json.loads(p.stdout);rows.append(row);print(p.stdout,end='')
 (HERE/'READER_FAULT_RESULTS.json').write_text(json.dumps(rows,indent=2)+'\n')
