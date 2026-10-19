"""Reviewed-entry cold runner: isolated flags/limits, then exact same-buffer loads."""
import sys
if not (sys.flags.isolated and sys.flags.ignore_environment and sys.flags.no_site
        and sys.flags.no_user_site and sys.flags.dont_write_bytecode):
    raise SystemExit('cold_isolated_flags_required')
import resource
resource.setrlimit(resource.RLIMIT_AS, (512*1024*1024, 512*1024*1024))
resource.setrlimit(resource.RLIMIT_FSIZE, (4*1024*1024, 4*1024*1024))
resource.setrlimit(resource.RLIMIT_CPU, (40,40))
import signal
signal.alarm(90)
import hashlib
import os
from pathlib import Path
import stat
import types
PINS = {'icarus_stage.py': (39139, '907dd10148db6d3de4e614453fb130638d2149ee523b16b4aa97246d04c29554'), 'test_icarus_stage_cold.py': (25715, '7f95cf7eb0b7f07904a22025f29f7fe2150f70877e87ca219684d69d9ae6cdae')}
ROOT = Path(__file__).absolute().parent
FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
DIRFLAGS = FLAGS | os.O_DIRECTORY

def need(ok):
    if not ok:
        raise SystemExit('cold_source_identity_refused')

def inode(st):
    return (st.st_dev,st.st_ino,st.st_mode,st.st_nlink,st.st_size,st.st_mtime_ns,st.st_ctime_ns)

def read_verified(name, root=ROOT, pin=None):
    size,digest=PINS[name] if pin is None else pin
    fd=os.open('/',DIRFLAGS)
    try:
        for piece in root.parts[1:]:
            child=os.open(piece,DIRFLAGS,dir_fd=fd)
            os.close(fd)
            fd=child
        child=os.open(name,FLAGS,dir_fd=fd)
        try:
            before=os.fstat(child)
            need(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_size==size)
            chunks=[]; count=0
            while count<=size:
                block=os.read(child,min(65536,size+1-count))
                if not block: break
                chunks.append(block); count+=len(block)
            raw=b''.join(chunks)
            need(len(raw)==size and hashlib.sha256(raw).hexdigest()==digest)
            need(inode(os.fstat(child))==inode(before))
            need(inode(os.stat(name,dir_fd=fd,follow_symlinks=False))==inode(before))
            return raw
        finally:
            os.close(child)
    finally:
        os.close(fd)

def loaded(name, injected=None):
    raw=read_verified(name)
    module=types.ModuleType('_verified_'+name.replace('.','_'))
    module.__file__=str(ROOT/name)
    if injected: module.__dict__.update(injected)
    # Exactly these hashed bytes are compiled; there is no second path read.
    exec(compile(raw,module.__file__,'exec',dont_inherit=True),module.__dict__)
    return module

production=loaded('icarus_stage.py')
import argparse
parser=argparse.ArgumentParser(allow_abbrev=False)
parser.add_argument('--package',type=Path,required=True)
parser.add_argument('--control-tar',type=Path,required=True)
parser.add_argument('--data-tar',type=Path,required=True)
args=parser.parse_args()
def fixture(p,size,digest):
    need(p.is_absolute() and '..' not in p.parts and p.name not in ('','.','..'))
    return read_verified(p.name,p.parent,(size,digest))
fixed_package=fixture(args.package,2125764,
    'f19394cee05ad526e0eb3873bc6c17a5828f56df17fbe2db40cb66513a2d4667')
fixed_control=fixture(args.control_tar,10240,
    'aeac2541904d12b884d3b263948dc6b5e05593d712fbb9705b56403810fd631e')
fixed_data=fixture(args.data_tar,6840320,
    'd520b7e4086b27bc55b984dd3ca73f7a58bbe2f310c877ad67c3e11eadf0fe01')
tests=loaded('test_icarus_stage_cold.py', {'TARGET':production, 'TEST_ROOT':str(ROOT),
    'FIXED_PACKAGE':fixed_package,'FIXED_CONTROL_TAR':fixed_control,'FIXED_DATA_TAR':fixed_data})
count=tests.run()
print('COLD_MOCK_DECODER_PASS tests='+str(count)+' optimized='+str(sys.flags.optimize))
