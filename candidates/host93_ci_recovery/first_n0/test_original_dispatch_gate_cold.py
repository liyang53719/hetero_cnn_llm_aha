#!/usr/bin/env python3
"""Cold, stdlib-only execution test of the byte-pinned original recover gate.

Run: python3 -I -S -B test_original_dispatch_gate.py --repo /absolute/repo
Never imports real Torch/NumPy, runs a model, or writes a reference receipt.
"""
import sys

# Reject before reading a target file or importing the original worker.
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('FLAGS: require -I -S -B')
if any(name.split('.')[0] in ('torch', 'numpy', 'transformers') for name in sys.modules):
    raise SystemExit('RUNTIME: numerical package already loaded')

import argparse
import builtins
import hashlib
import json
import os
from pathlib import Path
import stat
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

WORKER_REL = 'candidates/host93_first_n0_sources/reference/n0_reference.py'
PINS_REL = 'candidates/host93_first_n0_sources/reference/PINS.json'
WORKER_PIN = (13753, 'd26bd286857a6bff8217472733658cbdcb1e6590fa095e0d0589bc1be81b8fc4')
PINS_PIN = (6364, 'ecea4b9b9137c06ae3c3f37bf9710f40f12a4556d1ae2c9aa77b84a857548db8')


def check(condition, message):
    # Deliberately not an assert: identical checks run under python -O.
    if not condition:
        raise RuntimeError(message)


class ColdReject(Exception):
    pass


class BeforeThreadSentinel(BaseException):
    """Raised at entry to a fake setter, before any thread/native operation."""


class UnexpectedOperation(BaseException):
    pass


def verify(raw, pin):
    if len(raw) != pin[0]:
        raise ColdReject('SIZE')
    if hashlib.sha256(raw).hexdigest() != pin[1]:
        raise ColdReject('SHA')
    return raw


def pinned_read(path, pin):
    check(path.is_absolute() and '..' not in path.parts and path.resolve() == path,
          'target path must be canonical and absolute')
    check(not any(p.is_symlink() for p in (path, *path.parents)), 'symlink rejected')
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    try:
        before = os.fstat(fd)
        check(stat.S_ISREG(before.st_mode), 'not a regular file')
        if before.st_size != pin[0]:
            raise ColdReject('SIZE')
        chunks, total = [], 0
        while total <= pin[0]:
            part = os.read(fd, pin[0] + 1 - total)
            if not part:
                break
            chunks.append(part)
            total += len(part)
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        check(identity(before) == identity(os.fstat(fd)) == identity(path.stat()),
              'file changed while reading')
        return verify(b''.join(chunks), pin)
    finally:
        os.close(fd)


def load_original(worker_raw, pins_raw, filename, compile_fn):
    # Both pinned, immutable buffers are verified before any parse/compile/exec.
    verify(worker_raw, WORKER_PIN)
    verify(pins_raw, PINS_PIN)
    pins = json.loads(pins_raw)
    module = ModuleType('_frozen_n0_reference_dispatch_test')
    module.__file__ = str(filename)
    original_import = builtins.__import__
    fake_resource = ModuleType('resource')

    def cold_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name.split('.')[0] in ('torch', 'numpy', 'transformers'):
            raise UnexpectedOperation('numerical import during cold worker load')
        # The original only references this in limits(), which is mocked below.
        # Do not load even the stdlib resource extension for this test.
        if name == 'resource':
            return fake_resource
        return original_import(name, globals, locals, fromlist, level)

    code = compile_fn(worker_raw, str(filename), 'exec')
    with patch.object(builtins, '__import__', cold_import):
        exec(code, module.__dict__)
    return module, pins


class FakePath:
    """In-memory path facade; no original recover path creates a directory."""
    def __init__(self, value, calls):
        self.value, self.calls = str(value), calls

    def __str__(self):
        return self.value

    def __fspath__(self):
        return self.value

    @property
    def parent(self):
        return FakePath(str(Path(self.value).parent), self.calls)

    def is_dir(self):
        self.calls.append('fake_parent_is_dir')
        return True

    def mkdir(self, *, mode):
        check(mode == 0o700, 'original output mode changed')
        self.calls.append('fake_mkdir')


class GuardModule(ModuleType):
    def __getattr__(self, name):
        raise UnexpectedOperation('unprovided fake module attribute: ' + name)


def run_case(module, pins, capability, label, repo):
    calls, receipts = [], []
    expected = pins['runtime_requirements']
    fake_np, fake_torch = GuardModule('numpy'), GuardModule('torch')
    fake_np.__version__ = expected['numpy']
    fake_torch.__version__ = expected['torch']
    fake_torch.version = SimpleNamespace(git_version=expected['torch_commit'])
    fake_torch.nn = GuardModule('torch.nn')
    fake_torch.__path__ = []

    def fake_capability():
        calls.append('fake_capability')
        return capability

    def fake_build():
        calls.append('fake_build_string')
        return 'synthetic-build-description; no native runtime queried'

    def before_threads(count):
        check(count == 4, 'first original thread request changed')
        calls.append('before_thread_sentinel')
        raise BeforeThreadSentinel()

    fake_torch.backends = SimpleNamespace(cpu=SimpleNamespace(get_cpu_capability=fake_capability))
    fake_torch.__config__ = SimpleNamespace(show=fake_build)
    fake_torch.set_num_threads = before_threads
    original_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == 'numpy':
            calls.append('fake_numpy_import')
            return fake_np
        if name == 'torch':
            calls.append('fake_torch_import')
            return fake_torch
        if name.split('.')[0] in ('numpy', 'torch', 'transformers'):
            raise UnexpectedOperation('unexpected numerical import')
        return original_import(name, globals, locals, fromlist, level)

    def record(name, result):
        def replacement(*args, **kwargs):
            calls.append(name)
            return result
        return replacement

    def capture_receipt(out, name, raw):
        check(name == 'RECEIPT.json', 'unexpected original output write')
        check(type(raw) is bytes, 'receipt is not bytes')
        receipts.append(json.loads(raw))
        calls.append('captured_private_receipt')

    fake_buffers = {pins['official_class']['path']: b'not parsed: source is mocked'}
    replacements = {
        'limits': record('fake_limits', None),
        'path': lambda value: FakePath(value, calls),
        'source_buffers': record('fake_source_buffers', fake_buffers),
        'official_node': record('fake_official_node', object()),
        'read_checked': record('fake_raw_read', b''),
        'runtime_before': record('fake_runtime_identity', {}),
        'write_new': capture_receipt,
    }
    args = SimpleNamespace(repo=str(repo), runtime_root='/mock-runtime', python='/mock-python',
                           out='/mock-private-output', shared_stop=0.0,
                           embedding='/mock-embedding', gamma='/mock-gamma',
                           python_profile='ci31214')
    environment = dict(OMP_NUM_THREADS='4', MKL_NUM_THREADS='4',
                       OPENBLAS_NUM_THREADS='1', PYTHONNOUSERSITE='1')
    stopped, returned = False, None
    original_recover = module.recover
    with patch.multiple(module, **replacements), \
         patch.dict(os.environ, environment, clear=True), \
         patch.object(sys, 'path', list(sys.path)), \
         patch.object(sys, 'addaudithook', record('fake_audit_hook', None)), \
         patch.object(os.path, 'lexists', record('fake_lexists', False)), \
         patch.object(builtins, '__import__', fake_import):
        try:
            returned = module.recover(args, pins)
        except BeforeThreadSentinel:
            stopped = True
    check(module.recover is original_recover, 'original recover was replaced')
    check(len(receipts) == 1, 'original finally must issue exactly one receipt')
    receipt = receipts[0]
    check(receipt['stage'] == 'RUNTIME_IMPORT', 'wrong original stage')
    check(receipt['observed_runtime']['capability'] == capability,
          'private observed capability was not preserved exactly')
    check(not receipt['reference_accepted'] and not receipt['rtl_executed']
          and not receipt['fullblock_executed'], 'an execution claim escaped')
    check(calls.count('fake_raw_read') == 2, 'wrong mocked raw input count')
    check(calls.count('fake_capability') == 1, 'capability must be observed once')
    check(calls.count('fake_runtime_identity') == 1, 'wrong mocked runtime count')
    check(calls.count('fake_numpy_import') == 1 and calls.count('fake_torch_import') == 2,
          'original import sequence changed')
    if label == 'avx512':
        check(stopped and returned is None and calls.count('before_thread_sentinel') == 1,
              'AVX512 did not pass original gate to before-thread sentinel')
        check(receipt['code'] == 'UNEXPECTED' and receipt['status'] == 'NOT_COMPLETED',
              'sentinel receipt unexpectedly claimed completion')
        outcome = 'PASSED_TO_BEFORE_THREAD_SENTINEL'
    else:
        check(not stopped and 'before_thread_sentinel' not in calls,
              'rejected capability reached thread setter')
        check(returned == receipt and receipt['code'] == 'DISPATCH'
              and receipt['status'] == 'NOT_COMPLETED', 'not original DISPATCH rejection')
        outcome = 'ORIGINAL_DISPATCH_REJECTION'
    check(not any(n.split('.')[0] in ('torch', 'numpy', 'transformers') for n in sys.modules),
          'a real numerical module was imported')
    # Never export receipt contents or the arbitrary capability string.
    return dict(case=label, outcome=outcome, private_observation_preserved=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True, type=Path)
    args = parser.parse_args()
    repo = args.repo
    check(repo.is_absolute() and '..' not in repo.parts and repo.resolve() == repo,
          '--repo must be an explicit canonical absolute path')
    worker_raw = pinned_read(repo / WORKER_REL, WORKER_PIN)
    pins_raw = pinned_read(repo / PINS_REL, PINS_PIN)
    compiles = []

    def tracked_compile(raw, filename, mode):
        compiles.append(hashlib.sha256(raw).hexdigest())
        return compile(raw, filename, mode)

    negative_cases = []
    for subject, raw in (('worker', worker_raw), ('pins', pins_raw)):
        for rejection, altered in (('SIZE', raw + b'\n'),
                                   ('SHA', bytes([raw[0] ^ 1]) + raw[1:])):
            before = len(compiles)
            try:
                load_original(altered if subject == 'worker' else worker_raw,
                              altered if subject == 'pins' else pins_raw,
                              repo / WORKER_REL, tracked_compile)
            except ColdReject as error:
                check(str(error) == rejection, 'wrong loader rejection')
            else:
                raise RuntimeError('bad pinned buffer accepted')
            check(len(compiles) == before, 'bad buffer reached compile')
            negative_cases.append(subject + '_' + rejection)
    module, pins = load_original(worker_raw, pins_raw, repo / WORKER_REL, tracked_compile)
    check(compiles == [WORKER_PIN[1]], 'original source was not compiled once from verified bytes')
    check(module.PINS_BYTES == PINS_PIN[0] and module.PINS_SHA256 == PINS_PIN[1],
          'original module PINS identity mismatch')
    check(pins['runtime_requirements']['capability'] == 'AVX512', 'frozen expected capability changed')
    check(module.recover.__code__.co_filename == str(repo / WORKER_REL), 'wrong function origin')
    cases = [('default', 'DEFAULT'), ('avx2', 'AVX2'), ('avx512', 'AVX512'),
             ('unknown', 'synthetic private capability / free text \u2603\nunknown')]
    results = [run_case(module, pins, capability, label, repo) for label, capability in cases]
    summary = dict(
        schema=1, status='PASS', fixture_scope='ORIGINAL_PINNED_RECOVER_CAPABILITY_GATE_ONLY',
        optimized=bool(sys.flags.optimize), worker_sha256=WORKER_PIN[1], pins_sha256=PINS_PIN[1],
        loader_negative_cases=negative_cases, before_compile_rejections=4, cases=results,
        real_numerical_imports=0, real_thread_configuration_calls=0,
        real_resource_limit_calls=0, real_timer_calls=0, actual_forward_count=0,
        actual_tensor_operations=0, actual_downloads=0, actual_rtl_executions=0,
        actual_fullblock_executions=0, actual_reference_output_files=0,
        canonical_output_identity_verified=False, native_dispatch_verified=False,
    )
    print(json.dumps(summary, sort_keys=True, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
