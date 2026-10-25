"""Two-mode focused stdlib mocks under30CPU/45wall, no realworker/native."""
from pathlib import Path
import hashlib,json,os,resource,subprocess,sys,time
ROOT=Path(__file__).resolve().parent

def limits():
 os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});resource.setrlimit(resource.RLIMIT_CPU,(30,30));resource.setrlimit(resource.RLIMIT_AS,(1<<30,)*2);resource.setrlimit(resource.RLIMIT_CORE,(0,0))
start=time.monotonic();rows=[]
for optimized in (False,True):
 log=ROOT/'mock'/('optimized.log' if optimized else 'normal.log');before=resource.getrusage(resource.RUSAGE_CHILDREN);begin=time.monotonic()
 with log.open('xb') as f:p=subprocess.run([sys.executable,'-I','-S','-B',*(['-O'] if optimized else []),str(ROOT/'test_stability.py')],stdout=f,stderr=subprocess.STDOUT,preexec_fn=limits,timeout=45-(begin-start),env=dict(os.environ,TMPDIR=str(ROOT/'tmp'),PYTHONDONTWRITEBYTECODE='1'))
 after=resource.getrusage(resource.RUSAGE_CHILDREN);row=dict(optimized=optimized,returncode=p.returncode,cpu_seconds=after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,wall_seconds=time.monotonic()-begin,log=log.name,sha256=hashlib.sha256(log.read_bytes()).hexdigest());rows.append(row);print(json.dumps(row),flush=True)
 if p.returncode:break
result=dict(status='PASS_FOCUSED_STDLIB_ORDER_SUPERVISOR_ONLY' if len(rows)==2 and all(r['returncode']==0 for r in rows) else 'FAIL_RETAINED',runs=rows,total_cpu_seconds=sum(r['cpu_seconds'] for r in rows),wall_seconds=time.monotonic()-start,native_executed=False,actual_worker_imported=False,synthetic_fixture_only=True,real_DUT_budget_used=False)
(ROOT/'mock/RESULTS.json').write_text(json.dumps(result,indent=2)+'\n')
if not result['status'].startswith('PASS'):raise SystemExit(1)
