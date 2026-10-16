"""Cold source/entry checks, never a numerical execution or native verifier run.

Actual composed function bodies are extracted by AST. Entry prerequisite stubs
are explicitly synthetic and stop before runtime/native work. Source-contract
checks separately use real pinned files and the unchanged historical inventory.
"""
import argparse
import ast
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

from . import prepare as composition


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def file_sha(path):
    return sha(Path(path).read_bytes())


def extract(source, *, functions=None, **namespace):
    """No module imports/top-level execution; only exact function declarations."""
    tree = ast.parse(source)
    namespace = dict(Path=Path, require=need, hashlib=hashlib, json=json, sha=sha,
                     encoded=encoded, file_sha=file_sha, argparse=argparse,
                     ROOT=composition.ROOT, __doc__=__doc__) | namespace
    constants = ('PREFIX', 'EXECUTION_FILES', 'POLICY_ID', 'RAW_KV_SOURCES',
                 'RAW_KV_SOURCE_PROFILE', 'RAW_KV_COMPOSITION_SHA256', 'OWNER', 'SOURCE_VERSION', 'SOURCE_BASE_COMMIT',
                 'RECEIPT', 'RECEIPT_SHA', 'RECEIPT_COMMIT', 'HELPER', 'HELPER_SHA256',
                 'RAW_KV_HELPER_SHA256', 'HELPER_SOURCE_VERSION', 'REQUIRED_SOURCES',
                 'RAW_KV_EXECUTION_SOURCE_REPLACEMENTS', 'RAW_KV_CAPTURE_SHA256',
                 'RAW_KV_MONITORING_SHA256', 'CAPTURE_SHA256', 'MONITORING_SHA256',
                 'CAPTURE_SOURCE_VERSION', 'ADAPTER', 'PINS', 'EXECUTION_SOURCE_REPLACEMENTS',
                 'SERVICE', 'OBSERVER')
    def literal(node):
        if isinstance(node, ast.Name): return namespace[node.id]
        if isinstance(node, ast.Dict): return {literal(k): literal(v) for k, v in zip(node.keys, node.values)}
        if isinstance(node, (ast.Tuple, ast.List)):
            values = [literal(v) for v in node.elts]
            return tuple(values) if isinstance(node, ast.Tuple) else values
        return ast.literal_eval(node)
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in constants:
                namespace[name] = literal(node.value)
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and
             (functions is None or n.name in functions)]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<cold-extracted-source>', 'exec'), namespace)
    return namespace


class RuntimeBoundary(Exception):
    """Intentional stop before importing or invoking numerical dependencies."""


class ComposedSources(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='raw-kv-entry-tests-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.outputs, cls.reports, cls.sources = {}, {}, {}
        for enabled in (False, True):
            out = Path(cls.temp.name) / ('on' if enabled else 'off')
            cls.reports[enabled] = composition.prepare(out, enable_raw_kv=enabled)
            cls.outputs[enabled] = out
            cls.sources[enabled] = {name: (out / name).read_text() for name in cls.reports[enabled]['generated']}
        cls.entry = cls.sources[False][composition.ENTRY]
        cls.originals = {name: (composition.ROOT / name).read_text() for name in composition.TARGETS}

    def entry_namespace(self, **values):
        return extract(self.entry, **values)


class EntryControlTests(ComposedSources):
    def test_all_entry_flags_are_canonical_before_prerequisite_work(self):
        for function in ('source_hashes', 'runtime', 'prepare', 'verify_snapshot', 'run'):
            for bad in (0, 1, None, 'true', 0.0, object()):
                with self.subTest(function=function, bad=type(bad).__name__):
                    ns = self.entry_namespace(prior=NS())
                    args = {'source_hashes': (), 'runtime': (), 'prepare': ('out', None, None, None),
                            'verify_snapshot': ('snapshot', 'digest'), 'run': ('out', 'snapshot', 'digest')}[function]
                    with self.assertRaisesRegex(ValueError, 'canonical boolean'):
                        ns[function](*args, enable_raw_kv=bad)

    def test_snapshot_mode_is_exact_and_disabled_metadata_shape_is_unchanged(self):
        ns = self.entry_namespace()
        check = ns['_snapshot_raw_kv_mode']
        profile = ns['RAW_KV_SOURCE_PROFILE']
        self.assertFalse(check({}, False))
        self.assertTrue(check({'enable_raw_kv': True, 'raw_kv_source_profile': profile}, True))
        for value, selected in (({}, True), ({'enable_raw_kv': True, 'raw_kv_source_profile': profile}, False),
                                ({'enable_raw_kv': False}, False), ({'raw_kv_source_profile': profile}, False),
                                ({'enable_raw_kv': True}, True),
                                ({'enable_raw_kv': True, 'raw_kv_source_profile': 'stale'}, True),
                                ({'enable_raw_kv': 1, 'raw_kv_source_profile': profile}, True)):
            with self.subTest(value=value, selected=selected), self.assertRaises(ValueError):
                check(value, selected)

    def test_verify_cross_mode_rejects_before_prior_verifier_or_runtime(self):
        ns = self.entry_namespace(prior=NS(verify_snapshot=Mock(side_effect=AssertionError('prior verifier reached'))))
        ns['runtime'] = Mock(side_effect=AssertionError('runtime reached'))
        with tempfile.TemporaryDirectory(prefix='raw-kv-mode-') as directory:
            path = Path(directory) / 'SNAPSHOT.json'
            for stored, requested in ((False, True), (True, False)):
                snapshot = {} if not stored else dict(enable_raw_kv=True,
                    raw_kv_source_profile=ns['RAW_KV_SOURCE_PROFILE'])
                path.write_bytes(encoded(snapshot))
                with self.assertRaisesRegex(ValueError, 'mode mismatch'):
                    ns['verify_snapshot'](path, file_sha(path), enable_raw_kv=requested)
        ns['prior'].verify_snapshot.assert_not_called()
        ns['runtime'].assert_not_called()

    def synthetic_snapshot_namespace(self, root, rows):
        """Only preparation dependencies; no real verifier/library is imported."""
        root = Path(root)
        for name in ('base.py', 'entry.py', 'extra.py'):
            (root / name).write_bytes(('COLD_SOURCE:' + name).encode())
        original = dict(rows=rows, epoch=7, input_spec={}, loaded_inputs={}, binaries={},
                        metadata={}, host_tools={}, reference={'inputs': {'input_x_sha256': 'cold-input'}})
        independent = dict(rows=rows, readonly_input={'input_x_sha256': 'cold-input'},
                           directory='COLD_REFERENCE_METADATA', result_sha256='c' * 64)
        def prior_prepare(out, receipt, selected_rows):
            self.assertEqual(selected_rows, rows)
            out.mkdir(parents=True)
            path = out / 'SNAPSHOT.json'; path.write_bytes(encoded(original))
            return path, dict(original)
        prior = NS(source_hashes=lambda: {'base.py': file_sha(root / 'base.py')},
                   prepare=Mock(side_effect=prior_prepare),
                   verify_snapshot=Mock(return_value=original))
        ns = self.entry_namespace(prior=prior)
        ns.update(ROOT=root, PREFIX='', EXECUTION_FILES=('entry.py',), RAW_KV_SOURCES=('extra.py',))
        # Only this synthetic prerequisite fixture substitutes composition checks.
        # Real six-file checks and mode/drift rejection are exercised separately.
        ns['_verify_raw_kv_composition'] = ns['_raw_kv_mode']
        ns['runtime'] = Mock(return_value=(None, (NS(reference_spec=Mock(return_value=independent)),)))
        return ns

    def test_actual_prepare_freezes_sources_and_roundtrips_both_receipt_modes(self):
        for enabled in (False, True):
            with self.subTest(enabled=enabled), tempfile.TemporaryDirectory(prefix='raw-kv-snapshot-') as directory:
                root = Path(directory); ns = self.synthetic_snapshot_namespace(root, 16)
                path, snapshot = ns['prepare'](root / 'snapshot', 'cold-receipt', 'cold-reference', 'cold-digest',
                                               enable_raw_kv=enabled)
                self.assertEqual(snapshot['status'], 'PREPARED_REDUCED_PUBLIC21_NOT_EXECUTED')
                self.assertFalse(snapshot['old_pass_inherited'])
                self.assertEqual(snapshot['source_manifest_sha256'], sha(encoded(snapshot['source_sha256'])))
                self.assertEqual(set(snapshot['source_sha256']), {'base.py', 'entry.py'} | ({'extra.py'} if enabled else set()))
                self.assertEqual('enable_raw_kv' in snapshot, enabled)
                self.assertEqual('raw_kv_source_profile' in snapshot, enabled)
                for name, digest in snapshot['source_sha256'].items():
                    frozen = path.parent / 'frozen_sources' / name
                    self.assertEqual(frozen.read_bytes(), (root / name).read_bytes())
                    self.assertEqual(file_sha(frozen), digest)
                self.assertEqual(ns['verify_snapshot'](path, file_sha(path), enable_raw_kv=enabled), snapshot)
                ns['runtime'].assert_called_with(enable_raw_kv=enabled)
                frozen.write_bytes(b'changed cold source')
                with self.assertRaisesRegex(ValueError, 'frozen source drift'):
                    ns['verify_snapshot'](path, file_sha(path), enable_raw_kv=enabled)

    def test_snapshot_missing_extra_or_stale_source_hashes_are_rejected(self):
        with tempfile.TemporaryDirectory(prefix='raw-kv-snapshot-neg-') as directory:
            root = Path(directory); ns = self.synthetic_snapshot_namespace(root, 16)
            path, snapshot = ns['prepare'](root / 'snapshot', None, None, None, enable_raw_kv=True)
            for kind in ('missing', 'extra', 'stale'):
                changed = deepcopy(snapshot)
                if kind == 'missing':
                    del changed['source_sha256']['extra.py']
                elif kind == 'extra':
                    changed['source_sha256']['unexpected.py'] = '0' * 64
                else:
                    changed['source_sha256']['extra.py'] = '0' * 64
                changed['source_manifest_sha256'] = sha(encoded(changed['source_sha256']))
                path.write_bytes(encoded(changed))
                with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, 'source/policy/domain drift'):
                    ns['verify_snapshot'](path, file_sha(path), enable_raw_kv=True)

    def test_enabled_m128_stops_before_verifier_and_default_rows_budget_stay_original(self):
        with tempfile.TemporaryDirectory(prefix='raw-kv-launch-') as directory:
            root = Path(directory); path = root / 'SNAPSHOT.json'
            ns = self.entry_namespace()
            ns['verify_snapshot'] = Mock(return_value={'rows': 128})
            ns['runtime'] = Mock(side_effect=RuntimeBoundary('cold boundary'))
            path.write_bytes(encoded(dict(rows=128, enable_raw_kv=True,
                              raw_kv_source_profile=ns['RAW_KV_SOURCE_PROFILE'])))
            with self.assertRaisesRegex(ValueError, 'limited to M16'):
                ns['run'](root / 'out', path, file_sha(path), enable_raw_kv=True)
            ns['verify_snapshot'].assert_not_called(); ns['runtime'].assert_not_called()
            self.assertFalse((root / 'out').exists())
            for rows in (16, 128):
                self.assertEqual(ns['validate_rows'](rows), rows)
                ns['verify_snapshot'].return_value = {'rows': rows}
                with self.assertRaises(RuntimeBoundary):
                    ns['run'](root / 'out', path, file_sha(path), wall_budget=1800)
                ns['verify_snapshot'].assert_called_with(path.resolve(), file_sha(path), enable_raw_kv=False)
                ns['runtime'].assert_called_with(enable_raw_kv=False)
            for rows in (1, 8, 129, True, 16.0):
                with self.assertRaises(ValueError): ns['validate_rows'](rows)
            for budget in (0, -1, 1801):
                with self.assertRaisesRegex(ValueError, 'fresh bounded'):
                    ns['run'](root / 'out', path, file_sha(path), wall_budget=budget)
            self.assertEqual(ns['run'].__kwdefaults__, dict(wall_budget=900, enable_raw_kv=False))

    def test_cli_propagates_flag_rows_and_budget_without_running_any_entry(self):
        for enabled in (False, True):
            for preparing in (False, True):
                ns = self.entry_namespace()
                ns['prepare'] = Mock(return_value=(Path('COLD_SNAPSHOT'), {'status': 'COLD_PREPARE_ONLY'}))
                ns['run'] = Mock(return_value=dict(status='NOT_RUN', rows=16,
                    native_acceptance='NOT_RUN', host_wall_seconds=0))
                ns['file_sha'] = lambda path: '0' * 64
                args = ['cold-entry', '--out', 'unused']
                if preparing: args += ['--prepare-only', '--rows', '128']
                if enabled: args += ['--enable-raw-kv']
                with self.subTest(enabled=enabled, preparing=preparing), patch.object(sys, 'argv', args), redirect_stdout(io.StringIO()):
                    if preparing:
                        ns['main']()
                        self.assertEqual(ns['prepare'].call_args.kwargs, dict(rows=128, enable_raw_kv=enabled))
                        ns['run'].assert_not_called()
                    else:
                        with self.assertRaises(SystemExit) as ended: ns['main']()
                        self.assertEqual(ended.exception.code, 1)  # NOT_RUN cannot become PASS.
                        self.assertEqual(ns['run'].call_args.kwargs, dict(wall_budget=900, enable_raw_kv=enabled))
                        ns['prepare'].assert_not_called()
        with patch.object(sys, 'argv', ['cold-entry', '--out', 'unused', '--rows', '1']), redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as ended: ns['main']()
            self.assertEqual(ended.exception.code, 2)

    def test_disabled_suffix_and_capture_receive_original_call_shapes(self):
        run = next(n for n in ast.parse(self.entry).body if isinstance(n, ast.FunctionDef) and n.name == 'run')
        for called, module_name in (('execute_public_suffix', 'suffix'),
                                    ('ProfiledAttentionMonitoringObservation', 'observation')):
            branches = [n for n in ast.walk(run) if isinstance(n, ast.If) and isinstance(n.test, ast.Name)
                        and n.test.id == 'enable_raw_kv' and any(isinstance(v, ast.Call) and
                        isinstance(v.func, ast.Attribute) and v.func.attr == called for v in ast.walk(n))]
            self.assertEqual(len(branches), 1)
            for enabled in (False, True):
                callback = Mock(return_value=(object(), {}) if called == 'execute_public_suffix' else object())
                ns = dict(enable_raw_kv=enabled, report={}, x=NS(attention_owner=object()), physical=object(),
                          guarded=object(), out=object(), memory=object(), s={'source_sha256': {}})
                ns[module_name] = NS(**{called: callback})
                exec(compile(ast.Module(body=[branches[0]], type_ignores=[]), '<cold-call-plumbing>', 'exec'), ns)
                self.assertEqual(callback.call_count, 1)
                self.assertEqual('enable_raw_kv' in callback.call_args.kwargs, enabled)
                if enabled: self.assertIs(callback.call_args.kwargs['enable_raw_kv'], True)

    def test_original_comparisons_terminal_seal_and_official_gates_are_identical(self):
        old, new = (ast.parse(source) for source in (self.originals[composition.ENTRY], self.entry))
        def function(tree, name):
            return next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
        for name in ('compare', 'independent_bytes', 'validate_rows'):
            self.assertEqual(ast.dump(function(old, name)), ast.dump(function(new, name)))
        def terminal_tail(tree):
            run = function(tree, 'run')
            attempt = next(n for n in run.body if isinstance(n, ast.Try))
            body = next(n for n in attempt.body if isinstance(n, ast.With)).body
            first = next(i for i, n in enumerate(body) if isinstance(n, ast.Assign) and
                         ast.unparse(n.targets[0]) == "report['whole_terminal_host_wall_seconds']")
            return ast.Module(body=deepcopy(body[first:] + attempt.handlers), type_ignores=[])
        class ModeKeyword(ast.NodeTransformer):
            def visit_Call(self, node):
                if isinstance(node.func, ast.Name) and node.func.id == 'source_hashes':
                    node.keywords = [k for k in node.keywords if k.arg != 'enable_raw_kv']
                return self.generic_visit(node)
        self.assertEqual(ast.dump(terminal_tail(old)), ast.dump(ModeKeyword().visit(terminal_tail(new))))


class SourceContractTests(ComposedSources):
    def guard_tree(self, directory, enabled):
        """Real pinned source bytes in a local throwaway overlay, never imports."""
        root = Path(directory)
        inventory = composition._original_inventory()
        names = set(inventory) | set(composition.GUARDS) | {composition.INVENTORY,
            composition.PREFIX + 'official_bf16/owners.py', composition.PREFIX + 'official_bf16/dense_silu.py'}
        for name in names:
            path = root / name; path.parent.mkdir(parents=True, exist_ok=True)
            raw = (self.sources[True][name].encode() if enabled and name in self.sources[True]
                   else (composition.ROOT / name).read_bytes())
            path.write_bytes(raw)
        helper_source = (root / composition.GUARDS[0]).read_text()
        helper = extract(helper_source, functions={'require', 'sha', 'verify_execution_sources'}, ROOT=root)
        return root, helper, names

    def test_separate_fresh_composition_modes_are_reproducible_and_source_bound(self):
        self.assertEqual(set(self.sources[False]), {composition.ENTRY})
        self.assertEqual(set(self.sources[True]), set(composition.TARGETS))
        self.assertEqual(self.sources[False][composition.ENTRY], self.sources[True][composition.ENTRY])
        for enabled in (False, True):
            with self.subTest(enabled=enabled), tempfile.TemporaryDirectory(prefix='raw-kv-repeat-') as directory:
                out = Path(directory) / 'source'
                result = composition.prepare(out, enable_raw_kv=enabled)
                self.assertEqual(result['generated'], self.reports[enabled]['generated'])
                self.assertEqual(result['active_v4_sources'], 75)
                self.assertEqual(result['original_v4_replacements'], 6)
                self.assertEqual(result['raw_kv_replacements'], 2 if enabled else 0)
                self.assertFalse(result['arithmetic_executed'] or result['public_fullgraph_executed'] or result['old_pass_inherited'])
                with self.assertRaisesRegex(ValueError, 'fresh source directory'):
                    composition.prepare(out, enable_raw_kv=enabled)
        for name, raw in self.originals.items():
            self.assertEqual((composition.ROOT / name).read_text(), raw)
        for bad in (0, 1, None, 'on'):
            with self.assertRaisesRegex(ValueError, 'canonical composition'):
                composition.prepare('never-created', enable_raw_kv=bad)

    def test_exact_runtime_closure_freezes_numeric_bridge_and_pin_drift_fails(self):
        ns = self.entry_namespace(prior=NS(source_hashes=lambda: {}))
        declared = set(ns['RAW_KV_SOURCES'])
        pins = json.loads((composition.HERE / 'pins.json').read_text())
        self.assertEqual(declared, set(pins['raw_kv_sources']))
        self.assertIn(composition.BRIDGE, declared)
        ns.update(EXECUTION_FILES=(), PREFIX='')
        self.assertNotIn(composition.BRIDGE, ns['source_hashes']())
        # Actual prepare copies the real enabled closure in an overlay. Only
        # original reference/receipt prerequisites are synthetic metadata.
        with tempfile.TemporaryDirectory(prefix='raw-kv-bridge-freeze-') as directory:
            root = Path(directory) / 'sources'; root.mkdir()
            fixture = EntryControlTests.synthetic_snapshot_namespace(self, root, 16)
            for name in declared:
                path = root / name; path.parent.mkdir(parents=True, exist_ok=True)
                raw = (self.sources[True][name].encode() if name in self.sources[True]
                       else (composition.ROOT / name).read_bytes())
                path.write_bytes(raw)
            fixture.update(PREFIX='', EXECUTION_FILES=(), RAW_KV_SOURCES=tuple(sorted(declared)))
            fixture['_verify_raw_kv_composition'] = extract(self.entry, ROOT=root)['_verify_raw_kv_composition']
            fixture['prior'].source_hashes = lambda: {}
            hashes = fixture['source_hashes'](enable_raw_kv=True)
            self.assertEqual(set(hashes), declared)
            self.assertEqual(hashes[composition.BRIDGE], file_sha(composition.ROOT / composition.BRIDGE))
            path, snapshot = fixture['prepare'](Path(directory) / 'snapshot', None, None, None, enable_raw_kv=True)
            self.assertEqual(snapshot['source_sha256'], hashes)
            self.assertEqual((path.parent / 'frozen_sources' / composition.BRIDGE).read_bytes(),
                             (composition.ROOT / composition.BRIDGE).read_bytes())
            with self.assertRaisesRegex(ValueError, 'composition/request mode mismatch'):
                fixture['source_hashes'](enable_raw_kv=False)
        original_read = Path.read_bytes
        bridge = composition.ROOT / composition.BRIDGE
        def drift(path):
            raw = original_read(path)
            return raw + b'\n# controlled bridge drift\n' if path == bridge else raw
        with tempfile.TemporaryDirectory(prefix='raw-kv-bridge-drift-') as directory, patch.object(Path, 'read_bytes', drift):
            with self.assertRaisesRegex(ValueError, 'entry original source drift'):
                composition.prepare(Path(directory) / 'source', enable_raw_kv=True)

    def test_real_six_file_preflight_rejects_crossmode_and_each_mutation(self):
        for enabled in (False, True):
            with self.subTest(enabled=enabled), tempfile.TemporaryDirectory(prefix='raw-kv-preflight-') as directory:
                root, _, _ = self.guard_tree(directory, enabled)
                ns = self.entry_namespace(ROOT=root, prior=NS())
                expected = ns['RAW_KV_COMPOSITION_SHA256']['enabled' if enabled else 'disabled']
                self.assertEqual(set(expected), set(composition.TARGETS) - {composition.ENTRY})
                ns['_verify_raw_kv_composition'](enabled)
                with self.assertRaisesRegex(ValueError, 'composition/request mode mismatch'):
                    ns['_verify_raw_kv_composition'](not enabled)
                for name in expected:
                    target = root / name; raw = target.read_bytes()
                    target.write_bytes(raw + b'\n# controlled composition mutation\n')
                    try:
                        for function, args in (('source_hashes', ()), ('runtime', ()),
                                               ('prepare', ('out', None, None, None))):
                            with self.subTest(name=name, function=function), self.assertRaisesRegex(
                                    ValueError, 'composition/request mode mismatch'):
                                ns[function](*args, enable_raw_kv=enabled)
                        snapshot = {} if not enabled else dict(enable_raw_kv=True,
                            raw_kv_source_profile=ns['RAW_KV_SOURCE_PROFILE'])
                        path = root / 'SNAPSHOT.json'; path.write_bytes(encoded(snapshot))
                        with self.assertRaisesRegex(ValueError, 'composition/request mode mismatch'):
                            ns['verify_snapshot'](path, file_sha(path), enable_raw_kv=enabled)
                    finally:
                        target.write_bytes(raw)

    def test_full_preparer_rejects_enabled_only_callback_even_with_rehashed_patch(self):
        original_bytes, original_text = Path.read_bytes, Path.read_text
        patch_path = composition.HERE / 'entry.patch'
        pins_path = composition.HERE / 'pins.json'
        raw = original_bytes(patch_path)
        before = b'+        result.update({name:file_sha(ROOT/name) for name in RAW_KV_SOURCES})'
        self.assertEqual(raw.count(before), 1)
        changed = raw.replace(before, before + b'; unreviewed_callback()')
        pins = json.loads(original_text(pins_path))
        pins['patch_sha256']['entry.patch'] = sha(changed)
        def read_bytes(path):
            return changed if path == patch_path else original_bytes(path)
        def read_text(path, *args, **kwargs):
            return json.dumps(pins) if path == pins_path else original_text(path, *args, **kwargs)
        # The disabled projection intentionally cannot prove enabled semantics.
        # Full preparation must still reject the unchanged generated-byte pins.
        with tempfile.TemporaryDirectory(prefix='raw-kv-enabled-mutation-') as directory, \
                patch.object(Path, 'read_bytes', read_bytes), patch.object(Path, 'read_text', read_text):
            with self.assertRaisesRegex(ValueError, 'composed entry/source-contract identity drift'):
                composition.prepare(Path(directory) / 'source', enable_raw_kv=True)

    def test_guard_inventory_keeps_original_six_then_exactly_two_hooks(self):
        inventory = composition._original_inventory()
        outputs = {}
        for enabled in (False, True):
            with self.subTest(enabled=enabled), tempfile.TemporaryDirectory(prefix='raw-kv-real-guard-') as directory:
                root, helper, _ = self.guard_tree(directory, enabled)
                kwargs = {'enable_raw_kv': True} if enabled else {}
                actual = helper['verify_execution_sources'](**kwargs)
                outputs[enabled] = actual
                self.assertEqual(len(actual), 75)
                if not enabled: self.assertEqual(actual, inventory)
                for key in ('enable_h2048_rms_borrower', 'external_elementwise_loan'):
                    with self.assertRaises(ValueError): helper['verify_execution_sources'](**dict(kwargs, **{key: True}))
                if enabled:
                    with self.assertRaisesRegex(ValueError, 'source drift'):
                        helper['verify_execution_sources'](enable_raw_kv=False)
                unchanged = root / (composition.PREFIX + 'ffn_attention/scalar_recipe.py')
                unchanged.write_bytes(unchanged.read_bytes() + b'\n# stale unchanged source\n')
                with self.assertRaisesRegex(ValueError, 'source drift'):
                    helper['verify_execution_sources'](**kwargs)
        changed = {name for name in inventory if outputs[False][name] != outputs[True][name]}
        self.assertEqual(changed, set(composition.upstream.TARGETS))
        receipt = json.loads((composition.ROOT / composition.INVENTORY).read_text())['source_sha256']
        self.assertEqual(sum(outputs[True][name] == old for name, old in receipt.items()), 67)

    def test_guard_replacement_closure_and_hash_negatives(self):
        with tempfile.TemporaryDirectory(prefix='raw-kv-guard-neg-') as directory:
            _, helper, _ = self.guard_tree(directory, True)
            key = 'RAW_KV_EXECUTION_SOURCE_REPLACEMENTS'
            baseline = deepcopy(helper[key])
            for kind in ('missing', 'extra', 'origin', 'current'):
                changed = deepcopy(baseline)
                name = next(iter(changed))
                if kind == 'missing': del changed[name]
                elif kind == 'extra': changed['unapproved.py'] = ['0' * 64, '1' * 64]
                elif kind == 'origin': changed[name][0] = '0' * 64
                else: changed[name][1] = '0' * 64
                helper[key] = changed
                with self.subTest(kind=kind), self.assertRaises(ValueError):
                    helper['verify_execution_sources'](enable_raw_kv=True)
            helper[key] = baseline
            for bad in (1, None, 'yes'):
                with self.assertRaisesRegex(ValueError, 'canonical raw KV'):
                    helper['verify_execution_sources'](enable_raw_kv=bad)

    def test_real_observer_hash_selection_and_constructor_delta_remain_fail_closed(self):
        with tempfile.TemporaryDirectory(prefix='raw-kv-observer-') as directory:
            root, helper, names = self.guard_tree(directory, True)
            base = NS(sha=sha, SOURCE_VERSION=helper['SOURCE_VERSION'],
                      verify_execution_sources=helper['verify_execution_sources'])
            source = (root / composition.GUARDS[1]).read_text()
            observer = extract(source, functions={'verify_source_snapshot'}, ROOT=root, base=base)
            hashes = {name: file_sha(root / name) for name in names}
            actual = observer['verify_source_snapshot'](hashes, enable_raw_kv=True)
            self.assertEqual(len(actual), 75)
            with self.assertRaisesRegex(ValueError, 'helper source drift'):
                observer['verify_source_snapshot'](hashes, enable_raw_kv=False)
            missing = dict(hashes); del missing[next(iter(actual))]
            with self.assertRaises(ValueError): observer['verify_source_snapshot'](missing, enable_raw_kv=True)
            extra = dict(hashes, **{'../outside.py': '0' * 64})
            with self.assertRaisesRegex(ValueError, 'invalid frozen source'):
                observer['verify_source_snapshot'](extra, enable_raw_kv=True)
            stale = dict(hashes); stale[composition.GUARDS[1]] = '0' * 64
            with self.assertRaisesRegex(ValueError, 'observation source drift'):
                observer['verify_source_snapshot'](stale, enable_raw_kv=True)
            profiled = extract((root / composition.GUARDS[3]).read_text(), functions={'verify_constructor_delta'},
                ROOT=root, ast=ast, base=base,
                original=NS(SOURCE_VERSION=observer['SOURCE_VERSION'], OBSERVER=composition.GUARDS[1]),
                monitoring=NS(MONITORING=composition.GUARDS[2]))
            profiled['verify_constructor_delta'](enable_raw_kv=True)
            with self.assertRaisesRegex(ValueError, 'constructor source drift'):
                profiled['verify_constructor_delta'](enable_raw_kv=False)
            capture = root / composition.GUARDS[1]
            capture.write_bytes(capture.read_bytes() + b'\n# stale capture hash\n')
            with self.assertRaisesRegex(ValueError, 'constructor source drift'):
                profiled['verify_constructor_delta'](enable_raw_kv=True)

    def test_whole_ast_scope_rejects_comparison_callback_and_crossmode_changes(self):
        generated = self.sources[True]
        for name, method in ((composition.ENTRY, 'compare'), (composition.GUARDS[1], '_line')):
            tree = ast.parse(generated[name])
            function = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == method)
            function.body.append(ast.Pass())
            changed = dict(generated, **{name: ast.unparse(ast.fix_missing_locations(tree))})
            with self.subTest(method=method), self.assertRaisesRegex(ValueError, 'disabled source projection'):
                composition.check_scope(self.originals, changed, enable_raw_kv=True)
        with self.assertRaisesRegex(ValueError, 'target scope'):
            composition.check_scope(self.originals, self.sources[False], enable_raw_kv=True)
        with self.assertRaisesRegex(ValueError, 'target scope'):
            composition.check_scope(self.originals, generated, enable_raw_kv=False)
        with self.assertRaisesRegex(ValueError, 'target scope'):
            composition.check_scope(self.originals, dict(generated, **{'extra.py': ''}), enable_raw_kv=True)


if __name__ == '__main__':
    unittest.main()
