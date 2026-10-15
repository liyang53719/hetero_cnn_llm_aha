"""Pure, cold full29 binding validation, never runtime or numerical admission.

The caller supplies exact original pins bytes plus a reviewed root contract and
its SHA256 obtained independently of those bytes. Computing a digest from an
unreviewed input does not confer review. No contracts are generated here.

Root contract keys: schema=1, kind='full29-root-binding', root, pythonpath,
original_pins_sha256, native_paths (exact six absolute paths).
An optional separately reviewed observed-platform contract has keys schema=1,
kind='full29-observed-platform', root, native_files, runtime_requirements.
Each native record contains exactly path, bytes, sha256. Its identities and
requirements are observations supplied by a trusted reviewer, not verified by
this helper. Live verification and source/lifecycle gates remain mandatory.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import PurePosixPath
import re

ORIGINAL_SHA256 = '48e20d380cfc6ac0ab5b9e1690bb507e37cf99468b0df8e79a1d37da0f16110f'
RUNTIME = 'work/runtime_recovery/site-packages'
OLD_ROOT = '/workspace/scratch/f28987e955ed/hetero_recovery_20261013T1036'
NATIVE_NAMES = frozenset(('python', 'torch_C', 'numpy_multiarray', 'libc10.so',
                          'libtorch_cpu.so', 'libtorch_python.so'))


class Rejected(ValueError):
    pass


def need(ok, message):
    if not ok:
        raise Rejected(message)


def same(a, b):
    if type(a) is not type(b):
        return False
    if type(a) is dict:
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if type(a) is list:
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    return a == b


def digest(value):
    need(type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None,
         'lowercase SHA256 required')


def absolute(value):
    need(type(value) is str and value.startswith('/') and not value.startswith('//')
         and str(PurePosixPath(value)) == value and '..' not in value.split('/')
         and not any(c in value for c in ('\x00', '\n', '\r', ':', '\\')),
         'one canonical absolute POSIX path required')
    return value


def keys(value, expected):
    need(type(value) is dict and set(value) == set(expected), 'exact contract keys required')


def _pairs(items):
    out = {}
    for key, value in items:
        need(key not in out, 'duplicate JSON key')
        out[key] = value
    return out


def _bad_constant(value):
    raise Rejected('nonfinite JSON constant')


def document(raw, expected_sha256):
    need(type(raw) is bytes, 'exact contract bytes required')
    digest(expected_sha256)
    need(hashlib.sha256(raw).hexdigest() == expected_sha256, 'contract byte digest mismatch')
    try:
        return json.loads(raw, object_pairs_hook=_pairs, parse_constant=_bad_constant)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise Rejected('invalid contract JSON') from exc


def _requirements(observed, original):
    keys(observed, original)
    for name, old in original.items():
        new = observed[name]
        need(type(new) is type(old), 'runtime requirement type drift: ' + name)
        if type(old) is list:
            need(len(new) == len(old) and all(type(v) is int and v >= 0 for v in new),
                 'runtime version tuple invalid')
        elif type(old) is str:
            need(bool(new), 'runtime string must not be empty')
    digest(observed['torch_build_sha256'])
    need(re.fullmatch('[0-9a-f]{40}', observed['torch_commit']) is not None,
         'torch commit invalid')
    # These control numerical execution and are not platform-dependent metadata.
    for name in ('threads', 'interop_threads', 'deterministic_algorithms'):
        need(same(observed[name], original[name]), 'runtime execution policy drift: ' + name)


def bind_runtime(original_pins_bytes, binding_bytes, *, binding_sha256, root,
                 platform_bytes=None, platform_sha256=None):
    """Return a copy with only reviewed runtime binding fields changed.

    Entirely pure: does not stat paths, verify actual files, import packages,
    mutate inputs, start processes, write receipts or claim a numerical pass.
    Symlink/file identity and fresh-process runtime checks must happen later.
    """
    original = document(original_pins_bytes, ORIGINAL_SHA256)
    binding = document(binding_bytes, binding_sha256)
    keys(binding, ('schema', 'kind', 'root', 'pythonpath', 'original_pins_sha256', 'native_paths'))
    need(type(binding['schema']) is int and binding['schema'] == 1 and
         binding['kind'] == 'full29-root-binding', 'unsupported root contract')
    absolute(root)
    need(root != '/' and binding['root'] == root, 'exact reviewed root required')
    need(binding['original_pins_sha256'] == ORIGINAL_SHA256, 'original pin anchor drift')
    need(binding['pythonpath'] == root + '/' + RUNTIME, 'exact root runtime prefix required')
    keys(binding['native_paths'], NATIVE_NAMES)
    need(set(original['runtime_native_files']) == NATIVE_NAMES, 'six original identities required')
    need(original['capture_environment']['PYTHONPATH'] == OLD_ROOT + '/' + RUNTIME,
         'original runtime prefix drift')
    expected = copy.deepcopy(original['runtime_native_files'])
    requirements = original['runtime_requirements']
    for record in expected.values():
        if not record['path'].startswith('/'):
            record['path'] = root + '/' + record['path']
    need((platform_bytes is None) == (platform_sha256 is None),
         'separate reviewed platform bytes and external digest both required')
    if platform_bytes is not None:
        platform = document(platform_bytes, platform_sha256)
        keys(platform, ('schema', 'kind', 'root', 'native_files', 'runtime_requirements'))
        need(type(platform['schema']) is int and platform['schema'] == 1 and
             platform['kind'] == 'full29-observed-platform' and platform['root'] == root,
             'exact separately reviewed platform/root required')
        keys(platform['native_files'], NATIVE_NAMES)
        _requirements(platform['runtime_requirements'], requirements)
        expected = platform['native_files']
        requirements = platform['runtime_requirements']
    seen = set()
    for name, record in expected.items():
        keys(record, ('path', 'bytes', 'sha256'))
        path = absolute(record['path'])
        need(path not in seen, 'distinct native paths required')
        seen.add(path)
        need(binding['native_paths'][name] == path, 'unreviewed native remap: ' + name)
        if name != 'python':
            need(path.startswith(root + '/' + RUNTIME + '/'), 'native path outside exact runtime root')
        need(type(record['bytes']) is int and record['bytes'] > 0, 'positive native byte count required')
        digest(record['sha256'])
    result = copy.deepcopy(original)
    result['capture_environment']['PYTHONPATH'] = binding['pythonpath']
    result['runtime_native_files'] = copy.deepcopy(expected)
    result['runtime_requirements'] = copy.deepcopy(requirements)
    return {'status': 'COLD_BINDING_VALIDATED_NOT_RUNTIME_VERIFIED', 'pins': result,
            'root': root, 'binding_sha256': binding_sha256, 'platform_sha256': platform_sha256,
            'native_files_verified': False, 'runtime_initialized': False,
            'numeric_execution_allowed': False, 'model_executed': False,
            'historical_runtime_equivalence_claimed': False}
