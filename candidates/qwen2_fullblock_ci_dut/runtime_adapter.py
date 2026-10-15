"""Fixed CI wheel-root classifier adapter; no imports or I/O until initialize().

Import both reviewed package roots before original frozen_exec. Only their two
exact __init__.py filenames are tooling; subfiles and all other paths continue
through the unchanged original classifier. No disk edits or sys.prefix changes.
The wrapper stays installed for this fresh process and rechecks root identities.
"""
import hashlib
import importlib
import importlib.util
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
CI_ROOT=Path('/home/runner/work/hetero_cnn_llm_aha/hetero_cnn_llm_aha')
PACKAGE_ROOT=CI_ROOT/'work/runtime_recovery/site-packages'
PINS={
 'numpy':'93924ac4b793328947dfd9eb9355e54eccdfd26a92c8dd52188aed2e52c7eb38',
 'yaml':'b19dfcc333d6a75dfd73073901164507252f271b41d3b5f7d85510033a0547a7'}
HELPER='candidates.qwen2_resident_matrix.ffn_public.check_numeric'
HELPER_PATH=CI_ROOT/'candidates/qwen2_resident_matrix/ffn_public/check_numeric.py'
HELPER_SHA='7447baeb99a4a0c2ab3a8980cf18414db994728164d7905b597d67f5db39359b'
_MODULES=None
_CLASSIFIER=None
_ORIGINAL=None


def need(ok,message):
    if not ok:raise ValueError(message)


def identity(path,digest):
    need(path.is_absolute() and path.resolve(strict=True)==path and
         not any(p.is_symlink() for p in (path,*path.parents)), 'fixed runtime source alias')
    need(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==digest,
         'fixed runtime source identity drift')


def check_spec(name):
    path=PACKAGE_ROOT/name/'__init__.py'
    identity(path,PINS[name])
    spec=importlib.util.find_spec(name)
    need(spec is not None and spec.origin==str(path) and
         list(spec.submodule_search_locations or ())==[str(path.parent)],
         'fixed runtime package spec drift')
    return path


def check_loaded(name,module):
    path=check_spec(name)
    need(sys.modules.get(name) is module and getattr(module,'__file__',None)==str(path) and
         getattr(getattr(module,'__spec__',None),'origin',None)==str(path) and
         list(getattr(module,'__path__',()))==[str(path.parent)],
         'loaded fixed runtime package origin drift')


def initialize():
    global _MODULES,_CLASSIFIER,_ORIGINAL
    need(ROOT==CI_ROOT and ROOT.resolve()==ROOT,'fixed CI adapter workspace')
    # Validate both roots before either import; loaded modules are checked too.
    for name in PINS:check_spec(name)
    modules=tuple(importlib.import_module(name) for name in PINS)
    for name,module in zip(PINS,modules):check_loaded(name,module)
    if _MODULES is not None:
        need(all(a is b for a,b in zip(modules,_MODULES)),'runtime module replacement')
    identity(HELPER_PATH,HELPER_SHA)
    helper=importlib.import_module(HELPER)
    need(getattr(helper,'__file__',None)==str(HELPER_PATH) and helper.ROOT==ROOT,
         'original classifier helper origin drift')
    identity(HELPER_PATH,HELPER_SHA)
    if _CLASSIFIER is not None:
        need(helper.repository_source_path is _CLASSIFIER,'runtime classifier replaced')
        return modules
    original=helper.repository_source_path
    need(callable(original),'original runtime classifier required')
    approved={str(PACKAGE_ROOT/name/'__init__.py'):(name,module)
              for name,module in zip(PINS,modules)}
    def repository_source_path(filename):
        # Never resolve an arbitrary incoming filename into an exemption.
        entry=approved.get(filename) if type(filename) is str else None
        if entry is not None:
            check_loaded(*entry)
            return None
        return original(filename)
    _MODULES=modules;_ORIGINAL=original;_CLASSIFIER=repository_source_path
    helper.repository_source_path=repository_source_path
    return modules
