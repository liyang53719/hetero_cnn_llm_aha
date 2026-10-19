import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):raise SystemExit('require Python -I -S -B before source read')
import argparse,hashlib,json,os,resource,signal,stat,types
from pathlib import Path
ROOT=Path(__file__).absolute().parent
BOOTSTRAP='candidates/host93_first_n0_sources/local_dependency_bootstrap/bootstrap.py'
PINS={'qualification_entry.py': (10554, 'c6eaf2122c5be243c96e72ad9184af17d25178bc8d3a0c7d770eb083b9ae1b98'), 'preset_package_stage.py': (4415, '364647f02226c68a9ba5bbb23b907b19554a72c811af982fd136cebca6c066cf')}
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
p=argparse.ArgumentParser(add_help=False,allow_abbrev=False);p.add_argument('--source-check',action='store_true');known,rest=p.parse_known_args()
raw=read(ROOT/'qualification_entry.py',PINS['qualification_entry.py']);read(ROOT/'preset_package_stage.py',PINS['preset_package_stage.py'])
if known.source_check:
 print(json.dumps({'status':'SOURCE_ONLY_QUALIFICATION_ENTRY','pins':PINS,'native_started':False,'network_started':False},sort_keys=True))
else:
 sys.argv=[str(ROOT/'qualification_entry.py')]+rest
 ns={'__name__':'__main__','__file__':str(ROOT/'qualification_entry.py'),'ENTRY_BYTES':raw,'PRIOR_PINS':{}}
 exec(compile(raw,ns['__file__'],'exec',dont_inherit=True),ns)
