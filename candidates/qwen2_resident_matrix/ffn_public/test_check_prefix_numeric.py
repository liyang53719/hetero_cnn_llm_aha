"""Bounded runner guards; no actual payload capture, C++ compile or RTL."""
import math
from copy import deepcopy
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from candidates.qwen2_resident_matrix.ffn_public import check_prefix_numeric as c


class PrefixCaptureGuards(unittest.TestCase):
    def test_strict_flags_reject_math_overrides_and_unrecorded_options(self):
        base = ['g++', '-std=c++17', '-O2', '-ffp-contract=off', '-fno-fast-math',
                '-frounding-math', '-fPIC', '-shared', 'input.cpp', '-o', 'output.so']
        c.strict_flags(base, shared=True)
        for extra in ('-ffast-math', '-Ofast', '-ffp-contract=fast', '-march=native', '-I/tmp'):
            with self.subTest(extra=extra), self.assertRaisesRegex(ValueError, 'compile flags'):
                c.strict_flags(base + [extra], shared=True)

    def test_transpose_preserves_source_bf16_without_roundtrip(self):
        raw = struct.pack('<6H', 1, 2, 3, 4, 5, 6)
        self.assertEqual(c.transpose_bf16(raw, [2, 3]), struct.pack('<6H', 1, 4, 2, 5, 3, 6))
        self.assertEqual(c.fp32_from_bf16(struct.pack('<3H', 1, 0x8000, 0x3f80)),
                         struct.pack('<3I', 0x10000, 0x80000000, 0x3f800000))
        with self.assertRaisesRegex(ValueError, 'nonfinite'):
            c.fp32_from_bf16(struct.pack('<H', 0x7f80))

    def test_trig_original_double_recipe_public_sine_half_stride(self):
        raw = c.rope_bytes(16)
        self.assertEqual(len(raw), 2 * 1024 * 64 * 4)
        for t, j in ((0, 0), (1, 0), (7, 17), (15, 63)):
            angle = t / math.pow(1000000.0, 2.0 * j / 128)
            i = (t * 64 + j) * 4
            self.assertEqual(raw[i:i + 4], struct.pack('<f', math.cos(angle)))
            i += 1024 * 64 * 4
            self.assertEqual(raw[i:i + 4], struct.pack('<f', math.sin(angle)))
        self.assertEqual(raw[128 * 64 * 4:129 * 64 * 4], bytes(64 * 4))
        self.assertEqual(raw[16 * 64 * 4:17 * 64 * 4], bytes(64 * 4))
        with self.assertRaisesRegex(ValueError, 'trig layout'):
            c.rope_bytes(16, max_tokens=128)

    def test_readonly_provider_rejects_unaligned_or_out_of_span_access(self):
        raw = bytes(range(128))
        provider = c.bytes_provider(raw)
        self.assertEqual(provider(0), raw[:64])
        self.assertEqual(provider(64), raw[64:])
        for offset in (-64, 1, 128, '0'):
            with self.subTest(offset=offset), self.assertRaisesRegex(ValueError, 'provider bounds'):
                provider(offset)

    def test_reference_gate_rejects_saved_opens_and_oracle_calls_until_checkpoint(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'expected.f32le'
            path.write_bytes(b'gold')
            spec = {'comparison_only': {'n0': {'path': str(path)}}}
            with c.reference_gate(spec) as gate:
                library = gate.library(SimpleNamespace(td_step='actual', td_reference='reference'))
                self.assertEqual(library.td_step, 'actual')
                with self.assertRaisesRegex(ValueError, 'before prefix checkpoint'):
                    path.read_bytes()
                with self.assertRaisesRegex(ValueError, 'before prefix checkpoint'):
                    library.td_reference
                with self.assertRaisesRegex(ValueError, 'before prefix checkpoint'):
                    gate.audit('subprocess.Popen', ('prefix_recipe', ['/tmp/prefix_recipe']))
                gate.opened = True
                self.assertEqual(path.read_bytes(), b'gold')
                self.assertEqual(library.td_reference, 'reference')
            self.assertFalse(gate.active)

    def test_frozen_exec_checks_all_repository_code_paths(self):
        # compile()/exec() here exercises only a trivial synthetic code object.
        path = ROOT / 'candidates/qwen2_resident_matrix/ffn_public/check_prefix_numeric.py'
        code = compile('checked = 1', str(path), 'exec')
        with c.frozen_exec({str(path.relative_to(ROOT)): c.file_sha(path)}) as observed:
            namespace = {}
            exec(code, namespace)
        self.assertEqual(namespace['checked'], 1)
        self.assertIn(str(path.relative_to(ROOT)), observed)
        with c.frozen_exec({}), self.assertRaisesRegex(ValueError, 'unfrozen'):
            exec(code, {})

    def test_metadata_source_closure_and_oracle_generation_only(self):
        modules = c.runtime()
        self.assertIn('scripts/qwen2_block_recipe_model.py', c._import_hashes)
        self.assertIn('src/heteronpu/l9_transport_contract.py', c._import_hashes)
        files, identity = c.oracle_sources(modules[-1])
        text = files['prefix_recipe.cpp'].decode()
        self.assertNotIn('void attention()', text)
        self.assertNotIn('computeReference()', text)
        self.assertIn('model.dense(OFF_N0,weight,out,H,width);dump(raw,out,width);', text)
        self.assertIn('"qraw","qr"', text)
        self.assertIn('"kraw","kr"', text)
        self.assertIn('"vraw","v"', text)
        self.assertFalse(identity['modified_method_bodies'])

    def cached_fixture(self, root):
        """Synthetic bytes and receipts only, independent of ignored work/."""
        def write(path, raw):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            return c.sha(raw)
        hashes = {}
        for name in c.NUMERIC_SOURCES:
            raw = ('synthetic source ' + name).encode()
            hashes[name] = write(root / name, raw)
            write(root / c.CACHE / 'frozen_sources' / name, raw)
        library = root / c.CACHE / 'numeric_recipe.so'
        binary_sha = write(library, b'synthetic shared library; never loaded')
        argv = ['g++', '-std=c++17', '-O2', '-ffp-contract=off', '-fno-fast-math',
                '-frounding-math', '-fPIC', '-shared']
        argv += [str(root / c.CACHE / 'frozen_sources' / name) for name in c.NUMERIC_SOURCES[:2]]
        argv += ['-o', str(library)]
        cached = dict(source_sha256=hashes, compile=dict(argv=argv, binary_sha256=binary_sha,
                                                       compiler='synthetic compiler identity'))
        write(root / c.CACHE / 'summary.json', c.encoded(cached))
        generated = root / c.RECIPE / 'generated'
        cpp_sha = write(generated / 'software_recipe.cpp', b'synthetic generated oracle source')
        header_sha = write(generated / 'block_layout.h', b'synthetic oracle header')
        original_sha = write(root / 'original.cpp', b'synthetic original source')
        provenance = dict(source_sha256={'original.cpp': original_sha},
            generated_cpp_sha256=cpp_sha, generated_header_sha256=header_sha,
            compile_command=['g++', '-O2', '-std=c++17', '-ffp-contract=off', '-fno-fast-math',
                             str(generated / 'software_recipe.cpp'), '-o', str(generated / 'software_recipe')])
        write(generated / 'provenance.json', c.encoded(provenance))
        return {'source_identity': provenance}, cached

    def test_cached_library_verification_with_synthetic_receipts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            recipe, _ = self.cached_fixture(root)
            with patch.object(c, 'ROOT', root):
                receipt = c.verified_binaries(recipe)
            self.assertFalse(receipt['compilation_executed'])
            self.assertFalse(receipt['old_numeric_pass_inherited'])
            self.assertEqual(len(receipt['numeric_source_sha256']), 3)

    def test_cached_library_rejects_source_binary_flags_and_extra_translation_units(self):
        for mutation in ('source', 'frozen_source', 'binary', 'flag', 'extra_cpp', 'extra_object', 'oracle'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                recipe, receipt = self.cached_fixture(root)
                paths = {
                    'source': root / c.NUMERIC_SOURCES[0],
                    'frozen_source': root / c.CACHE / 'frozen_sources' / c.NUMERIC_SOURCES[0],
                    'binary': root / c.CACHE / 'numeric_recipe.so',
                    'oracle': root / c.RECIPE / 'generated/software_recipe.cpp',
                }
                if mutation in paths:
                    paths[mutation].write_bytes(b'changed')
                else:
                    extra = {'flag': '-ffast-math', 'extra_cpp': 'unrecorded.cpp', 'extra_object': 'unrecorded.o'}[mutation]
                    receipt['compile']['argv'].insert(-2, extra)
                    (root / c.CACHE / 'summary.json').write_bytes(c.encoded(receipt))
                with patch.object(c, 'ROOT', root), self.assertRaises(ValueError):
                    c.verified_binaries(recipe)

    def test_comparison_requires_checkpoint_before_any_file_access(self):
        with self.assertRaisesRegex(ValueError, 'validated prefix checkpoint'):
            c.compare_after_checkpoint({}, None, {}, None, 0, SimpleNamespace(opened=False))

    def test_m128_requires_successful_source_matched_m16(self):
        with self.assertRaisesRegex(ValueError, 'completed M16'):
            c.verify_m16(None, None, {})

    def prerequisite_fixture(self):
        snapshot = dict(source_sha256={'source': 'digest'}, input_spec={'frozen': 'input'}, binaries={'frozen': 'library'})
        outputs = {}
        for name in c.OUTPUTS:
            width = 512 if name == 'kv' else 1536 if name in ('n0', 'qraw', 'qr', 'q') else 256
            digest = c.sha(name.encode())
            outputs[name] = dict(values=16 * width, actual_sha256=digest, independent_sha256=digest,
                                 independent_bit_mismatches=0, saved_bit_mismatches=None)
            if name in (*c.STAGES, 'kv'):
                outputs[name].update(saved_sha256=digest, saved_bit_mismatches=0)
        prior = dict(snapshot, status='PASS_PUBLIC21_PREFIX_SOFTWARE_ONLY_NOT_NATIVE_ACCEPTED', rows=16,
            source_sha256_after=snapshot['source_sha256'], native_acceptance='NOT_NATIVE_ACCEPTED',
            comparison=dict(outputs=outputs, actual_public_pcs_executed=list(range(10))),
            comparison_gate=dict(public_completion_pcs=list(range(10)),
                all_actual_final_acks_before_comparison=True, pc10_not_executed=True,
                launch_terminal_observed=False, same_owner_and_banks=True),
            execution=dict(host=dict(completions=[dict(pc=i, status=None) for i in range(10)],
                launch_result=None, reset_required=False, same_owner_and_banks=True,
                accepted=dict(completion_fire=10, owner_result_fire=10, result_fire=0))))
        return snapshot, prior

    def check_prerequisite(self, snapshot, prior):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'summary.json'
            path.write_bytes(c.encoded(prior))
            return c.verify_m16(path, c.file_sha(path), snapshot)

    def test_m16_prerequisite_accepts_complete_synthetic_evidence(self):
        snapshot, prior = self.prerequisite_fixture()
        self.assertEqual(len(self.check_prerequisite(snapshot, prior)['sha256']), 64)

    def test_m16_prerequisite_rejects_empty_missing_extra_outputs_and_bad_metrics(self):
        snapshot, original = self.prerequisite_fixture()
        for mutation in ('empty', 'missing', 'extra', 'values', 'negative_values', 'negative_mismatches',
                         'mismatch', 'hash', 'saved_hash', 'saved_missing', 'raw_saved', 'invalid_hash'):
            with self.subTest(mutation=mutation):
                prior = deepcopy(original)
                outputs = prior['comparison']['outputs']
                if mutation == 'empty':
                    outputs.clear()
                elif mutation == 'missing':
                    del outputs['qraw']
                elif mutation == 'extra':
                    outputs['att'] = outputs['q']
                elif mutation == 'raw_saved':
                    outputs['qraw']['saved_bit_mismatches'] = 0
                else:
                    field, value = {
                        'values': ('values', 17 * 1536), 'negative_values': ('values', -1),
                        'negative_mismatches': ('independent_bit_mismatches', -1),
                        'mismatch': ('independent_bit_mismatches', 1),
                        'hash': ('independent_sha256', '0' * 64),
                        'saved_hash': ('saved_sha256', '0' * 64),
                        'saved_missing': ('saved_bit_mismatches', None),
                        'invalid_hash': ('actual_sha256', 'bad'),
                    }[mutation]
                    outputs['n0'][field] = value
                with self.assertRaises(ValueError):
                    self.check_prerequisite(snapshot, prior)

    def test_m16_prerequisite_rejects_incomplete_checkpoint_and_public_terminal(self):
        snapshot, original = self.prerequisite_fixture()
        for mutation in ('ack', 'pc', 'terminal', 'owner', 'completion', 'status', 'reset', 'count', 'source_after'):
            with self.subTest(mutation=mutation):
                prior = deepcopy(original)
                gate, host = prior['comparison_gate'], prior['execution']['host']
                if mutation == 'ack': gate['all_actual_final_acks_before_comparison'] = False
                elif mutation == 'pc': gate['public_completion_pcs'].pop()
                elif mutation == 'terminal': host['launch_result'] = {'completed': 10}
                elif mutation == 'owner': host['same_owner_and_banks'] = False
                elif mutation == 'completion': host['completions'].pop()
                elif mutation == 'status': host['completions'][3]['status'] = 'Fault'
                elif mutation == 'reset': host['reset_required'] = True
                elif mutation == 'count': host['accepted']['result_fire'] = 1
                elif mutation == 'source_after': prior['source_sha256_after'] = {}
                with self.assertRaises(ValueError):
                    self.check_prerequisite(snapshot, prior)


if __name__ == '__main__':
    unittest.main()
