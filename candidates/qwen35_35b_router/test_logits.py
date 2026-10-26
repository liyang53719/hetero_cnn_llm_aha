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
                'def audit(event, args):\n'
                '    if event=="ctypes.dlopen": raise RuntimeError("native load")\n'
                'sys.addaudithook(audit)\n'
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
        self.assertEqual(report['scope'], 'CURRENT_ROUTER_COLD_SOURCE_AUDIT_ONLY')
        self.assertEqual(report['status'], 'TEMP_REQUALIFICATION_REQUIRED')
        self.assertEqual(report['cold_source_identity_status'], 'PASS')
        self.assertFalse(report['historical_actual_pass_inherited'])

    def test_cold_identity_keeps_every_frozen_pin_and_optional_backend(self):
        identity, cold = gate.cold_source_identity()
        self.assertEqual(gate.sha(gate.IDENTITY), gate.FROZEN_IDENTITY_SHA256)
        self.assertEqual(len(identity['base_sources']) + len(identity['candidate_sources']), 108)
        self.assertEqual(set(cold['additional_sources']), gate.COLD_ADDITIONAL_SOURCES)
        self.assertEqual(set(cold['source_updates']), {
            'candidates/qwen35_gdn_prefill/chunk/vector.py',
            'candidates/qwen35_gdn_prefill/typed_dense.py',
            'candidates/qwen35_35b_router/run_logits.py',
            'candidates/qwen35_35b_router/test_logits.py'})

    def test_cold_rejects_drift_in_every_source_without_importing_it(self):
        identity, cold = gate.cold_source_identity()
        names = set(identity['base_sources']) | set(identity['candidate_sources']) | set(cold['additional_sources'])
        original = gate.sha
        for name in sorted(names):
            target = gate.ROOT / name
            def changed(path):
                return '0' * 64 if Path(path) == target else original(path)
            with self.subTest(source=name), patch.object(gate, 'sha', side_effect=changed):
                with self.assertRaisesRegex(ValueError, 'cold source drift'):
                    gate.cold_source_identity()

    def test_cold_rejects_changed_frozen_identity_and_incomplete_manifest(self):
        original = json.loads(gate.COLD_IDENTITY.read_bytes())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            historical = root / 'historical.json'
            historical.write_bytes(gate.IDENTITY.read_bytes() + b'\n')
            with self.assertRaisesRegex(ValueError, 'frozen replay identity drift'):
                gate.cold_source_identity(identity_path=historical)
            for key, value in (('source_updates', {}), ('additional_sources', {}),
                               ('scope', 'ACTUAL_PASS'), ('actual_qualification_status', 'PASS')):
                changed = {**original, key: value}
                lock = root / 'cold.json'
                lock.write_text(json.dumps(changed))
                with self.subTest(key=key), self.assertRaises(ValueError):
                    gate.cold_source_identity(cold_identity_path=lock)
            changed = json.loads(gate.COLD_IDENTITY.read_bytes())
            name = next(iter(changed['source_updates']))
            changed['source_updates'][name]['previous_sha256'] = '0' * 64
            lock.write_text(json.dumps(changed))
            with self.assertRaisesRegex(ValueError, 'frozen source provenance'):
                gate.cold_source_identity(cold_identity_path=lock)

    def test_cold_hashes_cannot_unlock_actual_or_allocate_output(self):
        gate.cold_source_identity()  # Current cold hashes are valid, not replay authority.
        out = gate.ROOT / 'work' / 'must-not-create-router-replay'
        self.assertFalse(out.exists())
        argv = ['--run-actual']
        for key in gate.REQUIRED:
            argv += ['--' + key.replace('_', '-'), str(out) if key == 'out' else '/missing/' + key]
        with patch.object(gate, 'cold_source_identity', side_effect=AssertionError('cold authority used')) as cold, \
                patch.object(gate, 'run_actual', side_effect=AssertionError('actual entered')) as actual, \
                patch.object(gate, 'validate_fixtures', side_effect=AssertionError('fixtures read')) as fixtures:
            with self.assertRaisesRegex(ValueError, 'source drift: candidates/qwen35_gdn_prefill/chunk/vector.py'):
                gate.main(argv)
        cold.assert_not_called(); actual.assert_not_called(); fixtures.assert_not_called()
        self.assertFalse(out.exists())

    def test_cold_rejects_source_symlink_outside_repository(self):
        identity = json.loads(gate.IDENTITY.read_bytes())
        first = next(iter(identity['base_sources']))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'repo'
            path = root / first
            path.parent.mkdir(parents=True)
            path.symlink_to(gate.ROOT / first)
            with self.assertRaisesRegex(ValueError, 'cold source containment'):
                gate.cold_source_identity(root=root)

    def test_cold_manifest_cannot_change_during_invocation(self):
        original = gate.record
        calls = 0
        def changed(path):
            nonlocal calls
            result = original(path)
            if Path(path) == gate.COLD_IDENTITY:
                calls += 1
                if calls > 1:
                    result['sha256'] = '0' * 64
            return result
        with patch.object(gate, 'record', side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'identity file changed during invocation'):
                gate.main([])

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


class OutputContainmentTests(unittest.TestCase):
    def check_path(self, root, path, accepted):
        with patch.object(gate, 'ROOT', root):
            args = gate.parser().parse_args(['--out', str(path)])
            if accepted:
                gate.validate_arguments(args)
            else:
                with self.assertRaisesRegex(ValueError, 'fresh ignored'):
                    gate.validate_arguments(args)

    def test_absent_work_root_is_not_a_fresh_run_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'repo'; root.mkdir()
            work = root / 'work'
            self.assertFalse(work.exists())
            self.check_path(root, work, False)
            self.assertFalse(work.exists())

    def test_fresh_child_is_admitted_without_creating_work_or_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'repo'; root.mkdir()
            self.check_path(root, root / 'work' / 'new-run', True)
            self.assertFalse((root / 'work').exists())

    def test_existing_work_and_existing_child_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'repo'; work = root / 'work'; work.mkdir(parents=True)
            child = work / 'old-run'; child.mkdir()
            self.check_path(root, work, False)
            self.check_path(root, child, False)
            self.check_path(root, work / 'new-run', True)

    def test_normalized_work_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'repo'; root.mkdir()
            self.check_path(root, root / 'work' / 'child' / '..', False)
            self.assertFalse((root / 'work').exists())

    def test_external_and_symlink_escape_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp); root = base / 'repo'; work = root / 'work'; work.mkdir(parents=True)
            external = base / 'external'; external.mkdir()
            self.check_path(root, external / 'new-run', False)
            (work / 'escape').symlink_to(external, target_is_directory=True)
            self.check_path(root, work / 'escape' / 'new-run', False)
            (work / 'dangling').symlink_to(base / 'missing')
            self.check_path(root, work / 'dangling', False)


if __name__ == '__main__':
    unittest.main()
