import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):raise SystemExit('require Python -I -S -B before source read')
import argparse,hashlib,json,os,resource,signal,stat,types
from pathlib import Path
ROOT=Path(__file__).absolute().parent
BOOTSTRAP='candidates/host93_first_n0_sources/local_dependency_bootstrap/bootstrap.py'
PINS={'bootstrap.py': (25509, 'c2a7ca58d8fba3df8b76071e25ad740386ab5113a59897181b39b4d303e50ea8'), 'binding_observer.py': (11781, '62a7f5b4f9250f66e5c62ed9d8b6a486642e135e5e934fc505ae2dfadc850904'), 'local_mount_profile.py': (7087, 'cdbe1030e3bf2a9b2222836f7f594b4800c4315dfb31a4438a8b76c07cd18c8f'), 'local_toolchain_adapter.py': (8776, '5b21cf3d8969873b3d751f52d64dc7e9528edc0a7d68ce3b91d88f65c8ca3896'), 'preset_package_stage.py': (4415, '364647f02226c68a9ba5bbb23b907b19554a72c811af982fd136cebca6c066cf'), 'test_preset_cold.py': (3675, '12edb4a5e335023d796388306bbc6aec43841da0717853ec1e87fabf8943bc2b')}
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
p=argparse.ArgumentParser(allow_abbrev=False);p.add_argument('--repo',type=Path,required=True);p.add_argument('--caller-source',type=Path,required=True);args=p.parse_args()
def audit(event,args):
 if event.startswith(('subprocess.','socket.')) or event in ('os.system','os.fork','os.exec','os.posix_spawn','urllib.Request'):raise RuntimeError('network/native forbidden')
sys.addaudithook(audit);resource.setrlimit(resource.RLIMIT_AS,(512*1024**2,512*1024**2));resource.setrlimit(resource.RLIMIT_CPU,(40,40));signal.alarm(60)
g=loaded(args.repo/BOOTSTRAP,'bootstrap.py');a=loaded(args.caller_source/'local_toolchain_adapter.py','local_toolchain_adapter.py');p=loaded(ROOT/'preset_package_stage.py','preset_package_stage.py')
raw=read(ROOT/'test_preset_cold.py',PINS['test_preset_cold.py']);ns={'__name__':'_cold','__file__':str(ROOT/'test_preset_cold.py'),'g':g,'a':a,'p':p,'REPO':args.repo,'TEST_ROOT':str(ROOT)}
exec(compile(raw,ns['__file__'],'exec',dont_inherit=True),ns)
