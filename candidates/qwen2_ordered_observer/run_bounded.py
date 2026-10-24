"""Four bounded software-only test processes; no source/native/RTL generation."""
import argparse,hashlib,json,os,resource,subprocess,sys,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--source-root',required=True,type=Path);p.add_argument('--owner-root',required=True,type=Path);p.add_argument('--buffer-source',required=True,type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
here=Path(__file__).resolve(strict=True).parent;a.output.mkdir(parents=True,exist_ok=False)
hashfile=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
pins={p.name:hashfile(p) for p in sorted(here.iterdir()) if p.is_file()}
def limits():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,256*1024**2));resource.setrlimit(resource.RLIMIT_CPU,(20,20))
results=[]
for name,flags in [('normal',[]),('optimized',['-O']),('isolated',['-I']),('isolated_optimized',['-I','-O'])]:
    cmd=[sys.executable,'-B',*flags,str(here/'test_observer.py'),'--source-root',str(a.source_root.resolve()),'--owner-root',str(a.owner_root.resolve()),'--buffer-source',str(a.buffer_source.resolve()),'-v']
    start=time.monotonic()
    with (a.output/(name+'.log')).open('wb') as log:
        try:r=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,timeout=25,preexec_fn=limits,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'});code=r.returncode
        except subprocess.TimeoutExpired:code='timeout'
    results.append(dict(mode=name,exit=code,wall_seconds=time.monotonic()-start,log_sha256=hashfile(a.output/(name+'.log'))))
    if code!=0:break
report=dict(scope='26 software-only observer tests per mode; synthetic arithmetic endpoints; not native/RTL',source_pins=pins,limits=dict(cpus=1,address_space_bytes=256*1024**2,cpu_seconds=20,wall_seconds=25),runs=results,source_unchanged=all(hashfile(here/name)==sha for name,sha in pins.items()))
(a.output/'RESULTS.json').write_text(json.dumps(report,indent=2)+'\n')
if len(results)!=4 or any(r['exit']!=0 for r in results) or not report['source_unchanged']:raise SystemExit(1)
