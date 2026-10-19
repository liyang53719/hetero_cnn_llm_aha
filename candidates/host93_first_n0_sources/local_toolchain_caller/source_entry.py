import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):raise SystemExit('require Python -I -S -B before source read')
import argparse,hashlib,json,os,resource,signal,stat,types
from pathlib import Path
ROOT=Path(__file__).absolute().parent
BOOTSTRAP='candidates/host93_first_n0_sources/local_dependency_bootstrap/bootstrap.py'
PINS={'bootstrap.py': (25509, 'c2a7ca58d8fba3df8b76071e25ad740386ab5113a59897181b39b4d303e50ea8'), 'binding_observer.py': (11781, '62a7f5b4f9250f66e5c62ed9d8b6a486642e135e5e934fc505ae2dfadc850904'), 'local_mount_profile.py': (7087, 'cdbe1030e3bf2a9b2222836f7f594b4800c4315dfb31a4438a8b76c07cd18c8f'), 'local_toolchain_adapter.py': (8776, '5b21cf3d8969873b3d751f52d64dc7e9528edc0a7d68ce3b91d88f65c8ca3896'), 'test_adapter_cold.py': (8327, 'aff6746cb62bc2bc6271b78f9e2e54ba557798d7c002b965287363d21676cac6')}
def need(ok):
    if not ok:raise ValueError('fixed same-buffer observer entry rejected')
def read(path,pin):
    size,digest=pin;need(path.is_absolute() and '..' not in path.parts)
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        for part in path.parent.parts[1:]:
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(fd);fd=child
        f=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
        try:
            before=os.fstat(f);need(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_size==size)
            data=[];count=0
            while count<=size:
                raw=os.read(f,min(65536,size+1-count))
                if not raw:break
                data.append(raw);count+=len(raw)
            raw=b''.join(data);stamp=lambda s:(s.st_dev,s.st_ino,s.st_mode,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
            need(len(raw)==size and hashlib.sha256(raw).hexdigest()==digest and stamp(before)==stamp(os.fstat(f))==stamp(os.stat(path.name,dir_fd=fd,follow_symlinks=False)))
            return raw
        finally:os.close(f)
    finally:os.close(fd)
def loaded(path,key):
    raw=read(path,PINS[key]);m=types.ModuleType('_fixed_'+key.replace('.','_'));m.__file__=str(path)
    exec(compile(raw,str(path),'exec',dont_inherit=True),m.__dict__);return m
p=argparse.ArgumentParser(allow_abbrev=False);p.add_argument('--repo',type=Path,required=True);p.add_argument('--binding-source',type=Path,required=True);a=p.parse_args()
def audit(event,args):
 if event.startswith(('subprocess.','socket.')) or event in ('os.system','os.fork','os.exec','os.posix_spawn','urllib.Request'):raise RuntimeError('native/network forbidden in source entry')
sys.addaudithook(audit)
g=loaded(a.repo/BOOTSTRAP,'bootstrap.py');o=loaded(a.binding_source/'binding_observer.py','binding_observer.py');l=loaded(a.binding_source/'local_mount_profile.py','local_mount_profile.py');adapter=loaded(ROOT/'local_toolchain_adapter.py','local_toolchain_adapter.py')
s=g.load_sources(a.repo);raw=g.checked(a.repo/adapter.CI,adapter.CI_PIN);ci=g.module(raw,a.repo/adapter.CI,'source_only_ci');support,pins,buffers=ci.load_sources(a.repo)
print(json.dumps({'status':'SOURCE_ONLY_LOCAL_CALLER_UNBOUND','ci_source':adapter.CI_PIN,'source_files':g.SOURCE_FILES,'ci_inputs':pins,'native_started':False,'network_started':False,'binding':'UNBOUND'},sort_keys=True))
