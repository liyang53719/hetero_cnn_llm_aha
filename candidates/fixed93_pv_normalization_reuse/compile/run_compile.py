"""Optional bounded single-file scalac reproduction. No download or emitter.

Supply the existing matching dependency jars/classes explicitly. Pinned input
hashes are mandatory, and output must be a new/empty directory. This portable
wrapper was syntax-reviewed but not executed; RESULT.json records the actual
previous bounded compile of the identical candidate source and input hashes.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import time

parser=argparse.ArgumentParser(description=__doc__)
for arg in ('java','jars-root','classes-root','candidate-source','work-dir'):
    parser.add_argument('--'+arg,type=Path,required=True)
args=parser.parse_args()
pins=json.loads(Path(__file__).with_name('INPUT_PINS.json').read_text())
def verify(path,pin):
    blob=path.read_bytes()
    if hashlib.sha256(blob).hexdigest()!=pin['sha256'] or len(blob)!=pin['bytes']:
        raise SystemExit('Compiler input pin mismatch: '+str(path))
java,jarsroot,classes,source,work=(p.resolve() for p in (args.java,args.jars_root,args.classes_root,args.candidate_source,args.work_dir))
verify(java,pins['java_launcher'])
jars=[]
for rel,pin in pins['jars'].items():
    path=jarsroot/rel;verify(path,pin);jars.append(path)
if {str(p.relative_to(classes)) for p in classes.rglob('*.class')}!=set(pins['classes']):
    raise SystemExit('Class dependency file set mismatch')
for rel,pin in pins['classes'].items():verify(classes/rel,pin)
if hashlib.sha256(source.read_bytes()).hexdigest()!=pins['candidate_source_sha256']:
    raise SystemExit('Candidate source pin mismatch')
if work.exists() and any(work.iterdir()):raise SystemExit('Work directory must be new or empty')
work.mkdir(parents=True,exist_ok=True)
for name in ('classes','home','tmp'):(work/name).mkdir()
cp=':'.join(map(str,jars));plugin=next(p for p in jars if p.name=='chisel-plugin_2.13.16-6.7.0.jar')
argv=[str(java),'-Xmx768m','-XX:ActiveProcessorCount=1','-XX:MaxMetaspaceSize=256m','-XX:ReservedCodeCacheSize=128m',
      '-cp',cp,'scala.tools.nsc.Main','-classpath',cp+':'+str(classes),'-Xplugin:'+str(plugin),
      '-language:reflectiveCalls','-d',str(work/'classes'),str(source)]
env={'PATH':'/usr/bin:/bin','HOME':str(work/'home'),'TMPDIR':str(work/'tmp'),'LANG':'C.UTF-8','LC_ALL':'C.UTF-8','TZ':'UTC'}
def limits():
    os.setsid();os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    resource.setrlimit(resource.RLIMIT_CPU,(90,91));resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,4*1024**3))
    resource.setrlimit(resource.RLIMIT_FSIZE,(16*1024**2,16*1024**2))
start=time.monotonic();timed_out=False
with (work/'compile.log').open('wb') as log:
    proc=subprocess.Popen(argv,cwd=work,env=env,stdout=log,stderr=subprocess.STDOUT,preexec_fn=limits)
    try:rc=proc.wait(timeout=120)
    except subprocess.TimeoutExpired:
        timed_out=True;os.killpg(proc.pid,signal.SIGKILL);rc=proc.wait()
usage=resource.getrusage(resource.RUSAGE_CHILDREN)
outputs={str(p.relative_to(work)):{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in (work/'classes').rglob('*.class')}
result={'status':'PASS_INCREMENTAL_SCALAC_ONLY' if rc==0 and outputs else 'FAIL_INCREMENTAL_SCALAC_ONLY',
        'exit_code':rc,'timed_out':timed_out,'wall_seconds':time.monotonic()-start,'cpu_seconds':usage.ru_utime+usage.ru_stime,
        'maxrss_kib':usage.ru_maxrss,'outputs':outputs,'compiled_source_files':1,'RTL_generated':False,
        'CHIRRTL_generated':False,'elaborated':False,'simulated':False,'physical_sram_ports_verified':False}
(work/'result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='outputs'},indent=2))
raise SystemExit(rc)
