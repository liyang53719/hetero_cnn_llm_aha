"""Orchestration checks only; never invoke official capture, a compiler or DUT."""
from pathlib import Path
import importlib.util
import contextlib
import io
import json
import tempfile
import types
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/run_host_bf16_qkv_fresh_gate.py'
MODES = ('pass', 'last-write-error', 'activation-read-error', 'weight-read-error', 'output-alias', 'reset-recovery')
BUILD_STATUS = 'BUILT_HOST_QKV_PROJECTIONS_ONLY_NOT_NUMERICAL_PASS'


class FreshGateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / 'work').mkdir()
        self.events = []
        self.head = 'a' * 40
        self.session = types.SimpleNamespace(fresh=True, manifest_sha256='b' * 64)
        self.session.verify = lambda: dict(source_sha256={})
        self.session.evidence = lambda: dict(fresh_official_executions=2, reused_official_executions=0)
        receipt = dict(status='VERIFIED_BOUNDED_INTEGER_C_QKV_TERMINALS', origin='fresh_same_invocation_integer_c',
            policy='test', head_jobs=48, windows={str(i): {} for i in range(4)}, source_sha256={},
            matrix_accumulator_steps=20971520, elapsed_seconds=1, native_operator_gate_pass=True,
            native_thresholds={'max_abs': .03125, 'mean_abs': .005}, maximum_head_accumulator_bytes=2097152,
            persistent_accumulator_traces=False, full128_reference_generated=False,
            cross_variant_input_identity_assumed=False, tools={})
        self.references = types.SimpleNamespace(receipt_sha256='c' * 64)
        self.references.verify = lambda *, session: receipt if session is self.session else self.fail('wrong session')
        self.receipt = receipt

        def module(name, **values):
            result = types.ModuleType(name)
            result.__dict__.update(values)
            return result

        def rebuild(*args):
            self.events.append('capture')
            return self.session

        def generate(session, output, *, variants):
            self.assertIs(session, self.session)
            self.assertEqual(variants, ('baseline', 'avx2'))
            self.events.append('references')
            return self.references

        def pack(output, **kwargs):
            self.assertIs(kwargs['session'], self.session)
            self.assertIs(kwargs['reference_session'], self.references)
            self.events.append(('pack', kwargs['variant'], kwargs['phase'], kwargs['token_base']))

        def verify(fixture, **kwargs):
            self.assertIs(kwargs['session'], self.session)
            self.assertIs(kwargs['reference_session'], self.references)
            return dict(input_sha256={'activation_window': 'd' * 64})

        def execute(build, fixture, mode, session, **kwargs):
            self.assertIs(session, self.session)
            self.assertIs(kwargs['reference_session'], self.references)
            self.events.append(('run', kwargs['label'], mode))
            return dict(status='PASS_PRODUCTION_HOST_QKV_CASE', actual_dut_identity_verified=True,
                numerical_acceptance_eligible=True, binary_sha256=self.subject.sha(build / 'obj/VHostBlockTop'),
                rtl_sha256=self.subject.sha(build / 'generated/HostBlockTop.sv'),
                runs=[dict(run=0, actual_sha256={'q': 'e' * 64})])

        def compact(out, summary, hashes):
            destination = out / 'compact'
            destination.mkdir(exist_ok=True)
            (destination / 'summary.json').write_text(json.dumps(summary))
            (destination / 'source_input_hashes.json').write_text(json.dumps(hashes))

        modules = {
            'pack_host_bf16_v_fixture': module('pack_host_bf16_v_fixture', ROOT=self.root, rebuild_session=rebuild),
            'pack_host_bf16_qkv_fixture': module('pack_host_bf16_qkv_fixture', pack_fixture=pack),
            'verify_host_bf16_qkv_fixture': module('verify_host_bf16_qkv_fixture', verify=verify),
            'host_bf16_qkv_execution': module('host_bf16_qkv_execution', BUILD_STATUS=BUILD_STATUS, MODES=MODES, run_case=execute,
                verify_all_build_sources=lambda *args: self.events.append('verify_build')),
            'host_bf16_qkv_reference': module('host_bf16_qkv_reference', generate_projection_references=generate),
            'run_host_bf16_v_fresh_gate': module('run_host_bf16_v_fresh_gate', _write_compact=compact,
                _native_failure_evidence=lambda session: {'baseline': {'gate_pass': False}},
                _preflight=lambda env, out: {}, _git_head=lambda: self.head),
        }
        spec = importlib.util.spec_from_file_location('_qkv_fresh_gate_subject', SCRIPT)
        self.subject = importlib.util.module_from_spec(spec)
        with patch.dict('sys.modules', modules):
            spec.loader.exec_module(self.subject)
        self.subject.ENTRY_SOURCES = ('source.py',)
        (self.root / 'source.py').write_text('source\n')
        self.args = self.subject.parser().parse_args(['--output', str(self.root / 'work/out')])

    def build(self, argv, **kwargs):
        self.events.append('build')
        self.assertEqual(argv[-1], '0')
        self.assertEqual(kwargs['env']['BUILD_JOBS'], '1')
        out = Path(argv[-2])
        (out / 'obj').mkdir(parents=True)
        (out / 'generated').mkdir()
        (out / 'obj/VHostBlockTop').write_bytes(b'fake binary')
        (out / 'generated/HostBlockTop.sv').write_bytes(b'fake RTL')
        (out / 'toolchain.json').write_text('{}')
        (out / 'sources.sha256.json').write_text('{}')
        ready = dict(status=BUILD_STATUS, numerical_pass=False, initial_verilation_exit=0,
                     actual_verilator={'entrypoint': {'sha256': '1' * 64},
                                       'actual_elf': {'kind': 'ELF', 'sha256': '2' * 64}},
                     binary_sha256=self.subject.sha(out / 'obj/VHostBlockTop'),
                     rtl_sha256=self.subject.sha(out / 'generated/HostBlockTop.sv'))
        (out / 'build_ready.json').write_text(json.dumps(ready))

    def invoke(self):
        with patch.object(self.subject, 'verify_checkout'), \
             patch.object(self.subject.subprocess, 'run', side_effect=self.build), \
             patch.dict('os.environ', {'BUILD_JOBS': '1'}):
            return self.subject.run(self.args)

    def test_success_uses_one_capture_reference_build_and_exact_nine_cases(self):
        report, code = self.invoke()
        self.assertEqual(code, 0)
        self.assertTrue(report['numerical_acceptance'])
        self.assertEqual(self.events[:3], ['capture', 'references', 'build'])
        self.assertEqual(sum(event == 'build' for event in self.events), 1)
        self.assertEqual(len([event for event in self.events if event[0] == 'pack']), 4)
        self.assertEqual(len(report['cases']), 9)
        self.assertEqual([row['mode'] for row in report['cases'][:6]], list(MODES))
        self.assertEqual({(row['variant'], row['phase'], row['token_base']) for row in report['cases']},
                         set(self.subject.WINDOWS))
        self.assertFalse(report['full128_accepted'])
        self.assertEqual(report['build']['actual_verilator']['actual_elf']['sha256'], '2' * 64)
        self.assertEqual(report['build']['initial_verilation_exit'], 0)
        self.assertFalse(report['build']['numerical_pass'])
        self.assertFalse(report['native_full_block_failures']['baseline']['gate_pass'])
        self.assertEqual({p.name for p in (self.args.output / 'compact').iterdir()},
                         {'summary.json', 'source_input_hashes.json'})

    def test_build_failure_retains_failure_not_acceptance(self):
        with patch.object(self, 'build', side_effect=RuntimeError('mock build failed')):
            report, code = self.invoke()
        self.assertEqual(code, 1)
        self.assertFalse(report['numerical_acceptance'])
        self.assertEqual(report['stage'], 'production_host_build_only')
        self.assertFalse(report['cases'])

    def test_missing_actual_elf_cannot_start_numerical_cases(self):
        original = self.build

        def missing_elf(argv, **kwargs):
            original(argv, **kwargs)
            path = Path(argv[-2]) / 'build_ready.json'
            ready = json.loads(path.read_text())
            del ready['actual_verilator']['actual_elf']
            path.write_text(json.dumps(ready))

        with patch.object(self, 'build', side_effect=missing_elf):
            report, code = self.invoke()
        self.assertEqual(code, 1)
        self.assertFalse(report['cases'])
        self.assertFalse(report['numerical_acceptance'])

    def test_case_failure_stops_remaining_cases_and_keeps_partial_report(self):
        original = self.subject.run_case
        calls = 0

        def fail_second(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise TimeoutError('mock timeout')
            return original(*args, **kwargs)

        with patch.object(self.subject, 'run_case', side_effect=fail_second):
            report, code = self.invoke()
        self.assertEqual(code, 1)
        self.assertEqual(len(report['cases']), 1)
        self.assertFalse(report['numerical_acceptance'])
        self.assertEqual(report['error']['type'], 'TimeoutError')

    def test_incomplete_reference_never_builds(self):
        self.receipt['head_jobs'] = 24
        report, code = self.invoke()
        self.assertEqual(code, 1)
        self.assertNotIn('build', self.events)

    def test_native_operator_failure_never_builds_or_claims_full_block(self):
        self.receipt['native_operator_gate_pass'] = False
        report, code = self.invoke()
        self.assertEqual(code, 1)
        self.assertNotIn('build', self.events)
        self.assertFalse(report['numerical_acceptance'])
        self.assertFalse(report['full_block_supported'])

    def test_case_with_other_binary_cannot_pass(self):
        with patch.object(self.subject, 'run_case', return_value=dict(status='PASS_PRODUCTION_HOST_QKV_CASE',
                actual_dut_identity_verified=True, numerical_acceptance_eligible=True,
                binary_sha256='wrong', rtl_sha256='wrong')):
            report, code = self.invoke()
        self.assertEqual(code, 1)
        self.assertFalse(report['numerical_acceptance'])

    def test_source_conflict_rejected(self):
        name = 'source.py'
        with self.assertRaisesRegex(ValueError, 'identity conflict'):
            self.subject.merge_sources({name: 'wrong'}, {name: self.subject.sha(self.root / name)})

    def test_exact_commit_rejects_untracked_source_and_wrong_sha(self):
        sources = {'source.py': self.subject.sha(self.root / 'source.py')}
        with patch.object(self.subject.subprocess, 'check_output', return_value=b'other.py\0'), \
             patch.dict('os.environ', {'GITHUB_SHA': self.head}):
            with self.assertRaisesRegex(ValueError, 'absent from exact commit'):
                self.subject.verify_checkout(self.head, sources)
        with patch.dict('os.environ', {'GITHUB_SHA': 'f' * 40}):
            with self.assertRaisesRegex(ValueError, 'differs from GITHUB_SHA'):
                self.subject.verify_checkout(self.head, sources)

    def test_exact_commit_rejects_dirty_worktree(self):
        sources = {'source.py': self.subject.sha(self.root / 'source.py')}
        with patch.object(self.subject.subprocess, 'check_output', side_effect=[b'source.py\0', ' M source.py\n']), \
             patch.dict('os.environ', {'GITHUB_SHA': self.head}):
            with self.assertRaisesRegex(ValueError, 'clean tracked'):
                self.subject.verify_checkout(self.head, sources)

    def test_existing_evidence_rejected(self):
        self.args.output.mkdir()
        with self.assertRaisesRegex(ValueError, 'new output'):
            self.subject.run(self.args)

    def test_full128_and_external_reference_arguments_rejected(self):
        for option in ('--full128', '--reference', '--capture-manifest', '--expected-outputs'):
            with self.subTest(option=option), self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                self.subject.parser().parse_args(['--output', str(self.args.output), option])


if __name__ == '__main__':
    unittest.main()
