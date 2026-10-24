"""One new bounded normal-import attempt; never launch task-level numerical work."""
import argparse,hashlib,importlib.util,json,os,resource,signal,subprocess,sys,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--optimized',action='store_true');a=p.parse_args()
here=Path(__file__).resolve(strict=True).parent;c=json.loads(a.config.read_text());sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
spec=importlib.util.spec_from_file_location('_source_binding_profile_gate',here/'profile_gate.py');gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
if Path(gate.__file__).resolve()!=here/'profile_gate.py':raise ValueError('gate import origin')
m=gate.validate(c,here);script=here/'check_binding.py'
if any(k.startswith('LD_') for k in os.environ):raise ValueError('loader override forbidden')
a.output.mkdir(parents=True,exist_ok=False);child=a.output/'worker';pins={p.name:sha(p) for p in here.iterdir() if p.is_file()}
def limits():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,)*2);resource.setrlimit(resource.RLIMIT_CPU,(20,20))
cmd=[sys.executable,'-I','-S','-B',*(['-O'] if a.optimized else []),str(script),'--config',str(a.config.resolve()),'--output',str(child)]
env={**os.environ,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1','PYTHONDONTWRITEBYTECODE':'1'}
start=time.monotonic()
with (a.output/'process.log').open('xb') as log:
    process=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,env=env,preexec_fn=limits,start_new_session=True)
    identity={'pid':process.pid,'parent_pid':os.getpid(),'process_group':process.pid,'stat':Path('/proc/'+str(process.pid)+'/stat').read_text()}
    (a.output/'IDENTITY.json').write_text(json.dumps(identity,indent=2)+'\n')
    try:code=process.wait(timeout=25);timeout=False
    except subprocess.TimeoutExpired:
        os.killpg(process.pid,signal.SIGKILL);code=process.wait();timeout=True
try:os.killpg(process.pid,0);clean=False
except ProcessLookupError:clean=True
report=dict(exit=code,timeout=timeout,cleanup_group_absent=clean,wall_seconds=time.monotonic()-start,mode='-I -S -B -O' if a.optimized else '-I -S -B',script_sha256=sha(script),config_sha256=sha(a.config),manifest_sha256=sha(here/'MANIFEST.json'),source_pins=pins,source_unchanged=all(sha(here/n)==h for n,h in pins.items()),log_sha256=sha(a.output/'process.log'),limits=dict(cpus=1,address_space_bytes=256*1024**2,cpu_seconds=20,wall_seconds=25))
(a.output/'RECEIPT.json').write_text(json.dumps(report,indent=2)+'\n')
if code!=0 or timeout or not clean or not report['source_unchanged']:raise SystemExit(1)
