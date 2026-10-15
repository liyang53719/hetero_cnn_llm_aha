"""Reinitialize the exact reviewed CI platform; never reuse an old summary as PASS.

Default is cold. Explicit initialize(execute=True) calls the published initializer
in this process, hashes the six native files there, and checks the current result.
Only the reviewed Python ELF differs from original full29 runtime pins. Returned
summary is path-free and grants no numerical execution or historical equivalence.
No historical receipt or summary is read, changed, or accepted as an input.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
CI_ROOT = Path('/home/runner/work/hetero_cnn_llm_aha/hetero_cnn_llm_aha')
PYTHON_HOME = Path('/opt/hostedtoolcache/Python/3.12.14/x64')
PYTHON_IDENTITY = {'bytes': 17752, 'sha256': 'bef88f140b625959f8af25c7b75cce2cd5d4b29cc2f2b079befd7f68eda4dba0'}
PIN = 'candidates/qwen2_fullblock_reference_m128/pins.json'
SOURCES = {
    PIN: '48e20d380cfc6ac0ab5b9e1690bb507e37cf99468b0df8e79a1d37da0f16110f',
    'candidates/qwen2_fullblock_ci_prepare/initialize_platform.py': 'a928c3593c2141e13d6ffd9b15c1c10433e393724759b66112fcb8284b1b75c4',
    'candidates/qwen2_fullblock_ci_prepare/platform_inventory.py': '356ffa5bd746b0f8e879ff40a09a1e9d22daaf0fb996068cb089548fc0730364',
}
NAMES = {'python', 'torch_C', 'numpy_multiarray', 'libc10.so', 'libtorch_cpu.so', 'libtorch_python.so'}


def need(ok, message):
    if not ok:
        raise ValueError(message)


def same(a, b):
    if type(a) is not type(b):
        return False
    if type(a) is dict:
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if type(a) is list:
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    return a == b


def sources(root):
    """Read only three source metadata files; no runtime files or old summaries."""
    raw_pins = None
    for name, digest in SOURCES.items():
        path = root / name
        need(path.resolve() == path and not any(p.is_symlink() for p in (path, *path.parents)),
             'source path alias')
        raw = path.read_bytes()
        need(hashlib.sha256(raw).hexdigest() == digest, 'platform source drift: ' + name)
        if name == PIN:
            raw_pins = raw
    return json.loads(raw_pins)


def location(root):
    root = Path(root)
    need(root == ROOT == CI_ROOT and root.resolve() == root, 'fixed CI platform root')
    need(not any(p.is_symlink() for p in (root, *root.parents)), 'CI platform root alias')
    need(sys.implementation.name == 'cpython' and sys.version_info[:3] == (3, 12, 14),
         'fixed CPython 3.12.14 required')
    executable = Path(sys.executable).resolve(strict=True)
    need(executable.is_relative_to(PYTHON_HOME) and executable != PYTHON_HOME,
         'fixed hostedtoolcache interpreter directory')
    need(not any(p.is_symlink() for p in (executable, *executable.parents)), 'resolved interpreter path alias')
    return executable


def _expected(pins):
    need(set(pins['runtime_native_files']) == NAMES, 'exact six original native identities')
    native = {name: {k: record[k] for k in ('bytes', 'sha256')}
              for name, record in pins['runtime_native_files'].items()}
    native['python'] = copy.deepcopy(PYTHON_IDENTITY)
    return dict(schema=1, status='RUNTIME_INITIALIZED_ONLY', python_version=[3, 12, 14],
                implementation='cpython', native_files=native,
                runtime=copy.deepcopy(pins['runtime_requirements']),
                expected_runtime_matches=True, native_five_match=True, new_python_identity=True,
                numeric_execution_allowed=False, model_executed=False,
                reference_executed=False, rtl_executed=False,
                environment_matches=True, incompatibilities=[])


def initialize(root=ROOT, *, execute=False):
    """Return the newly observed sanitized summary, only after exact live checks.

    An explicit True is needed. This call has no prior-summary argument or cache.
    A caller must use a fresh process and separately authorize later model work.
    """
    need(type(execute) is bool, 'execute must be boolean')
    if not execute:
        return dict(status='NOT_EXECUTED', numeric_execution_allowed=False)
    executable = location(root)
    pins = sources(Path(root))
    need(not any(n.split('.')[0] in ('torch', 'numpy', 'transformers') for n in sys.modules),
         'fresh numeric import process required')
    from candidates.qwen2_fullblock_ci_prepare import initialize_platform as published
    need(published.ROOT == CI_ROOT and Path(published.__file__).resolve() ==
         CI_ROOT / 'candidates/qwen2_fullblock_ci_prepare/initialize_platform.py',
         'published initializer root/origin drift')
    need(Path(published.inventory.__file__).resolve() ==
         CI_ROOT / 'candidates/qwen2_fullblock_ci_prepare/platform_inventory.py',
         'published inventory origin drift')
    need(same(published.inventory.identity(executable), PYTHON_IDENTITY), 'reviewed Python ELF identity required')
    current = published.initialize()
    need(same(current, _expected(pins)), 'current CI platform summary drift')
    need(location(root) == executable, 'interpreter path changed during initialization')
    need(same(published.inventory.identity(executable), PYTHON_IDENTITY), 'Python ELF changed during initialization')
    need(same(sources(Path(root)), pins), 'platform source changed during initialization')
    return copy.deepcopy(current)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--initialize', action='store_true')
    args = parser.parse_args(argv)
    print(json.dumps(initialize(execute=args.initialize), sort_keys=True))


if __name__ == '__main__':
    main()
