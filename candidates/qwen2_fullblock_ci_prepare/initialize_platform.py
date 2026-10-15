"""Initialize a fixed runtime and emit an allowlisted compact platform summary.

No raw/input/reference/model execution. This does not authorize a numerical run.
The old Python executable is NOT assumed identical to actions/setup-python.
new_python_identity means freshly observed, not necessarily a different ELF hash.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path
import sys
from candidates.qwen2_fullblock_ci_prepare import platform_inventory as inventory

ROOT=Path(__file__).resolve().parents[2]
PIN='candidates/qwen2_fullblock_reference_m128/pins.json'
PIN_SHA='48e20d380cfc6ac0ab5b9e1690bb507e37cf99468b0df8e79a1d37da0f16110f'
RUNTIME='work/runtime_recovery/site-packages'
SUMMARY_KEYS={'schema','status','python_version','implementation','native_files','runtime',
    'expected_runtime_matches','native_five_match','new_python_identity','numeric_execution_allowed',
    'model_executed','reference_executed','rtl_executed','environment_matches','incompatibilities'}

def need(ok,message):
    if not ok:raise ValueError(message)

def load_pins():
    raw=(ROOT/PIN).read_bytes()
    need(hashlib.sha256(raw).hexdigest()==PIN_SHA,'original full29 source pins drift')
    return json.loads(raw)

def sanitized_summary(native,runtime,expected,environment_matches):
    need(type(native) is dict and set(native)==set(inventory.NAMES),'six native identity summary')
    need(type(environment_matches) is bool,'environment bool required')
    runtime_keys={'python_major_minor','numpy','torch','torch_commit','capability','threads',
        'interop_threads','deterministic_algorithms','torch_build_sha256','implementation'}
    need(type(runtime) is dict and set(runtime)==runtime_keys,'exact runtime summary fields')
    need(type(runtime['python_major_minor']) is list and len(runtime['python_major_minor'])==2 and
        all(type(v) is int and 0<=v<100 for v in runtime['python_major_minor']),'runtime version tuple')
    need(runtime['implementation']=='cpython','runtime implementation')
    for key in ('numpy','torch','capability'):
        need(type(runtime[key]) is str and re.fullmatch('[A-Za-z0-9_.+\\-]{1,80}',runtime[key]),'safe runtime label')
    for key,size in (('torch_commit',40),('torch_build_sha256',64)):
        need(type(runtime[key]) is str and re.fullmatch('[0-9a-f]{'+str(size)+'}',runtime[key]),'runtime digest')
    for key in ('threads','interop_threads'):
        need(type(runtime[key]) is int and 0<runtime[key]<1024,'runtime thread integer')
    need(type(runtime['deterministic_algorithms']) is bool,'runtime deterministic bool')
    for record in native.values():
        need(type(record) is dict and set(record)=={'bytes','sha256'} and type(record['bytes']) is int and record['bytes']>0 and
            type(record['sha256']) is str and re.fullmatch('[0-9a-f]{64}',record['sha256']),
            'no paths/extra fields allowed in native summary')
    reasons=[]
    if runtime!=expected:reasons.append('runtime_requirements_differ')
    if not environment_matches:reasons.append('capture_environment_differ')
    result=dict(schema=1,status='RUNTIME_INITIALIZED_ONLY' if not reasons else 'RUNTIME_INITIALIZED_INCOMPATIBLE',
        python_version=list(sys.version_info[:3]),implementation=sys.implementation.name,
        native_files=native,runtime=runtime,expected_runtime_matches=runtime==expected,
        native_five_match=True,new_python_identity=True,numeric_execution_allowed=False,
        model_executed=False,reference_executed=False,rtl_executed=False,
        environment_matches=environment_matches,incompatibilities=reasons)
    need(set(result)==SUMMARY_KEYS,'summary allowlist')
    return result

def initialize():
    need(not any(n.split('.')[0] in ('torch','numpy','transformers') for n in sys.modules),'fresh native initialization process')
    need(sys.implementation.name=='cpython' and sys.version_info[:3]==(3,12,14),'fixed Python3.12.14 required')
    pins=load_pins();directory=ROOT/RUNTIME
    need(directory.resolve()==directory and not directory.is_symlink(),'runtime path alias')
    for name in ('torch','numpy'):
        spec=importlib.util.find_spec(name)
        need(spec is not None and spec.origin==str(directory/name/'__init__.py') and
            list(spec.submodule_search_locations or ())==[str(directory/name)],'foreign package origin')
    paths={}
    for name,record in pins['runtime_native_files'].items():
        if name=='python':path=Path(sys.executable).resolve()
        else:
            path=ROOT/record['path']
            need(path.resolve()==path and path.is_relative_to(directory),'fixed native relative path')
        paths[name]=path
    before={name:inventory.identity(path) for name,path in paths.items()}
    for name,record in pins['runtime_native_files'].items():
        if name!='python':need(before[name]=={k:record[k] for k in ('bytes','sha256')},'fixed native byte drift: '+name)
    environment=dict(pins['capture_environment']);environment['PYTHONPATH']=str(directory)
    env_matches={k:os.getenv(k) for k in environment}==environment
    need(env_matches,'exact capture environment required before native imports')
    import numpy as np
    import torch
    torch.set_num_threads(4);torch.set_num_interop_threads(1);torch.use_deterministic_algorithms(True)
    actual=dict(python_major_minor=list(sys.version_info[:2]),numpy=np.__version__,torch=str(torch.__version__),
        torch_commit=torch.version.git_version,capability=torch.backends.cpu.get_cpu_capability(),
        threads=torch.get_num_threads(),interop_threads=torch.get_num_interop_threads(),
        deterministic_algorithms=torch.are_deterministic_algorithms_enabled(),
        torch_build_sha256=hashlib.sha256(torch.__config__.show().encode()).hexdigest())
    if 'implementation' in pins['runtime_requirements']:actual['implementation']=sys.implementation.name
    need(Path(torch._C.__file__).resolve()==paths['torch_C'] and
        Path(np._core._multiarray_umath.__file__).resolve()==paths['numpy_multiarray'],'loaded native origin')
    need(before=={name:inventory.identity(path) for name,path in paths.items()},'native drift during initialization')
    return sanitized_summary(before,actual,pins['runtime_requirements'],env_matches)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--initialize',action='store_true');args=p.parse_args()
    print(json.dumps(initialize() if args.initialize else dict(status='NOT_EXECUTED',numeric_execution_allowed=False),sort_keys=True))
if __name__=='__main__':main()
