"""Cold gates and rejection tests: no Torch, downloaded weights or actual replay."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from . import run_logits as gate, reference, payload


class LogitsTests(unittest.TestCase):
    def test_cold_cli_has_no_numerical_import_or_actual_pass(self):
        code = ('import sys\nfrom candidates.qwen35_35b_router.run_logits import main\n'
                'r=main()\n'
                'if r["actual_status"]!="NOT_EXECUTED": raise RuntimeError("actual claim")\n'
                'if "torch" in sys.modules or "numpy" in sys.modules: raise RuntimeError("numeric import")\n')
        # Inherited -O is deliberate; the contract uses exceptions, never assert.
        command = [sys.executable] + (['-O'] if sys.flags.optimize else []) + ['-S', '-c', code]
        result = subprocess.run(command, cwd=gate.ROOT, capture_output=True, text=True,
                                env={**os.environ, 'PYTHONPATH': str(gate.ROOT / 'src')})
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report['actual_status'], 'NOT_EXECUTED')
        self.assertFalse(report['actual_matrix_owner_executed'])
        self.assertFalse(report['complete_router_owner'])

    def test_actual_requires_every_explicit_fixture(self):
        for missing in gate.REQUIRED:
            argv = ['--run-actual']
            for key in gate.REQUIRED:
                if key != missing:
                    argv += ['--' + key.replace('_', '-'), '/missing/' + key]
            with self.subTest(missing=missing), self.assertRaisesRegex(ValueError, 'all explicit fixture'):
                gate.validate_arguments(gate.parser().parse_args(argv))

    def test_cold_rejects_fixture_paths_without_opt_in(self):
        for key in gate.REQUIRED[:-1]:
            args = gate.parser().parse_args(['--' + key.replace('_', '-'), '/missing'])
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'require --run-actual'):
                gate.validate_arguments(args)

    def test_output_must_be_fresh_and_ignored(self):
        for out in (gate.HERE / 'never_write_output', gate.ROOT / 'work'):
            with self.subTest(out=out), self.assertRaisesRegex(ValueError, 'fresh ignored'):
                gate.validate_arguments(gate.parser().parse_args(['--out', str(out)]))

    def test_source_pin_and_containment_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'base.py').write_text('base')
            (root / 'candidate.py').write_text('candidate')
            identity = dict(schema=1, base_commit='8e0b2bbd35b3fee5ba2ca3e1f37e9274266b7689',
                            repository='liyang53719/hetero_cnn_llm_aha',
                            base_sources={'base.py': gate.sha(root / 'base.py')},
                            candidate_sources={'candidate.py': gate.sha(root / 'candidate.py')})
            lock = root / 'identity.json'
            lock.write_text(json.dumps(identity))
            self.assertEqual(gate.source_identity(root, lock), identity)
            (root / 'base.py').write_text('drift')
            with self.assertRaisesRegex(ValueError, 'source drift'):
                gate.source_identity(root, lock)
            identity['base_sources'] = {'../outside': '0' * 64}
            lock.write_text(json.dumps(identity))
            with self.assertRaisesRegex(ValueError, 'containment'):
                gate.source_identity(root, lock)

    def test_changed_identity_cannot_reauthorize_changed_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            identity = Path(tmp) / 'identity.json'
            identity.write_text(json.dumps(dict(source_sha256='a' * 64)))
            original = gate.record(identity)
            gate.identity_unchanged(original, identity)
            # Even a valid new JSON record is not the initial invocation's lock.
            identity.write_text(json.dumps(dict(source_sha256='b' * 64)))
            with self.assertRaisesRegex(ValueError, 'identity file changed'):
                gate.identity_unchanged(original, identity)

    def test_saved_producer_relocates_without_rewriting_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            raw = bytes(16 * 2048 * 2)
            path = directory / 'post_attention_norm.actual.bf16le'
            path.write_bytes(raw)
            digest = reference.sha(raw)
            receipt = dict(tokens=16, sources_unchanged=True, native_artifacts_unchanged=True,
                           observations=[dict(stage='post_attention_norm',
                            output=dict(path='/original/checkout/work/producer/' + path.name, sha256=digest),
                            owner=dict(complete=True, output_published=True, status=None, output_sha256=digest))])
            summary = directory / 'summary.json'
            summary.write_text(json.dumps(receipt))
            before = summary.read_bytes()
            self.assertEqual(reference.producer(directory, gate.sha(summary), 16)[0], raw)
            self.assertEqual(summary.read_bytes(), before)
            receipt['observations'][0]['output']['path'] = '/other/unrelated.bin'
            summary.write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError, 'filename'):
                reference.producer(directory, gate.sha(summary), 16)

    def test_fixture_hash_rejection_matrix(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = gate.parser().parse_args([])
            args.payload, args.runtime_root = root / 'payload', root / 'runtime'
            args.payload.mkdir(); args.runtime_root.mkdir()
            (args.payload / 'manifest.json').write_text('manifest')
            (args.runtime_root / 'python.sh').write_text('runtime')
            args.matrix_library, args.vector_library = root / 'matrix.so', root / 'vector.so'
            args.matrix_library.write_bytes(b'matrix'); args.vector_library.write_bytes(b'vector')
            compiler = root / 'gcc'; compiler.write_bytes(b'compiler')
            weight = b'weight'
            fixtures = dict(cases={}, payload_manifest=gate.record(args.payload / 'manifest.json'),
                            matrix_library=gate.record(args.matrix_library),
                            vector_library=gate.record(args.vector_library),
                            weight=dict(bytes=len(weight), sha256=reference.sha(weight)),
                            reference_compiler=gate.record(compiler))
            identity = dict(fixtures=fixtures, runtime=dict(sha256={'python.sh': gate.sha(args.runtime_root / 'python.sh')}))
            files = [args.payload / 'manifest.json', args.matrix_library, args.vector_library,
                     args.runtime_root / 'python.sh', compiler]
            for m in (16, 128):
                directory = root / str(m); directory.mkdir()
                setattr(args, 'producer_m' + str(m), directory)
                path = directory / 'post_attention_norm.actual.bf16le'
                path.write_bytes(bytes(m * 2048 * 2))
                digest = gate.sha(path)
                producer = dict(tokens=m, sources_unchanged=True, native_artifacts_unchanged=True,
                                matrix_library=fixtures['matrix_library'], vector_library=fixtures['vector_library'],
                                observations=[dict(stage='post_attention_norm', output=dict(path=str(path), sha256=digest),
                                 owner=dict(complete=True, output_published=True, status=None, output_sha256=digest))])
                summary = directory / 'summary.json'; summary.write_text(json.dumps(producer))
                fixtures['cases'][str(m)] = dict(input=gate.record(path), producer_summary=gate.record(summary))
                files += [path, summary]
            with patch.object(payload, 'load', return_value=({}, {'layers.0.mlp.gate.weight': weight})), \
                    patch.object(gate.shutil, 'which', return_value=str(compiler)):
                self.assertEqual(gate.validate_fixtures(args, identity)[2], weight)
                for path in files:
                    before = path.read_bytes()
                    path.write_bytes(before + b'X')
                    with self.subTest(path=path), self.assertRaises(ValueError):
                        gate.validate_fixtures(args, identity)
                    path.write_bytes(before)

    def test_no_expected_output_argument_in_execution(self):
        import inspect
        self.assertEqual(tuple(inspect.signature(gate.replay).parameters),
                         ('m', 'raw_input', 'weight', 'library', 'vector_path', 'out', 'identity'))

    def test_every_logit_and_both_oracles_must_match(self):
        for m in (16, 128):
            full = bytes(m * 256 * 2)
            changed_last = full[:-2] + b'\x80\x3f'
            self.assertEqual(gate.compare_outputs(full, full, full, m)['official']['bit_mismatches'], 0)
            for actual, official, independent in ((changed_last, full, full),
                                                   (full, changed_last, full),
                                                   (full, full, changed_last)):
                with self.subTest(m=m), self.assertRaisesRegex(ValueError, 'exact full-N256'):
                    gate.compare_outputs(actual, official, independent, m)
            with self.assertRaisesRegex(ValueError, 'full logits shape'):
                gate.compare_outputs(full[:-2], full, full, m)
            with self.assertRaisesRegex(ValueError, 'nonfinite'):
                gate.compare_outputs(b'\x80\x7f' + full[2:], full, full, m)


if __name__ == '__main__':
    unittest.main()
