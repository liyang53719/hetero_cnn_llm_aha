"""Synthetic ZIP and semantic-contract tests only; no real archive or native tools."""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('Use Python -I -S -B test_tiny.py.')
import ast
import builtins
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import struct
import tempfile
import time
import types
import unittest
from unittest import mock
import warnings
import zipfile

HERE = Path(__file__).absolute().parent
SOURCE = HERE / 'extract_idma.py'
RAW = SOURCE.read_bytes()
SIZE = 18268
SHA = 'c9367ce7401e0d6909ebb10f16222813a2436e71dece956772f013fd226a0b84'


def load(raw):
    if len(raw) != SIZE or hashlib.sha256(raw).hexdigest() != SHA:
        raise ValueError('source identity before compile')
    module = types.ModuleType('verified_tiny_idma')
    module.__file__ = str(SOURCE)
    module.__verified_source_pin__ = {'bytes': SIZE, 'sha256': SHA}
    exec(compile(raw, str(SOURCE), 'exec', dont_inherit=True), module.__dict__)
    return module


g = load(RAW)


def zipped(rows=None):
    if rows is None:
        rows = [('idma_export/a.sv', b'abc', stat.S_IFREG | 0o644)]
    buffer = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', UserWarning)
        with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_STORED) as z:
            for name, data, mode in rows:
                i = zipfile.ZipInfo(name)
                i.create_system = 3
                i.external_attr = mode << 16
                z.writestr(i, data)
    return buffer.getvalue()


def inspect(raw, count=1, size=3, digest=None):
    with zipfile.ZipFile(io.BytesIO(raw), 'r') as z:
        index = g.index_zip(z, count)
        return g.member(z, index, 'idma_export/a.sv', size, digest or g.sha(b'abc'))


def contract_fixture():
    sources = ['idma/s' + str(i) + '.sv' for i in range(294)]
    headers = ['idma/h' + str(i) + '.svh' for i in range(18)]
    admitted = {name: g.sha(b'abc') for name in sources + headers}
    manifest = dict(admitted)
    for name in set(g.EXTRAS) - {'SHA256SUMS.json'} | {g.CLOCK}:
        manifest[name] = g.sha(b'abc')
    for i in range(927 - len(manifest)):
        manifest['extra' + str(i)] = g.sha(b'x')
    closure = {'schema': 2, 'source_files': 294, 'include_directories': 8,
               'initial_filelist_defines': dict(g.DEFINES), 'admitted_input_hashes': admitted}
    lines = ['+define+' + name for name in g.DEFINES]
    lines += ['+incdir+@ROOT@/inc' + str(i) for i in range(8)]
    lines += ['@ROOT@/' + name for name in sources]
    return manifest, closure, ('\n'.join(lines) + '\n').encode()


class Tiny(unittest.TestCase):
    def test_01_source_bad_size_same_length_sha_precompile(self):
        for raw in (RAW + b'x', b'X' + RAW[1:]):
            with mock.patch.object(builtins, 'compile', side_effect=RuntimeError('no compile')) as compiler:
                with self.assertRaisesRegex(ValueError, 'before compile'):
                    load(raw)
                compiler.assert_not_called()

    def test_02_no_bare_assert_importlib_network_subprocess(self):
        nodes = list(ast.walk(ast.parse(RAW)))
        self.assertFalse(any(isinstance(node, ast.Assert) for node in nodes))
        imports = {a.name for n in nodes if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
        self.assertFalse(imports & {'subprocess', 'requests', 'socket', 'urllib', 'importlib'})
        self.assertNotIn(b'exec(', RAW)
        self.assertNotIn(b'.extractall(', RAW)

    def test_03_tiny_good_crc_size_hash(self):
        self.assertEqual(inspect(zipped()), b'abc')

    def test_04_unselected_unsafe_paths_rejected(self):
        for name in ['/abs', '../up', 'a/../up', 'a\\back', './dot', 'a//empty', 'C:/drive', 'dir/']:
            raw = zipped([('idma_export/a.sv', b'abc', stat.S_IFREG | 0o644),
                          (name, b'x', stat.S_IFREG | 0o644)])
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'unsafe'):
                inspect(raw, 2)

    def test_05_duplicate_and_nonregular(self):
        rows = [('idma_export/a.sv', b'abc', stat.S_IFREG | 0o644)] * 2
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            inspect(zipped(rows), 2)
        for mode in [stat.S_IFLNK | 0o777, stat.S_IFDIR | 0o700, stat.S_IFIFO | 0o600, 0o644]:
            raw = zipped([('idma_export/a.sv', b'abc', stat.S_IFREG | 0o644), ('unselected', b'x', mode)])
            with self.assertRaisesRegex(ValueError, 'nonregular'):
                inspect(raw, 2)

    def test_06_encrypted_metadata(self):
        for bit in [1, 0x40, 0x2000]:
            raw = bytearray(zipped())
            struct.pack_into('<H', raw, raw.index(b'PK\x01\x02') + 8, bit)
            with self.assertRaisesRegex(ValueError, 'encryption'):
                inspect(bytes(raw))

    def test_07_crc_size_and_sha_failures(self):
        raw = bytearray(zipped())
        struct.pack_into('<I', raw, raw.index(b'PK\x01\x02') + 16, 0)
        with self.assertRaises(zipfile.BadZipFile):
            inspect(bytes(raw))
        with self.assertRaisesRegex(ValueError, 'metadata size'):
            inspect(zipped(), size=4)
        with self.assertRaisesRegex(ValueError, 'SHA'):
            inspect(zipped(), digest='0' * 64)

    def test_08_semantic_319_contract(self):
        manifest, closure, filelist = contract_fixture()
        selected, basis = g.derive_selection(manifest, closure, filelist)
        self.assertEqual(len(selected), 319)
        self.assertEqual(len(basis['ordered_sources']), 294)
        self.assertEqual(len(basis['headers']), 18)
        self.assertIn(g.CLOCK, selected)
        self.assertTrue(set(g.EXTRAS) <= set(selected))
        self.assertNotIn('SAFE_IDENTITY.json', selected)

    def test_09_semantic_disagreement_and_counts_rejected(self):
        m, c, f = contract_fixture()
        bad = copy.deepcopy(c)
        bad['admitted_input_hashes']['idma/s0.sv'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'disagreement'):
            g.derive_selection(m, bad, f)
        with self.assertRaisesRegex(ValueError, 'token'):
            g.derive_selection(m, c, f + b'-f /escape\n')
        with self.assertRaisesRegex(ValueError, 'counts'):
            g.derive_selection(m, c, f + b'@ROOT@/idma/s0.sv\n')
        with self.assertRaisesRegex(ValueError, 'define'):
            g.derive_selection(m, c, f + b'+define+UVM\n')
        with self.assertRaisesRegex(ValueError, 'duplicate JSON'):
            g.unique_json(b'{"same":1,"same":2}')

    def test_10_archive_identity_before_zip_parse(self):
        with mock.patch.object(g.zipfile, 'ZipFile', side_effect=RuntimeError('no parsing')) as parser:
            with self.assertRaisesRegex(ValueError, 'before ZIP parse'):
                g.prepare(b'not-the-real-archive')
            parser.assert_not_called()

    def test_11_fresh_output_modes_overwrite_and_symlinks(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / 'fresh'
            fd = g.fresh(out)
            try:
                g.write(fd, 'sources/a.sv', b'abc')
                self.assertEqual(g.tree(fd), (['sources/a.sv'], 3))
                self.assertEqual((out / 'sources/a.sv').read_bytes(), b'abc')
                self.assertEqual(stat.S_IMODE(out.stat().st_mode), 0o700)
                self.assertEqual(stat.S_IMODE((out / 'sources/a.sv').stat().st_mode), 0o600)
                with self.assertRaises(FileExistsError):
                    g.write(fd, 'sources/a.sv', b'new')
                (out / 'link').symlink_to(Path(td))
                with self.assertRaises(OSError):
                    g.write(fd, 'link/escape', b'x')
            finally:
                os.close(fd)
            with self.assertRaises(FileExistsError):
                g.fresh(out)
            self.assertFalse((Path(td) / 'escape').exists())

    def test_12_checked_read_type_size_sha_symlink(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'tiny'
            p.write_bytes(b'abc')
            self.assertEqual(g.checked_read(p, 3, g.sha(b'abc'))[0], b'abc')
            with self.assertRaisesRegex(ValueError, 'size'):
                g.checked_read(p, 4, g.sha(b'abc'))
            with self.assertRaisesRegex(ValueError, 'identity'):
                g.checked_read(p, 3, '0' * 64)
            alias = Path(td) / 'link'
            alias.symlink_to(p)
            with self.assertRaises(OSError):
                g.checked_read(alias, 3, g.sha(b'abc'))

    def test_13_current_process_resource_limits_mocked(self):
        with mock.patch.object(g.resource, 'getrlimit', return_value=(-1, -1)), \
             mock.patch.object(g.resource, 'setrlimit') as resource_limits, \
             mock.patch.object(g.os, 'sched_getaffinity', side_effect=[{3, 4}, {3}]), \
             mock.patch.object(g.os, 'sched_setaffinity') as affinity, mock.patch.object(g, 'arm') as arm:
            g.limits(10.0)
            self.assertEqual(resource_limits.call_args_list, [mock.call(g.resource.RLIMIT_CPU, (40, 40)),
                             mock.call(g.resource.RLIMIT_AS, (512 * 1024**2, 512 * 1024**2)),
                             mock.call(g.resource.RLIMIT_FSIZE, (4 * 1024**2, 4 * 1024**2))])
            affinity.assert_called_once_with(0, {3})
            arm.assert_called_once_with(65.0)

    def test_14_failure_report_preserved_without_archive(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / 'failed'
            with mock.patch.object(g, 'limits'), mock.patch.object(g, 'arm'), \
                 mock.patch.object(g, 'checked_read', side_effect=ValueError('synthetic read failure')):
                with self.assertRaisesRegex(ValueError, 'synthetic read failure'):
                    g.extract('/unused/archive', out, time.monotonic())
            report = json.loads((out / 'EXTRACTION_REPORT.json').read_bytes())
            self.assertFalse(report['complete'])
            self.assertFalse(report['native_executed'])
            self.assertEqual(report['subset_inventory'], [])

    def test_15_default_entry_data_only(self):
        with mock.patch.object(sys, 'argv', ['extract_idma.py']), \
             mock.patch.object(g, 'extract', side_effect=RuntimeError('no extraction')) as run, \
             mock.patch.object(builtins, 'print') as output:
            g.main()
            run.assert_not_called()
            self.assertEqual(json.loads(output.call_args.args[0])['status'], 'SOURCE_ONLY_NO_ARCHIVE_READ_NO_EXTRACTION')

    def test_16_actual_loader_bad_size_same_length_sha_precompile(self):
        raw = (HERE / 'ENTRY.json').read_bytes()
        self.assertEqual(len(raw), 5433)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         'cd4289a148af3da6e67747085d3a72467386a28cd7d8b3e6e64e79f20851fad7')
        code = compile(json.loads(raw)['bootstrap'], '<pinned actual loader>', 'exec', dont_inherit=True)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'extract_idma.py'
            for content in (RAW + b'x', b'X' + RAW[1:]):
                path.write_bytes(content)
                with mock.patch.object(sys, 'argv', ['-c', str(path)]), \
                     mock.patch.object(builtins, 'compile', side_effect=RuntimeError('no compile')) as compiler:
                    with self.assertRaisesRegex(ValueError, 'before compile'):
                        exec(code, {})
                    compiler.assert_not_called()

    def test_17_actual_loader_source_only_and_isolation_guard(self):
        raw = (HERE / 'ENTRY.json').read_bytes()
        self.assertEqual(len(raw), 5433)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         'cd4289a148af3da6e67747085d3a72467386a28cd7d8b3e6e64e79f20851fad7')
        code = compile(json.loads(raw)['bootstrap'], '<pinned actual loader>', 'exec', dont_inherit=True)
        with mock.patch.object(sys, 'argv', ['-c', str(SOURCE)]), \
             mock.patch.object(builtins, 'print') as output:
            exec(code, {})
        self.assertEqual(json.loads(output.call_args.args[0])['status'], 'SOURCE_ONLY_NO_ARCHIVE_READ_NO_EXTRACTION')
        with mock.patch.object(sys, 'flags', types.SimpleNamespace(isolated=False)), \
             mock.patch.object(os, 'open', side_effect=RuntimeError('must not read local code')) as read:
            with self.assertRaises(SystemExit):
                exec(code, {})
            read.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
