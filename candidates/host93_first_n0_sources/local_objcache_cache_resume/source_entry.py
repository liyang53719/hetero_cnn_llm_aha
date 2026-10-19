"""Pinned cold entry. --source-check only reads/parses fixed SOURCE files."""
import sys
if not(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):raise SystemExit('require -I -S -B before source read')
import argparse,hashlib,json,math,os,resource,signal,stat,time,types
from pathlib import Path
ROOT=Path(__file__).absolute().parent
LOCAL_PINS={'accepted_toolchain.py': {'bytes': 4312, 'sha256': '8719c513afec5bf48565bdb1dc27e70bdf150560828de7fc08936bc33c550dcd'}, 'cached_flex_header.py': {'bytes': 3269, 'sha256': 'afaf98d6137562790b0664293acf465859288549e30d87f197879cb334979403'}, 'continuation_entry.py': {'bytes': 17732, 'sha256': 'b0f344600b9ab86d5fa53ac4b3fec1e33db416438f49014786a53a490deeca14'}, 'resume_toolchain.py': {'bytes': 8626, 'sha256': 'e0e0c10015ed96f36bbf63c1bff7454c59a63468aa243b84a0024bedd03a0d7a'}}
DEPENDENCY_PINS={'candidates/host93_first_n0_sources/local_dependency_bootstrap/bootstrap.py': {'bytes': 25509, 'sha256': 'c2a7ca58d8fba3df8b76071e25ad740386ab5113a59897181b39b4d303e50ea8'}, 'candidates/host93_first_n0_sources/local_binding_observer/binding_observer.py': {'bytes': 11781, 'sha256': '62a7f5b4f9250f66e5c62ed9d8b6a486642e135e5e934fc505ae2dfadc850904'}, 'candidates/host93_first_n0_sources/local_binding_observer/local_mount_profile.py': {'bytes': 7087, 'sha256': 'cdbe1030e3bf2a9b2222836f7f594b4800c4315dfb31a4438a8b76c07cd18c8f'}, 'candidates/host93_first_n0_sources/local_toolchain_caller/local_toolchain_adapter.py': {'bytes': 8776, 'sha256': '5b21cf3d8969873b3d751f52d64dc7e9528edc0a7d68ce3b91d88f65c8ca3896'}, 'candidates/host93_ci_recovery/run.py': {'bytes': 77532, 'sha256': 'bb9775cc22b305e392c67934aa7b081319f7dd7350da50098fe10b647c68982d'}, 'candidates/host93_ci_recovery/ci_support_v3.py': {'bytes': 16348, 'sha256': '653de8cdfbdbb5ffe9b3725467ee0f44c98da353e1d680fec4f282d2b73d00d1'}, 'candidates/host93_ci_recovery/SUPPORT_PINS.json': {'bytes': 806, 'sha256': 'c2fd4d03c0dc30226a22992e5cd4d347659409d7625505404bd9b714a20105d2'}, 'candidates/host93_ci_recovery/RUN_PINS.json': {'bytes': 14979, 'sha256': '0f37b29343210e20febba4fb364291e1a0e8b1938395f8719dde43839b3f90af'}}
CONSUMER_PINS={'consumer.py': {'bytes': 10384, 'sha256': '9c484ba21665fc0f0a92845d579e8566d3e538f776bcb9bc027e8904a5258129'}, 'pipeline_historical.py': {'bytes': 31296, 'sha256': 'c3885d039b97861b17a29d74e6bf58448873d1ae476dbffa806a22a199b581cd'}}
def need(ok,message='same-buffer continuation entry rejected'):
    if not ok:raise ValueError(message)
def read(path,pin):
    need(type(pin) is dict and set(pin)=={'bytes','sha256'} and type(pin['bytes']) is int and 0<=pin['bytes']<=4*1024**2,'finite source pin')
    size,digest=pin['bytes'],pin['sha256'];path=Path(path)
    need(path.is_absolute() and '..' not in path.parts,'absolute fixed source path')
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        for part in path.parent.parts[1:]:
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(fd);fd=child
        f=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
        try:
            before=os.fstat(f);need(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_size==size,'regular single-link exact source size')
            parts=[];count=0
            while count<=size:
                raw=os.read(f,min(65536,size+1-count))
                if not raw:break
                parts.append(raw);count+=len(raw)
            raw=b''.join(parts);stamp=lambda s:(s.st_dev,s.st_ino,s.st_mode,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
            need(len(raw)==size and hashlib.sha256(raw).hexdigest()==digest and stamp(before)==stamp(os.fstat(f))==stamp(os.stat(path.name,dir_fd=fd,follow_symlinks=False)),'same-buffer stable source hash')
            return raw
        finally:os.close(f)
    finally:os.close(fd)
def module(path,raw,label):
    m=types.ModuleType('_local_continuation_'+label);m.__file__=str(path);sys.modules[m.__name__]=m
    exec(compile(raw,str(path),'exec',dont_inherit=True),m.__dict__);return m

def main(argv=None):
    parser=argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--source-check',action='store_true');parser.add_argument('--execute-fixed-continuation',action='store_true')
    parser.add_argument('--repo',type=Path,required=True);parser.add_argument('--consumer-source',type=Path,required=True)
    parser.add_argument('--binding',type=Path);parser.add_argument('--binding-bytes',type=int);parser.add_argument('--binding-sha')
    parser.add_argument('--started',type=float);parser.add_argument('--deadline',type=float)
    args=parser.parse_args(argv)
    need(bool(LOCAL_PINS) and bool(DEPENDENCY_PINS) and bool(CONSUMER_PINS),'frozen source pins required')
    need(args.source_check != args.execute_fixed_continuation,'one explicit entry mode')
    if args.execute_fixed_continuation:
        need(type(args.started) is float and type(args.deadline) is float and math.isfinite(args.started) and math.isfinite(args.deadline) and abs(args.deadline-args.started-6600)<0.000001 and args.started<=time.monotonic()<args.deadline-3720,'original total deadline before initial hash')
        need(args.binding is not None and type(args.binding_bytes) is int and type(args.binding_sha) is str,'explicit private binding pin')
        def expired(*unused):raise TimeoutError('continuation source/preflight deadline exhausted')
        signal.signal(signal.SIGALRM,expired);signal.signal(signal.SIGTERM,expired)
        signal.setitimer(signal.ITIMER_REAL,max(0.001,args.deadline-3720-time.monotonic()))
        resource.setrlimit(resource.RLIMIT_AS,(1024**3,8*1024**3));resource.setrlimit(resource.RLIMIT_CPU,(120,6600));resource.setrlimit(resource.RLIMIT_FSIZE,(128*1024**2,1024**3))
        allowed=os.sched_getaffinity(0);need(bool(allowed));os.sched_setaffinity(0,{min(allowed)})
    local={n:read(ROOT/n,p) for n,p in LOCAL_PINS.items()}
    deps={n:read(args.repo/n,p) for n,p in DEPENDENCY_PINS.items()}
    consumer={n:read(args.consumer_source/n,p) for n,p in CONSUMER_PINS.items()}
    if args.source_check:
        print(json.dumps({'status':'SOURCE_ONLY_LOCAL_CONTINUATION','local':LOCAL_PINS,'dependencies':DEPENDENCY_PINS,'consumer':CONSUMER_PINS,'native_started':False},sort_keys=True));return 0
    def decode(raw):
        def pairs(values):
            result={}
            for k,v in values:need(k not in result,'duplicate binding key');result[k]=v
            return result
        return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('nonfinite binding JSON')))
    binding_pin={'bytes':args.binding_bytes,'sha256':args.binding_sha};binding_raw=read(args.binding,binding_pin);cfg=decode(binding_raw)
    need(cfg['repo']==str(args.repo),'explicit repository binding')
    mods={}
    for key,name in (('bootstrap','local_dependency_bootstrap/bootstrap.py'),('observer','local_binding_observer/binding_observer.py'),('profile','local_binding_observer/local_mount_profile.py'),('adapter','local_toolchain_caller/local_toolchain_adapter.py')):
        relative='candidates/host93_first_n0_sources/'+name;mods[key]=module(args.repo/relative,deps[relative],key)
    for key,name in (('coordinator','run.py'),('supervisor','ci_support_v3.py')):
        relative='candidates/host93_ci_recovery/'+name;mods[key]=module(args.repo/relative,deps[relative],key)
    for key,name in (('accepted','accepted_toolchain.py'),('header','cached_flex_header.py'),('resume','resume_toolchain.py')):mods[key]=module(ROOT/name,local[name],key)
    mods['header_raw']=local['cached_flex_header.py'];mods['consumer']=module(args.consumer_source/'consumer.py',consumer['consumer.py'],'consumer')
    entry=module(ROOT/'continuation_entry.py',local['continuation_entry.py'],'entry')
    def source_check():
        need(read(args.binding,binding_pin)==binding_raw,'private invocation binding drift')
        for n,p in LOCAL_PINS.items():need(read(ROOT/n,p)==local[n],'local source drift')
        for n,p in DEPENDENCY_PINS.items():need(read(args.repo/n,p)==deps[n],'dependency source drift')
        for n,p in CONSUMER_PINS.items():need(read(args.consumer_source/n,p)==consumer[n],'consumer source drift')
    result=entry.run(cfg,args.started,args.deadline,mods,source_check)
    print(json.dumps({'status':result['status'],'native_phases':len(result['stages']),'full_block_pass':False},sort_keys=True))
    return 0 if result['status']=='PASS_FIRST_N0_LIMITED_TOLERANCE_ONLY' else 1
if __name__=='__main__':raise SystemExit(main())
