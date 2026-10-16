"""Cold M128 asset-contract tests; CONTROL_ONLY receipts prove no numerics.

Apply the reviewed patch to a temporary source tree. Only tiny JSON receipts and
filesystem alias fixtures are materialized; no tensor payload, native library,
producer, or numerical verifier is imported or executed.
"""
import ast
import builtins
from copy import deepcopy
import importlib.util
import math
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from ..raw_kv_public_fresh import assets as original

HERE = Path(__file__).resolve().parent
RELATIVE = 'candidates/qwen2_resident_matrix/raw_kv_public_fresh/assets.py'
SEMANTICS = ('mask_exact', 'native_fp32_probability_sum_within_2e_5',
    'independent_fp32_probability_sum_within_2e_5', 'native_cache_append_k_exact',
    'native_cache_append_v_exact', 'independent_cache_append_k_exact',
    'independent_cache_append_v_exact', 'native_future_probability_zero',
    'independent_future_probability_zero')


def record(path, size=1, digest='0' * 64):
    return dict(path='CONTROL_ONLY/' + path, bytes=size, sha256=digest)


def manifest_fixture(a):
    """Pure schema fixture. Listed payloads do not exist and are not verified."""
    sources = {'CONTROL_ONLY/source.py': '0' * 64}
    m = dict(schema=1, status=a.STATUS, profile=a.PROFILE, rows=128, past_tokens=0,
        source_sha256=sources, source_manifest_sha256=a.sha(a.encoded(sources)),
        payload=dict(manifest=record('payload.json'), tensors={name: record(name, p['bytes'], p['sha256'])
            for name, p in a.TENSOR_PINS.items()}),
        readonly=dict(arena=record('arena', a.ARENA_BYTES, a.ARENA_SHA256),
            table=record('table', 328448, a.TABLE_SHA256),
            input_x=record('input_x', 128 * 1536 * 4, a.INPUT_X_SHA256),
            input_x_sha256=a.INPUT_X_SHA256, intermediate_preloads=0),
        library=dict(receipt=record('receipt.json'), binary=record('library.so')))
    for role in ('sequential', 'reduced'):
        m[role] = dict(producer=a.PRODUCERS[role],
            cpp=record(role + '/candidate.cpp', digest=a.CPP_SHA256[role]),
            header=record(role + '/layout.h', digest=a.HEADER_SHA256),
            executable=record(role + '/candidate'), compile=record(role + '/compile.json'),
            run=record(role + '/run.json'), outputs={name: record(role + '/' + name, size)
                for name, size in a.output_inventory().items()})
    m['sequential'].update(export_receipt=record('sequential/export.json'), tensors={
        name: record('sequential/' + name, 4 * math.prod(shape)) for name, shape in a.shapes().items()})
    for role, rows in (('native_m16', 16), ('native', 128)):
        m[role] = dict(producer=a.NATIVE_PRODUCER, result=record(role + '/RESULT.json'), outputs={
            mode: {method: {name: record(role + '/' + mode + '/phase_0/' + prefix + '_' + name + '.f32le',
                4 * math.prod(shape), (a.M16_X_SHA256 if rows == 16 else a.INPUT_X_SHA256)
                if name == 'x' else '0' * 64) for name, shape in a.shapes(rows).items()}
                for method, prefix in zip(a.METHODS, ('native', 'independent'))} for mode in a.MODES})
    return m


class Assets128Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='assets128-cold-')
        cls.addClassCleanup(cls.temp.cleanup)
        target = Path(cls.temp.name) / RELATIVE
        target.parent.mkdir(parents=True)
        target.write_bytes(Path(original.__file__).read_bytes())
        result = subprocess.run(['patch', '--batch', '--fuzz=0', '-p1'], cwd=cls.temp.name,
            input=(HERE / 'assets128.patch').read_bytes(), capture_output=True, timeout=10)
        if result.returncode:
            raise RuntimeError('source-only assets128 patch failed: ' + result.stderr.decode())
        spec = importlib.util.spec_from_file_location(
            'candidates.qwen2_resident_matrix.raw_kv_public_fresh._assets128_control', target)
        cls.a = importlib.util.module_from_spec(spec)
        imported = builtins.__import__
        def stdlib_only(name, *args, **kwargs):
            if name.split('.')[0] in ('torch', 'numpy', 'transformers', 'ctypes'):
                raise AssertionError('numerical/native import forbidden: ' + name)
            return imported(name, *args, **kwargs)
        with patch('builtins.__import__', side_effect=stdlib_only):
            spec.loader.exec_module(cls.a)
        cls.tree = ast.parse(target.read_text())
        cls.old_tree = ast.parse(Path(original.__file__).read_text())

    def test_exact_geometry_and_export_inventories(self):
        a = self.a; m = manifest_fixture(a)
        self.assertEqual((a.ROWS, a.PROFILE, a.STATUS),
            (128, 'qwen2-public-pv16-fresh-assets-m128-v1', 'READY_FOR_ACTUAL_M128'))
        self.assertEqual(set(a.shapes()), set(original.shapes()))
        self.assertEqual(len(a.shapes()), 29)
        self.assertEqual(a.shapes()['scores'], [1, 12, 128, 128])
        self.assertEqual(a.shapes()['mask'], [1, 1, 128, 128])
        self.assertEqual(a.shapes()['cache_k'], [1, 2, 128, 128])
        self.assertEqual(a.export_shapes()['q'], [1, 128, 1536])
        self.assertEqual(a.export_shapes()['k'], [1, 128, 256])
        self.assertEqual(a.shapes(16), original.shapes())
        self.assertEqual(a.export_shapes(16), original.export_shapes())
        self.assertEqual(len(a.output_inventory()), 22)
        self.assertEqual(set(a.output_inventory()), set(original.output_inventory()))
        for name, size in original.output_inventory().items():
            factor = 64 if name in ('scores.f32le', 'logits.f32le', 'softmax_fp32.f32le', 'prob.f32le') else 8
            self.assertEqual(a.output_inventory()[name], factor * size)
        self.assertEqual((len(m['payload']['tensors']), len(m['sequential']['tensors'])), (13, 29))
        self.assertEqual(sum(len(nodes) for role in ('native_m16', 'native')
            for methods in m[role]['outputs'].values() for nodes in methods.values()), 232)
        self.assertEqual(m['readonly']['input_x']['bytes'], 786432)

    def test_canonical_m128_before_import_or_artifact_access(self):
        a = self.a
        with patch('builtins.__import__', side_effect=AssertionError('unexpected import')), \
                patch.object(Path, 'open', side_effect=AssertionError('unexpected artifact access')):
            m = manifest_fixture(a)
            self.assertIs(a.validate_manifest(m), m)
            self.assertTrue(a.fresh_mode(True, 'CONTROL_ONLY/manifest', '0' * 64, rows=128))
            for bad in (16, True, False, 128.0, '128', 0, None):
                with self.subTest(rows=bad), self.assertRaises(ValueError):
                    a.validate_manifest(m, rows=bad)
                with self.subTest(read_rows=bad), self.assertRaises(ValueError):
                    a.read_manifest('unopened', '0' * 64, rows=bad)
            for bad in (16, True, 128.0):
                with self.subTest(fresh_rows=bad), self.assertRaises(ValueError):
                    a.fresh_mode(True, 'unopened', '0' * 64, rows=bad)
                value = deepcopy(m); value['rows'] = bad
                with self.assertRaises(ValueError): a.validate_manifest(value)
            with self.assertRaises(ValueError):
                a.read_native_reference({}, b'', rows=16, method=a.METHODS[0], name='x', shape=[1,16,1536])
            with self.assertRaises(ValueError): original.validate_manifest(m)
        for bad in (True, 16.0, 128.0, '16', 1):
            with self.subTest(geometry=bad), self.assertRaises(ValueError): a.shapes(bad)

    def test_native_prerequisite_exact_inventory_sizes_and_input_pins(self):
        a = self.a
        for role in ('native_m16', 'native'):
            for mode in a.MODES:
                for method in a.METHODS:
                    for mutation in ('missing', 'extra', 'bytes', 'x_hash'):
                        m = manifest_fixture(a); nodes = m[role]['outputs'][mode][method]
                        if mutation == 'missing': del nodes['mask']
                        elif mutation == 'extra': nodes['unapproved'] = nodes['mask']
                        elif mutation == 'bytes': nodes['q']['bytes'] += 1
                        else: nodes['x']['sha256'] = '0' * 64
                        with self.subTest(role=role, mode=mode, method=method, mutation=mutation), self.assertRaises(ValueError):
                            a.validate_manifest(m)
        m = manifest_fixture(a); del m['native_m16']
        with self.assertRaises(ValueError): a.validate_manifest(m)
        m = manifest_fixture(a); m['native_m16'] = deepcopy(m['native'])
        with self.assertRaises(ValueError): a.validate_manifest(m)

    def native_fixture(self, workspace):
        """CONTROL_ONLY runtime metadata; verdicts do not evaluate tensors."""
        a = self.a; m = manifest_fixture(a)
        identity = dict(CONTROL_ONLY=True, threads=4)
        policy = dict(CONTROL_ONLY=True)
        native = Mock()
        native.runtime_identity.return_value = (None, identity)
        native.load_policy.return_value = policy
        native.stage_verdict.return_value = dict(passed=True)
        results = {}
        for role, rows in (('native_m16', 16), ('native', 128)):
            result = dict(schema_version=1, status='PASS_BF16_STAGE_BUDGET', model_id=a.MODEL,
                layer=0, tokens=rows, carried=False, m16_gate_sha256=None, torch_threads=4,
                payload_manifest_sha256=m['payload']['manifest']['sha256'], official_framework_forward=True,
                rtl_execution=False, hardware_recipe_acceptance=False, logits=False, full_model_quality=False,
                manifest_whole_checkpoint_hash_verified=False, identity=deepcopy(identity), policy=deepcopy(policy),
                blas_environment={key: os.environ.get(key) for key in
                    ('OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'OMP_NUM_THREADS')}, modes={}, seconds=0.1)
            for mode in a.MODES:
                stages = {}
                for name, shape in a.shapes(rows).items():
                    item = dict(shape=shape, elements=math.prod(shape), finite=True, bit_exact=True, passed=True)
                    for method, prefix in zip(a.METHODS, ('native', 'independent')):
                        item.update({prefix + '_file': mode + '/phase_0/' + prefix + '_' + name + '.f32le',
                            prefix + '_export_shape': a.export_shapes(rows)[name],
                            prefix + '_file_sha256': m[role]['outputs'][mode][method][name]['sha256']})
                    stages[name] = item
                phase = dict(phase=0, past_tokens=0, token_ids=list(range(rows)), position_ids=list(range(rows)),
                    semantics=dict.fromkeys(SEMANTICS, True), all_semantics_exact=True, stages=stages,
                    failed_stages=[], status='PASS_BF16_STAGE_BUDGET' if mode == 'bf16' else 'DIAGNOSTIC_FP32', seconds=0.1)
                result['modes'][mode] = dict(phases=[phase], seconds=0.1)
            results[role] = result
        self.save_receipts(workspace, m, results)
        real_resolver = a.resolve_artifact
        def CONTROL_ONLY_export_path(workspace, item):
            if item['path'].endswith('/RESULT.json'):
                return real_resolver(workspace, item)
            return workspace / item['path']
        return m, results, native, CONTROL_ONLY_export_path

    def save_receipts(self, workspace, m, results):
        for role in ('native_m16', 'native'):
            if role == 'native': results[role]['m16_gate_sha256'] = m['native_m16']['result']['sha256']
            raw = self.a.encoded(results[role]); path = workspace / m[role]['result']['path']
            path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
            m[role]['result'].update(bytes=len(raw), sha256=self.a.sha(raw))

    def test_real_tiny_receipt_hashes_bind_both_metadata_roles(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp); m, results, native, resolver = self.native_fixture(workspace)
            with patch.object(self.a, 'resolve_artifact', side_effect=resolver):
                self.assertEqual(self.a._verify_native(workspace, m, native), results['native'])
            self.assertEqual(native.stage_verdict.call_count, 116)
            self.assertEqual(native.runtime_identity.call_count, 2)
            self.assertEqual(len(list(workspace.rglob('*.*'))), 2)
            path = workspace / m['native_m16']['result']['path']
            raw = path.read_bytes(); path.write_bytes(raw.replace(b'CONTROL_ONLY', b'CONTROL_ONLX'))
            with patch.object(self.a, 'resolve_artifact', side_effect=resolver), \
                    self.assertRaisesRegex(ValueError, 'metadata content drift'):
                self.a._verify_native(workspace, m, native)

    def test_metadata_role_payload_runtime_and_verdict_negatives(self):
        for role in ('native_m16', 'native'):
            for mutation in ('rows', 'status', 'payload', 'identity', 'policy', 'blas',
                             'semantics', 'passed', 'bit_exact', 'export_hash'):
                with self.subTest(role=role, mutation=mutation), tempfile.TemporaryDirectory() as temp:
                    workspace = Path(temp); m, results, native, resolver = self.native_fixture(workspace)
                    result = results[role]; phase = result['modes']['bf16']['phases'][0]
                    if mutation == 'rows': result['tokens'] = 128 if role == 'native_m16' else 16
                    elif mutation == 'status': result['status'] = 'FAIL_BF16_STAGE_BUDGET'
                    elif mutation == 'payload': result['payload_manifest_sha256'] = '1' * 64
                    elif mutation == 'identity': result['identity']['threads'] = True
                    elif mutation == 'policy': result['policy']['CONTROL_ONLY'] = 1
                    elif mutation == 'blas': result['blas_environment']['OMP_NUM_THREADS'] = 'CONTROL_ONLY_DRIFT'
                    elif mutation == 'semantics': phase['semantics']['mask_exact'] = 1
                    elif mutation == 'passed': phase['stages']['mask']['passed'] = 1
                    elif mutation == 'bit_exact': phase['stages']['mask']['bit_exact'] = 1
                    else: phase['stages']['x']['native_file_sha256'] = '1' * 64
                    self.save_receipts(workspace, m, results)
                    with patch.object(self.a, 'resolve_artifact', side_effect=resolver), self.assertRaises(ValueError):
                        self.a._verify_native(workspace, m, native)

    def test_m16_gate_digest_and_canonical_roles_are_required(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp); m, results, native, resolver = self.native_fixture(workspace)
            for role, rows, gate in (('native_m16',128,None), ('native',16,'0'*64),
                                    ('native',128,None), ('native_m16',16,'0'*64), ('native',128.0,'0'*64)):
                with self.subTest(role=role, rows=rows), self.assertRaisesRegex(ValueError, 'prerequisite role'):
                    self.a._verify_native_record(workspace, m, native, role=role, rows=rows, small_gate_sha256=gate)
            results['native']['m16_gate_sha256'] = '1' * 64
            raw = self.a.encoded(results['native']); path = workspace / m['native']['result']['path']; path.write_bytes(raw)
            m['native']['result'].update(bytes=len(raw), sha256=self.a.sha(raw))
            with patch.object(self.a, 'resolve_artifact', side_effect=resolver), self.assertRaises(ValueError):
                self.a._verify_native(workspace, m, native)

    def test_prerequisite_hashing_alias_and_late_reference_coverage(self):
        functions = {n.name: n for n in self.tree.body if isinstance(n, ast.FunctionDef)}
        verify = ast.unparse(functions['verify'])
        self.assertIn('for item in records(manifest):\n        checked_artifact(workspace, item)', verify)
        self.assertIn("('payload', 'readonly', 'sequential', 'reduced', 'native_m16', 'native', 'library')", verify)
        self.assertIn("records(manifest['native_m16']['outputs'])", ast.unparse(functions['_views']))
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp); first = workspace / 'CONTROL_ONLY/a'; first.parent.mkdir()
            first.write_bytes(b'x'); second = first.with_name('b'); second.write_bytes(b'x')
            groups = {'native_m16': [record('a')], 'native': [record('b')]}
            self.assertTrue(self.a.reject_aliases(workspace, groups))
            groups['native'] = [record('a')]
            with self.assertRaises(ValueError): self.a.reject_aliases(workspace, groups)
            groups['native'] = [record('b')]; second.unlink(); os.link(first, second)
            with self.assertRaises(ValueError): self.a.reject_aliases(workspace, groups)

    def test_payload_tolerances_verdict_call_and_decoder_are_unchanged(self):
        a = self.a
        for name in ('MODEL', 'REVISION', 'TENSOR_PINS', 'CPP_SHA256', 'HEADER_SHA256', 'TABLE_SHA256', 'STAGES'):
            self.assertEqual(getattr(a, name), getattr(original, name))
        self.assertEqual(sum(p['bytes'] for p in a.TENSOR_PINS.values()), 94382080)
        funcs = lambda tree: {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
        old, new = funcs(self.old_tree), funcs(self.tree)
        for name in ('same', '_verify_payload', '_verify_exports', '_finite_seconds', 'read_reference_bytes'):
            self.assertEqual(ast.dump(new[name]), ast.dump(old[name]), name)
        self.assertEqual([ast.dump(n) for n in new['read_native_reference'].body[2:]],
                         [ast.dump(n) for n in old['read_native_reference'].body[2:]])
        verdicts = lambda node: [ast.dump(n) for n in ast.walk(node) if isinstance(n, ast.Call)
                                and isinstance(n.func, ast.Attribute) and n.func.attr == 'stage_verdict']
        self.assertEqual(verdicts(new['_verify_native_record']), verdicts(old['_verify_native']))


if __name__ == '__main__':
    unittest.main()
