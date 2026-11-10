"""Reproduce all bounded mathematical audits; propagate every process failure."""
from pathlib import Path
import os,sys,json,subprocess,time
R=Path(__file__).resolve().parent
if __name__=='__main__':
 env=dict(os.environ,OPENBLAS_NUM_THREADS='1');reports=[]
 for script in ['test_exact.py','run.py','softmax.py','rms.py','elementwise.py','silu.py']:
  t=time.monotonic();p=subprocess.run([sys.executable,'-O',str(R/script)],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=600)
  (R/(script+'.reproduce.log')).write_text(p.stdout);reports.append(dict(script=script,exit=p.returncode,seconds=time.monotonic()-t))
  (R/'REPRODUCE_RECEIPT.json').write_text(json.dumps(reports,indent=2))
  if p.returncode:raise SystemExit(p.returncode)
