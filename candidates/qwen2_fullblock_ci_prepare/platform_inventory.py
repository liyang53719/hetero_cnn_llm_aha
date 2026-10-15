"""Cold platform inventory only. Never admits a numerical run or loads native code."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys

NAMES=('python','torch_C','numpy_multiarray','libc10.so','libtorch_cpu.so','libtorch_python.so')

def identity(path):
    path=Path(path).resolve(strict=True)
    if not path.is_file(): raise ValueError('regular file required')
    h=hashlib.sha256()
    with path.open('rb') as f:
        before=path.stat()
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
        after=path.stat()
    if (before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns):
        raise ValueError('identity changed during inventory')
    return dict(bytes=after.st_size,sha256=h.hexdigest())

def one(directory,pattern):
    found=sorted(directory.glob(pattern)) if directory else []
    return found[0] if len(found)==1 else None

def package(name):
    spec=importlib.util.find_spec(name)
    return Path(spec.origin).parent if spec is not None and spec.origin else None

def collect(paths,compiler=None):
    if set(paths)!=set(NAMES): raise ValueError('exact six identities required')
    result={};missing=[]
    for name in NAMES:
        p=paths[name]
        if p is None or not Path(p).is_file(): missing.append(name)
        else: result[name]=identity(p)
    compiler_identity=identity(compiler) if compiler and Path(compiler).is_file() else None
    return dict(schema=1,status='PLATFORM_INVENTORY_ONLY_NOT_NUMERICAL_ADMITTED',
        numeric_execution_allowed=False,model_executed=False,old_pass_inherited=False,
        native_files=result,missing_native_names=missing,compiler=compiler_identity,
        next_gate='independently pin and initialize this platform; regenerate inputs/reference; review exact new execution closure')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory',action='store_true')
    args=parser.parse_args()
    if not args.inventory:
        print(json.dumps(dict(status='NOT_EXECUTED',numeric_execution_allowed=False)));return
    t,n=package('torch'),package('numpy')
    paths={'python':Path(sys.executable),'torch_C':one(t,'_C*.so'),
        'numpy_multiarray':one(n,'_core/_multiarray_umath*.so')}
    paths.update({name:(t/'lib'/name if t else None) for name in NAMES[3:]})
    r=collect(paths,shutil.which('g++'))
    r['python_version']=list(sys.version_info[:3]);r['implementation']=sys.implementation.name
    print(json.dumps(r,sort_keys=True))

if __name__=='__main__':main()
