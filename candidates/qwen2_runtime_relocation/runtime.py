"""One fixed checkout relocation; no model, raw data, capture, or receipt rewriting."""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys

ROOT = Path('/workspace/scratch/f28987e955ed/hetero_recovery_20261014T2131')
OLD_ROOT = '/workspace/scratch/f28987e955ed/hetero_recovery_20261013T1036'
RUNTIME = 'work/runtime_recovery/site-packages'
OLD_PYTHONPATH = OLD_ROOT + '/' + RUNTIME
NEW_PYTHONPATH = str(ROOT / RUNTIME)
NATIVE_NAMES = frozenset(('python','torch_C','numpy_multiarray','libc10.so','libtorch_cpu.so','libtorch_python.so'))
SOURCES = {
    'qkv': ('candidates/qwen2_live_qkv_inputs_m128', {
        'pins.json': '503b452bb030050f0a570cde89448a4f5bd4c8b95b86e1d1cdb81a362729618d',
        'recipe.py': '15ff7d73838e2d049d3930abd0c05b17c3927bc7fd336aef0d5ddc93b98ba489',
        'capture.py': '7393857f674545e22de86d5685372b6801f422f06ad757c6565f1e82a23834a4'}),
    'full29': ('candidates/qwen2_fullblock_reference_m128', {
        'pins.json': '48e20d380cfc6ac0ab5b9e1690bb507e37cf99468b0df8e79a1d37da0f16110f',
        'recipe.py': '2548e4b447ac58580c0e941bdc5287f2fcbc9dea861bb2d0c601884e5dd2ff36',
        'capture.py': '7bbee0a7edc6d36fb4996657ecea75c5181d292c9761bbb18ca4b12fc2486a86'}),
}


class Rejected(ValueError):
    pass


def need(ok, why):
    if not ok:
        raise Rejected(why)


def same(a, b):
    if type(a) is not type(b):
        return False
    if type(a) is dict:
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if type(a) is list:
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    return a == b


def regular(path):
    need(path.is_absolute() and str(path) == str(path.resolve()), 'canonical absolute path required')
    for parent in (path, *path.parents):
        need(not parent.is_symlink(), 'symlink path refused')
    need(path.is_file(), 'regular file required: ' + str(path))
    return path


def identity(path):
    regular(path)
    h = hashlib.sha256()
    with path.open('rb') as stream:
        before = os.fstat(stream.fileno())
        need(stat.S_ISREG(before.st_mode), 'nonregular file refused')
        for block in iter(lambda: stream.read(1 << 20), b''):
            h.update(block)
        after = os.fstat(stream.fileno())
    keys = ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns')
    need(all(getattr(before,k) == getattr(after,k) for k in keys), 'file changed while hashing')
    need(all(getattr(after,k) == getattr(path.stat(),k) for k in keys), 'file replaced while hashing')
    return {'bytes': after.st_size, 'sha256': h.hexdigest()}


def load_original(family):
    """Cold: read only the three fixed original source files, never ignored work."""
    need(type(family) is str and family in SOURCES, 'only qkv/full29 supported')
    need(Path(__file__).absolute().parents[2] == ROOT and ROOT.resolve() == ROOT, 'fixed current checkout required')
    package, hashes = SOURCES[family]
    values = {}
    for name, digest in hashes.items():
        path = regular(ROOT / package / name)
        raw = path.read_bytes()
        need(hashlib.sha256(raw).hexdigest() == digest, 'original source identity drift: ' + name)
        values[name] = raw
    pins = json.loads(values['pins.json'])
    need(pins['capture_environment']['PYTHONPATH'] == OLD_PYTHONPATH, 'exact old import prefix required')
    need(set(pins['runtime_native_files']) == NATIVE_NAMES, 'exact six native pins required')
    return pins


def _expected(family):
    pins = load_original(family)
    pins['capture_environment']['PYTHONPATH'] = NEW_PYTHONPATH
    return pins


def check_native(pins, *, family):
    """Check a relocated copy against immutable original pins and stream all six files."""
    need(same(pins, _expected(family)), 'only the fixed PYTHONPATH relocation is allowed')
    result = {}
    for name, pin in pins['runtime_native_files'].items():
        path = Path(pin['path'])
        path = path if path.is_absolute() else ROOT / path
        actual = identity(path)
        need(same(actual, {k:pin[k] for k in ('bytes','sha256')}), 'native byte/hash drift: ' + name)
        result[name] = {'path':str(path), **actual}
    need(Path(sys.executable).resolve() == Path(result['python']['path']), 'pinned interpreter required')
    return result


def relocate_runtime(original_pins, *, family):
    """Return a separate pins copy after six-file verification; never mutate its input."""
    need(same(original_pins, load_original(family)), 'unmodified original pins required')
    moved = copy.deepcopy(original_pins)
    moved['capture_environment']['PYTHONPATH'] = NEW_PYTHONPATH
    check_native(moved, family=family)
    return moved


def initialize_runtime(family):
    """Fresh-process metadata probe only; call separately from later capture processes."""
    need(not any(n.split('.')[0] in ('torch','numpy','transformers') for n in sys.modules), 'fresh numeric imports required')
    pins = relocate_runtime(load_original(family), family=family)
    need({k:os.getenv(k) for k in pins['capture_environment']} == pins['capture_environment'], 'explicit relocated environment required')
    before = check_native(pins, family=family)
    for name in ('torch','numpy'):
        spec = importlib.util.find_spec(name)
        expected = regular(ROOT / RUNTIME / name / '__init__.py')
        need(spec is not None and spec.origin == str(expected) and
             list(spec.submodule_search_locations or ()) == [str(expected.parent)], 'foreign package origin: ' + name)
    import numpy as np
    import torch
    torch.set_num_threads(4)
    torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    runtime = {'python_major_minor':list(sys.version_info[:2]), 'numpy':np.__version__,
        'torch':str(torch.__version__), 'torch_commit':torch.version.git_version,
        'capability':torch.backends.cpu.get_cpu_capability(), 'threads':torch.get_num_threads(),
        'interop_threads':torch.get_num_interop_threads(),
        'deterministic_algorithms':torch.are_deterministic_algorithms_enabled(),
        'torch_build_sha256':hashlib.sha256(torch.__config__.show().encode()).hexdigest()}
    if 'implementation' in pins['runtime_requirements']:
        runtime['implementation'] = sys.implementation.name
    need(same(runtime, pins['runtime_requirements']), 'actual runtime requirements drift')
    for name, path in (('torch_C',torch._C.__file__),('numpy_multiarray',np._core._multiarray_umath.__file__)):
        need(str(regular(Path(path))) == before[name]['path'], 'native import origin drift')
    need(same(before, check_native(pins, family=family)), 'native identity changed during initialization')
    return {'status':'RELOCATED_RUNTIME_INITIALIZED_NO_MODEL_EXECUTION', 'family':family,
        'runtime':runtime, 'native_files':before, 'environment':pins['capture_environment'],
        'path_delta':{'field':'capture_environment.PYTHONPATH','old':OLD_PYTHONPATH,'new':NEW_PYTHONPATH},
        'raw_read':False,'model_executed':False,'rtl_executed':False,'historical_runtime_equivalence_claimed':False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--family', choices=tuple(SOURCES), default='full29')
    parser.add_argument('--initialize', action='store_true')
    args = parser.parse_args(argv)
    if args.initialize:
        result = initialize_runtime(args.family)
    else:
        load_original(args.family)
        result = {'status':'NOT_EXECUTED_SOURCE_CHECK_PASS','family':args.family,
            'native_read':False,'raw_read':False,'model_executed':False,'outputs_written':False}
    print(json.dumps(result,sort_keys=True))


if __name__ == '__main__':
    main()
