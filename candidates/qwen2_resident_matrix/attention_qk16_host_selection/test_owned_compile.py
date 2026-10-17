import argparse,os,signal,sys,tempfile,threading
from pathlib import Path
import owned_compile as o
p=argparse.ArgumentParser();p.add_argument('--cleanup-helper',required=True,type=Path);a=p.parse_args()
with tempfile.TemporaryDirectory() as d:
 with open(Path(d)/'log','wb') as log:
  for mode,code in [('zero','pass'),('nonzero','raise SystemExit(7)'),('term','import time;time.sleep(10)')]:
   timer=None
   if mode=='term':timer=threading.Timer(.2,lambda:os.kill(os.getpid(),signal.SIGTERM));timer.start()
   try:r=o.execute([sys.executable,'-I','-B','-c',code],cwd=d,log=log,cleanup_helper=a.cleanup_helper,work_seconds=2,cleanup_seconds=2)
   finally:
    if timer:timer.cancel();timer.join()
   assert r['cleanup_complete']
   assert r['exit_code']==(0 if mode=='zero' else 7 if mode=='nonzero' else None)
   assert r['error']==('InterruptedError' if mode=='term' else None)
   print(mode,'PASS',r['cleanup_scope'])
