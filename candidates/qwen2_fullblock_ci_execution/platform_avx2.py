"""Explicit AVX2 candidate initializer. Original AVX512 initializer is unchanged.

The body is the original checked initializer with only the reviewed pins projection.
This limits ATen dispatch; no claim about other backends or numerical equivalence.
"""
import hashlib
import importlib.util
import os
from pathlib import Path
import sys
from candidates.qwen2_fullblock_ci_prepare.initialize_platform import (
    ROOT, RUNTIME, need, load_pins, inventory, sanitized_summary)
from . import runtime_profile

def hardware_gate():
    # The official override bypasses feature detection. Refuse an unsafe host
    # before importing Torch; these Linux flags represent OS-enabled features.
    records = [set(line.split(':', 1)[1].split())
               for line in Path('/proc/cpuinfo').read_text().splitlines()
               if line.startswith('flags') and ':' in line]
    need(records and all({'avx2', 'fma'} <= flags for flags in records),
         'AVX2/FMA-capable Linux host required')


def initialize():
    need(runtime_profile.selected(), 'explicit AVX2 candidate required')
    hardware_gate()
    need(not any(n.split('.')[0] in ('torch','numpy','transformers') for n in sys.modules),'fresh native initialization process')
    need(sys.implementation.name=='cpython' and sys.version_info[:3]==(3,12,14),'fixed Python3.12.14 required')
    pins=runtime_profile.apply(load_pins());directory=ROOT/RUNTIME
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
