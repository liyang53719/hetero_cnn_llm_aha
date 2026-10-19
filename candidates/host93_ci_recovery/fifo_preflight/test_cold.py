"""Tiny source-only FIFO glue tests. All acquisition/native/library work is mocked."""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('require Python -I -S -B before project loads')
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import types
import unittest
from unittest import mock

HERE = Path(__file__).absolute().parent
HELPER_PIN = {'bytes': 16203, 'sha256': 'b587e46b579537a720e89089c0fc860c64880b9186570d6bd2f70cb90b1ffdf5'}


def fixed(path, pin):
    if path.is_symlink() or not path.is_file() or path.stat().st_size != pin['bytes']:
        raise ValueError('fixed tiny-test source')
    with path.open('rb') as stream:
        raw = stream.read(pin['bytes'] + 1)
    if len(raw) != pin['bytes'] or hashlib.sha256(raw).hexdigest() != pin['sha256']:
        raise ValueError('fixed tiny-test source identity')
    return raw


def load(raw, path, name):
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec', dont_inherit=True), module.__dict__)
    return module


parser = argparse.ArgumentParser()
parser.add_argument('--repo', type=Path, required=True)
parser.add_argument('--miter', type=Path, default=HERE / 'fifo_ready_split_miter.sv')
options, rest = parser.parse_known_args()
g = load(fixed(HERE / 'fifo_preflight.py', HELPER_PIN), HERE / 'fifo_preflight.py', 'fixed_fifo_preflight_test')
SOURCE_BUFFERS = {name: fixed(options.miter if name == g.MITER else options.repo / name, pin)
                  for name, pin in g.REQUIRED_SOURCES.items()}


class Fixture:
    def __init__(self, root):
        self.repo, self.work = root / 'repo', root / 'private'
        self.repo.mkdir()
        self.buffers = dict(SOURCE_BUFFERS)
        for name, raw in self.buffers.items():
            target = self.repo / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        self.micro, self.acquisition = g._load_helpers(self.repo, self.buffers)
        m, a = self.micro, self.acquisition
        self.calls, self.verified, self.trees = [], [], []
        self.libraries = {'private-canary': {'path': '/usr/lib/x86_64-linux-gnu/private_canary',
                                           'bytes': 10, 'sha256': '0' * 64}}
        self.package = {'selected': [{'path': name, 'bytes': a.SELECTED_PINS[name][0],
                                     'sha256': a.SELECTED_PINS[name][1]}
                                    for name in a.SELECTED_PATHS]}
        self.hook = None
        self.elf = mock.Mock()
        self.libs = mock.Mock(side_effect=lambda: json.loads(json.dumps(self.libraries)))
        self.verify = mock.Mock(side_effect=self.verify_stage)
        self.support = types.SimpleNamespace(identity=self.identity, checked_read=self.checked_read,
                                             tree_inventory=self.tree_inventory)

    def identity(self, path, cap):
        raw = self.micro.read(path, cap)
        return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                'mode': oct(stat.S_IMODE(path.stat().st_mode))}

    def checked_read(self, path, size, sha):
        return self.micro.exact(path, {'bytes': size, 'sha256': sha})

    def tree_inventory(self, *args):
        self.trees.append(args)
        return {}

    def verify_stage(self, stage, package):
        self.verified.append(stage)
        if (stage / 'mock_mutated').exists():
            raise ValueError('private stage mutation canary')
        if package != self.package:
            raise ValueError('package mutation')

    def callback(self, name, argv, cwd, env, bounds):
        self.calls.append((name, list(argv), cwd, dict(env), dict(bounds)))
        result = {'raw_log': b''}
        if name == 'icarus_acquire':
            (self.work / 'icarus').mkdir(mode=0o700)
            self.micro.write_json(self.work / 'icarus/RECEIPT.json', self.package)
        elif name == 'fifo_compile':
            ivl = self.work / 'icarus/usr/lib/x86_64-linux-gnu/ivl'
            (cwd / 'fifo.vvp').write_bytes((':vpi_module "' + str(ivl / 'system.vpi') + '";\n').encode())
        elif name == 'fifo_run':
            result['raw_log'] = ('\n'.join(sorted(self.micro.FIFO_LINES)) + '\n' + self.micro.FIFO_PASS + '\n' +
                                str(self.work / 'fixtures/fifo_valid_split_cases.sv') +
                                ':229: $finish called at 42 (1ps)\n').encode()
        else:
            raise AssertionError('unexpected native phase')
        if self.hook:
            self.hook(name, result)
        return result

    def run(self):
        with mock.patch.object(g, '_load_helpers', return_value=(self.micro, self.acquisition)), \
             mock.patch.object(self.acquisition, 'verify_stage', self.verify), \
             mock.patch.object(self.acquisition, '_download', side_effect=AssertionError('no downloads')), \
             mock.patch.object(self.acquisition, '_zstd_library', side_effect=AssertionError('no native decoder')), \
             mock.patch.object(self.micro, 'verify_package_elf', self.elf), \
             mock.patch.object(self.micro, 'library_identities', self.libs):
            return g.run(self.repo, self.work, self.callback, self.support, self.buffers)


class Cold(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='fifo_cold_')
        self.addCleanup(self.tmp.cleanup)
        self.f = Fixture(Path(self.tmp.name))

    def rejected(self, boundary, code=None):
        with self.assertRaises(BaseException) as caught:
            self.f.run()
        error = caught.exception
        self.assertEqual(getattr(error, 'safe_contract_boundary', None), boundary)
        if code:
            self.assertEqual(getattr(error, 'safe_contract_code', None), code)
        self.assertTrue(self.f.micro.safe_contract_pair(error.safe_contract_boundary, error.safe_contract_code))
        return error

    def test_success_exact_three_phases_private_projection_and_bounds(self):
        with mock.patch.dict(os.environ, {'HTTPS_PROXY': 'private-proxy-canary', 'SSL_CERT_FILE': 'private-ca-canary',
                                         'LD_PRELOAD': 'must-not-inherit', 'PYTHONPATH': 'must-not-inherit'}, clear=True):
            result = self.f.run()
        self.assertEqual(result, {'cases': 4, 'comparisons': 5180, 'tools': self.f.micro.ICARUS_IDENTITIES})
        self.assertEqual([r[0] for r in self.f.calls], ['icarus_acquire', 'fifo_compile', 'fifo_run'])
        self.assertEqual(self.f.calls[0][4], g.ACQUIRE_LIMITS)
        self.assertEqual(self.f.calls[1][4], g.MICRO_LIMITS)
        self.assertEqual(self.f.calls[2][4], g.MICRO_LIMITS)
        self.assertEqual(self.f.calls[0][3]['HTTPS_PROXY'], 'private-proxy-canary')
        self.assertEqual(self.f.calls[0][3]['SSL_CERT_FILE'], 'private-ca-canary')
        for row in self.f.calls[1:]:
            self.assertFalse(set(row[3]) & set(g.TRANSPORT_KEYS))
        for row in self.f.calls:
            self.assertNotIn('LD_PRELOAD', row[3])
            self.assertNotIn('PYTHONPATH', row[3])
        self.assertEqual(len(self.f.verified), 4)
        self.assertEqual(self.f.libs.call_count, 4)
        self.assertEqual(self.f.elf.call_count, 1)
        self.assertEqual(len(self.f.trees), 2)
        self.assertEqual(len(self.f.package['selected']), 39)
        self.assertNotIn('private', json.dumps(result))
        self.assertNotIn(str(self.f.work), json.dumps(result))
        self.assertIn('private_canary', (self.f.work / 'icarus_libraries_private.json').read_text())
        self.assertEqual(self.f.calls[1][1][-2:], [str(self.f.work / 'fixtures/fifo_ready_split_miter.sv'),
                                                  str(self.f.work / 'fixtures/fifo_valid_split_cases.sv')])
        self.assertEqual(SOURCE_BUFFERS[g.CASES].splitlines()[228].strip(), b'$finish;')

    def test_load_checks_entire_closure_before_any_compile(self):
        for name in g.REQUIRED_SOURCES:
            buffers = dict(SOURCE_BUFFERS)
            buffers[name] = buffers[name] + b'\n'
            with self.subTest(name=name), mock.patch('builtins.compile') as compile_mock:
                with self.assertRaises(ValueError) as caught:
                    g._load_helpers(self.f.repo, buffers)
                compile_mock.assert_not_called()
                self.assertEqual(caught.exception.safe_contract_boundary, 'ICARUS_CONTRACT_LOAD')
                self.assertEqual(caught.exception.safe_contract_code, 'SOURCE_LOAD')

    def test_compile_receives_exact_verified_buffer_objects(self):
        original = compile
        with mock.patch('builtins.compile', wraps=original) as recorder:
            g._load_helpers(self.f.repo, SOURCE_BUFFERS)
        self.assertEqual(recorder.call_count, 2)
        self.assertIs(recorder.call_args_list[0].args[0], SOURCE_BUFFERS[g.RUNNER])
        self.assertIs(recorder.call_args_list[1].args[0], SOURCE_BUFFERS[g.ACQUISITION])

    def test_success_markers_do_not_accept_partial_extra_or_wrong_counts(self):
        base = ('\n'.join(sorted(self.f.micro.FIFO_LINES)) + '\n' + self.f.micro.FIFO_PASS + '\n' +
                str(self.f.work / 'fixtures/fifo_valid_split_cases.sv') + ':229: $finish called at 1 (1ps)\n').encode()
        for bad in (base + b'extra\n', base.replace(b'checks=1294', b'checks=1293', 1),
                    base.replace(b':229:', b':228:'), b'PASS\n', base.replace(b'(1ps)', b'(1ns)')):
            with self.subTest(bad=bad[-25:]), self.assertRaises(ValueError):
                self.f.micro.fifo_observation(bad, self.f.work / 'fixtures/fifo_valid_split_cases.sv')

    def test_invalid_runtime_observation_blocks_success(self):
        self.f.hook = lambda name, row: row.update(raw_log=b'PASS\n') if name == 'fifo_run' else None
        self.rejected('FIFO_RUN_OBSERVATION', 'FIFO_OBSERVATION')

    def test_fixture_mutation_after_compile_stops_run(self):
        def hook(name, row):
            if name == 'fifo_compile':
                (self.f.work / 'fixtures/fifo_ready_split_miter.sv').write_bytes(b'mutation')
        self.f.hook = hook
        self.rejected('FIFO_AFTER_COMPILE_FIXTURES', 'INPUT_SHA')
        self.assertEqual(len(self.f.calls), 2)

    def test_source_mutation_after_acquisition_stops_compile(self):
        def hook(name, row):
            if name == 'icarus_acquire':
                (self.f.repo / g.ACQUISITION).write_bytes(b'mutation')
        self.f.hook = hook
        self.rejected('FINAL_SOURCE_IDENTITIES', 'INPUT_SHA')
        self.assertEqual(len(self.f.calls), 1)

    def test_source_mutation_after_run_rejects(self):
        def hook(name, row):
            if name == 'fifo_run':
                (self.f.repo / g.MITER).write_bytes(b'mutation')
        self.f.hook = hook
        self.rejected('FIFO_AFTER_RUN_FIXTURES', 'INPUT_SHA')

    def test_changed_package_after_compile_stops_run(self):
        def hook(name, row):
            if name == 'fifo_compile':
                (self.f.work / 'icarus/mock_mutated').write_bytes(b'1')
        self.f.hook = hook
        self.rejected('FIFO_AFTER_COMPILE_STAGE', 'PACKAGE_STAGE')
        self.assertEqual(len(self.f.calls), 2)

    def test_library_change_after_compile_stops_run(self):
        self.f.libs.side_effect = [self.f.libraries, self.f.libraries, {'changed': True}]
        self.rejected('FIFO_AFTER_COMPILE_LIBRARIES', 'LIBRARY_CHANGED')
        self.assertEqual(len(self.f.calls), 2)

    def test_empty_compiled_artifact_rejected(self):
        def hook(name, row):
            if name == 'fifo_compile':
                (self.f.work / 'fifo/fifo.vvp').write_bytes(b'')
        self.f.hook = hook
        self.rejected('FIFO_COMPILED_NONEMPTY', 'COMPILED_EMPTY')

    def test_external_vpi_module_rejected(self):
        def hook(name, row):
            if name == 'fifo_compile':
                (self.f.work / 'fifo/fifo.vvp').write_bytes(b':vpi_module "/tmp/external/system.vpi";\n')
        self.f.hook = hook
        self.rejected('FIFO_COMPILED_MODULES', 'VVP_MODULES')

    def test_compiled_artifact_changed_after_run_rejected(self):
        def hook(name, row):
            if name == 'fifo_run':
                with (self.f.work / 'fifo/fifo.vvp').open('ab') as stream:
                    stream.write(b'# mutation\n')
        self.f.hook = hook
        self.rejected('FIFO_RUN_SAME_COMPILED', 'COMPILED_CHANGED')

    def test_original_phase_exception_survives_postflight_error(self):
        sentinel = TimeoutError('original private timeout canary')
        def hook(name, row):
            if name == 'fifo_compile':
                (self.f.work / 'icarus/mock_mutated').write_bytes(b'1')
                raise sentinel
        self.f.hook = hook
        with self.assertRaises(TimeoutError) as caught:
            self.f.run()
        self.assertIs(caught.exception, sentinel)
        self.assertEqual(len(self.f.calls), 2)
        self.assertEqual(len(self.f.verified), 3)

    def test_oversized_phase_log_rejected(self):
        self.f.hook = lambda name, row: row.update(raw_log=b'x' * 65537) if name == 'fifo_compile' else None
        self.rejected('PHASE_LOG_POSTFLIGHT', 'PHASE_LOG_BOUND')

    def test_finite_boundaries_are_tied_to_completed_prefix(self):
        counts = g.CONTRACT_COMPLETED_COUNTS
        self.assertEqual(set(counts), set(g.PARENT_CONTRACTS))
        self.assertEqual(counts['ICARUS_CONTRACT_LOAD'], (0,))
        self.assertEqual(counts['ICARUS_STAGE_VERIFY'], (1,))
        self.assertEqual(counts['FIFO_AFTER_COMPILE_STAGE'], (2,))
        self.assertEqual(counts['FIFO_RUN_OBSERVATION'], (3,))
        self.assertEqual(counts['FINAL_SOURCE_IDENTITIES'], (0, 1, 2, 3))
        self.assertEqual(counts['FIFO_BEFORE_COMPILE_FIXTURES'], (0, 1))
        self.assertTrue(all(type(n) is int and 0 <= n <= 3 for values in counts.values() for n in values))

    def test_fixed_plus_library_path_exception_is_narrow(self):
        self.f.micro.path('/usr/lib/x86_64-linux-gnu/libstdc++.so.6.0.123')
        for path in ('/tmp/libstdc++.so.6', '/usr/lib/x86_64-linux-gnu/libstdc++.so.6.evil', '/tmp/a+b'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.f.micro.path(path)


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0]] + rest)
