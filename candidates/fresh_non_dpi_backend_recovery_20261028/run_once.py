#!/usr/bin/env python3
"""Fresh helper compile / simulation-backend emission, never Verilator or numerical execution."""
import argparse,fcntl,hashlib,json,os,resource,shutil,signal,subprocess,time
from pathlib import Path
D=Path(__file__).resolve().parent
P=argparse.ArgumentParser();P.add_argument('stage',choices=['compile','fma','host']);P.add_argument('--execute-approved-once',action='store_true');a=P.parse_args()
if not a.execute_approved_once:raise SystemExit('PREPARED_NOT_EXECUTED: independent parent review required')
def need(ok,msg):
 if not ok:raise RuntimeError(msg)
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
pins=json.loads((D/'INPUT_PINS.json').read_text())
def verify():
 for x in pins['files']:
  p=Path(x['path']);need(str(p.resolve())==x['resolved'],'resolved path drift '+str(p));need((os.readlink(p) if p.is_symlink() else None)==x['symlink'],'symlink drift '+str(p));need(p.stat().st_size==x['bytes'] and digest(p)==x['sha256'],'bytes drift '+str(p))
 actual=sorted(str(p) for p in Path(pins['baseline_classes']).rglob('*.class'))
 expected=sorted(x['path'] for x in pins['files'] if x['path'].startswith(pins['baseline_classes']+'/') and x['path'].endswith('.class'))
 need(actual==expected and len(actual)==901,'baseline full class inventory drift')
verify()
need(shutil.disk_usage(D).free>=3<<30,'requires 3 GiB disk free')
mem={x.split(':',1)[0]:x.split(':',1)[1] for x in Path('/proc/meminfo').read_text().splitlines()};need(int(mem['MemAvailable'].split()[0])*1024>=6<<30,'requires 6 GiB MemAvailable')
lock=(D/'gate.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
out=D/('actual-'+a.stage);out.mkdir(exist_ok=False);home=out/'home';home.mkdir()
if a.stage=='compile':
 classes=out/'classes';shutil.copytree(pins['baseline_classes'],classes);cp=str(classes)+':'+':'.join(pins['jars'])
 cmd=[pins['java'],'-Xmx2g','-Xss4m','-XX:ActiveProcessorCount=1','-XX:ReservedCodeCacheSize=128m','-cp',cp,'scala.tools.nsc.Main','-classpath',cp,'-Xplugin:'+pins['plugin'],'-language:reflectiveCalls','-d',str(classes),*pins['sources']]
 cpu,wall,rss_cap,as_cap,file_cap,tree_cap=150,180,3<<30,6<<30,64<<20,128<<20
else:
 r=json.loads((D/'actual-compile/RESULT.json').read_text());need(r['status']=='PASS_FRESH_HELPER_TYPECHECK_ONLY','fresh compile required')
 classes=D/'actual-compile/classes';rows=json.loads((D/'actual-compile/CLASS_PINS.json').read_text())
 need(sorted(str(p.relative_to(classes)) for p in classes.rglob('*.class'))==sorted(x['path'] for x in rows),'class inventory drift')
 for x in rows:need(digest(classes/x['path'])==x['sha256'],'compiled class drift '+x['path'])
 cp=str(classes)+':'+':'.join(pins['jars'])
 if a.stage=='fma':
  cmd=[pins['java'],'-Xmx1g','-Xss4m','-XX:ActiveProcessorCount=1','-XX:ReservedCodeCacheSize=128m','-cp',cp,'chiseltest.simulator.EmitPhysicalFmaStageLibrary',str(out/'fma-library')]
  cpu,wall,rss_cap,as_cap,file_cap,tree_cap=120,150,2<<30,4<<30,16<<20,64<<20
 else:
  cmd=[pins['java'],'-Xmx4g','-Xss8m','-XX:ActiveProcessorCount=1','-XX:ReservedCodeCacheSize=128m','-cp',cp,'chiseltest.simulator.FreshHostHighSimulationEmitter']
  cpu,wall,rss_cap,as_cap,file_cap,tree_cap=600,660,5<<30,10<<30,384<<20,1<<30

def child():
 os.setsid();os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});resource.setrlimit(resource.RLIMIT_CPU,(cpu,cpu+5));resource.setrlimit(resource.RLIMIT_AS,(as_cap,as_cap));resource.setrlimit(resource.RLIMIT_FSIZE,(file_cap,file_cap));resource.setrlimit(resource.RLIMIT_CORE,(0,0))
interrupted=[];signal.signal(signal.SIGTERM,lambda s,f:interrupted.append(s));signal.signal(signal.SIGINT,lambda s,f:interrupted.append(s))
log=out/'run.log';start=time.monotonic();peak=0;reason=None
with log.open('xb') as f:
 p=subprocess.Popen(cmd,stdout=f,stderr=subprocess.STDOUT,cwd=out,preexec_fn=child,env={'PATH':'/usr/bin:/bin','HOME':str(home),'LANG':'C.UTF-8'})
 try:
  while p.poll() is None:
   try:rss=int(next(x.split()[1] for x in Path(f'/proc/{p.pid}/status').read_text().splitlines() if x.startswith('VmRSS:')))*1024;peak=max(peak,rss)
   except (OSError,StopIteration):rss=0
   total=sum(q.stat().st_size for q in out.rglob('*') if q.is_file())
   if interrupted:reason='external signal '+str(interrupted[-1])
   elif time.monotonic()-start>wall:reason='wall cap'
   elif rss>rss_cap:reason='sampled JVM RSS cap'
   elif total>tree_cap:reason='sampled tree cap'
   elif log.stat().st_size>4<<20:reason='sampled log cap'
   if reason:break
   time.sleep(.2)
 finally:
  try:os.killpg(p.pid,signal.SIGTERM)
  except ProcessLookupError:pass
  try:p.wait(timeout=5)
  except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=5)
  try:os.killpg(p.pid,signal.SIGKILL)
  except ProcessLookupError:pass
if p.returncode!=0:reason=reason or 'native exit '+str(p.returncode)+'; see primary run.log'
secondary=[]
try:
 verify();need(sum(q.stat().st_size for q in out.rglob('*') if q.is_file())<=tree_cap,'post-exit tree cap');need(log.stat().st_size<=4<<20,'post-exit log cap');need(all(q.stat().st_size<=file_cap for q in out.rglob('*') if q.is_file()),'post-exit single-file cap')
 if a.stage=='compile' and p.returncode==0:
  for q in Path(pins['baseline_classes']).rglob('*.class'):need(digest(classes/q.relative_to(pins['baseline_classes']))==digest(q),'baseline class overwritten '+str(q))
  for n in ['chiseltest/simulator/FreshHostHighSimulationEmitter$.class','heteronpu/continuous/model/FreshHostDenseAccMemoryLowering$.class','heteronpu/continuous/model/FreshHostMatrixResultFifoMemoryLowering$.class']:need((classes/n).is_file(),'missing helper '+n)
  rows=[dict(path=str(q.relative_to(classes)),bytes=q.stat().st_size,sha256=digest(q)) for q in sorted(classes.rglob('*.class'))];(out/'CLASS_PINS.json').write_text(json.dumps(rows,indent=2)+'\n')
 if a.stage=='fma' and p.returncode==0:
  for n in ['PhysicalFmaStageLibrary.sv','SCOPE.txt']:need((out/'fma-library'/n).is_file(),'missing FMA artifact '+n)
 if a.stage=='host' and p.returncode==0:
  for n in ['HostBlockTopV4.sv','actual_top_ports.tsv','official-emission-ast.fir','EMITTER_SCOPE.txt','canonical-low-identity.json']:need((out/'compiled-host'/n).is_file(),'missing Host artifact '+n)
except Exception as e:secondary.append(str(e));reason=reason or str(e)
statuses={'compile':'PASS_FRESH_HELPER_TYPECHECK_ONLY','fma':'PASS_ORIGINAL_FOUR_STAGE_FMA_LIBRARY_EMISSION_ONLY','host':'PASS_FRESH_HOST_SIMULATION_BACKEND_EMISSION_ONLY'}
status=statuses[a.stage] if not reason else 'FAIL_'+a.stage.upper()
r=dict(status=status,returncode=p.returncode,reason=reason,secondary_diagnostics=secondary,elapsed_seconds=time.monotonic()-start,peak_jvm_rss_bytes=peak,command=cmd,scope='No numerical simulation or frozen final RTL acceptance; single JVM sampled supervision, not escaped-descendant hard containment')
(out/'RESULT.json').write_text(json.dumps(r,indent=2)+'\n')
arts=[dict(path=str(q.relative_to(out)),bytes=q.stat().st_size,sha256=digest(q)) for q in sorted(out.rglob('*')) if q.is_file() and q.name!='ARTIFACT_PINS.json'];(out/'ARTIFACT_PINS.json').write_text(json.dumps(arts,indent=2)+'\n')
print(json.dumps({k:v for k,v in r.items() if k!='command'},indent=2));raise SystemExit(0 if not reason else 1)
