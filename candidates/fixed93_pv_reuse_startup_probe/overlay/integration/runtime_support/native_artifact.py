"""Source-bound forwarding to parent-owned existing0754 profile2 ELF adapter.

No ctypes/CDLL/native-symbol/compiler implementation lives here. Missing or
unreviewed top-level native_reuse.py/NATIVE_REUSE_PINS.json fails closed. Source
parity and a historical result never substitute for the parent's native review.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
from ..interface import MissingPrerequisite

CANDIDATE = Path(__file__).resolve().parents[2]
MODE = 'verified_existing_profile2_elf_reused'
_MODULE = None


def _file(path):
    if not path.is_file() or path.resolve() != path or any(p.is_symlink() for p in (path, *path.parents)):
        raise MissingPrerequisite('missing/aliased exact native adapter prerequisite: ' + str(path))
    raw = path.read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def _load_parent_adapter(path, expected):
    """Use pinned source bytes, not a potentially stale or poisoned pyc."""
    import types
    key = '_fixed93_parent_native_reuse'
    if key in sys.modules:
        raise MissingPrerequisite('unexpected previously loaded parent native adapter')
    path = Path(path)
    if path.resolve() != path or any(p.is_symlink() for p in (path, *path.parents)):
        raise MissingPrerequisite('aliased parent native adapter source')
    raw = path.read_bytes()
    if dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()) != expected:
        raise MissingPrerequisite('parent native adapter source changed after prerequisite checks')
    code = compile(raw, str(path), 'exec', dont_inherit=True, optimize=0)
    module = types.ModuleType(key)
    module.__file__, module.__package__ = str(path), ''
    sys.modules[key] = module
    try:
        exec(code, module.__dict__)
        if sys.modules.get(key) is not module or module.__file__ != str(path) or module.__name__ != key:
            raise MissingPrerequisite('canonical parent native adapter required')
    except BaseException:
        if sys.modules.get(key) is module:
            del sys.modules[key]
        raise
    return module


def _adapter():
    global _MODULE
    approval = CANDIDATE / 'ADMISSION.json'
    expected = os.environ.get('QWEN2_FIXED93_ADMISSION_SHA256', '')
    if len(expected) != 64 or _file(approval)['sha256'] != expected:
        raise MissingPrerequisite('new externally pinned native adapter admission missing')
    value = json.loads(approval.read_bytes())
    if not (value.get('schema') == 'fixed93-startup-probe-admission-v1' and
            value.get('startup_only') is True and value.get('fullblock_authorized') is False and
            value.get('M128_authorized') is False and value.get('entrypoint') == 'integration/startup_probe.py' and
            value.get('stop_before') == 'first_x.advance_to_request'):
        raise MissingPrerequisite('only exact startup-only native initialization is admitted')
    if value.get('status') != 'REVIEWED_FIXED93_STARTUP_PROBE_ACTUAL' or value.get('actual_execution_authorized') is not True:
        raise MissingPrerequisite('source-only proposal cannot load existing0754 native artifact')
    for name in ('native_reuse.py', 'NATIVE_REUSE_PINS.json'):
        if value.get('files', {}).get(name) != _file(CANDIDATE / name):
            raise MissingPrerequisite('unreviewed parent native adapter identity: ' + name)
    if _MODULE is None:
        key = '_fixed93_parent_native_reuse'
        if key in sys.modules:
            raise MissingPrerequisite('unexpected previously loaded parent native adapter')
        module = _load_parent_adapter(CANDIDATE / 'native_reuse.py', value['files']['native_reuse.py'])
        if not all(callable(getattr(module, name, None)) for name in ('identity', 'load')):
            raise MissingPrerequisite('parent native adapter interface incomplete')
        _MODULE = module
    if Path(_MODULE.__file__).resolve() != CANDIDATE / 'native_reuse.py':
        raise MissingPrerequisite('parent native adapter loaded path drift')
    return _MODULE


def identity():
    """Delegate exact existing library/receipt identity verification once."""
    return _adapter().identity()


def load(dense):
    """Delegate existing0754 load once; never compile, reset, or use old0546 ELF.

    Parent returns (library, compile_receipt, reuse). Compile receipt is historical
    existing-artifact identity, not a claim that this task built anything. Parent
    alone implements ABI/source/flags/mapped-resource checks. Existing runner then
    performs its already-declared fresh Matrix/SiLU state reset.
    """
    return _adapter().load(dense)
