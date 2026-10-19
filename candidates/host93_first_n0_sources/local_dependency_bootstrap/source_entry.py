import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('require Python -I -S -B before source read')
import hashlib,os,stat,types
from pathlib import Path
ROOT=Path(__file__).absolute().parent
PINS={'bootstrap.py': (25509, 'c2a7ca58d8fba3df8b76071e25ad740386ab5113a59897181b39b4d303e50ea8')}
def need(ok):
    if not ok:raise ValueError('same-buffer entry identity rejected')
def read(name):
    size,digest=PINS[name]
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        for part in ROOT.parts[1:]:
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(fd);fd=child
        f=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
        try:
            before=os.fstat(f);need(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_size==size)
            chunks=[];count=0
            while count<=size:
                block=os.read(f,min(65536,size+1-count))
                if not block:break
                chunks.append(block);count+=len(block)
            raw=b''.join(chunks);stamp=lambda s:(s.st_dev,s.st_ino,s.st_mode,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
            need(len(raw)==size and hashlib.sha256(raw).hexdigest()==digest)
            need(stamp(before)==stamp(os.fstat(f))==stamp(os.stat(name,dir_fd=fd,follow_symlinks=False)))
            return raw
        finally:os.close(f)
    finally:os.close(fd)
def loaded(name,injected=None):
    raw=read(name);m=types.ModuleType('_pinned_'+name.replace('.','_'));m.__file__=str(ROOT/name)
    if injected:m.__dict__.update(injected)
    exec(compile(raw,m.__file__,'exec',dont_inherit=True),m.__dict__)
    return m
import argparse,json
parser=argparse.ArgumentParser(allow_abbrev=False)
parser.add_argument('--repo',type=Path,required=True)
a=parser.parse_args()
g=loaded('bootstrap.py')
print(json.dumps(g.source_check(a.repo),sort_keys=True))
