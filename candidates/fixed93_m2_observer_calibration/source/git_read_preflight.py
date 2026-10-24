"""Real pinned Git-profile verify under actual read policy, no Git/native/DUT.

Only guard initialization is a source-bound fixture: it supplies exact current
runtime and provenance allowed files without constructing any model/ctypes.
The original verify body and actual installed CalibrationIO.audit are executed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import sys
import time
import types

HERE=Path(__file__).resolve().parent


def need(ok,msg):
    if not ok: raise ValueError(msg)


def main():
    p=argparse.ArgumentParser();p.add_argument('--base',required=True);p.add_argument('--manifest-sha',required=True)
    args=p.parse_args();start=time.monotonic();cpu=time.process_time()
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    resource.setrlimit(resource.RLIMIT_AS,(256<<20,)*2);resource.setrlimit(resource.RLIMIT_CPU,(15,)*2)
    def expired(*_):raise TimeoutError('Git read preflight 15s')
    signal.signal(signal.SIGALRM,expired);signal.setitimer(signal.ITIMER_REAL,15)
    attempts=[]
    def no_execution(event,args):
        if event.startswith(('ctypes.','socket.','subprocess.')) or event in ('os.system','os.fork','os.posix_spawn','os.exec','os.spawn'):
            attempts.append(event);raise RuntimeError('read preflight denied '+event)
        if event=='import' and args[0].split('.')[0] in ('ctypes','numpy','torch','yaml','candidates','integration','observation'):
            attempts.append(event+':'+args[0]);raise RuntimeError('DUT/runtime import denied')
    sys.addaudithook(no_execution)
    raw=(HERE/'SOURCE_MANIFEST.json').read_bytes();need(hashlib.sha256(raw).hexdigest()==args.manifest_sha,'new source pin')
    own=json.loads(raw);raw=(HERE/'m2_authority.py').read_bytes();pin=own['files']['m2_authority.py']
    need(pin==dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()),'authority bytes')
    a=types.ModuleType('m2_authority');a.__file__=str(HERE/'m2_authority.py');sys.modules[a.__name__]=a
    exec(compile(raw,a.__file__,'exec',dont_inherit=True),vars(a))
    io=a.load_source(HERE/'m2_io.py','_m2_read_policy',own['files']['m2_io.py'])
    base=Path(args.base);need(str(base)==own['base']['path'],'exact baseline')
    manifest=a.parse(a.checked(base/'SOURCE_MANIFEST.json',own['base']['manifest']))
    runtime=a.parse(a.checked(base/'RUNTIME_PINS.json',manifest['preparation_files']['RUNTIME_PINS.json']))
    specs=io.git_profile_read_specs(runtime,manifest,base)
    profile=Path(runtime['git_profile_root'])/'git_profile.py'
    lineage=profile.with_name('LINEAGE.json')
    missing=set(specs)-set(runtime['files']);need(len(missing)==1,'one source witness addition')
    mirror=next(iter(missing));need(specs[mirror]['bytes']==23995,'fixed mirror extent')
    g=object.__new__(io.CalibrationIO)
    g.out=HERE/'__NO_PREFLIGHT_OUTPUT__';need(not g.out.exists(),'no output namespace')
    g.allowed=dict(runtime['files']);g.allowed_proc=set();g.reads=set()
    negatives=[]
    def rejects(name,call):
        try:call()
        except ValueError:negatives.append(name);return
        raise AssertionError('expected reject '+name)
    rejects('old runtime-only allowlist rejects missing mirror',lambda:g.audit('open',(mirror,'r',0)))
    g.allowed.update(specs)
    rejects('mirror is never writable',lambda:g.audit('open',(mirror,'w',os.O_WRONLY)))
    rejects('neighbor is not a permitted directory',lambda:g.audit('open',(mirror+'.unlisted','r',0)))
    rejects('relative mirror spelling rejected',lambda:g.audit('open',('qwen2_block.cpp','r',0)))
    # Exact canonical runtime source pins before the hook. Original verify then
    # actually rechecks every one of the fifteen spec payloads with this policy.
    sys.addaudithook(g.audit)
    module=a.load_source(profile,'_m2_exact_git_read_profile',runtime['files'][str(profile)])
    value=module.verify()
    expected={str(profile),str(lineage),*specs}
    need(g.reads==expected and len(expected)==17,'complete original verify read closure')
    need(value['mirror_cpp']['path']==mirror and not attempts,'read-only profile result')
    result=dict(status='PASS_REAL_GIT_VERIFY_READ_CLOSURE_ONLY',source_manifest_sha256=args.manifest_sha,
        native_executed=False,DUT_executed=False,git_process_executed=False,model_executed=False,
        guard_constructor_scope='Explicit exact allowlist fixture; real audit callback and original verify body executed',
        unique_read_paths=len(expected),spec_count=len(specs),spec_bytes=sum(x['bytes'] for x in specs.values()),
        routes=sorted(g.reads),negative_controls=negatives,denied_execution_attempts=attempts,
        wall_seconds=time.monotonic()-start,cpu_seconds=time.process_time()-cpu,
        peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    print(json.dumps(result,sort_keys=True));signal.setitimer(signal.ITIMER_REAL,0)
    return 0


if __name__=='__main__':raise SystemExit(main())
