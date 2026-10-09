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


    def test_profile_is_receiver_selected_and_cannot_cross_accept(self):
        core_archive = self.root / 'core.tar.gz'
        with patch.object(gate, 'build_admission', return_value=(self.ready, self.sources, {})) as admission:
            digest, manifest = gate.package(self.build, core_archive, self.commit, profile='core')
        admission.assert_called_once_with(self.build, self.commit, profile='core')
        self.assertEqual(manifest['status'], gate.CORE_BUILD_STATUS)
        self.assertEqual(manifest['scope'], gate.CORE_SCOPE)
        self.assertEqual(manifest['build_profile'], 'core')
        self.assertFalse(manifest['numerical_pass'])
        self.assertEqual(len(manifest['files']), 14)
        for archive, sha, receiver in ((self.archive, self.digest, 'core'),
                                       (core_archive, digest, 'dense-conv')):
            with self.subTest(receiver=receiver), self.assertRaisesRegex(ValueError, 'receiver-selected'):
                gate.unpack(archive, sha, self.commit, self.root / 'wrong', profile=receiver)
            self.assertFalse((self.root / 'wrong').exists())
        with patch.object(gate, 'verify_checkout'):
            received = gate.unpack(core_archive, digest, self.commit, self.root / 'core', profile='core')
        self.assertEqual(received, manifest)
        self.assertEqual({str(p.relative_to(self.root / 'core')) for p in (self.root / 'core').rglob('*')
                          if p.is_file()}, gate.FILES | {gate.MANIFEST})

    def test_core_malformed_scope_status_schema_and_entries_fail_before_extract(self):
        self.archive = self.root / 'core.tar.gz'
        with patch.object(gate, 'build_admission', return_value=(self.ready, self.sources, {})):
            gate.package(self.build, self.archive, self.commit, profile='core')
        changes = [lambda m: m.update(build_profile='dense-conv'),
                   lambda m: m.update(scope=gate.SCOPE),
                   lambda m: m.update(status=gate.BUILD_STATUS),
                   lambda m: m.update(numerical_pass=True),
                   lambda m: m.update(schema=True),
                   lambda m: m['files'].update({'toolchain.json': []}),
                   lambda m: m['files']['toolchain.json'].update(sha256='0' * 64),
                   lambda m: m['sources'].update({'../escape': '0' * 64})]
        for change in changes:
            path = self.write_archive(change=change)
            with self.assertRaises(ValueError):
                gate.unpack(path, gate.sha(path), self.commit, self.root / 'wrong', profile='core')
            self.assertFalse((self.root / 'wrong').exists())
        for name, kind in [('obj/VHostBlockTop', tarfile.REGTYPE),
                           ('../outside', tarfile.REGTYPE), ('link', tarfile.SYMTYPE),
                           ('weights.npz', tarfile.REGTYPE)]:
            entry = tarfile.TarInfo(name)
            entry.mode = 0o644
            entry.type = kind
            entry.size = int(kind == tarfile.REGTYPE)
            entry.linkname = '../outside' if kind == tarfile.SYMTYPE else ''
            path = self.write_archive(extra=entry)
            with self.subTest(name=name), self.assertRaises(ValueError):
                gate.unpack(path, gate.sha(path), self.commit, self.root / 'wrong', profile='core')
            self.assertFalse((self.root / 'wrong').exists())


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

    def unpack(self, archive, digest, commit, build, *, profile='dense-conv'):
        self.assertEqual(profile, 'dense-conv')
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
            values = dict(ROOT=self.root, source_closure=lambda **kwargs: self.sources,
                          verify_checkout=lambda *args: None, unpack=self.unpack,
                          build_admission=lambda *args, **kwargs: (self.ready, self.sources, {}),
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


class CoreRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'work').mkdir()
        self.events = []
        self.invocations = 0
        self.commit = 'a' * 40
        self.sources = {'core_source.py': 'b' * 64}
        self.ready = dict(binary_sha256='c' * 64, rtl_sha256='d' * 64)
        self.args = gate.parser().parse_args([
            'run', '--profile', 'core', '--output', str(self.root / 'work/out'),
            '--archive', str(self.root / 'archive'), '--expected-sha256', 'e' * 64,
            '--expected-commit', self.commit, '--mode', 'pass', '--timeout-seconds', '7200'])
        self.fixture_report = dict(
            status='SOURCE_AUTHENTICATED_HOST_GDN_CORE_TWO_TOKEN_FIXTURE',
            scope=gate.CORE_FIXTURE_SCOPE, token_ids=[19, 92], tokens_per_launch=1,
            launches=2, commands_per_launch=8, heads=16, head_width=128,
            reference_head_jobs=66, reference_padded_fma_steps=17301504,
            actual_useful_dense_macs=16842752,
            canonical_acceptance='EXACT_BITS_EVERY_STAGE_AND_BOTH_STATES',
            native_operator_gate_pass=True,
            frozen_operator_metrics=[dict(token=token, passed=True) for token in range(2)],
            native_core_gate_pass=None, native_full_block_gate_pass=None,
            native_full_block_status='NOT_ESTABLISHED_BY_CORE_FIXTURE', full_block_supported=False,
            input_norm_dut=False, o_projection_dut=False, residual_dut=False, ffn_dut=False,
            rtl_executed=False, generations=[0, 1, 2], input_boundary='official embedding and inputNorm',
            official_stage_acceptance='UNASSIGNED_DIAGNOSTIC_ONLY', reference_elapsed_seconds=1,
            max_rss_kib=500000, tools={}, files={'activation0.bf16le': {'sha256': 'f' * 64}},
            source_payload_manifest_sha256={'qwen35_layer0_payload': '1' * 64, 'qwen35_prefix_payload': '2' * 64})
        self.session = types.SimpleNamespace(verify=self.verify_session)
        self.result = dict(status='PASS_PRODUCTION_HOST_GDN_CORE_CANONICAL', scope=gate.CORE_SCOPE,
            actual_dut_identity_verified=True, source_immutability_verified=True,
            canonical_core_pass=True, actual_useful_dense_macs=16842752,
            actual_ack_history_state_carry=True, native_operator_gate_pass=True,
            frozen_operator_metrics=self.fixture_report['frozen_operator_metrics'], native_core_gate_pass=None,
            native_full_block_gate_pass=None, full_block_supported=False, fault_restore_supported=False,
            input_norm_dut=False, o_projection_dut=False, residual_dut=False, ffn_dut=False,
            **self.ready, log_sha256='3' * 64,
            runs=[dict(token=token, committed_generation=token+1, canonical_bit_mismatches=0,
                       commands=[dict(pc=pc) for pc in range(8)], ddr_after_sha256=str(4+token) * 64)
                  for token in range(2)])

    def verify_session(self, path):
        self.events.append('verify_live_session')
        return self.fixture_report

    def generate(self, path):
        self.events.append('fresh_core_reference')
        path.mkdir()
        (path / 'manifest.json').write_text('{}')
        return self.session

    def unpack(self, archive, digest, commit, build, *, profile):
        self.assertEqual(profile, 'core')
        self.events.append('transfer_core')
        build.mkdir()
        (build / 'build_ready.json').write_text('{}')
        return {'sources': self.sources}

    def admit(self, build, commit, *, profile):
        self.assertEqual(profile, 'core')
        self.events.append('admit_core')
        return self.ready, self.sources, {}

    def execute(self, build, fixture, *, session, source_root, timeout_seconds):
        self.assertIs(session, self.session)
        self.assertEqual(source_root, self.root)
        self.assertEqual(timeout_seconds, 7200)
        self.events.append('actual_core_case')
        return self.result

    def invoke(self):
        import pack_host_bf16_gdn_core_fixture as core_fixture
        import host_bf16_gdn_core_execution as core_execution
        self.args.output = self.root / 'work' / ('out' + str(self.invocations))
        self.invocations += 1
        self.events.clear()
        with contextlib.ExitStack() as stack:
            for name, value in dict(ROOT=self.root, source_closure=lambda **kwargs: self.sources,
                                    verify_checkout=lambda *args: None, unpack=self.unpack,
                                    build_admission=self.admit, runtime_identity=lambda path: {}).items():
                stack.enter_context(patch.object(gate, name, value))
            for name in ('generate_fixture', 'authenticate_fixture', 'run_case'):
                stack.enter_context(patch.object(gate, name, side_effect=AssertionError('v1 pipeline used for core')))
            stack.enter_context(patch.object(core_fixture, 'generate_fixture', self.generate))
            stack.enter_context(patch.object(core_execution, 'run_case', self.execute))
            stack.enter_context(patch.dict(os.environ, {'HF_HUB_OFFLINE': '1'}))
            return gate.run(self.args)

    def test_live_core_session_continues_on_same_case_and_scope_stays_bounded(self):
        report, code = self.invoke()
        self.assertEqual(code, 0)
        self.assertEqual(self.events, ['transfer_core', 'admit_core', 'fresh_core_reference',
                                      'verify_live_session', 'actual_core_case',
                                      'verify_live_session', 'admit_core'])
        self.assertEqual(report['status'], 'PASS_PRODUCTION_HOST_GDN_CORE_CANONICAL')
        self.assertEqual(report['numerical_acceptance_scope'], 'canonical_gdn_core_only')
        self.assertTrue(report['canonical_core_pass'])
        self.assertTrue(report['numerical_acceptance'])
        self.assertTrue(report['native_operator_gate_pass'])
        self.assertTrue(report['recurrent_state_supported'])
        self.assertTrue(report['gated_norm_supported'])
        self.assertEqual(report['pending_gates'], list(gate.CORE_PENDING_GATES))
        self.assertIsNone(report['native_core_gate_pass'])
        self.assertIsNone(report['native_full_block_gate_pass'])
        self.assertFalse(report['full_block_supported'])
        self.assertFalse(report['fault_restore_supported'])
        compact = self.args.output / 'compact'
        self.assertEqual({p.name for p in compact.iterdir()}, gate.COMPACT_FILES)
        hashes = gate.read_json(compact / 'source_input_hashes.json')
        self.assertEqual(hashes['output_sha256'], {'0': '4' * 64, '1': '5' * 64})

    def test_unsupported_faults_and_excess_budget_never_transfer_or_generate(self):
        for mode, budget in [(mode, 7200) for mode in gate.CI_MODES[1:]] + [('pass', 7201), ('pass', 0)]:
            self.args.mode, self.args.timeout_seconds = mode, budget
            with self.subTest(mode=mode, budget=budget):
                report, code = self.invoke()
                self.assertEqual(code, 1)
                self.assertFalse(self.events)
                self.assertFalse(report['numerical_acceptance'])

    def test_changed_reference_shape_count_or_broadened_claim_never_starts_dut(self):
        for key, bad in [('reference_head_jobs', 48), ('reference_padded_fma_steps', 16842752),
                         ('actual_useful_dense_macs', 17301504), ('tokens_per_launch', 2),
                         ('heads', True), ('full_block_supported', True), ('native_core_gate_pass', True),
                         ('native_operator_gate_pass', False)]:
            original = self.fixture_report[key]
            self.fixture_report[key] = bad
            with self.subTest(key=key):
                report, code = self.invoke()
                self.assertEqual(code, 1)
                self.assertNotIn('actual_core_case', self.events)
                self.assertFalse(report['numerical_acceptance'])
            self.fixture_report[key] = original

    def test_artifact_only_or_foreign_or_broadened_result_is_never_accepted(self):
        for key, bad in [('status', 'PASS_HOST_GDN_CORE_ARTIFACT_CHECK_ONLY'), ('scope', gate.SCOPE),
                         ('binary_sha256', '0' * 64), ('rtl_sha256', '0' * 64),
                         ('source_immutability_verified', False), ('actual_ack_history_state_carry', False),
                         ('native_core_gate_pass', True), ('full_block_supported', True),
                         ('native_operator_gate_pass', False), ('frozen_operator_metrics', []),
                         ('actual_useful_dense_macs', 17301504), ('runs', self.result['runs'][:1])]:
            original = self.result[key]
            self.result[key] = bad
            with self.subTest(key=key):
                report, code = self.invoke()
                self.assertEqual(code, 1)
                self.assertFalse(report['canonical_core_pass'])
                self.assertFalse(report['numerical_acceptance'])
            self.result[key] = original

    def test_timeout_is_pending_and_final_identity_failure_revokes_pass(self):
        def timeout(*args, **kwargs):
            raise subprocess.TimeoutExpired('actual-core-dut', 7200)
        original = self.execute
        self.execute = timeout
        report, code = self.invoke()
        self.assertEqual(code, 1)
        self.assertEqual(report['status'], 'PENDING_INCOMPLETE_PRODUCTION_HOST_GDN_CORE')
        self.assertEqual(report['stage'], 'actual_host_core_cold_carried')
        self.assertFalse(report['numerical_acceptance'])
        self.execute = original
        original_admit = self.admit
        def changed(build, commit, *, profile):
            if 'actual_core_case' in self.events:
                raise ValueError('source changed after actual case')
            return original_admit(build, commit, profile=profile)
        self.admit = changed
        report, code = self.invoke()
        self.assertEqual(code, 1)
        self.assertFalse(report['canonical_core_pass'])
        self.assertFalse(report['numerical_acceptance'])


class CoreAdmissionTests(unittest.TestCase):
    def test_source_closure_covers_core_producers_and_rejects_stale_build_rebinding(self):
        sources = gate.source_closure(profile='core')
        required = {
            gate.SCRIPT, gate.CORE_WORKFLOW,
            'chisel/continuous_prefill/config/host_bf16_gdn_core_descriptor_contract.json',
            'chisel/continuous_prefill/scripts/pack_host_bf16_gdn_core_fixture.py',
            'chisel/continuous_prefill/scripts/host_bf16_gdn_core_descriptor.py',
            'chisel/continuous_prefill/scripts/host_bf16_gdn_core_execution.py',
            'chisel/continuous_prefill/scripts/host_bf16_gdn_execution.py',
            'chisel/continuous_prefill/scripts/gdn_input_prep_reference.py',
            'chisel/continuous_prefill/scripts/gdn_gated_norm_reference.py',
            'src/heteronpu/qwen35_gdn_recurrent_fp32.py',
            'chisel/continuous_prefill/tests/host_bf16_gdn_core.cpp',
        }
        self.assertTrue(required <= set(sources))
        self.assertIn(gate.WORKFLOW, gate.source_closure())
        self.assertNotIn(gate.CORE_WORKFLOW, gate.source_closure())
        with tempfile.TemporaryDirectory() as directory:
            build = Path(directory)
            gate.save(build / 'sources.sha256.json', {gate.CORE_WORKFLOW: '0' * 64})
            with self.assertRaisesRegex(ValueError, 'source identity conflict'):
                gate.source_closure(build, profile='core')

    def test_emitted_core_scope_is_fixed_and_receipt_path_cannot_be_rebound(self):
        with tempfile.TemporaryDirectory() as directory:
            build = Path(directory) / 'build'
            (build / 'generated').mkdir(parents=True)
            commit = 'a' * 40
            hf = Path(directory) / 'hardfloat'
            actual = dict(actual_elf=dict(kind='ELF', sha256='b' * 64, version='Verilator 5.032'),
                          entrypoint=dict(sha256='c' * 64))
            ready = dict(source_base_commit=commit, initial_verilation_exit=0,
                         source_snapshot_manifest_sha256=None, hardfloat_source=str(hf), actual_verilator=actual)
            toolchain = dict(compiler_jars_verified_after_build=True,
                             compiler_jars_sha256={}, hardfloat_source_sha256={}, idma_identity={},
                             tools=dict(verilator_backend=dict(version='Verilator 5.032', sha256='c' * 64),
                                        firtool=dict(version='1.62.1')))
            scope = dict(experimental_bf16_gdn=True, experimental_gdn_core=True, default_enabled=False,
                         scope=gate.CORE_SCOPE, policy_version=2, hidden=1024, gdn_channels=6144,
                         conv_kernel=4, scalar_service_shared=True, full_block_supported=False,
                         burst_writes=False, logical_matrix_engines=1, physical_matrix_slices=8,
                         pinned_idma_instances=1, max_tokens=1, heads=16, head_dim=128,
                         managed_state_contexts=1, softplus_enabled=True, recurrent_state_dtype='FP32',
                         output_projection_supported=False, ffn_supported=False, timing_signoff=False)
            for filename, value in {'build_ready.json': ready, 'generated/SCOPE.json': scope,
                                    'source_scope.json': {'scope': 'full', 'unrelated_helpers_bound': True},
                                    'toolchain.json': toolchain, 'compiler_jars.sha256.json': {},
                                    'hardfloat.sha256.json': {}, 'idma_identity.json': {},
                                    'actual_verilator_before.json': actual,
                                    'actual_verilator_after.json': actual}.items():
                gate.save(build / filename, value)
            (build / 'build.exit').write_text('0\n')
            (build / 'source_base_commit.txt').write_text(commit + '\n')
            with contextlib.ExitStack() as stack:
                identity = stack.enter_context(patch.object(gate, '_build_identity', return_value={}))
                for name in ('validate_maps', 'verify_checkout', 'verify_all_build_sources'):
                    stack.enter_context(patch.object(gate, name))
                stack.enter_context(patch.object(gate, 'source_closure', return_value={'source.py': 'd' * 64}))
                stack.enter_context(patch.dict(os.environ, {'HARDFLOAT_SOURCE': str(hf)}))
                gate.build_admission(build, commit, profile='core')
                identity.assert_called_once_with(build, profile='core')
                for key, bad in [('policy_version', 1), ('max_tokens', 128), ('max_tokens', True),
                                 ('heads', 48), ('head_dim', 256), ('recurrent_state_dtype', 'BF16'),
                                 ('full_block_supported', True), ('output_projection_supported', True),
                                 ('ffn_supported', True), ('physical_matrix_slices', 1)]:
                    gate.save(build / 'generated/SCOPE.json', dict(scope, **{key: bad}))
                    with self.subTest(key=key, value=bad), self.assertRaisesRegex(ValueError, 'build profile'):
                        gate.build_admission(build, commit, profile='core')
                gate.save(build / 'generated/SCOPE.json', scope)
                gate.save(build / 'build_ready.json', dict(ready, hardfloat_source=str(hf / 'another')))
                with self.assertRaisesRegex(ValueError, 'do not rebind receipts'):
                    gate.build_admission(build, commit, profile='core')

    def test_build_passes_explicit_profile_and_cannot_claim_numerical_acceptance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'work').mkdir()
            args = gate.parser().parse_args(['build', '--profile', 'core', '--output', str(root / 'work/out')])
            commit, digest = 'a' * 40, 'b' * 64
            manifest = dict(sources={'source.py': 'c' * 64}, binary_sha256='d' * 64, rtl_sha256='e' * 64)
            with patch.object(gate, 'ROOT', root), patch.object(gate, 'git_commit', return_value=commit), \
                    patch.object(gate, 'source_closure', return_value=manifest['sources']), \
                    patch.object(gate, 'verify_checkout'), patch.object(gate.subprocess, 'run') as process, \
                    patch.object(gate, 'package', return_value=(digest, manifest)) as package, \
                    patch.dict(os.environ, {'BUILD_JOBS': '1'}):
                report, code = gate.run(args)
            self.assertEqual(code, 0)
            self.assertEqual(process.call_count, 1)
            self.assertEqual(process.call_args.args[0][-2:], ['0', 'core'])
            self.assertEqual(process.call_args.kwargs['timeout'], 6300)
            self.assertEqual(package.call_args.kwargs, {'profile': 'core'})
            self.assertEqual(report['status'], gate.CORE_BUILD_STATUS)
            self.assertFalse(report['numerical_acceptance'])
            self.assertFalse(report['canonical_core_pass'])
            self.assertEqual(gate.parser().parse_args(['build', '--output', str(root / 'work/default')]).profile,
                             'dense-conv')

    def test_compact_outputs_reject_raw_tensors_symlinks_and_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'work/out/compact').mkdir(parents=True)
            out = root / 'work/out'
            with patch.object(gate, 'ROOT', root), self.assertRaisesRegex(ValueError, 'new output'):
                gate.fresh_output(out)
            tensor = out / 'compact/tensor.npz'
            tensor.write_bytes(b'private test tensor')
            with self.assertRaisesRegex(ValueError, 'non-allowlisted'):
                gate.write_compact(out, {}, {})
            tensor.unlink()
            target = root / 'outside.json'
            target.write_text('preserved')
            (out / 'compact/summary.json').symlink_to(target)
            with self.assertRaisesRegex(ValueError, 'non-allowlisted'):
                gate.write_compact(out, {}, {})
            self.assertEqual(target.read_text(), 'preserved')


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

    def test_core_workflow_only_runs_bounded_continuous_core_and_compact_uploads(self):
        workflow = yaml.load((gate.ROOT / gate.CORE_WORKFLOW).read_text(), Loader=yaml.BaseLoader)
        jobs = workflow['jobs']
        self.assertEqual(set(jobs), {'build', 'core-canonical-pass', 'core-only-acceptance'})
        self.assertEqual(jobs['build']['timeout-minutes'], '120')
        self.assertEqual(jobs['core-canonical-pass']['needs'], 'build')
        self.assertEqual(jobs['core-canonical-pass']['timeout-minutes'], '180')
        self.assertEqual(jobs['core-only-acceptance']['needs'], ['build', 'core-canonical-pass'])
        self.assertEqual(jobs['core-only-acceptance']['if'], 'always()')
        self.assertEqual(workflow['concurrency']['cancel-in-progress'], 'false')
        commands = '\n'.join(step.get('run', '') for job in jobs.values() for step in job['steps'])
        self.assertEqual(commands.count('run_host_bf16_gdn_fresh_gate.py run'), 1)
        self.assertIn('build --profile core', commands)
        self.assertIn('run --profile core', commands)
        self.assertIn('--mode pass --timeout-seconds 7200', commands)
        self.assertIn('HostBlockCommandsGdnCoreSpec', commands)
        self.assertIn('HostBlockCommandsGdnSpec', commands)
        self.assertIn('torch==2.10.0', commands)
        self.assertIn('numpy==2.3.5', commands)
        self.assertIn('14e738b5d0cc69aa27a95dde272aea41fde44f2f', commands)
        self.assertNotIn('collect_qwen35_layer3_payload', commands)
        self.assertNotIn('full128', commands)
        self.assertNotIn('--mode reset-recovery', commands)
        self.assertNotIn('--mode last-history-ack-error', commands)
        self.assertIn('native core acceptance and full-block acceptance remain PENDING', commands)
        self.assertEqual(jobs['core-canonical-pass']['env']['TRUSTED_PACKAGE_SHA'],
                         '${{ needs.build.outputs.package_sha256 }}')
        self.assertEqual(jobs['core-canonical-pass']['env']['TRUSTED_SOURCE_COMMIT'],
                         '${{ needs.build.outputs.source_commit }}')
        for job in jobs.values():
            for step in job['steps']:
                if step.get('uses') == 'actions/checkout@v4':
                    self.assertEqual(step['with']['ref'], '${{ github.sha }}')
                if step.get('uses') == 'actions/upload-artifact@v4':
                    paths = step['with']['path'].splitlines()
                    self.assertTrue(all(path.endswith(('/host_gdn_build.tar.gz', '/compact/summary.json',
                                                       '/compact/source_input_hashes.json')) for path in paths))


if __name__ == '__main__':
    unittest.main()
