"""Synthetic authority/plumbing tests; no fresh capture, C build or RTL run.

Projection arithmetic, C compilation and C invocation are explicitly mocked.
The small Norm/RoPE integer computations remain real. These tests do not claim
a new native-data execution or an independent-C arithmetic acceptance.
"""
import contextlib
import dataclasses
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np

TESTS = Path(__file__).resolve().parent
sys.path[:0] = [str(TESTS.parent / 'scripts'), str(TESTS)]
import host_bf16_qk_rope_reference as ref
import test_host_bf16_qkv_reference as projection_tests


class AttentionAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.base_test = projection_tests.FreshReferenceAuthorityTests()
        self.base_test.setUp()
        self.source = self.base_test.source
        self.stack = contextlib.ExitStack()
        self.gamma = {'q_gamma': bytes(512), 'k_gamma': bytes(512)}
        self.stack.enter_context(patch.object(ref, '_parameters', return_value=self.gamma))
        norm_values = {}
        for role, word, heads in (('q', 0x40000000, 8), ('k', 0x40400000, 2)):
            trace = ref.arithmetic.norm.head_trace([word] * 256, [0] * 256)
            norm_values[role] = np.tile(np.asarray(trace['output_bf16'], dtype='<u4'), (heads, 1))
        for variant in ref.VARIANTS:
            directory = self.source.capture_dir / variant / 'native'
            path = directory / 'all_bf16_producers.npz'
            with np.load(path, allow_pickle=False) as archive:
                arrays = {name: archive[name] for name in archive.files}
            comparisons = []
            for phase, _, _ in ref.WINDOWS:
                prefix = phase + '_m128_'
                trig = np.asarray([0x3F400000] * 32 + [0x3E800000] * 32, dtype='<u4')
                arrays[prefix + 'native_cos'] = np.full((1, 128, 64), 0.75, dtype='<f4')
                arrays[prefix + 'native_sin'] = np.full((1, 128, 64), 0.25, dtype='<f4')
                for role, heads, ni, ri in (('q', 8, 16, 29), ('k', 2, 25, 32)):
                    normalized = norm_values[role]
                    arrays[prefix + f'native_producer_{ni:02d}'] = np.tile(normalized.view('<f4'), (1, 128, 1, 1))
                    rotated, cp, sp = [], [], []
                    for head in normalized:
                        output, _, _, full, _ = ref.arithmetic.rope_execution_trace(head, trig)
                        rotated.append(output[:64])
                        cp.append(np.concatenate((full[:, 8], full[:, 11])))
                        sp.append(np.concatenate((full[:, 9] ^ np.uint32(0x80000000), full[:, 10])))
                    for index, data in ((ri, rotated), (ri - 2, cp), (ri - 1, sp)):
                        words = np.asarray(data, dtype='<u4')
                        arrays[prefix + f'native_producer_{index:02d}'] = np.tile(words[:, None, :].view('<f4'), (1, 128, 1))[None, ...]
                for stage, producer in ref.STAGES.items():
                    comparisons.append(dict(case=phase + '_m128', producer=producer, storage_dtype='bfloat16',
                        max_abs_limit=0.03125, mean_abs_limit=0.005, max_abs_error=0.0, mean_abs_error=0.0, **{'pass': True}))
            np.savez(path, **arrays)
            report = dict(status='BLOCKED_BF16_PRODUCER_GATE', gate_pass=False,
                failed_producers=[{'producer': 'synthetic retained full-block failure', 'pass': False}],
                comparisons=comparisons, thresholds={'operator': {'max_abs': 0.03125, 'mean_abs': 0.005},
                                                    'block': {'max_abs': 0.05, 'mean_abs': 0.01}})
            report_path = directory / 'result.json'
            report_path.write_text(json.dumps(report))
            self.source.official['corpora'][variant]['fresh_audit_arrays'] = ref.capture._record(path)
            self.source.official['corpora'][variant]['fresh_audit_report'] = ref.capture._record(report_path)
        self.source.official.update(revision=ref.arithmetic.MODEL_REVISION, framework_revision=ref.arithmetic.FRAMEWORK_REVISION)
        manifest = self.source.capture_dir / 'provenance.json'
        manifest.write_text(json.dumps(self.source.official))
        self.source.digest = ref.file_digest(manifest)
        self.source.session = dataclasses.replace(self.source.session, manifest_sha256=self.source.digest)
        self.projection = self.base_test.generate(('baseline', 'avx2'))
        def compile_stub(directory):
            executables = {}
            for name in ('norm', 'rope'):
                path = directory / name; path.write_bytes(b'UNIT_TEST_ONLY_NEVER_EXECUTED')
                executables[name] = path
            python = ref.projection._tool_file(sys.executable)
            return executables, dict(compiler=python, python=python, compiler_version='UNIT_TEST_ONLY',
                executables={name: ref.projection._tool_file(path) for name, path in executables.items()},
                dynamic_runtime={python['path']: python}, python_version=sys.version, numpy_version=np.__version__)
        def c_stub(executables, scratch, ni, nt, ri, rt):
            self.assertEqual(len(ni), 20)
            self.assertEqual(nt.shape, (20, 3132))
            self.assertEqual(len(ri), 640)
            self.assertEqual(rt.shape, (640, 25))
            return dict(status='UNIT_TEST_ONLY_C_INVOCATION_MOCKED', norm_heads=20, rope_pairs=640,
                        norm_bit_or_flag_mismatches=0, rope_bit_or_flag_mismatches=0)
        self.compiler = self.stack.enter_context(patch.object(ref, '_compile_references', side_effect=compile_stub))
        self.c_reference = self.stack.enter_context(patch.object(ref.arithmetic, 'crosscheck_c', side_effect=c_stub))

    def tearDown(self):
        self.stack.close()
        self.base_test.tearDown()

    def generate(self, variants=('baseline',)):
        return ref.generate_attention_references(self.source.session, self.projection,
            self.source.base / 'attention', variants=variants)

    def verify(self, session):
        return session.verify(session=self.source.session, reference_session=self.projection)

    def select(self, session, **overrides):
        activation, weights = self.base_test.inputs()
        kwargs = dict(session=self.source.session, projection_reference_session=self.projection,
                      variant='baseline', phase='cold', token_base=0, token_count=1)
        return session.select(activation.tobytes(), {key: value.tobytes() for key, value in weights.items()}, **(kwargs | overrides))

    def test_live_binding_all_payloads_thresholds_and_no_recomputation_on_select(self):
        session = self.generate(('baseline', 'avx2'))
        receipt = self.verify(session)
        self.assertEqual(len(receipt['windows']), 4)
        self.assertTrue(receipt['original_operator_gate_pass'])
        self.assertEqual(receipt['native_full_block_gate_pass'], {'baseline': False, 'avx2': False})
        self.assertEqual(receipt['additional_matrix_evaluations'], 0)
        self.assertEqual(receipt['fresh_official_executions_in_this_factory'], 0)
        for key, row in receipt['windows'].items():
            self.assertEqual(row['positionBase'], 0 if key.endswith('cold0') else 255)
            self.assertTrue(row['original_operator_gate_pass'])
            self.assertEqual(row['original_operator_checks']['norm_q']['original_thresholds'], {'max_abs': 0.03125, 'mean_abs': 0.005})
            self.assertEqual(row['original_operator_checks']['rope_q']['native_product_bit_mismatches'], 0)
        payload, proof = self.select(session)
        self.assertEqual(set(payload), set(ref.TERMINALS + ref.PARAMETERS + ref.NATIVE_TERMINALS))
        self.assertEqual({key: len(payload[key]) for key in ref.TERMINALS},
                         dict(norm_q=4096, norm_k=1024, gate=4096, rope_q=4096, rope_k=1024))
        self.assertEqual(len(payload['trig']), 128)
        self.assertTrue(proof['expected_only'])
        self.assertFalse(proof['intermediate_preload_allowed'])
        self.assertEqual(self.c_reference.call_count, 4)
        self.compiler.assert_called_once()
        self.assertEqual(self.base_test.arithmetic.call_count, 48)

    def test_opaque_authority_saved_receipt_clone_and_other_projection_rejected(self):
        session = self.generate()
        with self.assertRaises(TypeError): ref.FreshAttentionReferenceSession(session.directory, session.receipt_sha256)
        forged = object.__new__(ref.FreshAttentionReferenceSession)
        with self.assertRaisesRegex(ValueError, 'unissued'): self.verify(forged)
        with self.assertRaisesRegex(ValueError, 'different live'):
            session.verify(session=dataclasses.replace(self.source.session), reference_session=self.projection)
        with self.assertRaisesRegex(ValueError, 'conflicting projection'):
            session.verify(session=self.source.session, reference_session=object(), projection_reference_session=self.projection)
        with self.assertRaisesRegex(ValueError, 'different live'):
            session.verify(session=self.source.session, reference_session=object.__new__(ref.projection.FreshProjectionReferenceSession))

    def test_modified_expected_receipt_trace_and_unexpected_files_rejected(self):
        session = self.generate()
        receipt = self.verify(session)
        relative = receipt['windows']['baseline/cold0']['terminals']['norm_q']
        path = session.directory / relative; original = path.read_bytes()
        path.write_bytes(bytes([original[0] ^ 1]) + original[1:])
        with self.assertRaisesRegex(ValueError, 'bytes changed'): self.verify(session)
        altered = json.loads((session.directory / 'receipt.json').read_text())
        altered['files'][relative] = ref.projection._file_record(path)
        (session.directory / 'receipt.json').write_text(json.dumps(altered))
        with self.assertRaisesRegex(ValueError, 'live authority'): self.verify(session)

    def test_actual_input_variant_window_dtype_and_output_path_are_bounded(self):
        session = self.generate()
        for change in ({'variant': 'avx2'}, {'token_count': 128}, {'token_base': True}, {'phase': 'carried', 'token_base': 0}):
            with self.subTest(change=change), self.assertRaises(ValueError): self.select(session, **change)
        a, weights = self.base_test.inputs()
        a[127, 0] ^= 1
        with self.assertRaisesRegex(ValueError, 'actual A/W differs'):
            session.select(a, weights, session=self.source.session, reference_session=self.projection,
                           variant='baseline', phase='cold', token_base=0, token_count=1)
        with self.assertRaisesRegex(ValueError, 'activation backing byte'):
            session.select(b'bad', weights, session=self.source.session, reference_session=self.projection,
                           variant='baseline', phase='cold', token_base=0, token_count=1)
        with self.assertRaisesRegex(ValueError, 'fresh output'): self.generate()

    def test_source_tool_gamma_and_projection_mutation_are_detected(self):
        session = self.generate()
        with patch.object(ref, '_source_identity', return_value={}):
            with self.assertRaisesRegex(ValueError, 'source changed'): self.verify(session)
        with patch.object(ref, '_parameters', return_value=self.gamma | {'q_gamma': bytes(510) + b'xx'}):
            with self.assertRaisesRegex(ValueError, 'gamma/trig changed'): self.verify(session)
        tool = session.directory / 'norm'; original = tool.read_bytes(); tool.write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, 'runtime drift'): self.verify(session)
        tool.write_bytes(original)
        projection_receipt = self.projection.verify(session=self.source.session)
        target = self.projection.directory / projection_receipt['windows']['baseline/cold0']['terminals']['q']['bf16']
        target.write_bytes(b'x' * target.stat().st_size)
        with self.assertRaisesRegex(ValueError, 'terminal bytes changed'): self.verify(session)

    def test_original_operator_failure_is_retained_not_replaced_by_composed_pass(self):
        original = ref._load_window
        def corrupted_native_product(*args):
            activation, native_projection, trig, native = original(*args)
            native['rope_q_cos_product'][0, 0] ^= np.uint32(0x10000)
            return activation, native_projection, trig, native
        with patch.object(ref, '_load_window', side_effect=corrupted_native_product):
            session = self.generate()
            receipt = self.verify(session)
        self.assertFalse(receipt['original_operator_gate_pass'])
        self.assertTrue(receipt['native_operator_gate_pass'])
        self.assertFalse(receipt['native_full_block_gate_pass']['baseline'])
        for window in receipt['windows'].values():
            self.assertEqual(window['original_operator_checks']['rope_q']['native_product_bit_mismatches'], 1)

    def test_c_failure_never_issues_authority_or_receipt(self):
        with patch.object(ref.arithmetic, 'crosscheck_c', side_effect=ValueError('independent C node mismatch')):
            with self.assertRaisesRegex(ValueError, 'independent C node mismatch'): self.generate()
        self.assertFalse((self.source.base / 'attention/receipt.json').exists())

    def test_fresh_seven_command_packer_selects_live_authority_without_regeneration(self):
        import host_bf16_qkv_rope_fixture as chain
        session = self.generate()
        output = self.source.base / 'seven_command_fixture'
        authorities = dict(session=self.source.session, reference_session=self.projection,
                           attention_reference_session=session)
        receipt = chain.pack(output, 'carried127', variant='baseline', **authorities)
        checked = chain.verify(output, **authorities)
        self.assertEqual(receipt['source_mode'], 'fresh_ref')
        self.assertFalse(checked['actual_chain_executed'])
        self.assertTrue(receipt['independent_reference']['original_operator_gate_pass'])
        self.assertFalse(receipt['native_full_block_failures']['baseline']['gate_pass'])
        self.assertIn('report_sha256', receipt['native_full_block_failures']['baseline'])
        self.assertEqual((output / 'independent_norm_q.bf16le').stat().st_size, 4096)
        self.assertEqual((output / 'native_rope_q_prefix.bf16le').stat().st_size, 1024)
        self.assertEqual(self.c_reference.call_count, 2)
        self.compiler.assert_called_once()
        self.assertEqual(self.base_test.arithmetic.call_count, 48)


if __name__ == '__main__':
    unittest.main()
