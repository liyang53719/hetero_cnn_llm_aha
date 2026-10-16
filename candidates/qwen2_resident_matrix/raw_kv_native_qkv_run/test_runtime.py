"""Cold source/control checks; no packages, payloads, compiler or native gate."""
import copy
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from . import runtime as r


def contract_fixture():
    _, union, generated = r.baseline_contract()
    sources = dict(union)
    sources.update({name: 'a' * 64 for name in r.OWN})
    sources[r.PREFIX + 'runtime.py'] = r.IMPORTED_SHA256
    return dict(schema=1, profile=r.PROFILE, base_commit=r.BASE_COMMIT,
        total_budget_seconds=900, cleanup_grace_seconds=5, receipt_reserve_seconds=1,
        phase_limits=dict(r.PHASE_LIMITS), original_launch_contract_sha256=r.ORIGINAL_CONTRACT_SHA256,
        recipe_pins_sha256=r.RECIPE_PINS_SHA256, smoke_evidence_sha256=r.SMOKE_EVIDENCE_SHA256,
        generated_module_sha256=r.GENERATED_MODULE_SHA256,
        source_sha256=sources, generated_sha256=generated)


def context_fixture(workspace):
    start = time.monotonic_ns()
    return dict(schema=1, profile=r.PROFILE, workspace=str(workspace), checkout_commit='b' * 40,
        source_sha256={'control/source.py': 'a' * 64}, contract_sha256='c' * 64,
        start_ns=start, deadline_ns=start + 900000000000,
        generated_module=str(workspace / 'generated' / r.GATE),
        generated_module_sha256=r.GENERATED_MODULE_SHA256)


class SourceContractTests(unittest.TestCase):
    def test_original_and_recipe_inventory_exact(self):
        original, union, generated = r.baseline_contract()
        self.assertEqual((len(original), len(union), len(generated)), (221, 229, 10))
        self.assertEqual(union[r.GATE], '917d56f038c646606e9dc67d1d36752f70097adec9748db55b2a915af8147c85')
        self.assertNotEqual(union[r.GATE], r.GENERATED_MODULE_SHA256)
        self.assertEqual(union[r.RECIPE_PREFIX + 'SMOKE_EVIDENCE.json'], r.SMOKE_EVIDENCE_SHA256)

    def test_contract_shape_and_canonical_fields(self):
        value = contract_fixture()
        self.assertEqual(len(r.validate_contract(value)), 221)
        for key, replacement in (('schema', True), ('total_budget_seconds', 900.0),
                ('profile', 'READY_FOR_ACTUAL_M128'), ('base_commit', '0' * 40),
                ('generated_module_sha256', '0' * 64)):
            changed = copy.deepcopy(value); changed[key] = replacement
            with self.subTest(key=key), self.assertRaises(ValueError):
                r.validate_contract(changed)
        for change in (lambda x: x.pop('phase_limits'), lambda x: x.update(extra=True)):
            changed = copy.deepcopy(value); change(changed)
            with self.assertRaises(ValueError):
                r.validate_contract(changed)

    def test_every_frozen_source_and_overlay_stays_pinned(self):
        value = contract_fixture()
        for section, name in (('source_sha256', r.GATE),
                ('source_sha256', r.PREFIX + 'runtime.py'),
                ('source_sha256', r.RECIPE_PREFIX + 'pins.json'),
                ('source_sha256', r.RECIPE_PREFIX + 'SMOKE_EVIDENCE.json'),
                ('generated_sha256', next(iter(value['generated_sha256'])))):
            changed = copy.deepcopy(value); changed[section][name] = '0' * 64
            with self.subTest(name=name), self.assertRaises(ValueError):
                r.validate_contract(changed)
        for name in ('missing.py', '../escape.py', 'bad\\name.py', 'bad\0name.py'):
            changed = copy.deepcopy(value); changed['source_sha256'][name] = 'a' * 64
            with self.subTest(name=name), self.assertRaises(ValueError):
                r.validate_contract(changed)

    def test_missing_contract_and_noncanonical_mode_fail_closed(self):
        with mock.patch.object(r, 'read_source', side_effect=FileNotFoundError):
            with self.assertRaises(FileNotFoundError):
                r.snapshot()
        with mock.patch.object(r, 'read_source', side_effect=AssertionError('must reject first')):
            for value in (0, 1, None, 'false'):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    r.snapshot(composed=value)

    def test_real_frozen_sources_and_separate_preparation(self):
        frozen = r.snapshot()
        self.assertEqual(len(frozen['sources']), 238)
        self.assertEqual(len(frozen['original_setup_sources']), 221)
        self.assertEqual(set(frozen['git_blobs']), set(frozen['sources']))
        original = (r.ROOT / r.GATE).read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / 'prepared'
            result = r.prepare_outputs(out)
            self.assertEqual(result['status'], 'PASS_SOURCE_PREPARATION_ONLY')
            self.assertIs(result['numerical_execution'], False)
            self.assertIs(result['public_execution'], False)
            self.assertIs(result['rtl_execution'], False)
            self.assertEqual(r.sha((out / 'generated' / r.GATE).read_bytes()), r.GENERATED_MODULE_SHA256)
            self.assertFalse((out / 'overlays' / r.GATE).exists())
            files = {str(p.relative_to(out / 'overlays')): r.sha(p.read_bytes())
                     for p in (out / 'overlays').rglob('*') if p.is_file()}
            self.assertEqual(files, frozen['generated'])
            self.assertEqual([str(p.relative_to(out / 'generated')) for p in
                              (out / 'generated').rglob('*') if p.is_file()], [r.GATE])
            with self.assertRaises(ValueError):
                r.prepare_outputs(out)
        self.assertEqual((r.ROOT / r.GATE).read_bytes(), original)

    def test_real_composed_union_and_original_context_are_separate(self):
        frozen = r.snapshot()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); checkout = root / 'checkout'; checkout.mkdir()
            workspace = root / 'workspace'; r.prepare_outputs(workspace)
            for name in frozen['sources']:
                target = checkout / name; target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((r.ROOT / name).read_bytes())
            for name in frozen['generated']:
                (checkout / name).write_bytes((workspace / 'overlays' / name).read_bytes())
            script = '''import json,sys,time
from pathlib import Path
def audit(event,args):
    if event == 'import' and (args[0].split('.')[0] in ('numpy','torch')):
        raise AssertionError('numerical package imported during source proof')
    if event in ('ctypes.dlopen','subprocess.Popen'):
        raise AssertionError('native/process execution during source proof')
sys.addaudithook(audit)
from candidates.qwen2_resident_matrix.raw_kv_native_qkv_run import runtime as r
from candidates.qwen2_resident_matrix.raw_kv_public_fresh import setup
workspace=Path(sys.argv[1]);frozen=r.snapshot(composed=True)
if len(frozen['sources'])!=238 or len(frozen['original_setup_sources'])!=221:raise AssertionError('counts')
start=time.monotonic_ns()
context=r.make_context(workspace,'b'*40,start,start+900000000000,frozen)
(workspace/'validation_context.json').write_bytes(r.encoded(context))
old=r.old_setup_context(context,frozen)
(workspace/'context.json').write_bytes(r.encoded(old))
if r.read_context(workspace/'validation_context.json')!=(context,workspace):raise AssertionError('new context')
observed,found=setup._read_context(workspace/'context.json')
if observed!=old or found!=workspace:raise AssertionError('original context')
if setup.source_snapshot(True)!=frozen['original_setup_sources']:raise AssertionError('original map')
old['source_sha256']=context['source_sha256']
(workspace/'context.json').write_bytes(r.encoded(old))
try:setup._read_context(workspace/'context.json')
except Exception:pass
else:raise AssertionError('union admitted as original context')
if any(n.split('.')[0] in ('torch','numpy') for n in sys.modules):raise AssertionError('native import')
print('SOURCE_CONTEXT_PASS 238 221')
'''
            env = {k: v for k, v in os.environ.items() if k not in ('PYTHONPATH', 'PYTHONHOME', 'PYTHONOPTIMIZE')}
            env['PYTHONDONTWRITEBYTECODE'] = '1'
            result = subprocess.run([sys.executable, '-B', '-c', script, str(workspace)],
                                    cwd=checkout, env=env, text=True, capture_output=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr[-4096:])
            self.assertEqual(result.stdout.strip(), 'SOURCE_CONTEXT_PASS 238 221')


class MetadataTests(unittest.TestCase):
    def test_json_rejects_duplicates_and_nonfinite_including_overflow(self):
        for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}', b'{"x":-Infinity}', b'{"x":1e999}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                r.json_bytes(raw)
        self.assertEqual(r.json_bytes(b'{"x":1.25}'), {'x': 1.25})
        self.assertFalse(r.same({'x': True}, {'x': 1}))
        self.assertFalse(r.same({'x': 1.0}, {'x': 1}))

    def test_paths_symlinks_fifo_and_size(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); path = root / 'file'; path.write_bytes(b'abc')
            self.assertEqual(r.read_bytes(path, 3), b'abc')
            with self.assertRaises(ValueError): r.read_bytes(path, 2)
            link = root / 'link'; link.symlink_to(path)
            with self.assertRaises(ValueError): r.read_bytes(link)
            alias = root / 'rootlink'; alias.symlink_to(root, target_is_directory=True)
            with self.assertRaises(ValueError): r.read_bytes(alias / 'file')
            with self.assertRaises(ValueError): r.read_bytes(root / 'sub' / '..' / 'file')
            fifo = root / 'fifo'; os.mkfifo(fifo)
            with self.assertRaises(ValueError): r.read_bytes(fifo)

    def test_same_byte_replacement_during_read_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'small.json'; path.write_bytes(b'{"x":1}')
            real_fstat = os.fstat; calls = 0
            def replace_on_second(fd):
                nonlocal calls
                calls += 1
                if calls == 2:
                    replacement = path.with_suffix('.new')
                    replacement.write_bytes(path.read_bytes()); replacement.replace(path)
                return real_fstat(fd)
            with mock.patch.object(r.os, 'fstat', side_effect=replace_on_second):
                with self.assertRaises(ValueError): r.read_json(path)

    def test_source_names_are_canonical_before_access(self):
        for name in ('/absolute', '../escape', 'a/../b', 'a//b', './a', 'a\\b', 'a\0b', '', '.'):
            with self.subTest(name=name), mock.patch.object(r, 'read_bytes', side_effect=AssertionError):
                with self.assertRaises(ValueError): r.read_source(name)


class ContextTests(unittest.TestCase):
    def test_context_canonical_domain_before_source_access(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); context = context_fixture(root)
            self.assertEqual(r.check_context(context), context)
            cases = [('schema', True), ('profile', 'READY_FOR_ACTUAL_M128'), ('checkout_commit', 'x' * 40),
                     ('start_ns', True), ('deadline_ns', float(context['deadline_ns'])),
                     ('source_sha256', []), ('generated_module_sha256', 'a' * 64),
                     ('generated_module', str(root / r.GATE))]
            for key, value in cases:
                changed = dict(context); changed[key] = value
                path = root / 'validation_context.json'; path.write_bytes(r.encoded(changed))
                with self.subTest(key=key), mock.patch.object(r, 'snapshot', side_effect=AssertionError('source access')):
                    with self.assertRaises(ValueError): r.read_context(path)

    def test_absolute_deadline_never_refreshes_and_reserves_cleanup(self):
        # Elapsed895s is a simulated scenario, not an assumption about host uptime.
        now = 1000 * 1000000000
        with mock.patch.object(r.time, 'monotonic_ns', return_value=now):
            context = context_fixture(Path('/control'))
            context.update(start_ns=now - 895000000000, deadline_ns=now + 5000000000)
            with self.assertRaises(ValueError): r.check_context(context)
            r.check_context(context, check_deadline=False)
            context.update(start_ns=now - 880000000000, deadline_ns=now + 20000000000)
            self.assertEqual(r.remaining(context, 120), 14)
            self.assertEqual(r.remaining(context, 2), 2)
            for ceiling in (True, 0, -1, float('inf'), 901):
                with self.subTest(ceiling=ceiling), self.assertRaises(ValueError): r.remaining(context, ceiling)
            context['deadline_ns'] += 1
            with self.assertRaises(ValueError): r.check_context(context)

    def test_elapsed_fixture_is_independent_of_low_host_uptime(self):
        for uptime in (1, 1000000000, 10000000000, 894000000000):
            with self.subTest(uptime=uptime), mock.patch.object(r.time, 'monotonic_ns', return_value=uptime):
                self.test_absolute_deadline_never_refreshes_and_reserves_cleanup()
                fresh = context_fixture(Path('/control'))
                self.assertEqual(r.check_context(fresh), fresh)
                invalid = dict(fresh, start_ns=uptime-895000000000, deadline_ns=uptime+5000000000)
                with self.assertRaises(ValueError): r.check_context(invalid, check_deadline=False)

    def test_original_context_has_only_original_221_sources(self):
        original, _, generated = r.baseline_contract(); original.update(generated)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); context = context_fixture(root)
            frozen = dict(sources=context['source_sha256'], contract_sha256=context['contract_sha256'],
                          original_setup_sources=original)
            with mock.patch.object(r, 'snapshot', return_value=frozen):
                value = r.old_setup_context(context, frozen)
            self.assertEqual(set(value), {'schema', 'workspace', 'checkout_commit', 'enable_raw_kv',
                'source_sha256', 'asset_source_sha256', 'work_deadline_ns'})
            self.assertIs(value['enable_raw_kv'], True)
            self.assertEqual(value['source_sha256'], original)
            self.assertEqual(value['asset_source_sha256'], original)
            self.assertEqual(len(value['source_sha256']), 221)
            self.assertEqual(value['work_deadline_ns'], context['deadline_ns'] - 6000000000)
            self.assertNotIn(r.PREFIX + 'runtime.py', value['source_sha256'])

    def test_context_source_and_generated_file_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); context = context_fixture(root)
            path = root / 'validation_context.json'; path.write_bytes(r.encoded(context))
            frozen = dict(sources={'changed.py': 'd' * 64}, contract_sha256=context['contract_sha256'])
            with mock.patch.object(r, 'snapshot', return_value=frozen):
                with self.assertRaises(ValueError): r.read_context(path)
            frozen['sources'] = context['source_sha256']
            module = Path(context['generated_module']); module.parent.mkdir(parents=True)
            module.write_text('deliberately not the real generated gate')
            with mock.patch.object(r, 'snapshot', return_value=frozen):
                with self.assertRaises(ValueError): r.read_context(path)

    def test_make_context_uses_checked_snapshot_and_exact_generated_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); control = context_fixture(root)
            frozen = dict(sources=control['source_sha256'], contract_sha256=control['contract_sha256'])
            with mock.patch.object(r, 'snapshot', return_value=frozen):
                with self.assertRaises(ValueError):
                    r.make_context(root, control['checkout_commit'], control['start_ns'], control['deadline_ns'], {})
                module = Path(control['generated_module']); module.parent.mkdir(parents=True); module.write_bytes(b'wrong')
                with self.assertRaises(ValueError):
                    r.make_context(root, control['checkout_commit'], control['start_ns'], control['deadline_ns'], frozen)


if __name__ == '__main__':
    unittest.main()
