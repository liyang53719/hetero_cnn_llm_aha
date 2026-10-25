from pathlib import Path
import subprocess,sys,resource,os,time,json,hashlib
D=Path(__file__).resolve().parent;out=D/sys.argv[1];out.mkdir(exist_ok=False)
def limits():
 os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,)*2);resource.setrlimit(resource.RLIMIT_CPU,(30,)*2)
rows=[]
for name,flags in [('isolated',['-I','-S','-B']),('optimized',['-I','-S','-O','-B'])]:
 cmd=[sys.executable,*flags,str(D/'test_selective.py')];start=time.monotonic()
 with (out/(name+'.log')).open('xb') as f:
  try:r=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,timeout=45,preexec_fn=limits,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'});code=r.returncode
  except subprocess.TimeoutExpired:code='timeout'
 rows.append(dict(command=cmd,exit=code,wall=time.monotonic()-start,sha256=hashlib.sha256((out/(name+'.log')).read_bytes()).hexdigest()))
 if code!=0:break
(out/'RESULTS.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps(rows));raise SystemExit(any(r['exit']!=0 for r in rows))
