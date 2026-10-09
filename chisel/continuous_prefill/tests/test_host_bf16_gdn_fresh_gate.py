"""CI transfer/orchestration regressions. No model, compiler or actual DUT runs."""
from pathlib import Path
import contextlib
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import types
import unittest
from unittest.mock import patch

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_host_bf16_gdn_fresh_gate as gate


class TransferTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.commit = 'a' * 40
        self.build = self.root / 'build'
        for name in gate.FILES:
            path = self.build / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(('synthetic unit identity: ' + name).encode())
        self.ready = dict(binary_sha256=gate.sha(self.build / 'obj/VHostBlockTop'),
                          rtl_sha256=gate.sha(self.build / 'generated/HostBlockTop.sv'))
        self.sources = {'source.py': 'b' * 64}
        self.archive = self.root / 'package.tar.gz'
        with patch.object(gate, 'build_admission', return_value=(self.ready, self.sources, {})):
            self.digest, self.manifest = gate.package(self.build, self.archive, self.commit)

    def write_archive(self, *, extra=None, change=None, omit=None):
        path = self.root / 'changed.tar.gz'
        with tarfile.open(self.archive, 'r:gz') as original, tarfile.open(path, 'w:gz', format=tarfile.USTAR_FORMAT) as output:
            for entry in original:
                if entry.name == omit:
                    continue
                data = original.extractfile(entry).read()
                if change and entry.name == gate.MANIFEST:
                    value = json.loads(data)
                    change(value)
                    data = gate.encoded(value)
                    entry.size = len(data)
                output.addfile(entry, io.BytesIO(data))
            if extra is not None:
                output.addfile(extra, io.BytesIO(b'x') if extra.isreg() else None)
        return path

    def test_exact_allowlist_roundtrip_and_no_fixture_transfer(self):
        self.assertEqual(gate.validate_archive(self.archive, self.digest, self.commit), self.manifest)
        out = self.root / 'restored'
        with patch.object(gate, 'verify_checkout') as verify:
            gate.unpack(self.archive, self.digest, self.commit, out)
        verify.assert_called_once_with(self.commit, self.sources)
        self.assertEqual({str(p.relative_to(out)) for p in out.rglob('*') if p.is_file()},
                         gate.FILES | {gate.MANIFEST})
        self.assertFalse(self.manifest['numerical_pass'])
        self.assertEqual((out / 'obj/VHostBlockTop').stat().st_mode & 0o777, 0o755)
        self.assertFalse(any(word in name.lower() for name in gate.FILES
                             for word in ('fixture', 'weight', '.npz', 'ddr', 'tensor')))

    def test_wrong_trusted_digest_or_commit_never_extracts(self):
        out = self.root / 'restored'
        for digest, commit in [('0' * 64, self.commit), (self.digest, 'c' * 40)]:
            with self.subTest(digest=digest, commit=commit), self.assertRaises(ValueError):
                gate.unpack(self.archive, digest, commit, out)
            self.assertFalse(out.exists())

    def test_traversal_symlink_duplicate_and_raw_tensor_are_rejected_before_extraction(self):
        for name, kind in [('../escape', tarfile.REGTYPE), ('link', tarfile.SYMTYPE),
                           ('obj/VHostBlockTop', tarfile.REGTYPE), ('ddr_after.bin', tarfile.REGTYPE)]:
            entry = tarfile.TarInfo(name)
            entry.type = kind
            entry.mode = 0o644
            entry.size = 1 if kind == tarfile.REGTYPE else 0
            entry.linkname = '../escape' if kind == tarfile.SYMTYPE else ''
            path = self.write_archive(extra=entry)
            out = self.root / 'restored'
            with self.subTest(name=name), self.assertRaises(ValueError):
                gate.unpack(path, gate.sha(path), self.commit, out)
            self.assertFalse(out.exists())

    def test_missing_file_forged_pass_digest_and_oversize_fail(self):
        modifications = [lambda m: m.update(status='PASS'),
                         lambda m: m.update(numerical_pass=True),
                         lambda m: m['files']['toolchain.json'].update(sha256='f' * 64),
                         lambda m: m['files']['toolchain.json'].update(bytes=gate.MAX_BYTES + 1)]
        for modify in modifications:
            path = self.write_archive(change=modify)
            with self.assertRaises(ValueError):
                gate.validate_archive(path, gate.sha(path), self.commit)
        path = self.write_archive(omit='toolchain.json')
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            gate.validate_archive(path, gate.sha(path), self.commit)

    def test_source_checkout_rejects_dirty_untracked_and_changed_bytes(self):
        (self.root / 'source.py').write_text('source')
        sources = {'source.py': gate.sha(self.root / 'source.py')}
        with patch.object(gate, 'ROOT', self.root), patch.object(gate, 'git_commit', return_value=self.commit), \
                patch.dict(os.environ, {'GITHUB_SHA': self.commit}):
            for outputs, message in [([b'other.py\0'], 'uncommitted'),
                                     ([b'source.py\0', ' M source.py\n'], 'clean checkout')]:
                with patch.object(gate.subprocess, 'check_output', side_effect=outputs), \
                        self.assertRaisesRegex(ValueError, message):
                    gate.verify_checkout(self.commit, sources)
            with patch.object(gate.subprocess, 'check_output', side_effect=[b'source.py\0', '']), \
                    self.assertRaisesRegex(ValueError, 'source changed'):
                gate.verify_checkout(self.commit, {'source.py': '0' * 64})


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'work').mkdir()
        self.events = []
        self.commit = 'a' * 40
        self.sources = {'source.py': 'b' * 64}
        self.ready = dict(binary_sha256='c' * 64, rtl_sha256='d' * 64)
        self.args = gate.parser().parse_args([
            'run', '--output', str(self.root / 'work/out'), '--archive', str(self.root / 'archive'),
            '--expected-sha256', 'e' * 64, '--expected-commit', self.commit, '--mode', 'pass'])
        self.session = types.SimpleNamespace(verify=lambda path: self.fixture_report)
        self.authority = types.SimpleNamespace(verify=lambda path: self.events.append('verify_live_authority'))
        self.fixture_report = dict(token_ids=[19, 92], head_jobs=48, matrix_accumulator_steps=12582912,
            input_boundary='official embedding and inputNorm', native_gate_pass=True,
            native_full_block_status='NOT_EVALUATED_BY_THIS_BOUNDED_PREFIX', reference_elapsed_seconds=1,
            max_rss_kib=500000, tools={}, files={'activation0.bf16le': {'sha256': 'f' * 64}},
            source_payload_manifest_sha256={'qwen35_layer0_payload': '1' * 64, 'qwen35_prefix_payload': '2' * 64})
        self.result = dict(status='PASS_PRODUCTION_HOST_GDN_CASE', actual_dut_identity_verified=True,
            numerical_acceptance_eligible=True, source_immutability_verified=True,
            mode='pass', **self.ready, log_sha256='3' * 64, source_admission={},
            runs=[dict(run=0, actual_sha256={'dense0': '4' * 64})])

    def unpack(self, archive, digest, commit, build):
        self.events.append('transfer')
        build.mkdir()
        (build / 'build_ready.json').write_text('{}')
        return {'sources': self.sources}

    def generate(self, path):
        self.events.append('fresh_reference')
        path.mkdir()
        (path / 'manifest.json').write_text('{}')
        return self.session

    def authenticate(self, path, *, session):
        self.assertIs(session, self.session)
        self.events.append('authenticate_live_session')
        return self.authority

    def execute(self, build, fixture, mode, **kwargs):
        self.assertIs(kwargs['authority'], self.authority)
        self.assertEqual(kwargs['source_root'], self.root)
        self.assertEqual(kwargs['timeout_seconds'], 5400)
        self.events.append('actual_case')
        return self.result

    def invoke(self):
        with contextlib.ExitStack() as stack:
            values = dict(ROOT=self.root, source_closure=lambda: self.sources,
                          verify_checkout=lambda *args: None, unpack=self.unpack,
                          build_admission=lambda *args: (self.ready, self.sources, {}),
                          runtime_identity=lambda path: {}, generate_fixture=self.generate,
                          authenticate_fixture=self.authenticate, run_case=self.execute)
            for name, value in values.items():
                stack.enter_context(patch.object(gate, name, value))
            stack.enter_context(patch.dict(os.environ, {'HF_HUB_OFFLINE': '1'}))
            return gate.run(self.args)

    def test_single_fresh_live_authority_and_full_identity_bound_actual_case(self):
        report, code = self.invoke()
        self.assertEqual(code, 0)
        self.assertEqual(self.events, ['transfer', 'fresh_reference', 'authenticate_live_session',
                                      'actual_case', 'verify_live_authority'])
        self.assertTrue(report['numerical_acceptance'])
        self.assertFalse(report['full_block_supported'])
        self.assertFalse(report['cross_host_byte_equivalence_claimed'])
        compact = self.args.output / 'compact'
        self.assertEqual({p.name for p in compact.iterdir()}, gate.COMPACT_FILES)
        hashes = gate.read_json(compact / 'source_input_hashes.json')
        self.assertEqual(hashes['input_sha256'], {'activation0.bf16le': 'f' * 64})
        self.assertEqual(hashes['package_sha256'], 'e' * 64)

    def test_timeout_is_pending_and_never_numerical_failure_or_pass(self):
        def timeout(*args, **kwargs):
            raise subprocess.TimeoutExpired('actual-dut', 5400)
        self.execute = timeout
        report, code = self.invoke()
        self.assertEqual(code, 1)
        self.assertEqual(report['status'], 'PENDING_INCOMPLETE_PRODUCTION_HOST_GDN')
        self.assertEqual(report['stage'], 'actual_host_pass')
        self.assertFalse(report['numerical_acceptance'])

    def test_untrusted_reference_never_starts_dut(self):
        self.fixture_report['native_gate_pass'] = False
        report, code = self.invoke()
        self.assertEqual(code, 1)
        self.assertNotIn('actual_case', self.events)
        self.assertFalse(report['numerical_acceptance'])

    def test_another_binary_or_artifact_only_result_never_passes(self):
        self.result['binary_sha256'] = 'wrong'
        report, code = self.invoke()
        self.assertEqual(code, 1)
        self.assertFalse(report['numerical_acceptance'])

    def test_incomplete_transfer_never_captures_or_runs(self):
        def reject(*args):
            raise ValueError('bad package')
        self.unpack = reject
        report, code = self.invoke()
        self.assertEqual(code, 1)
        self.assertFalse(self.events)
        self.assertEqual(report['stage'], 'verify_build_transfer')

    def test_only_reviewed_modes_and_bounded_budget_can_run(self):
        self.assertEqual(gate.CI_MODES, ('pass', 'last-history-ack-error', 'output-alias', 'reset-recovery'))
        self.args.timeout_seconds = 5401
        report, code = self.invoke()
        self.assertEqual(code, 1)
        self.assertFalse(self.events)


class WorkflowTests(unittest.TestCase):
    def test_pass_precedes_all_required_faults_and_uploads_are_explicit(self):
        workflow = yaml.load((gate.ROOT / gate.WORKFLOW).read_text(), Loader=yaml.BaseLoader)
        jobs = workflow['jobs']
        self.assertEqual(jobs['four-command-pass']['needs'], 'build')
        self.assertEqual(jobs['required-faults']['needs'], ['build', 'four-command-pass'])
        self.assertEqual(jobs['required-faults']['strategy']['matrix']['mode'], list(gate.CI_MODES[1:]))
        self.assertEqual(jobs['dense-conv-v1-acceptance']['needs'], ['build', 'four-command-pass', 'required-faults'])
        self.assertEqual(jobs['dense-conv-v1-acceptance']['if'], 'always()')
        self.assertEqual(workflow['concurrency']['cancel-in-progress'], 'false')
        small = next(step for step in jobs['build']['steps'] if step.get('name', '').startswith('Small scalar'))
        self.assertEqual(small['env']['MAKEFLAGS'], '-j1 VK_PCH_I_FAST= VK_PCH_I_SLOW=')
        for name, job in jobs.items():
            self.assertLessEqual(int(job['timeout-minutes']), 180)
            for step in job['steps']:
                if step.get('uses') == 'actions/upload-artifact@v4':
                    paths = step['with']['path'].splitlines()
                    self.assertTrue(all(path.endswith(('/host_gdn_build.tar.gz', '/compact/summary.json',
                                                       '/compact/source_input_hashes.json')) for path in paths))
            commands = '\n'.join(step.get('run', '') for step in job['steps'])
            self.assertNotIn('collect_qwen35_layer3_payload', commands)
            self.assertNotIn('full128', commands)
            if name in ('four-command-pass', 'required-faults'):
                self.assertIn('torch==2.10.0', commands)
                self.assertIn('numpy==2.3.5', commands)
                self.assertIn('--timeout-seconds 5400', commands)
                self.assertIn('14e738b5d0cc69aa27a95dde272aea41fde44f2f', commands)


if __name__ == '__main__':
    unittest.main()
