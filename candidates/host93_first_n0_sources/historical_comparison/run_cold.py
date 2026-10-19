"""Fixed-pin same-buffer test loader. Source-only; no native model or numeric runtime."""
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import types
import unittest

INPUT_PINS = {'n0_compare.py': (21000, 'e2d1a644e369147772ccd3e6b074559a9b29e9230ace172a3f4bcb4594794800'), 'launch.py': (1984, '0c0f313d288419fadff3254f4dfb04d7a45a6042e39ea271ffc7323aa7effbee'), 'test_cold.py': (20332, 'ce2bf7b04305ab2c4a90ae5a00cdce7cea86548bbfc858494a32a2eee6b63460'), 'test_historical_cold.py': (18036, '5e56045ba2537b0e43bff54d2608b8b80dd483ad7c439635e8f632a1f9efba13'), 'SOURCE_PINS.json': (1484, 'c20b35592a315a62184341be7494fbef9d290aa8974d38cedc7962ae48fd1a20'), 'DELTA.json': (642, '46c0cfbc94c253132c68c13aac05c0a76059a93fe8501d40d426bd8259f59d82'), 'fixtures/candidates/host93_first_n0_sources/bridge/metadata/CLI_CONTRACT.json': (1970, '299ec18b8e0990a4e8b95f1b95cbf9747e860b56376630438522df598fe460ae'), 'fixtures/candidates/host93_first_n0_sources/reference/PINS.json': (6364, 'ecea4b9b9137c06ae3c3f37bf9710f40f12a4556d1ae2c9aa77b84a857548db8'), 'fixtures/candidates/host93_first_n0_sources/reference/n0_reference.py': (13753, 'd26bd286857a6bff8217472733658cbdcb1e6590fa095e0d0589bc1be81b8fc4'), 'fixtures/scripts/qwen2_layer0_model_gate.py': (37776, '917d56f038c646606e9dc67d1d36752f70097adec9748db55b2a915af8147c85'), 'fixtures/spec/numerical_contract.md': (2256, '5cf7f538577e171ad42d70de60a24907b27e59991cc4d3895c42885fec962bb5')}
FORBIDDEN_ROOTS = frozenset(('torch', 'numpy', 'transformers'))


def need(ok, code):
    if not ok:
        raise ValueError(code)


def read_fixed(path, pin):
    need(path.is_absolute() and '..' not in path.parts and path.resolve() == path and
         all(not p.is_symlink() for p in (path, *path.parents)), 'PATH')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        first = os.fstat(fd)
        need(stat.S_ISREG(first.st_mode) and first.st_size == pin[0], 'FILE')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(pin[0] + 1)
        last = os.fstat(fd)
        stamp = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        need(stamp(first) == stamp(last) == stamp(path.stat()), 'CHANGED')
        need(len(raw) == pin[0] and hashlib.sha256(raw).hexdigest() == pin[1], 'SOURCE')
        return raw
    finally:
        os.close(fd)


def load_test(raw, pin, path, name):
    need(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode, 'FLAGS')
    need(type(raw) is bytes and len(raw) == pin[0] and hashlib.sha256(raw).hexdigest() == pin[1], 'SOURCE')
    module = types.ModuleType(name)
    module.__file__ = str(path)
    # The exact bytes that passed size+SHA checks are the bytes compiled below.
    exec(compile(raw, '<fixed-' + name + '>', 'exec', dont_inherit=True), module.__dict__)
    return module


def main():
    need(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode, 'FLAGS')
    need(not any(name.split('.')[0] in FORBIDDEN_ROOTS for name in sys.modules), 'COLD')
    root = Path(__file__).absolute().parent
    buffers = {name: read_fixed(root / name, pin) for name, pin in INPUT_PINS.items()}
    os.environ['N0_COMPARISON_SOURCE_REPO'] = str(root / 'fixtures')
    os.environ['N0_COMPARISON_REFERENCE_WORKER'] = str(root / 'fixtures/candidates/host93_first_n0_sources/reference/n0_reference.py')
    os.environ['N0_COMPARISON_BRIDGE_CONTRACT'] = str(root / 'fixtures/candidates/host93_first_n0_sources/bridge/metadata/CLI_CONTRACT.json')
    prohibited_attempts = []
    def guard(event, args):
        if ((event == 'import' and args[0].split('.')[0] in FORBIDDEN_ROOTS) or
                event.startswith('socket.') or event in ('subprocess.Popen', 'os.system',
                'os.exec', 'os.posix_spawn', 'os.fork', 'os.forkpty', 'ctypes.dlopen')):
            prohibited_attempts.append(event)
            raise RuntimeError('COLD_ONLY')
    sys.addaudithook(guard)
    modules = [load_test(buffers[name], INPUT_PINS[name], root / name, name[:-3])
               for name in ('test_cold.py', 'test_historical_cold.py')]
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromModule(module) for module in modules)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    need(not prohibited_attempts, 'COLD')
    need(not any(name.split('.')[0] in FORBIDDEN_ROOTS for name in sys.modules), 'COLD')
    need(all(read_fixed(root / name, pin) == buffers[name] for name, pin in INPUT_PINS.items()), 'CHANGED')
    print(json.dumps({'status': 'PASS' if result.wasSuccessful() else 'FAIL',
        'tests_run': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
        'skipped': len(result.skipped), 'optimized': bool(sys.flags.optimize),
        'fixed_inputs_verified': len(INPUT_PINS), 'prohibited_runtime_attempts': len(prohibited_attempts),
        'native_model_executed': False, 'numerical_runtime_imported': False,
        'actual_arrays_compared': False, 'baseline_adopted': False}, sort_keys=True))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
