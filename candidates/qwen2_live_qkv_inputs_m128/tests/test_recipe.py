"""Cold stdlib gates only. No weights, network, compiler, Torch, or RTL execution."""
import ast
import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

PACKAGE = Path(__file__).resolve().parents[1]
ROOT = PACKAGE.parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(PACKAGE))
import recipe as R

SCRATCH = ROOT / 'work/qwen2_live_qkv_inputs_m128/cold'


# Keep source admission separate from payload and side-effect rejection. The
# header exception names one pinned metadata file, never every *.header.bin.
COLD_PROGRAM = r'''
import builtins, importlib.abc, json, os, pathlib, runpy, sys
recipe = pathlib.Path(sys.argv[1]).resolve()
root = recipe.parents[2]
sources = {root / name for name in json.loads(sys.argv[2])}
stdlib = pathlib.Path(os.__file__).resolve().parent
payload_roots = tuple(root / name for name in ('work', 'raw', 'oracle', 'oracles'))
header = root / 'config/upstream/weight_headers/qwen2_1p5b/model.safetensors.header.bin'
payload_suffixes = {'.bin', '.safetensors', '.bf16', '.bf16le', '.f16', '.f16le',
                    '.f32', '.f32le', '.npy', '.npz', '.pt', '.pth', '.pkl', '.pickle'}
forbidden = {'torch', 'numpy', 'transformers', 'ctypes', 'urllib'}
original_import = builtins.__import__
def guarded_import(name, *args, **kwargs):
    if name.split('.')[0] in forbidden:
        raise RuntimeError('forbidden cold dependency: ' + name)
    return original_import(name, *args, **kwargs)
builtins.__import__ = guarded_import
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in forbidden:
            raise RuntimeError('forbidden cold dependency: ' + fullname)
sys.meta_path.insert(0, Block())
def audit(event, args):
    if event.startswith(('socket.', 'subprocess.', 'os.exec', 'os.spawn', 'os.posix_spawn')) or event in (
            'os.system', 'os.fork', 'os.forkpty', 'os.startfile', 'os.mkdir', 'os.remove',
            'os.rmdir', 'os.rename', 'os.link', 'os.symlink', 'os.chmod', 'os.chown',
            'os.truncate', 'os.utime'):
        raise RuntimeError('forbidden cold event: ' + event)
    if event == 'open':
        name, mode, flags = args
        if ((isinstance(mode, str) and any(c in mode for c in 'wax+')) or
                (flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))):
            raise RuntimeError('forbidden cold write: ' + str(name))
        if not isinstance(name, (str, bytes)):
            raise RuntimeError('forbidden cold file descriptor: ' + str(name))
        path = pathlib.Path(os.path.abspath(os.fsdecode(name)))
        resolved = path.resolve()
        if any(path.is_relative_to(base) or resolved.is_relative_to(base) for base in payload_roots):
            raise RuntimeError('forbidden cold payload root: ' + str(path))
        if (path.suffix.lower() in payload_suffixes or resolved.suffix.lower() in payload_suffixes) and not (
                path == resolved == header):
            raise RuntimeError('forbidden cold payload suffix: ' + str(path))
        source = path == resolved and path in sources
        stdlib_import = resolved.is_relative_to(stdlib) and resolved.suffix in ('.py', '.pyc')
        if not (source or stdlib_import):
            raise RuntimeError('forbidden cold file access: ' + str(path))
sys.addaudithook(audit)
if len(sys.argv) > 3:
    exec(sys.argv[3])
else:
    sys.argv = [str(recipe)]
    runpy.run_path(sys.argv[0], run_name='__main__')
'''



class RecipeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pins = R.load_pins(ROOT)
        cls.metadata_verdict_blocks = 0
        cls.metadata_baselines = 0
        SCRATCH.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        print('METADATA_MUTATION_VERDICT_BLOCKS=%d BASELINES=%d' %
              (cls.metadata_verdict_blocks, cls.metadata_baselines))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='cold-', dir=SCRATCH)
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def reject(self, function, *args, **kwargs):
        with self.assertRaises((R.Rejected, FileExistsError)):
            function(*args, **kwargs)

    def cold_run(self, root, optimize, probe=None):
        # The audited child may read only fixed checkout sources/metadata and
        # stdlib import files. A runner ancestor named "work" is not a payload.
        sources = [*self.pins['sources'],
                   'candidates/qwen2_live_qkv_inputs_m128/recipe.py',
                   'candidates/qwen2_live_qkv_inputs_m128/pins.json']
        argv = [sys.executable, '-B', '-S', *optimize, '-c', COLD_PROGRAM,
                str(root / 'candidates/qwen2_live_qkv_inputs_m128/recipe.py'),
                json.dumps(sources)]
        if probe is not None:
            argv.append(probe)
        return subprocess.run(argv, cwd=root, capture_output=True, text=True)

    def assert_cold(self, root):
        for optimize in ([], ['-O']):
            with self.subTest(root=str(root), optimize=optimize):
                run = self.cold_run(root, optimize)
                self.assertEqual(run.returncode, 0, run.stderr)
                result = json.loads(run.stdout)
                self.assertEqual(result['status'], 'NOT_EXECUTED')
                self.assertEqual(result['cold_check'], 'PASS')
                for key in ('torch_imported', 'numpy_imported', 'network_used', 'raw_payload_read',
                            'model_executed', 'rtl_executed', 'outputs_written'):
                    self.assertIs(result[key], False)

    def github_checkout(self):
        root = self.root / 'home/runner/work/repo/repo'
        (root / '.git').mkdir(parents=True)
        for name in (*self.pins['sources'],
                     'candidates/qwen2_live_qkv_inputs_m128/recipe.py',
                     'candidates/qwen2_live_qkv_inputs_m128/pins.json'):
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / name).read_bytes())
        return root

    def test_default_cold_is_stdlib_and_no_side_effects(self):
        self.assert_cold(ROOT)

    def test_default_cold_accepts_github_workspace_ancestor(self):
        # Run the real pinned recipe, including the exact header.bin source.
        self.assert_cold(self.github_checkout())

    def test_cold_audit_rejects_payload_aliases_and_side_effects(self):
        root = self.github_checkout()
        for name in ('work/payload.json', 'raw/payload.json', 'oracle/payload.json',
                     'oracles/payload.json', 'payload.bin', 'payload.f32le',
                     'payload.safetensors', 'model.safetensors.header.bin'):
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('synthetic forbidden payload')
        (root / 'linked-work').symlink_to(root / 'work', target_is_directory=True)
        (root / 'linked.json').symlink_to(root / 'work/payload.json')
        external = self.root / 'external-oracle.json'
        external.write_text('synthetic external oracle')
        (root / 'external.json').symlink_to(external)
        # Even an explicitly admitted source must not alias into ignored work.
        header = root / 'config/upstream/weight_headers/qwen2_1p5b/model.safetensors.header.bin'
        header.unlink()
        header.symlink_to(root / 'work/payload.json')
        reads = ['work/payload.json', './work/payload.json', 'config/../work/payload.json',
                 'raw/payload.json', 'oracle/payload.json', 'oracles/payload.json',
                 'payload.bin', 'payload.f32le', 'payload.safetensors',
                 'model.safetensors.header.bin', 'linked-work/payload.json',
                 'linked.json', 'external.json', str(external),
                 str(root / 'work/payload.json'), str(header)]
        probes = ["open(%r, 'rb').read()" % name for name in reads]
        probes += ["open(os.fsencode('work/payload.json'), 'rb').read()",
                   "os.open('work/payload.json', os.O_RDONLY)",
                   "open('new.txt', 'w')", "open('new.txt', 'a')",
                   "open('candidates/qwen2_live_qkv_inputs_m128/recipe.py', 'r+')",
                   "os.open('new.txt', os.O_WRONLY | os.O_CREAT)",
                   "os.mkdir('new-directory')", "os.remove('payload.bin')",
                   "os.system('exit 0')", "import subprocess; subprocess.run(['true'])",
                   "import socket; socket.socket()"]
        probes += ['import ' + name for name in ('torch', 'numpy', 'transformers', 'ctypes', 'urllib')]
        for optimize in ([], ['-O']):
            for probe in probes:
                with self.subTest(optimize=optimize, probe=probe):
                    run = self.cold_run(root, optimize, probe)
                    self.assertNotEqual(run.returncode, 0, run.stdout)
                    self.assertIn('forbidden cold', run.stderr)
        self.assertFalse((root / 'new.txt').exists())
        self.assertFalse((root / 'new-directory').exists())
        self.assertTrue((root / 'payload.bin').exists())

    def test_exact_pinned_coverage(self):
        self.assertEqual(R.source_check(ROOT, self.pins), {
            'pinned_source_files': 18, 'official_ast_nodes': 15, 'raw_tensors': 8,
            'payload_bytes': 7085056, 'input_roles': 9, 'reference_nodes': 9})
        self.assertEqual(set(self.pins['roles']), {'x', 'gamma0', 'wq', 'wk', 'wv', 'bq', 'bk', 'bv', 'rope'})
        self.assertEqual(self.pins['contract']['token_ids'], list(range(128)))
        self.assertIs(self.pins['contract']['direct_gamma'], True)

    def test_pin_file_tamper_rejected(self):
        target = self.root / 'candidates/qwen2_live_qkv_inputs_m128/pins.json'
        target.parent.mkdir(parents=True)
        target.write_bytes((PACKAGE / 'pins.json').read_bytes() + b' ')
        self.reject(R.load_pins, self.root)

    def test_source_tamper_rejected(self):
        (self.root / '.git').mkdir()
        (self.root / 'source.py').write_text('changed source')
        pins = copy.deepcopy(self.pins)
        pins['sources'] = {'source.py': {'bytes': 1, 'sha256': '0' * 64}}
        self.reject(R.source_check, self.root, pins)

    def test_exact_types_reject_boolean_dimensions(self):
        self.assertFalse(R.same([True, 16, 1536], [1, 16, 1536]))
        self.reject(R.fields, {'rows': True}, {'rows': 1}, 'rows')
        self.reject(R.fields, {'rows': 16.0}, {'rows': 16}, 'rows')
        self.assertFalse(R.same({'a': 1, 'extra': 2}, {'a': 1}))

    def test_duplicate_and_nonfinite_json_rejected(self):
        for data in ('{"a":1,"a":2}', '{"x":NaN}', '{"x":Infinity}', '{"x":-Infinity}'):
            self.reject(R.parse_json, data)

    def test_timestamp_rejects_naive_or_wrong_zone(self):
        R.timestamp('2026-10-14T08:28:22.438065+00:00')
        for value in (None, True, 1, 'yesterday', '2026-10-14T08:28:22', '2026-10-14T08:28:22+01:00'):
            self.reject(R.timestamp, value)

    def test_paths_reject_absolute_traversal_aliases(self):
        for name in ('/tmp/a', '../a', './a', 'a/../b', 'a//b', 'a\\b', ''):
            self.reject(R.safe_path, self.root, name)

    def test_paths_reject_parent_or_file_symlinks(self):
        (self.root / 'target').mkdir()
        (self.root / 'linked').symlink_to(self.root / 'target', target_is_directory=True)
        self.reject(R.safe_path, self.root, 'linked/new/file')
        (self.root / 'filelink').symlink_to(self.root / 'missing')
        self.reject(R.safe_path, self.root, 'filelink')

    def test_stage_namespace_is_narrow(self):
        good = R.OUTPUT_PREFIX + '/run_01/raw'
        self.assertEqual(R.stage_path(self.root, good), self.root / good)
        for name in ('work/arbitrary/run', 'work/qwen2_input_recovery_20261014',
                     R.OUTPUT_PREFIX, R.OUTPUT_PREFIX + '/r', R.OUTPUT_PREFIX + '/r/s/nested',
                     R.OUTPUT_PREFIX + '/r/../s', R.OUTPUT_PREFIX + '/r/s/',
                     R.OUTPUT_PREFIX + '/-run/s', R.OUTPUT_PREFIX + '/r/s.bad'):
            self.reject(R.stage_path, self.root, name)

    def test_existing_empty_or_nonempty_output_rejected(self):
        relative = R.OUTPUT_PREFIX + '/run/raw'
        target = self.root / relative
        target.mkdir(parents=True)
        self.reject(R.fresh_output, self.root, relative)
        (target / 'receipt.json').write_text('immutable')
        self.reject(R.fresh_output, self.root, relative)
        self.assertEqual((target / 'receipt.json').read_text(), 'immutable')

    def test_output_input_overlap_rejected(self):
        relative = R.OUTPUT_PREFIX + '/run/raw'
        out = self.root / relative
        self.reject(R.fresh_output, self.root, relative, [out])
        self.reject(R.fresh_output, self.root, relative, [out.parent])
        self.reject(R.fresh_output, self.root, relative, [out / 'nested'])

    def test_write_is_exclusive(self):
        path = self.root / 'receipt.json'
        R.write_new(path, b'first')
        self.reject(R.write_new, path, b'second')
        self.assertEqual(path.read_bytes(), b'first')

    def test_all_execution_actions_require_opt_in(self):
        for action in R.STAGES:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as err:
                rc = R.main(['--action', action])
            self.assertEqual(rc, 2)
            self.assertIn('--execute required', err.getvalue())
        self.assertNotIn('torch', sys.modules)
        self.assertNotIn('numpy', sys.modules)

    def test_cold_rejects_execution_or_data_path_options(self):
        for args in (['--execute'], ['--download'], ['--reuse-frozen'],
                     ['--out', R.OUTPUT_PREFIX + '/r/s'], ['--subset', 'work/old']):
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(R.main(args), 2)

    def test_wrong_root_rejected(self):
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(R.main(['--root', str(self.root)]), 2)
        self.assertIn('checkout', err.getvalue())

    def test_reject_before_network_or_capture_import(self):
        for args in (
            ['--action', 'acquire', '--execute', '--download', '--out', 'work/other/x'],
            ['--action', 'acquire', '--execute', '--out', R.OUTPUT_PREFIX + '/rejected-no-source/raw'],
            ['--action', 'capture', '--execute', '--out', R.OUTPUT_PREFIX + '/rejected-no-input/ref'],
            ['--action', 'audit', '--execute', '--download', '--out', R.OUTPUT_PREFIX + '/rejected-download/audit']):
            with mock.patch.object(R, 'download_range', side_effect=RuntimeError('network called')):
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(R.main(args), 2)
        self.assertNotIn('capture', sys.modules)
        self.assertNotIn('torch', sys.modules)
        self.assertFalse((ROOT / R.OUTPUT_PREFIX / 'rejected-no-source').exists())

    def test_acquisition_cannot_silently_choose_source(self):
        out = self.root / 'never-created'
        for reuse, download in ((False, False), (True, True)):
            self.reject(R.acquire, self.root, self.pins, out, reuse_frozen=reuse, download=download)
        self.assertFalse(out.exists())

    def test_exact_http_receipt_identity(self):
        spec = self.pins['tensors'][0]
        good = {'acquired_at': '2026-10-14T00:00:00+00:00', 'requested_url': self.pins['shard']['url'],
                'request_range': 'bytes=%d-%d' % (spec['start'], spec['end']), 'status': 206,
                'content_range': 'bytes %d-%d/%d' % (spec['start'], spec['end'], self.pins['shard']['file_bytes']),
                'bytes': spec['bytes'], 'sha256': spec['sha256']}
        R.verify_http(good, spec, self.pins)
        for key, bad in (('status', 200), ('status', True), ('bytes', True), ('bytes', spec['bytes'] + 1),
                         ('sha256', '0' * 64), ('requested_url', self.pins['shard']['url'].replace(self.pins['contract']['revision'], 'main')),
                         ('request_range', 'bytes=0-1'), ('content_range', 'bytes 0-1/2'), ('acquired_at', 'old')):
            changed = {**good, key: bad}
            self.reject(R.verify_http, changed, spec, self.pins)

    def test_http_refuses_full_body_wrong_range_length_or_encoding(self):
        import urllib.request
        spec = self.pins['tensors'][0]
        expected = 'bytes %d-%d/%d' % (spec['start'], spec['end'], self.pins['shard']['file_bytes'])
        headers = {'Content-Range': expected, 'Content-Length': str(spec['bytes']), 'Content-Encoding': 'identity'}
        for status, changed in ((200, {}), (206, {'Content-Range': 'bytes 0-1/2'}),
                                (206, {'Content-Length': '2'}), (206, {'Content-Encoding': 'gzip'})):
            response = mock.MagicMock()
            response.__enter__.return_value = response
            response.status = status
            response.headers = {**headers, **changed}
            with mock.patch.object(urllib.request, 'urlopen', return_value=response) as opener:
                self.reject(R.download_range, self.pins, spec)
                request = opener.call_args.args[0]
                self.assertEqual(request.full_url, self.pins['shard']['url'])
                self.assertEqual(request.get_header('Range'), 'bytes=%d-%d' % (spec['start'], spec['end']))
                response.read.assert_not_called()
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.status, response.headers = 206, headers
        response.read.return_value = b''
        with mock.patch.object(urllib.request, 'urlopen', return_value=response):
            self.reject(R.download_range, self.pins, spec)
            response.read.assert_called_once_with(spec['bytes'] + 1)
        self.reject(R.download_range, self.pins, {**spec, 'bytes': 4718593})

    def test_report_identity_rejects_historical_full_layer_or_claims(self):
        good = R.report(ROOT, self.pins, 'acquire')
        good.update(status='RECOVERED_PINNED_QWEN2_PREFIX_SUBSET_ONLY', payload_bytes=7085056,
                    acquisition='fresh_HTTP206', tensors=[])
        R.verify_report(good, ROOT, self.pins, 'acquire')
        for key, value in (('schema', True), ('rows', 16), ('direct_gamma', False),
                           ('old_pass_inherited', True), ('rtl_executed', True), ('intermediate_preloads', 1)):
            changed = copy.deepcopy(good)
            changed['contract'][key] = value
            self.reject(R.verify_report, changed, ROOT, self.pins, 'acquire')
        self.reject(R.verify_report, {'status': 'ACQUIRED_PINNED_QWEN2_LAYER0_AND_EMBEDDING_ROWS_ONLY'},
                    ROOT, self.pins, 'acquire')
        self.reject(R.verify_report, {**good, 'old_pass_inherited': True}, ROOT, self.pins, 'acquire')
        for key, value in (('stage', 'materialize'), ('source_pins_sha256', '0' * 64), ('recipe', {})):
            self.reject(R.verify_report, {**good, key: value}, ROOT, self.pins, 'acquire')

    def test_node_metadata_coverage_path_shape_dtype_hash_rejections(self):
        specs = self.pins['roles']
        good = {name: {**spec, 'file': name + '.bin'} for name, spec in specs.items()}
        with mock.patch.object(R, 'checked', return_value=b''):
            R.check_records(self.root, good, specs, '.bin')
            missing = copy.deepcopy(good)
            missing.pop('x')
            self.reject(R.check_records, self.root, missing, specs, '.bin')
            self.reject(R.check_records, self.root, {**good, 'n0': good['x']}, specs, '.bin')
            changed = copy.deepcopy(good)
            changed['x']['unreviewed_extra'] = True
            self.reject(R.check_records, self.root, changed, specs, '.bin')
            for field, value in (('file', '../x.bin'), ('shape', [1, 16, 1536]),
                                 ('dtype', 'bfloat16'), ('bytes', True), ('sha256', '0' * 64)):
                changed = copy.deepcopy(good)
                changed['x'][field] = value
                self.reject(R.check_records, self.root, changed, specs, '.bin')

    def test_subset_metadata_inventory_receipts_and_cross_identity(self):
        relative = R.OUTPUT_PREFIX + '/unit/raw'
        directory = self.root / relative
        directory.mkdir(parents=True)
        good = R.report(ROOT, self.pins, 'acquire')
        good.update(status='RECOVERED_PINNED_QWEN2_PREFIX_SUBSET_ONLY', payload_bytes=7085056, acquisition='fresh_HTTP206')
        records = []
        for spec in self.pins['tensors']:
            receipt = {'acquired_at': '2026-10-14T00:00:00+00:00',
                'requested_url': self.pins['shard']['url'],
                'request_range': 'bytes=%d-%d' % (spec['start'], spec['end']), 'status': 206,
                'content_range': 'bytes %d-%d/%d' % (spec['start'], spec['end'], self.pins['shard']['file_bytes']),
                'bytes': spec['bytes'], 'sha256': spec['sha256']}
            records.append({**spec, 'http_ranges': [receipt]})
            (directory / (spec['local_name'] + '.receipt.json')).write_bytes(R.json_bytes(receipt))
        good['tensors'] = records
        manifest = directory / 'subset_manifest.json'
        def read(value):
            manifest.write_bytes(R.json_bytes(value))
            return R.read_subset(self.root, self.pins, relative)
        # Payload byte validation is mocked ONLY for this metadata-layer unit test;
        # byte/hash rejection is separately tested using checked(). No model data.
        with mock.patch.object(R, 'recipe_identity', return_value=good['recipe']), \
                mock.patch.object(R, 'checked', return_value=b''):
            read(good)
            for label, changed in self.mutations(good):
                with self.subTest(top_level=label):
                    self.reject(read, changed)
            mutations = []
            missing = copy.deepcopy(good)
            missing['tensors'].pop()
            mutations.append(missing)
            extra = copy.deepcopy(good)
            extra['tensors'].append(extra['tensors'][0])
            mutations.append(extra)
            swapped = copy.deepcopy(good)
            swapped['tensors'][0], swapped['tensors'][1] = swapped['tensors'][1], swapped['tensors'][0]
            mutations.append(swapped)
            duplicate = copy.deepcopy(good)
            duplicate['tensors'][1] = duplicate['tensors'][0]
            mutations.append(duplicate)
            for key, value in (('file', '../weights.bin'), ('dtype', 'F32'), ('bytes', True),
                               ('shape', [True, 1536]), ('sha256', '0' * 64), ('http_ranges', [])):
                changed = copy.deepcopy(good)
                changed['tensors'][0][key] = value
                mutations.append(changed)
            for changed in mutations:
                self.reject(read, changed)
            receipt_path = directory / (records[0]['local_name'] + '.receipt.json')
            changed_receipt = {**records[0]['http_ranges'][0], 'acquired_at': '2026-10-14T00:00:01+00:00'}
            receipt_path.write_bytes(R.json_bytes(changed_receipt))
            self.reject(read, good)

    def test_checked_requires_both_byte_count_and_digest(self):
        path = self.root / 'scalar.dat'
        path.write_bytes(struct.pack('<I', 0x3f800000))
        good = {'bytes': 4, 'sha256': R.sha(path.read_bytes())}
        self.assertEqual(R.checked(self.root, 'scalar.dat', good), path.read_bytes())
        for pin in ({**good, 'bytes': True}, {**good, 'bytes': 8}, {**good, 'sha256': '0' * 64}):
            self.reject(R.checked, self.root, 'scalar.dat', pin)

    def test_input_manifest_binding_rejects_stale_subset(self):
        relative = R.OUTPUT_PREFIX + '/unit/inputs'
        directory = self.root / relative
        directory.mkdir(parents=True)
        manifest = R.report(ROOT, self.pins, 'materialize')
        manifest.update(status='PINNED_PREFIX_INPUTS_READY_NO_MODEL_EXECUTION',
                        subset=R.OUTPUT_PREFIX + '/unit/raw', subset_manifest_sha256='a' * 64,
                        torch_imported=False, numpy_imported=False)
        (directory / 'INPUTS_READY.json').write_bytes(R.json_bytes(manifest))
        with mock.patch.object(R, 'recipe_identity', return_value=manifest['recipe']):
            self.reject(R.read_inputs, self.root, self.pins, relative, manifest['subset'], 'b' * 64)
            self.reject(R.read_inputs, self.root, self.pins, relative, R.OUTPUT_PREFIX + '/other/raw', 'a' * 64)

    def test_scalar_exact_widening_has_no_plus_one(self):
        word = struct.pack('<H', 0x3f80)
        self.assertEqual(R.widen_bf16(word), struct.pack('<I', 0x3f800000))
        self.assertEqual(R.widen_bf16(struct.pack('<H', 0)), struct.pack('<I', 0))
        self.reject(R.widen_bf16, b'\x00')

    def test_transpose_does_not_round_or_convert_bf16(self):
        # Generated index words test the address rule; no model tensor fixture.
        raw = b''.join(struct.pack('<H', n) for n in range(6))
        moved = R.transpose_words(raw, 2, 3)
        for row in range(2):
            for column in range(3):
                self.assertEqual(moved[(column * 2 + row) * 2:(column * 2 + row + 1) * 2],
                                 raw[(row * 3 + column) * 2:(row * 3 + column + 1) * 2])
        self.reject(R.transpose_words, raw, True, 6)
        self.reject(R.transpose_words, raw, 2, 4)

    def test_bf16_rounding_ties_even_and_finite_gates(self):
        self.assertEqual(R.bf16_rne_word(0x3f808000), 0x3f800000)
        self.assertEqual(R.bf16_rne_word(0x3f818000), 0x3f820000)
        self.assertEqual(R.bf16_rne_word(0xbf818000), 0xbf820000)
        self.assertEqual(R.bf16_rne_word(0x80000000), 0x80000000)
        for value in (True, -1, 0x100000000, 0x7f800000, 0x7fc00000, 0x7f7fffff):
            self.reject(R.bf16_rne_word, value)

    def test_official_ast_coverage_and_each_pin(self):
        self.assertEqual(len(R.official_nodes(ROOT, self.pins)), 15)
        for index in range(15):
            changed = copy.deepcopy(self.pins)
            changed['official_ast_nodes'][index]['ast_sha256'] = '0' * 64
            self.reject(R.official_nodes, ROOT, changed)
        changed = copy.deepcopy(self.pins)
        changed['official_ast_nodes'].pop()
        self.reject(R.official_nodes, ROOT, changed)

    def test_c_source_is_hash_pinned_without_import_or_compile(self):
        source = R.rope_source(ROOT, self.pins)
        self.assertEqual(R.sha(source.encode()), self.pins['rope_c_source_sha256'])
        self.reject(R.rope_source, ROOT, {**self.pins, 'rope_c_source_sha256': '0' * 64})

    def test_qk_export_layout_is_address_rule_not_error_selection(self):
        shape = [1, 2, 128, 128]
        raw = b''.join(struct.pack('<I', n) for n in range(2 * 128 * 128))
        out = R.head_to_token(raw, shape)
        for head in range(2):
            for token in range(128):
                src, dst = (head * 128 + token) * 512, (token * 2 + head) * 512
                self.assertEqual(out[dst:dst + 512], raw[src:src + 512])
        for bad in ([True,2,128,128],[1,2,16,128],[1,2,127,128],[1,2,129,128],
                    [1,3,128,128],[1,2,128,64]):
            self.reject(R.head_to_token, raw, bad)

    def synthetic_runtime(self):
        # This is deliberately generated test metadata, not an archived build log.
        # The test pin is local to the unit fixture; production load_pins remains
        # cryptographically bound to the real reviewed Torch build-text digest.
        pins = copy.deepcopy(self.pins)
        build = 'SYNTHETIC UNIT METADATA: TORCH_VERSION=2.10.0 COMMIT_SHA=' + pins['runtime_requirements']['torch_commit']
        build += ' USE_CUDA=0 CPU capability usage: AVX512'
        pins['runtime_requirements']['torch_build_sha256'] = R.sha(build.encode())
        runtime = {**pins['runtime_requirements'], 'python': sys.version,
                   'torch_build': build, 'affinity': sorted(os.sched_getaffinity(0)),
                   'environment': copy.deepcopy(pins['capture_environment']),
                   'new_process': True, 'historical_runtime_equivalence_claimed': False,
                   'identity_scope': R.RUNTIME_IDENTITY_SCOPE,
                   'native_files': {key: {'path': '/synthetic-unit/' + key, 'bytes': 1, 'sha256': 'a' * 64}
                                    for key in ('torch_C', 'numpy_multiarray', 'libtorch_cpu.so', 'libc10.so', 'libtorch_python.so')}}
        runtime['native_files']['python'] = R.python_identity()
        patch = mock.patch.object(R, 'runtime_files', return_value=copy.deepcopy(runtime['native_files']))
        patch.start()
        self.addCleanup(patch.stop)
        return pins, runtime

    def test_current_key_runtime_identity_is_required(self):
        pins, runtime = self.synthetic_runtime()
        R.check_runtime(runtime, pins)
        for key, value in (('torch_commit', 'wrong'), ('threads', True), ('new_process', False),
                           ('historical_runtime_equivalence_claimed', True), ('native_files', {})):
            self.reject(R.check_runtime, {**runtime, key: value}, pins)
        self.reject(R.check_runtime, runtime, self.pins)

    def metadata_audit_fixture(self):
        """Complete synthetic metadata, no real raw data, model or compiler execution."""
        pins, runtime = self.synthetic_runtime()
        subset = R.OUTPUT_PREFIX + '/unit/raw'
        inputs = R.OUTPUT_PREFIX + '/unit/inputs'
        reference = R.OUTPUT_PREFIX + '/unit/reference'
        directory = self.root / inputs
        build_dir = directory / 'rope_build'
        build_dir.mkdir(parents=True, exist_ok=True)
        # Pinned C text is source only. The placeholder is never loaded or run.
        (build_dir / 'independent.c').write_text(R.rope_source(ROOT, pins))
        (build_dir / 'independent.so').write_bytes(b'UNEXECUTED UNIT PLACEHOLDER')
        compiler = {'compiler': 'gcc (synthetic unit compiler, not executed) 0.0', 'compiler_sha256': 'c' * 64}
        build = {'command': R.compile_command(directory), 'source_sha256': pins['rope_c_source_sha256'],
                 'binary_sha256': R.sha((build_dir / 'independent.so').read_bytes()), **compiler,
                 'historical_binary_identity_claimed': False}
        material = R.report(ROOT, pins, 'materialize')
        material.update(status='PINNED_PREFIX_INPUTS_READY_NO_MODEL_EXECUTION',
                        roles={name: {**spec, 'file': name + '.bin'} for name, spec in pins['roles'].items()},
                        subset=subset, subset_manifest_sha256='a' * 64,
                        rope={**pins['rope'], 'file': 'rope_full.f32le'}, rope_build=build,
                        python=sys.version, python_executable=R.python_identity(),
                        torch_imported=False, numpy_imported=False)
        ref = R.report(ROOT, pins, 'capture')
        ref.update(status='FRESH_OFFICIAL_AST_PREFIX_CAPTURE_ONLY', subset=subset, inputs=inputs,
                   subset_manifest_sha256='a' * 64, input_ready_sha256=R.sha(R.json_bytes(material)),
                   official_ast_nodes=pins['official_ast_nodes'],
                   outputs={name: {**spec, 'file': name + '.f32le'} for name, spec in pins['references'].items()},
                   runtime=runtime, official_ast_subset_executed=True, old_runtime_identity_claimed=False,
                   posthoc_oracle_only=True, numerical_acceptance_claimed=False, transformers_imported=False,
                   rotary_cache_max_position_embeddings=256, original_config_max_position_embeddings=32768,
                   configuration_equivalence_claimed=False, layout_rule=pins['layout_rule'], reference_freeze=pins['reference_freeze'],
                   reference_hash_comparison=R.expected_comparison(pins), old_raw_archive_read=False)
        refdir = self.root / reference
        refdir.mkdir(parents=True, exist_ok=True)
        return pins, subset, inputs, reference, material, ref, compiler

    def run_metadata_audit(self, fixture, material, reference, expect_pass=False, rebind=True, computed=None):
        pins, subset, inputs, refpath, _, _, compiler = fixture
        (self.root / inputs / 'INPUTS_READY.json').write_bytes(R.json_bytes(material))
        reference = copy.deepcopy(reference)
        # Rebind the cross-manifest seal after the mutation so it cannot mask a
        # missing semantic/provenance check in the reader being tested.
        if rebind:
            reference['input_ready_sha256'] = R.sha(R.json_bytes(material))
        (self.root / refpath / 'REFERENCE.json').write_bytes(R.json_bytes(reference))
        with mock.patch.object(R, 'boundary_snapshot', return_value={}), \
             mock.patch.object(R, 'recipe_identity', return_value=fixture[4]['recipe']), \
             mock.patch.object(R, 'read_subset', return_value=({}, {}, 'a' * 64, self.root / subset)), \
             mock.patch.object(R, 'checked', return_value=b''), \
             mock.patch.object(R, 'rope_source', return_value=R.rope_source(ROOT, pins)), \
             mock.patch.object(R, 'compiler_identity', return_value=compiler), \
             mock.patch.object(R, 'compare_reference', return_value=R.expected_comparison(pins) if computed is None else computed), \
             mock.patch.object(R, 'start_output') as start, mock.patch.object(R, 'write_new') as write:
            if expect_pass:
                value = R.audit(self.root, pins, subset, inputs, refpath, self.root / 'mock-audit')
                self.assertEqual(value['status'], 'VERIFIED_PREFIX_ARTIFACTS_ONLY')
                start.assert_called_once()
                write.assert_called_once()
                type(self).metadata_baselines += 1
            else:
                self.reject(R.audit, self.root, pins, subset, inputs, refpath, self.root / 'mock-audit')
                start.assert_not_called()
                write.assert_not_called()
                type(self).metadata_verdict_blocks += 1

    def mutations(self, value):
        for key, original in value.items():
            removed = copy.deepcopy(value)
            del removed[key]
            yield key + ':delete', removed
            if original is not None:
                changed = copy.deepcopy(value)
                changed[key] = None
                yield key + ':null', changed
            changed = copy.deepcopy(value)
            changed[key] = [] if type(original) is not list else {}
            yield key + ':wrong_type', changed

    def test_complete_metadata_audit_baseline_without_data_execution(self):
        fixture = self.metadata_audit_fixture()
        self.run_metadata_audit(fixture, fixture[4], fixture[5], expect_pass=True)

    def test_materialized_every_required_field_mutation_blocks_verdict(self):
        fixture = self.metadata_audit_fixture()
        for label, material in self.mutations(fixture[4]):
            with self.subTest(mutation=label):
                self.run_metadata_audit(fixture, material, fixture[5])

    def test_capture_every_required_field_mutation_blocks_verdict(self):
        fixture = self.metadata_audit_fixture()
        for label, reference in self.mutations(fixture[5]):
            with self.subTest(mutation=label):
                self.run_metadata_audit(fixture, fixture[4], reference,
                                        rebind=not label.startswith('input_ready_sha256:'))

    def test_rope_build_every_field_and_semantic_mutation_blocks_verdict(self):
        fixture = self.metadata_audit_fixture()
        for label, build in self.mutations(fixture[4]['rope_build']):
            material = copy.deepcopy(fixture[4])
            material['rope_build'] = build
            with self.subTest(mutation=label):
                self.run_metadata_audit(fixture, material, fixture[5])
        bad_values = {'command': ['/usr/bin/gcc', '-ffast-math'], 'source_sha256': '0' * 64,
                      'binary_sha256': '0' * 64, 'compiler_sha256': '0' * 64,
                      'compiler': 'gcc (wrong compiler receipt) 999', 'historical_binary_identity_claimed': True}
        for key, value in bad_values.items():
            material = copy.deepcopy(fixture[4])
            material['rope_build'][key] = value
            with self.subTest(semantic=key):
                self.run_metadata_audit(fixture, material, fixture[5])
        for flag in R.C_FLAGS:
            material = copy.deepcopy(fixture[4])
            material['rope_build']['command'].remove(flag)
            with self.subTest(removed_flag=flag):
                self.run_metadata_audit(fixture, material, fixture[5])

    def test_rope_build_actual_source_and_binary_tamper_blocks_verdict(self):
        for filename in ('independent.c', 'independent.so'):
            fixture = self.metadata_audit_fixture()
            path = self.root / fixture[2] / 'rope_build' / filename
            path.write_bytes(path.read_bytes() + b' changed')
            self.run_metadata_audit(fixture, fixture[4], fixture[5])

    def test_python_provenance_semantic_mutations_block_verdict(self):
        fixture = self.metadata_audit_fixture()
        material = copy.deepcopy(fixture[4])
        material['python'] = '3.12.999 (forged provenance)'
        self.run_metadata_audit(fixture, material, fixture[5])
        for label, identity in self.mutations(fixture[4]['python_executable']):
            material = copy.deepcopy(fixture[4])
            material['python_executable'] = identity
            with self.subTest(mutation=label):
                self.run_metadata_audit(fixture, material, fixture[5])
        for key, value in (('sha256', '0' * 64), ('bytes', 1), ('path', '/arbitrary/python')):
            material = copy.deepcopy(fixture[4])
            material['python_executable'][key] = value
            self.run_metadata_audit(fixture, material, fixture[5])

    def test_runtime_every_required_field_mutation_blocks_verdict(self):
        fixture = self.metadata_audit_fixture()
        for label, runtime in self.mutations(fixture[5]['runtime']):
            reference = copy.deepcopy(fixture[5])
            reference['runtime'] = runtime
            with self.subTest(mutation=label):
                self.run_metadata_audit(fixture, fixture[4], reference)

    def test_runtime_environment_each_field_mutation_blocks_verdict(self):
        fixture = self.metadata_audit_fixture()
        for label, environment in self.mutations(fixture[5]['runtime']['environment']):
            reference = copy.deepcopy(fixture[5])
            reference['runtime']['environment'] = environment
            with self.subTest(mutation=label):
                self.run_metadata_audit(fixture, fixture[4], reference)
        for key in fixture[5]['runtime']['environment']:
            reference = copy.deepcopy(fixture[5])
            reference['runtime']['environment'][key] = 'unreviewed override'
            self.run_metadata_audit(fixture, fixture[4], reference)

    def test_runtime_semantic_values_and_build_pin_block_verdict(self):
        fixture = self.metadata_audit_fixture()
        for key, value in (('python', '3.12.999 changed'), ('torch_build', 'forged build flags'),
                           ('torch_build_sha256', '0' * 64), ('identity_scope', 'full historical runtime equivalent'),
                           ('affinity', [True]), ('affinity', [-1]), ('affinity', []),
                           ('affinity', fixture[5]['runtime']['affinity'] + fixture[5]['runtime']['affinity']),
                           ('capability', 'AVX2'), ('threads', 8), ('interop_threads', 2),
                           ('deterministic_algorithms', False), ('historical_runtime_equivalence_claimed', True)):
            reference = copy.deepcopy(fixture[5])
            reference['runtime'][key] = value
            with self.subTest(field=key, value=value):
                self.run_metadata_audit(fixture, fixture[4], reference)
        # The real loader's exact build pin rejects this synthetic test-only build.
        self.reject(R.check_runtime, fixture[5]['runtime'], self.pins)

    def test_native_library_each_field_mutation_blocks_verdict(self):
        fixture = self.metadata_audit_fixture()
        for name, item in fixture[5]['runtime']['native_files'].items():
            for label, changed in self.mutations(item):
                reference = copy.deepcopy(fixture[5])
                reference['runtime']['native_files'][name] = changed
                with self.subTest(library=name, mutation=label):
                    self.run_metadata_audit(fixture, fixture[4], reference)
            reference = copy.deepcopy(fixture[5])
            del reference['runtime']['native_files'][name]
            self.run_metadata_audit(fixture, fixture[4], reference)

    def test_layout_rule_each_field_mutation_blocks_verdict(self):
        fixture = self.metadata_audit_fixture()
        reference = copy.deepcopy(fixture[5])
        reference['layout_rule'] = 'Old archived raw bytes were compared directly.'
        self.run_metadata_audit(fixture, fixture[4], reference)
        for name, entry in fixture[5]['reference_hash_comparison'].items():
            reference = copy.deepcopy(fixture[5])
            del reference['reference_hash_comparison'][name]
            self.run_metadata_audit(fixture, fixture[4], reference)
            for label, changed in self.mutations(entry):
                reference = copy.deepcopy(fixture[5])
                reference['reference_hash_comparison'][name] = changed
                with self.subTest(node=name, mutation=label):
                    self.run_metadata_audit(fixture, fixture[4], reference)
            for key, value in (('logical_sha256', '0' * 64), ('token_major_sha256', '0' * 64),
                               ('frozen_reference_hash_matches', False), ('layout', 'unreviewed layout')):
                reference = copy.deepcopy(fixture[5])
                reference['reference_hash_comparison'][name][key] = value
                self.run_metadata_audit(fixture, fixture[4], reference)

    def test_independent_comparison_disagreement_blocks_verdict(self):
        fixture = self.metadata_audit_fixture()
        comparison = R.expected_comparison(fixture[0])
        comparison['q']['token_major_sha256'] = '0' * 64
        self.run_metadata_audit(fixture, fixture[4], fixture[5], computed=comparison)

    def test_unknown_provenance_and_claim_fields_block_verdict(self):
        fixture = self.metadata_audit_fixture()
        targets = (('material', ()), ('material', ('rope_build',)), ('material', ('python_executable',)),
                   ('reference', ()), ('reference', ('runtime',)), ('reference', ('runtime', 'environment')),
                   ('reference', ('runtime', 'native_files', 'python')),
                   ('reference', ('reference_hash_comparison', 'q')))
        for owner, path in targets:
            material, reference = copy.deepcopy(fixture[4]), copy.deepcopy(fixture[5])
            target = material if owner == 'material' else reference
            for key in path:
                target = target[key]
            target['unreviewed_historical_acceptance'] = True
            with self.subTest(owner=owner, path=path):
                self.run_metadata_audit(fixture, material, reference)

    def test_torch_version_str_subclass_is_canonicalized_only_by_producer(self):
        # TorchVersion is a str subclass; reproduce that exact strict-type edge
        # without importing Torch or depending on an ignored runtime directory.
        class TorchVersionEquivalent(str):
            pass
        class TorchMetadata:
            pass
        expected = self.pins['runtime_requirements']['torch']
        torch_metadata = TorchMetadata()
        torch_metadata.__version__ = TorchVersionEquivalent(expected)
        self.assertEqual(torch_metadata.__version__, expected)
        self.assertIsNot(type(torch_metadata.__version__), str)
        self.reject(R.fields, {'torch': torch_metadata.__version__}, {'torch': expected}, 'strict reader')
        tree = ast.parse((PACKAGE / 'capture.py').read_text())
        capture_function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'capture')
        runtime = next(node.value for node in ast.walk(capture_function) if isinstance(node, ast.Assign) and
                       any(isinstance(target, ast.Name) and target.id == 'runtime' for target in node.targets))
        expression = next(value for key, value in zip(runtime.keys, runtime.values)
                          if isinstance(key, ast.Constant) and key.value == 'torch')
        self.assertEqual(ast.unparse(expression), 'str(torch.__version__)')
        compiled = compile(ast.Expression(expression), '<actual capture producer field>', 'eval')
        value = eval(compiled, {'torch': torch_metadata})
        self.assertIs(type(value), str)
        R.fields({'torch': value}, {'torch': expected}, 'canonical producer / strict reader')
        for wrong in (TorchVersionEquivalent('2.10.1+cpu'), TorchVersionEquivalent('2.10.0+cu128'), None, 2):
            torch_metadata.__version__ = wrong
            self.reject(R.fields, {'torch': eval(compiled, {'torch': torch_metadata})}, {'torch': expected}, 'strict value pin')

    def test_m128_contract_rows_positions_past_and_identity(self):
        R.check_contract(self.pins)
        for key, value in (('rows',16),('rows',127),('rows',129),('rows',True),
                           ('position_ids',list(range(16))*8),('token_ids',list(range(16))*8),
                           ('past_tokens',1),('past_tokens',False),('direct_gamma',False),
                           ('recipe_id','qwen2-live-qkv-inputs-m16-v1')):
            pins = copy.deepcopy(self.pins)
            pins['contract'][key] = value
            self.reject(R.check_contract, pins)
        for name in ('x','rope'):
            pins = copy.deepcopy(self.pins)
            pins['roles'][name]['sha256'] = 'a' * 64
            self.reject(R.check_contract, pins)

    def test_unfrozen_and_placeholder_references_never_accepted(self):
        R.require_frozen_references(self.pins)
        for status in ('BOOTSTRAP_UNACCEPTED',None,'PASS',True):
            pins = copy.deepcopy(self.pins)
            pins['reference_freeze']['status'] = status
            self.reject(R.require_frozen_references, pins)
        for name in self.pins['references']:
            for key in ('sha256','token_major_sha256'):
                for value in (None,'','0'*64,'pending',True):
                    pins = copy.deepcopy(self.pins)
                    pins['references'][name][key] = value
                    self.reject(R.require_frozen_references, pins)
            for key,value in (('shape',[1,16,1536]),('bytes',True),('native_dtype','torch.float32')):
                pins = copy.deepcopy(self.pins)
                pins['references'][name][key] = value
                self.reject(R.require_frozen_references, pins)
        pins = copy.deepcopy(self.pins)
        pins['references']['q']['historical_archive_sha256'] = 'a'*64
        self.reject(R.require_frozen_references, pins)

    def test_m128_x_uses_true_prefix_without_repetition(self):
        # Synthetic address words only, no checkpoint data or optional imports.
        raw = b''.join(struct.pack('<H',row)*1536 for row in range(256))
        value = R.input_x(raw)
        self.assertEqual(len(value),786432)
        for row in (0,15,16,17,126,127):
            self.assertEqual(value[row*6144:(row+1)*6144],struct.pack('<I',row<<16)*1536)
        self.assertNotEqual(value[16*6144:17*6144],value[:6144])
        for shortened in (raw[:16*3072],raw[:128*3072],raw[:-1]):
            self.reject(R.input_x,shortened)

    def test_m128_rope_raw_planes_stride_and_zero_unused_suffix(self):
        raw = b''.join(struct.pack('<I',i) for i in range(328448//4))
        value = R.input_rope(raw)
        self.assertEqual(len(value),524288)
        for plane in range(2):
            start = (192+(plane+1)*16384)*4
            base = plane*1024*64*4
            self.assertEqual(value[base:base+128*256],raw[start:start+128*256])
            self.assertEqual(value[base+128*256:base+1024*256],bytes((1024-128)*256))
            for row in (16,127):
                self.assertEqual(value[base+row*256:base+(row+1)*256],raw[start+row*256:start+(row+1)*256])
        self.assertNotEqual(value[:128*256],value[1024*256:1024*256+128*256])
        self.reject(R.input_rope,raw[:-4])

    def test_reference_metadata_helper_cannot_read_tensor_payloads(self):
        fixture = self.metadata_audit_fixture()
        pins,subset,inputs,reference,material,ref,_ = fixture
        path = self.root/reference/'REFERENCE.json'
        path.write_bytes(R.json_bytes(ref))
        original = Path.read_bytes
        reads = []
        def read(path):
            reads.append(path)
            self.assertEqual(path.suffix,'.json','reference payload read before output sealing')
            return original(path)
        with mock.patch.object(R,'recipe_identity',return_value=ref['recipe']), \
             mock.patch.object(R,'check_runtime'), mock.patch.object(Path,'read_bytes',read):
            value = R.verify_reference_metadata(self.root,pins,subset,inputs,reference,
                                                'a'*64,R.sha(R.json_bytes(material)))
        self.assertEqual(value['outputs'],ref['outputs'])
        self.assertEqual(reads,[path])

    def test_post_boundary_source_input_or_tool_drift_rejects(self):
        before = {'source.py':{'bytes':3,'sha256':'a'*64}}
        with mock.patch.object(R,'boundary_snapshot',return_value=copy.deepcopy(before)):
            R.finish_boundary(ROOT,self.pins,[],before)
        for after in ({},{'source.py':{'bytes':4,'sha256':'a'*64}},
                      {'source.py':{'bytes':3,'sha256':'b'*64}},
                      {**before,'unexpected':{'bytes':1,'sha256':'a'*64}}):
            with mock.patch.object(R,'boundary_snapshot',return_value=after):
                self.reject(R.finish_boundary,ROOT,self.pins,[],before)

    def test_stages_guard_inputs_sources_tools_before_manifest_commit(self):
        tree = ast.parse((PACKAGE/'recipe.py').read_text())
        for name in ('acquire','materialize','audit'):
            node = next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
            source = ast.get_source_segment((PACKAGE/'recipe.py').read_text(),node)
            self.assertIn('boundary_snapshot(',source)
            self.assertIn('finish_boundary(',source)
            self.assertLess(source.index('finish_boundary('),source.rindex('write_new('))
        source = (PACKAGE/'capture.py').read_text()
        self.assertLess(source.index('boundary_snapshot('),source.index('import numpy'))
        self.assertLess(source.index('finish_boundary('),source.rindex('write_new('))

    def test_reference_reader_environment_is_independent_but_receipt_pinned(self):
        pins,runtime = self.synthetic_runtime()
        with mock.patch.dict(os.environ, {'PYTHONPATH':'/different/reader',
                                         'PYTHONNOUSERSITE':'0', 'OMP_NUM_THREADS':'1'}):
            R.check_runtime(runtime,pins)
        for key in pins['capture_environment']:
            changed = copy.deepcopy(runtime)
            changed['environment'][key] = '/reader-must-not-authorize-receipt'
            self.reject(R.check_runtime,changed,pins)

    def test_no_runtime_guard_uses_assert(self):
        for name in ('recipe.py', 'capture.py'):
            tree = ast.parse((PACKAGE / name).read_text())
            self.assertFalse(any(isinstance(node, ast.Assert) for node in ast.walk(tree)))


if __name__ == '__main__':
    unittest.main(verbosity=2)
