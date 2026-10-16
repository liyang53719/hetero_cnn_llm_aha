"""Cold fresh-profile controls: metadata fixtures are not numerical evidence.

No weights, reference producers, native libraries or numerical verifiers run.
Pure schema fixtures describe synthetic paths; only tiny temporary files exercise
actual filesystem guards. Original source composition is checked separately.
"""
import argparse
import ast
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
import math
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

from . import assets
from . import prepare as composition


def literal(relative, name):
    tree = ast.parse((assets.ROOT / relative).read_text())
    value = next(n.value for n in tree.body if isinstance(n, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == name for t in n.targets))
    return ast.literal_eval(value)


def metadata_fixture():
    """Schema-only synthetic fixture; it contains no materialized asset files."""
    def record(name, size=1, digest='0' * 64):
        return dict(path='CONTROL_ONLY/' + name, bytes=size, sha256=digest)
    sources = {'CONTROL_ONLY/source.py': '0' * 64}
    result = dict(schema=1, status=assets.STATUS, profile=assets.PROFILE, rows=16, past_tokens=0,
                  source_sha256=sources, source_manifest_sha256=assets.sha(assets.encoded(sources)),
                  payload=dict(manifest=record('payload/manifest.json'), tensors={
                      name: record('payload/' + name, pin['bytes'], pin['sha256'])
                      for name, pin in assets.TENSOR_PINS.items()}),
                  readonly=dict(arena=record('readonly/arena', assets.ARENA_BYTES, assets.ARENA_SHA256),
                      table=record('readonly/table', (192 + 5 * 16384) * 4, assets.TABLE_SHA256),
                      input_x=record('readonly/input_x', 16 * 1536 * 4, assets.INPUT_X_SHA256),
                      input_x_sha256=assets.INPUT_X_SHA256, intermediate_preloads=0),
                  native=dict(producer=assets.NATIVE_PRODUCER, result=record('native/RESULT.json'),
                      outputs={mode: {method: {name: record('native/' + mode + '/' + method + '/' + name,
                          4 * math.prod(shape)) for name, shape in assets.shapes().items()}
                          for method in assets.METHODS} for mode in assets.MODES}),
                  library=dict(receipt=record('library/receipt.json'), binary=record('library/library.so')))
    for role in ('sequential', 'reduced'):
        result[role] = dict(producer=assets.PRODUCERS[role],
            cpp=record(role + '/candidate.cpp', digest=assets.CPP_SHA256[role]),
            header=record(role + '/block_layout.h', digest=assets.HEADER_SHA256),
            executable=record(role + '/candidate'), compile=record(role + '/compile.json'),
            run=record(role + '/run.json'), outputs={name: record(role + '/raw_stages/' + name, size)
                for name, size in assets.output_inventory().items()})
    result['sequential'].update(export_receipt=record('sequential/export.json'), tensors={
        name: record('sequential/tensors/' + name, 4 * math.prod(shape))
        for name, shape in assets.shapes().items()})
    return result


def at(value, path):
    for part in path:
        value = value[part]
    return value


class ManifestTests(unittest.TestCase):
    def test_schema_only_fixture_validates_without_import_or_artifact_access(self):
        value = metadata_fixture()
        with patch('builtins.__import__', side_effect=AssertionError('unexpected import')), \
                patch.object(Path, 'open', side_effect=AssertionError('unexpected artifact access')):
            self.assertIs(assets.validate_manifest(value), value)
        self.assertEqual(len(value['payload']['tensors']), 13)
        self.assertEqual([len(value[r]['outputs']) for r in ('sequential', 'reduced')], [22, 22])
        self.assertEqual(len(value['sequential']['tensors']), 29)
        self.assertEqual(sum(len(nodes) for methods in value['native']['outputs'].values()
                             for nodes in methods.values()), 116)

    def test_geometry_matches_original_sources_without_importing_producers(self):
        prefix = 'candidates/qwen2_resident_matrix/'
        names = literal(prefix + 'ffn_public/check_prefix_numeric.py', 'TENSORS')
        names.update(literal(prefix + 'ffn_public/check_fullgraph_numeric.py', 'EXTRA_TENSORS'))
        self.assertEqual({name: shape for name, shape in names.values()},
                         {name: pin['shape'] for name, pin in assets.TENSOR_PINS.items()})
        self.assertEqual(sum(pin['bytes'] for pin in assets.TENSOR_PINS.values()), 94382080)
        self.assertEqual(set(assets.shapes()), literal('scripts/qwen2_layer0_model_gate.py', 'REQUIRED_STAGES'))
        stages = literal(prefix + 'dense_block_reduce/reference/workload.py', 'STAGES')
        self.assertEqual(assets.STAGES, stages)
        self.assertEqual(assets.export_shapes()['q'], [1, 16, 1536])
        self.assertEqual(assets.export_shapes()['k'], [1, 16, 256])
        self.assertEqual((assets.ARENA_BYTES, (192 + 5 * 16384) * 4, 16 * 1536 * 4),
                         (188043264, 328448, 98304))
        self.assertNotEqual(assets.CPP_SHA256['sequential'], assets.CPP_SHA256['reduced'])

    def test_workload_profile_and_zero_preload_are_canonical(self):
        for bad in (True, False, 16.0, 0, 1, 8, 128, '16', None):
            with self.subTest(rows=bad), self.assertRaises(ValueError):
                assets.validate_manifest(metadata_fixture(), rows=bad)
        cases = {'schema': (True, 0, '1'), 'rows': (True, 16.0, 128),
                 'past_tokens': (False, 0.0, 1, 128),
                 'profile': ('archived', '', None), 'status': ('PASS', 'PARTIAL', None)}
        for key, values in cases.items():
            for bad in values:
                value = metadata_fixture(); value[key] = bad
                with self.subTest(key=key, bad=bad), self.assertRaises(ValueError):
                    assets.validate_manifest(value)
        for key, bad in (('intermediate_preloads', True), ('intermediate_preloads', 1),
                         ('input_x_sha256', '0' * 64)):
            value = metadata_fixture(); value['readonly'][key] = bad
            with self.subTest(key=key), self.assertRaises(ValueError): assets.validate_manifest(value)

    def test_exact_top_nested_and_file_record_keys(self):
        paths = [(), ('payload',), ('readonly',), ('sequential',), ('reduced',), ('native',),
                 ('library',), ('payload', 'tensors'), ('sequential', 'outputs'),
                 ('reduced', 'outputs'), ('sequential', 'tensors'), ('native', 'outputs'),
                 ('native', 'outputs', 'bf16'), ('native', 'outputs', 'bf16', 'official_self_cache'),
                 ('payload', 'manifest')]
        for path in paths:
            for kind in ('missing', 'extra'):
                value = metadata_fixture(); target = at(value, path)
                if kind == 'missing': del target[next(iter(target))]
                else: target['UNAPPROVED'] = None
                with self.subTest(path=path, kind=kind), self.assertRaises(ValueError):
                    assets.validate_manifest(value)

    def test_hashes_sizes_and_pinned_identities_reject_drift(self):
        for bad in ('A' * 64, 'g' * 64, '0' * 63, '', None, 0, True):
            value = metadata_fixture(); value['library']['binary']['sha256'] = bad
            with self.subTest(hash=bad), self.assertRaises(ValueError): assets.validate_manifest(value)
        for bad in (True, 1.0, -1, assets.ARENA_BYTES + 1, '1', None):
            value = metadata_fixture(); value['library']['binary']['bytes'] = bad
            with self.subTest(bytes=bad), self.assertRaises(ValueError): assets.validate_manifest(value)
        paths = [('readonly', k) for k in ('arena', 'table', 'input_x')]
        paths += [('payload', 'tensors', k) for k in assets.TENSOR_PINS]
        paths += [(r, k) for r in ('sequential', 'reduced') for k in ('cpp', 'header')]
        for path in paths:
            value = metadata_fixture(); at(value, path)['sha256'] = '0' * 64
            with self.subTest(path=path), self.assertRaises(ValueError): assets.validate_manifest(value)
        value = metadata_fixture(); value['sequential']['outputs'][next(iter(assets.output_inventory()))]['bytes'] -= 1
        with self.assertRaises(ValueError): assets.validate_manifest(value)
        value = metadata_fixture(); value['native']['outputs']['bf16']['official_self_cache']['q']['bytes'] -= 1
        with self.assertRaises(ValueError): assets.validate_manifest(value)
        value = metadata_fixture(); value['source_manifest_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'source manifest digest'): assets.validate_manifest(value)

    def test_artifact_and_source_path_schema_rejects_escaping_spellings(self):
        paths = ('/absolute', '../escape', 'a/../escape', './a', 'a//b', 'a/', '', 'a\\b', 'a\x00b')
        for name in paths:
            value = metadata_fixture(); value['library']['binary']['path'] = name
            with self.subTest(artifact=name), self.assertRaises(ValueError): assets.validate_manifest(value)
            value = metadata_fixture(); value['source_sha256'] = {name: '0' * 64}
            value['source_manifest_sha256'] = assets.sha(assets.encoded(value['source_sha256']))
            with self.subTest(source=name), self.assertRaises(ValueError): assets.validate_manifest(value)


class ProfileTests(unittest.TestCase):
    def test_flags_and_fresh_arguments_are_canonical_without_file_access(self):
        with patch.object(Path, 'open', side_effect=AssertionError('profile opened a file')):
            self.assertFalse(assets.fresh_mode(False))
            self.assertTrue(assets.fresh_mode(True, 'CONTROL_ONLY/manifest', '0' * 64, rows=16))
            for bad in (0, 1, None, 'true'):
                with self.subTest(flag=bad), self.assertRaises(ValueError): assets.fresh_mode(bad)
            for args in ((False, 'manifest', None), (False, None, '0' * 64),
                         (True, None, '0' * 64), (True, 'manifest', None)):
                with self.subTest(args=args), self.assertRaises(ValueError): assets.fresh_mode(*args)
            for rows in (True, 16.0, 0, 128):
                with self.subTest(rows=rows), self.assertRaises(ValueError):
                    assets.fresh_mode(True, 'manifest', '0' * 64, rows=rows)

    def test_snapshot_profile_and_raw_mode_matching_are_exact(self):
        def snapshot(raw=False):
            return dict(rows=16, fresh_profile=True, fresh_assets=dict(profile=assets.PROFILE,
                manifest='CONTROL_ONLY/manifest', manifest_sha256='0' * 64, enable_raw_kv=raw))
        self.assertIsNone(assets.snapshot_mode({'rows': 16}, False))
        for raw in (False, True):
            value = snapshot(raw)
            self.assertEqual(assets.snapshot_mode(value, True, enable_raw_kv=raw), value['fresh_assets'])
            with self.assertRaisesRegex(ValueError, 'source profile mismatch'):
                assets.snapshot_mode(value, True, enable_raw_kv=not raw)
            with self.assertRaisesRegex(ValueError, 'fresh profile mismatch'):
                assets.snapshot_mode(value, False, enable_raw_kv=raw)
        for value in ({'rows':16}, {'rows':16,'fresh_profile':False},
                      {'rows':16,'fresh_profile':True}, {'rows':16,'fresh_assets':{}}):
            with self.subTest(value=value), self.assertRaises(ValueError): assets.snapshot_mode(value, True)
        for key, bad in (('profile', 'archived'), ('enable_raw_kv', 1),
                         ('manifest_sha256', 'stale')):
            value = snapshot(); value['fresh_assets'][key] = bad
            with self.subTest(key=key), self.assertRaises(ValueError): assets.snapshot_mode(value, True)
        for missing in ('profile','manifest','manifest_sha256','enable_raw_kv'):
            value = snapshot(); del value['fresh_assets'][missing]
            with self.subTest(missing=missing), self.assertRaises(ValueError): assets.snapshot_mode(value, True)
        value = snapshot(); value['fresh_assets']['unapproved'] = True
        with self.assertRaises(ValueError): assets.snapshot_mode(value, True)
        for key in ('fresh_profile','fresh_assets'):
            with self.assertRaises(ValueError): assets.snapshot_mode({'rows':16,key:False}, False)

    def test_source_inventory_matches_real_immutable_ledger(self):
        path = assets.ROOT / assets.LEDGER
        self.assertEqual(assets.file_sha(path), assets.LEDGER_SHA256)
        ledger = json.loads(path.read_text())
        self.assertEqual((ledger['model_id'], ledger['revision'], ledger['layer_id']),
                         (assets.MODEL, assets.REVISION, 0))
        expected = {record['local_name']: {key: record[key] for key in ('bytes','sha256','shape')}
                    for record in ledger['tensors']}
        self.assertEqual(expected, assets.TENSOR_PINS)


class ManifestReadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='fresh-manifest-cold-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'MANIFEST.json'

    def write(self, raw=None):
        raw = assets.encoded(metadata_fixture()) if raw is None else raw
        self.path.write_bytes(raw)
        return assets.sha(raw)

    def test_schema_only_read_never_touches_referenced_artifacts_or_imports(self):
        digest = self.write()
        with patch.object(assets, 'resolve_artifact', side_effect=AssertionError('artifact access')), \
                patch('builtins.__import__', side_effect=AssertionError('runtime import')):
            self.assertEqual(assets.read_manifest(self.path, digest), metadata_fixture())
        # A schema-only read does not certify READY artifacts or execute a verifier.
        self.assertEqual(list(self.root.iterdir()), [self.path])

    def test_rows_and_digest_rejected_before_manifest_open(self):
        with patch.object(assets, 'safe_path', side_effect=AssertionError('manifest access')):
            for rows in (True, 16.0, 0, 128, '16', None):
                with self.subTest(rows=rows), self.assertRaisesRegex(ValueError, 'canonical M16'):
                    assets.read_manifest(self.path, '0' * 64, rows=rows)
            for digest in (True, None, '0' * 63, 'A' * 64):
                with self.subTest(digest=digest), self.assertRaisesRegex(ValueError, 'digest required'):
                    assets.read_manifest(self.path, digest)

    def test_duplicate_nonfinite_oversize_and_wrong_hash_rejected(self):
        cases = [(b'{"schema":1,"schema":1}', 'duplicate'),
                 (b'{"x":NaN}', 'nonfinite'), (b'{"x":Infinity}', 'nonfinite'),
                 (b'{"x":-Infinity}', 'nonfinite'), (b'{"x":1e999}', 'nonfinite'),
                 (b' ' * (assets.MAX_MANIFEST_BYTES + 1), 'byte bound')]
        for raw, reason in cases:
            digest = self.write(raw)
            with self.subTest(reason=reason, length=len(raw)), self.assertRaisesRegex(ValueError, reason):
                assets.read_manifest(self.path, digest)
        self.write()
        with self.assertRaisesRegex(ValueError, 'hash drift'):
            assets.read_manifest(self.path, '0' * 64)

    def test_json_numeric_overflow_is_rejected_even_inside_nested_values(self):
        for raw in (b'{"x":1e999}', b'{"x":[0,{"nested":-1e999}]}'):
            with self.subTest(raw=raw), self.assertRaisesRegex(ValueError, 'nonfinite'):
                assets.json_bytes(raw)

    def test_returned_manifest_is_bound_to_the_exact_hashed_bytes(self):
        original = metadata_fixture(); digest = self.write(assets.encoded(original))
        changed = deepcopy(original)
        changed['source_sha256'] = {'CONTROL_ONLY/changed.py': '1' * 64}
        changed['source_manifest_sha256'] = assets.sha(assets.encoded(changed['source_sha256']))
        raw = assets.encoded(changed); original_open = Path.open; reads = []
        def open_with_controlled_change(path, mode='r', *args, **kwargs):
            if path == self.path and 'r' in mode:
                reads.append(mode)
                if len(reads) == 2:
                    with original_open(path, 'wb') as stream: stream.write(raw)
            return original_open(path, mode, *args, **kwargs)
        with patch.object(Path, 'open', open_with_controlled_change):
            try:
                observed = assets.read_manifest(self.path, digest)
            except ValueError:
                return  # A detected concurrent change is fail-closed.
        self.assertEqual(assets.sha(assets.encoded(observed)), digest,
                         'parsed manifest escaped its supplied content hash')

    def test_nonregular_or_symlink_manifest_rejected_before_hashing(self):
        self.write()
        alias = self.root / 'alias.json'; alias.symlink_to(self.path)
        fifo = self.root / 'pipe.json'; os.mkfifo(fifo)
        with patch.object(assets, 'file_sha', side_effect=AssertionError('invalid file opened')):
            for path in (alias, fifo, self.root):
                with self.subTest(path=path.name), self.assertRaises(ValueError):
                    assets.read_manifest(path, '0' * 64)


class VerifierBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='fresh-verify-boundary-')
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'MANIFEST.json'

    def write(self, value):
        raw = assets.encoded(value); self.path.write_bytes(raw)
        return assets.sha(raw)

    def test_invalid_raw_mode_rows_and_profile_stop_before_artifact_or_import(self):
        with patch.object(assets, 'read_manifest', side_effect=AssertionError('manifest accessed')):
            for mode in (0, 1, 'false', None):
                with self.subTest(raw_mode=mode), self.assertRaisesRegex(ValueError, 'canonical raw KV'):
                    assets.verify(self.path, '0' * 64, enable_raw_kv=mode)
        with patch.object(assets, 'safe_path', side_effect=AssertionError('manifest accessed')):
            for rows in (True, 16.0, 128):
                with self.subTest(rows=rows), self.assertRaisesRegex(ValueError, 'canonical M16'):
                    assets.verify(self.path, '0' * 64, rows=rows)
        for key, bad in (('profile','archived'), ('rows',128), ('past_tokens',1), ('schema',True)):
            value = metadata_fixture(); value[key] = bad; digest = self.write(value)
            with patch.object(assets, 'source_snapshot', side_effect=AssertionError('source access')), \
                    patch.object(assets, 'checked_artifact', side_effect=AssertionError('artifact access')), \
                    patch('builtins.__import__', side_effect=AssertionError('native import')):
                with self.subTest(key=key), self.assertRaises(ValueError): assets.verify(self.path, digest)

    def test_source_profile_mismatch_stops_before_referenced_artifacts(self):
        value = metadata_fixture(); digest = self.write(value)
        # Synthetic source identity only tests ordering; no verifier success is claimed.
        with patch.object(assets, 'source_snapshot', return_value={'OTHER_PROFILE.py':'1' * 64}) as source, \
                patch.object(assets, 'checked_artifact', side_effect=AssertionError('artifact access')), \
                patch('builtins.__import__', side_effect=AssertionError('native import')):
            with self.assertRaisesRegex(ValueError, 'producer source closure differs'):
                assets.verify(self.path, digest, enable_raw_kv=True)
            source.assert_called_once_with(enable_raw_kv=True)

    def test_schema_only_fixture_cannot_become_verified_ready(self):
        value = metadata_fixture(); digest = self.write(value)
        with patch.object(assets, 'source_snapshot', return_value=value['source_sha256']), \
                patch('builtins.__import__', side_effect=AssertionError('native import')):
            with self.assertRaises(FileNotFoundError): assets.verify(self.path, digest)

    def test_native_bf16_failure_cannot_reach_readiness_or_runtime_checks(self):
        manifest = metadata_fixture()
        result = dict(schema_version=1, status='FAIL_BF16_STAGE_BUDGET', model_id=assets.MODEL,
            layer=0, tokens=16, carried=False, m16_gate_sha256=None, torch_threads=4,
            payload_manifest_sha256=manifest['payload']['manifest']['sha256'],
            official_framework_forward=True, rtl_execution=False, hardware_recipe_acceptance=False,
            logits=False, full_model_quality=False, manifest_whole_checkpoint_hash_verified=False)
        native = Mock()
        native.runtime_identity.side_effect = AssertionError('failed native receipt reached runtime')
        with patch.object(assets, 'metadata', return_value=result):
            with self.assertRaises(ValueError): assets._verify_native(self.path.parent, manifest, native)
        native.runtime_identity.assert_not_called()

    def native_mask_control_fixture(self):
        """Partial metadata fixture that must stop at the first mask type check."""
        manifest = metadata_fixture()
        semantics = ('mask_exact','native_fp32_probability_sum_within_2e_5',
            'independent_fp32_probability_sum_within_2e_5','native_cache_append_k_exact',
            'native_cache_append_v_exact','independent_cache_append_k_exact','independent_cache_append_v_exact',
            'native_future_probability_zero','independent_future_probability_zero')
        mask = dict(shape=assets.shapes()['mask'], elements=256, finite=True, bit_exact=True, passed=True)
        stages = dict(mask=mask)
        stages.update({name:{} for name in assets.shapes() if name != 'mask'})
        phase = dict(phase=0, past_tokens=0, token_ids=list(range(16)), position_ids=list(range(16)),
                     semantics=dict.fromkeys(semantics,True), all_semantics_exact=True, stages=stages)
        result = dict(schema_version=1, status='PASS_BF16_STAGE_BUDGET', model_id=assets.MODEL,
            layer=0, tokens=16, carried=False, m16_gate_sha256=None, torch_threads=4,
            payload_manifest_sha256=manifest['payload']['manifest']['sha256'],
            official_framework_forward=True, rtl_execution=False, hardware_recipe_acceptance=False,
            logits=False, full_model_quality=False, manifest_whole_checkpoint_hash_verified=False,
            identity={}, policy={}, modes=dict(bf16=dict(phases=[phase]), fp32=dict(phases=[])))
        native = Mock()
        native.runtime_identity.return_value = (None,{})
        native.load_policy.return_value = {}
        return manifest,result,mask,native

    def test_native_passed_integer_aliases_reject_against_boolean_verdict(self):
        for bad in (0,1):
            manifest,result,mask,native = self.native_mask_control_fixture()
            mask['passed'] = bad
            native.stage_verdict.return_value = {'passed':bool(bad)}
            with patch.object(assets,'metadata',return_value=result), \
                    patch.object(assets,'resolve_artifact',return_value=self.path.parent / 'native/RESULT.json') as resolve:
                with self.subTest(passed=bad), self.assertRaisesRegex(ValueError,'stage verdict differs'):
                    assets._verify_native(self.path.parent,manifest,native)
            native.stage_verdict.assert_called_once_with('mask',mask,'bf16',{})
            resolve.assert_called_once()  # No exported tensor path was reached.

    def test_native_mask_bit_exact_integer_aliases_reject_before_verdict(self):
        for bad in (0,1):
            manifest,result,mask,native = self.native_mask_control_fixture()
            mask['bit_exact'] = bad
            native.stage_verdict.side_effect = AssertionError('noncanonical mask reached verdict')
            with patch.object(assets,'metadata',return_value=result), \
                    patch.object(assets,'resolve_artifact',return_value=self.path.parent / 'native/RESULT.json'):
                with self.subTest(bit_exact=bad), self.assertRaisesRegex(ValueError,'bit-exact flag must be boolean'):
                    assets._verify_native(self.path.parent,manifest,native)
            native.stage_verdict.assert_not_called()

    def test_runtime_string_subclass_serializes_but_bool_int_metadata_drift_rejects(self):
        class VersionString(str): pass
        class ControlBoundary(Exception): pass
        manifest,result,mask,native = self.native_mask_control_fixture()
        live_identity = dict(version=VersionString('CONTROL_ONLY_VERSION'), threads=1, enabled=True)
        result['identity'] = json.loads(assets.encoded(live_identity))
        result['policy'] = dict(rows=16, enabled=True)
        self.assertIs(type(result['identity']['version']),str)
        native.runtime_identity.return_value = (None,live_identity)
        native.load_policy.return_value = dict(result['policy'])
        native.stage_verdict.side_effect = ControlBoundary('metadata accepted; no verdict executed')
        with patch.object(assets,'metadata',return_value=result), \
                patch.object(assets,'resolve_artifact',return_value=self.path.parent / 'native/RESULT.json'):
            with self.assertRaises(ControlBoundary): assets._verify_native(self.path.parent,manifest,native)
        native.stage_verdict.assert_called_once_with('mask',mask,'bf16',result['policy'])
        for field,key,value in (('identity','threads',True),('identity','enabled',1),
                                ('policy','rows',16.0),('policy','enabled',1)):
            changed = deepcopy(result); changed[field][key] = value
            native.stage_verdict.reset_mock()
            with patch.object(assets,'metadata',return_value=changed), \
                    patch.object(assets,'resolve_artifact',side_effect=AssertionError('typed drift reached artifacts')):
                with self.subTest(field=field,key=key), self.assertRaisesRegex(ValueError,'runtime/source/threshold identity'):
                    assets._verify_native(self.path.parent,manifest,native)
            native.stage_verdict.assert_not_called()

    def test_invalid_late_reference_geometry_or_hash_rejects_before_array_import(self):
        reference = dict(fresh_profile=assets.PROFILE, fresh_lookup={
            'references/official_self_cache/q.f32le':dict(path='CONTROL_ONLY/q', bytes=98304, sha256='0' * 64)})
        with patch('builtins.__import__', side_effect=AssertionError('array import')):
            for values in (dict(rows=128, method='official_self_cache', name='q', shape=(1,12,128,128)),
                           dict(rows=16, method='wrong', name='q', shape=(1,12,16,128)),
                           dict(rows=16, method='official_self_cache', name='q', shape=(1,16,12,128)),
                           dict(rows=16, method='official_self_cache', name='q', shape=(1,12,16,128))):
                with self.subTest(values=values), self.assertRaises(ValueError):
                    assets.read_native_reference(reference, b'CONTROL_ONLY', **values)


class ViewMappingTests(unittest.TestCase):
    def test_fresh_rope_label_is_exact_original_rms_policy_literal(self):
        source = ast.parse((assets.ROOT / 'scripts/qwen2_rms_rope_prefill_candidate.py').read_text())
        policy = next(node.value for node in source.body if isinstance(node,ast.Assign)
                      and any(isinstance(target,ast.Name) and target.id == 'POLICY' for target in node.targets))
        self.assertIsInstance(policy,ast.Call)
        original = ast.literal_eval(next(keyword.value for keyword in policy.keywords if keyword.arg == 'rope'))
        fresh = ast.parse(Path(assets.__file__).read_text())
        views = next(node for node in fresh.body if isinstance(node,ast.FunctionDef) and node.name == '_views')
        labels = [ast.literal_eval(keyword.value) for node in ast.walk(views) if isinstance(node,ast.Call)
                  for keyword in node.keywords if keyword.arg == 'rope_table_recipe']
        self.assertEqual(labels,[original])

    def test_control_only_views_keep_producers_and_diagnostic_meanings_separate(self):
        manifest = metadata_fixture()
        manifest['source_sha256']['scripts/qwen2_layer0_model_gate.py'] = '1' * 64
        root = Path('/CONTROL_ONLY')
        native = dict(status='CONTROL_ONLY_NOT_VERIFIED', policy={}, identity={}, modes={
            'bf16':dict(phases=[dict(failed_stages=['CONTROL_ONLY_DIAGNOSTIC'])])})
        # Exercise mapping only, never verify(); file resolution is explicitly mocked.
        with patch.object(assets, 'resolve_artifact', side_effect=lambda workspace, record: root / record['path']):
            view = assets._views(root, root / 'manifest.json', '2' * 64, manifest, [], native,
                                 {'reduced':root / 'reduced/raw_stages'}, enable_raw_kv=True)
        reference, reduced = view['reference'], view['independent_reference']
        self.assertEqual(reference['prior_failures'], {})
        self.assertEqual(view['provenance']['native_vs_independent_failed_stages'], ['CONTROL_ONLY_DIAGNOSTIC'])
        self.assertFalse(view['provenance']['historical_receipts_reused'])
        self.assertFalse(view['provenance']['actual_chain_executed'])
        self.assertEqual(len(reference['fresh_lookup']), 22 + 29 + 58)
        self.assertEqual(len(reduced['fresh_lookup']), 22)
        for name, record in manifest['sequential']['outputs'].items():
            self.assertEqual(reference['fresh_lookup']['raw_stages/' + name], record)
            self.assertEqual(reduced['fresh_lookup']['raw_stages/' + name], manifest['reduced']['outputs'][name])
        for name in ('scores','logits','softmax_fp32','prob','pv','silu'):
            self.assertEqual(reference['fresh_lookup']['tensors/candidate_' + name + '.f32le'],
                             manifest['sequential']['tensors'][name])
        for method in assets.METHODS:
            for name in assets.shapes():
                self.assertEqual(reference['fresh_lookup']['references/' + method + '/' + name + '.f32le'],
                                 manifest['native']['outputs']['bf16'][method][name])


class SourceCompositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='fresh-entries-cold-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.reports, cls.sources, cls.baselines = {}, {}, {}
        for enabled in (False, True):
            output = Path(cls.temp.name) / ('on' if enabled else 'off')
            cls.reports[enabled] = composition.prepare(output, enable_raw_kv=enabled)
            cls.sources[enabled] = {name:(output / name).read_text() for name in cls.reports[enabled]['generated']}
            baseline = Path(cls.temp.name) / ('base-on' if enabled else 'base-off')
            composition.upstream.prepare(baseline, enable_raw_kv=enabled)
            cls.baselines[enabled] = {composition.OFFICIAL:(assets.ROOT / composition.OFFICIAL).read_text(),
                                     composition.ENTRY:(baseline / composition.ENTRY).read_text()}

    def namespace(self, name):
        tree = ast.parse(self.sources[False][name])
        ns = dict(Path=Path, json=json, argparse=argparse, ROOT=assets.ROOT, fresh_assets=assets,
                  require=assets.need, file_sha=assets.file_sha, sha=assets.sha, encoded=assets.encoded,
                  __doc__='Cold extracted entry control', prior=NS(), old=NS())
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                try: ns[node.targets[0].id] = ast.literal_eval(node.value)
                except (ValueError, TypeError): pass
        functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
        exec(compile(ast.Module(body=functions, type_ignores=[]), '<cold-fresh-entry>', 'exec'), ns)
        return ns

    def test_real_composition_is_reproducible_exact_scope_and_fresh_only(self):
        self.assertEqual(len(self.reports[False]['generated']), 2)
        self.assertEqual(len(self.reports[True]['generated']), 8)
        for enabled in (False, True):
            report = self.reports[enabled]
            self.assertEqual(set(report['fresh_targets']), set(composition.FRESH_TARGETS))
            self.assertFalse(report['historical_assets_relabelled'] or report['numerical_execution'] or report['native_execution'])
            with tempfile.TemporaryDirectory(prefix='fresh-repeat-') as directory:
                output = Path(directory) / 'source'
                repeated = composition.prepare(output, enable_raw_kv=enabled)
                self.assertEqual(repeated['generated'], report['generated'])
                with self.assertRaisesRegex(ValueError, 'fresh composition directory'):
                    composition.prepare(output, enable_raw_kv=enabled)

    def test_real_source_snapshot_freezes_profiles_and_rejects_drift(self):
        for enabled in (False, True):
            with self.subTest(enabled=enabled), tempfile.TemporaryDirectory(prefix='fresh-source-overlay-') as directory:
                root = Path(directory)
                for name in self.reports[enabled]['inputs']:
                    path = root / name; path.parent.mkdir(parents=True, exist_ok=True)
                    raw = (self.sources[enabled][name].encode() if name in self.sources[enabled]
                           else (assets.ROOT / name).read_bytes())
                    path.write_bytes(raw)
                here = root / composition.HERE.relative_to(composition.ROOT)
                with patch.object(assets, 'ROOT', root), patch.object(assets, 'HERE', here):
                    snapshot = assets.source_snapshot(enable_raw_kv=enabled)
                    expected = dict(self.reports[enabled]['inputs'], **self.reports[enabled]['generated'])
                    self.assertEqual(snapshot, expected)
                    with self.assertRaisesRegex(ValueError, 'source composition drift'):
                        assets.source_snapshot(enable_raw_kv=not enabled)
                    ledger = root / assets.LEDGER; ledger.write_bytes(ledger.read_bytes() + b'\n')
                    with self.assertRaisesRegex(ValueError, 'source composition drift'):
                        assets.source_snapshot(enable_raw_kv=enabled)

    def test_disabled_profile_freezes_loaded_helper_and_rejects_helper_drift(self):
        official = self.namespace(composition.OFFICIAL)
        official.update(old=NS(source_hashes=lambda:{}), NEW_SOURCES=())
        public = self.namespace(composition.ENTRY)
        public.update(prior=NS(source_hashes=official['source_hashes']), EXECUTION_FILES=(), PREFIX='')
        expected = assets.own_sources()
        self.assertEqual(set(expected), {str((composition.HERE / name).relative_to(composition.ROOT))
                                         for name in composition.OWN_INPUTS})
        self.assertEqual(len(expected),7)
        with patch.object(assets,'source_snapshot',side_effect=AssertionError('fresh producer closure reached')):
            for ns in (official,public):
                self.assertEqual(ns['source_hashes'](fresh_profile=False),expected)
            original_sha = assets.file_sha
            helper = Path(assets.__file__)
            def drift(path): return '0' * 64 if Path(path) == helper else original_sha(path)
            with patch.object(assets,'file_sha',side_effect=drift):
                for ns in (official,public):
                    with self.assertRaisesRegex(ValueError,'loaded fresh verifier source drift'):
                        ns['source_hashes'](fresh_profile=False)

    def test_entry_flags_and_m16_admission_precede_artifact_access_and_runtime(self):
        for name in composition.FRESH_TARGETS:
            ns = self.namespace(name)
            args = {'source_hashes':(), 'runtime':(), 'verify_snapshot':('unused','0' * 64),
                    'prepare': ('unused', None) if name == composition.OFFICIAL else ('unused',None,None,None)}
            if name == composition.ENTRY: args['run'] = ('unused','unused','0' * 64)
            for function, positional in args.items():
                for bad in (0, 1, None, 'true'):
                    with self.subTest(entry=name, function=function, bad=bad), self.assertRaisesRegex(ValueError, 'canonical'):
                        ns[function](*positional, fresh_profile=bad)
            with patch.object(assets, 'verify', side_effect=AssertionError('artifact verifier reached')):
                with self.assertRaisesRegex(ValueError, 'canonical M16'):
                    ns['prepare'](*args['prepare'], rows=128, fresh_profile=True,
                                  fresh_manifest='CONTROL_ONLY', fresh_manifest_sha256='0' * 64)

    def test_entry_cross_profile_snapshot_rejection_precedes_runtime(self):
        with tempfile.TemporaryDirectory(prefix='fresh-cross-profile-') as directory:
            path = Path(directory) / 'SNAPSHOT.json'
            for name in composition.FRESH_TARGETS:
                ns = self.namespace(name)
                ns['runtime'] = Mock(side_effect=AssertionError('runtime reached'))
                for stored, requested in ((False, True), (True, False)):
                    snapshot = dict(rows=16)
                    if stored:
                        snapshot.update(fresh_profile=True, fresh_assets=dict(profile=assets.PROFILE,
                            manifest='CONTROL_ONLY', manifest_sha256='0' * 64, enable_raw_kv=False))
                    path.write_bytes(assets.encoded(snapshot))
                    with self.subTest(entry=name, requested=requested), self.assertRaisesRegex(ValueError, 'profile mismatch'):
                        ns['verify_snapshot'](path, assets.file_sha(path), fresh_profile=requested)
                ns['runtime'].assert_not_called()

    def test_cli_freezes_fresh_arguments_and_rejects_run_overrides(self):
        for fresh in (False, True):
            for raw in (False, True):
                ns = self.namespace(composition.ENTRY)
                ns['prepare'] = Mock(return_value=(Path('CONTROL_ONLY'), {'status':'CONTROL_ONLY_PREPARE'}))
                ns['run'] = Mock(return_value=dict(status='NOT_RUN',rows=16,native_acceptance='NOT_RUN',host_wall_seconds=0))
                ns['file_sha'] = lambda path: '0' * 64
                options = ['--fresh-profile'] if fresh else []
                if raw: options += ['--enable-raw-kv']
                manifest = ['--fresh-manifest','CONTROL_ONLY','--fresh-manifest-sha256','0' * 64] if fresh else []
                argv = ['entry','--out','UNUSED','--prepare-only', *options, *manifest]
                with patch.object(sys,'argv',argv), redirect_stdout(io.StringIO()): ns['main']()
                self.assertEqual(ns['prepare'].call_args.kwargs, dict(rows=16,enable_raw_kv=raw,
                    fresh_profile=fresh,fresh_manifest=Path('CONTROL_ONLY') if fresh else None,
                    fresh_manifest_sha256='0' * 64 if fresh else None))
                ns['run'].assert_not_called()
                with patch.object(sys,'argv',['entry','--out','UNUSED',*options]), redirect_stdout(io.StringIO()):
                    with self.assertRaises(SystemExit) as stopped: ns['main']()
                self.assertEqual(stopped.exception.code,1)
                self.assertEqual(ns['run'].call_args.kwargs, dict(wall_budget=900,enable_raw_kv=raw,fresh_profile=fresh))
                ns['run'].reset_mock()
                with patch.object(sys,'argv',['entry','--out','UNUSED',*options,'--fresh-manifest','UNAPPROVED']):
                    with self.assertRaisesRegex(ValueError,'only frozen fresh manifest'): ns['main']()
                ns['run'].assert_not_called()

    def test_preparer_rejects_original_input_and_patch_drift(self):
        original_read = Path.read_bytes
        for target, reason in ((composition.ROOT / composition.OFFICIAL,'fresh base source drift'),
                               (composition.HERE / 'official_entry.patch','fresh entry patch drift')):
            def changed(path):
                raw = original_read(path)
                return raw + b'\n# controlled source drift\n' if path == target else raw
            with self.subTest(target=target.name), tempfile.TemporaryDirectory(prefix='fresh-source-drift-') as directory, \
                    patch.object(Path,'read_bytes',changed):
                with self.assertRaisesRegex(ValueError,reason):
                    composition.prepare(Path(directory) / 'source',enable_raw_kv=True)

    def test_full_preparer_rejects_enabled_callback_with_only_patch_hash_updated(self):
        original_read, original_text = Path.read_bytes, Path.read_text
        patch_path, pins_path = composition.HERE / 'official_entry.patch', composition.HERE / 'pins.json'
        raw = original_read(patch_path)
        before = b"+        admitted = fresh_assets.verify(fresh_manifest, fresh_manifest_sha256, rows=rows, enable_raw_kv=enable_raw_kv)"
        self.assertEqual(raw.count(before),1)
        changed = raw.replace(before,before + b'; unreviewed_callback()')
        pins = json.loads(original_text(pins_path))
        pins['patch_sha256']['official_entry.patch'] = assets.sha(changed)
        def read(path): return changed if path == patch_path else original_read(path)
        def text(path,*args,**kwargs): return json.dumps(pins) if path == pins_path else original_text(path,*args,**kwargs)
        with tempfile.TemporaryDirectory(prefix='fresh-enabled-mutation-') as directory, \
                patch.object(Path,'read_bytes',read),patch.object(Path,'read_text',text):
            with self.assertRaisesRegex(ValueError,'fresh generated source identity drift'):
                composition.prepare(Path(directory) / 'source',enable_raw_kv=True)

    def test_disabled_projection_rejects_comparison_gate_and_scope_changes(self):
        originals = self.baselines[True]
        generated = {name:self.sources[True][name] for name in composition.FRESH_TARGETS}
        for name, method in ((composition.OFFICIAL,'compare'),(composition.ENTRY,'run')):
            tree = ast.parse(generated[name])
            function = next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name == method)
            function.body.append(ast.Pass())
            changed = dict(generated, **{name:ast.unparse(ast.fix_missing_locations(tree))})
            with self.subTest(method=method), self.assertRaisesRegex(ValueError,'historical disabled projection'):
                composition.check_scope(originals,changed)
        with self.assertRaisesRegex(ValueError,'exact two fresh-entry targets'):
            composition.check_scope(originals,dict(generated, **{'unapproved.py':''}))

    def test_original_tolerances_masks_and_late_terminal_gate_are_preserved(self):
        for enabled in (False, True):
            original = self.baselines[enabled]
            generated = {name:self.sources[enabled][name] for name in composition.FRESH_TARGETS}
            composition.check_scope(original, generated)
            for name in composition.FRESH_TARGETS:
                before = ast.parse(original[name]); after = ast.parse(generated[name])
                projected = composition._HistoricalProjection(official=name == composition.OFFICIAL).visit(deepcopy(after))
                def function(tree, method):
                    return next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == method)
                self.assertEqual(ast.dump(function(before,'compare')), ast.dump(function(projected,'compare')))
                if name == composition.ENTRY:
                    self.assertEqual(ast.dump(function(before,'run')), ast.dump(function(projected,'run')))
                    run = function(after,'run')
                    statements = sorted((n.lineno,ast.unparse(n)) for n in ast.walk(run)
                        if isinstance(n,(ast.Assign,ast.Expr)))
                    def line(text): return next(i for i,s in statements if text in s)
                    self.assertLess(line("report['sealed_actual_outputs'] ="), line('gate.opened = True'))
                    self.assertLess(line('gate.opened = True'), line("report['comparison'] = compare("))
        # The whole-reference gate source is an untouched input, not an emitted target.
        gate = 'candidates/qwen2_resident_matrix/official_bf16/execution.py'
        self.assertNotIn(gate, self.reports[True]['generated'])
        self.assertEqual(self.reports[True]['inputs'][gate], assets.file_sha(assets.ROOT / gate))


class ArtifactPathTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='fresh-assets-cold-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def tiny(self, name, raw=b'CONTROL_ONLY'):
        path = self.root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
        return dict(path=name, bytes=len(raw), sha256=assets.sha(raw))

    def test_real_small_file_size_and_hash_checks(self):
        record = self.tiny('sequential/output')
        self.assertEqual(assets.checked_artifact(self.root, record), self.root / record['path'])
        changed = dict(record, bytes=record['bytes'] + 1)
        with self.assertRaisesRegex(ValueError, 'size drift'): assets.checked_artifact(self.root, changed)
        changed = dict(record, sha256='0' * 64)
        with self.assertRaisesRegex(ValueError, 'content drift'): assets.checked_artifact(self.root, changed)

    def test_symlink_leaf_and_escaped_parent_fail_before_open(self):
        record = self.tiny('real/output')
        (self.root / 'leaf').symlink_to(self.root / record['path'])
        (self.root / 'parent').symlink_to(self.root / 'real', target_is_directory=True)
        with tempfile.TemporaryDirectory(prefix='fresh-assets-outside-') as outside:
            (Path(outside) / 'output').write_bytes(b'CONTROL_ONLY')
            (self.root / 'escaped').symlink_to(outside, target_is_directory=True)
            with patch.object(assets, 'file_sha', side_effect=AssertionError('opened symlink')):
                for name in ('leaf', 'parent/output', 'escaped/output'):
                    with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'symlink'):
                        assets.checked_artifact(self.root, dict(record, path=name))

    def test_workspace_root_symlink_and_lexical_parent_escape_rejected(self):
        record = self.tiny('real/output')
        alias = self.root / 'workspace'; alias.symlink_to(self.root / 'real', target_is_directory=True)
        with patch.object(assets, 'file_sha', side_effect=AssertionError('invalid root opened')):
            with self.assertRaisesRegex(ValueError, 'workspace symlink'):
                assets.checked_artifact(alias, dict(record, path='output'))
            with self.assertRaisesRegex(ValueError, 'noncanonical'):
                assets.checked_artifact(self.root / 'real' / '..', record)

    def test_directory_and_fifo_fail_before_open(self):
        (self.root / 'directory').mkdir()
        os.mkfifo(self.root / 'fifo')
        with patch.object(assets, 'file_sha', side_effect=AssertionError('opened nonregular')):
            for name in ('directory', 'fifo'):
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'regular file'):
                    assets.checked_artifact(self.root, dict(path=name, bytes=0, sha256='0' * 64))

    def test_sequential_reduced_path_and_inode_alias_rejected_but_equal_hash_allowed(self):
        a = self.tiny('sequential/output'); b = self.tiny('reduced/output')
        self.assertEqual(a['sha256'], b['sha256'])
        self.assertTrue(assets.reject_aliases(self.root, {'sequential': [a], 'reduced': [b]}))
        with self.assertRaisesRegex(ValueError, 'path/inode alias'):
            assets.reject_aliases(self.root, {'sequential': [a], 'reduced': [a]})
        (self.root / b['path']).unlink(); os.link(self.root / a['path'], self.root / b['path'])
        with self.assertRaisesRegex(ValueError, 'path/inode alias'):
            assets.reject_aliases(self.root, {'sequential': [a], 'reduced': [b]})


if __name__ == '__main__':
    unittest.main()
