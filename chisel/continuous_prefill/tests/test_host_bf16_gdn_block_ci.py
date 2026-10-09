"""Full-block CI fail-closed profile tests, without models, compilers or DUT runs."""
from pathlib import Path
import contextlib
import copy
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import yaml
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_host_bf16_gdn_fresh_gate as gate
from host_bf16_gdn_execution import _build_identity


def reference(passed=True):
    checks = {}
    for name in ('input_norm', 'qkv', 'z', 'ab', 'conv', 'recurrent', 'norm', 'o', 'residual1',
                 'post_norm', 'gate', 'up', 'silu_mul', 'down', 'residual2', 'history'):
        maximum, mean = (.05, .01) if name == 'residual2' else (.03125, .005)
        checks[name] = dict(thresholds=dict(max_abs=maximum, mean_abs=mean), max_abs=0., mean_abs=0., **{'pass': True})
    checks['state'] = dict(atol=1e-4, rtol=1e-4, mismatches=0 if passed else 1, **{'pass': passed})
    return dict(schema_version=3, status='SOURCE_AUTHENTICATED_HOST_GDN_BLOCK_TWO_TOKEN_FIXTURE',
                scope=gate.BLOCK_FIXTURE_SCOPE, token_ids=[19, 92], tokens_per_launch=1,
                launches=2, commands_per_launch=17, heads=16, head_width=128,
                reference_head_jobs=138, reference_padded_fma_steps=43515904, actual_useful_dense_macs=43057152,
                canonical_acceptance='EXACT_BITS_EVERY_STAGE_AND_BOTH_STATES', native_core_gate_pass=None,
                full_block_supported=True, input_norm_dut=True, o_projection_dut=True, residual_dut=True,
                ffn_dut=True, rtl_executed=False, fault_restore_supported=False, generations=[0, 1, 2],
                layout=dict(actual_write_bytes=2388096,
                            launches=[dict(commands=17, descriptor_records=216) for _ in range(2)]),
                native_operator_gate_pass=True, frozen_operator_metrics=[dict(passed=True) for _ in range(2)],
                native_full_block_gate_pass=passed, native_full_block_status='PASS' if passed else 'FAIL',
                native_full_block_metrics=[dict(token=i, passed=passed, checks=copy.deepcopy(checks)) for i in range(2)],
                input_boundary='raw original hidden rows', native_gate_threshold_sources=['spec/numerical_contract.md'],
                reference_elapsed_seconds=0., max_rss_kib=1, tools={}, files={'hidden.bf16le': {'sha256': '3'*64}},
                source_payload_manifest_sha256={'payload': '6'*64})


def result(report, ready):
    passed = report['native_full_block_gate_pass']
    return dict(status='PASS_PRODUCTION_HOST_GDN_BLOCK' if passed else 'FAIL_PRODUCTION_HOST_GDN_BLOCK_NATIVE_ACCEPTANCE',
                scope=gate.BLOCK_FIXTURE_SCOPE, canonical_block_pass=True, canonical_core_pass=True,
                actual_dut_identity_verified=True, source_immutability_verified=True,
                actual_useful_dense_macs=43057152, actual_ack_history_state_carry=True,
                native_operator_gate_pass=report['native_operator_gate_pass'], native_core_gate_pass=None,
                native_full_block_gate_pass=passed, native_full_block_status=report['native_full_block_status'],
                native_full_block_metrics=report['native_full_block_metrics'],
                frozen_operator_metrics=report['frozen_operator_metrics'], overall_pass=passed,
                full_block_supported=True, fault_restore_supported=False, input_norm_dut=True,
                o_projection_dut=True, residual_dut=True, ffn_dut=True,
                binary_sha256=ready['binary_sha256'], rtl_sha256=ready['rtl_sha256'], log_sha256='7'*64,
                runs=[dict(token=i, committed_generation=i+1, canonical_bit_mismatches=0,
                           commands=[{}]*17, write_ack_bytes=1194048, ddr_after_sha256=str(i+4)*64) for i in range(2)])


class BlockOrchestrationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name); (self.root/'work').mkdir()
        self.args = gate.parser().parse_args(['run', '--profile', 'block', '--output', str(self.root/'work/out'),
            '--archive', str(self.root/'archive.tar.gz'), '--expected-sha256', 'a'*64,
            '--expected-commit', 'b'*40, '--mode', 'pass', '--timeout-seconds', '18000'])
        self.ready = dict(binary_sha256='1'*64, rtl_sha256='2'*64)
        self.report = reference(); self.result = result(self.report, self.ready)
        self.sources = {'source.py': '8'*64}; self.events = []; self.invocations = 0
        self.session = types.SimpleNamespace(verify=self.verify)

    def verify(self, fixture):
        self.events.append('verify_live'); return self.report

    def generate(self, fixture):
        self.events.append('fresh_block'); fixture.mkdir(); (fixture/'manifest.json').write_text('{}')
        return self.session

    def unpack(self, archive, digest, commit, build, *, profile):
        self.assertEqual(profile, 'block'); self.events.append('transfer_block')
        build.mkdir(); (build/'build_ready.json').write_text('{}'); return dict(sources=self.sources)

    def admit(self, build, commit, *, profile):
        self.assertEqual(profile, 'block'); self.events.append('admit_block')
        return self.ready, self.sources, {}

    def execute(self, build, fixture, *, session, source_root, timeout_seconds):
        self.assertIs(session, self.session); self.assertEqual(source_root, self.root)
        self.assertEqual(timeout_seconds, 18000); self.events.append('same_dut_block')
        return self.result

    def invoke(self):
        import pack_host_bf16_gdn_block_fixture as fixture
        import host_bf16_gdn_block_execution as execution
        self.args.output = self.root/'work'/('out'+str(self.invocations)); self.invocations += 1
        self.events.clear()
        with contextlib.ExitStack() as stack:
            for name, value in dict(ROOT=self.root, source_closure=lambda **kwargs: self.sources,
                                   verify_checkout=lambda *args: None, unpack=self.unpack,
                                   build_admission=self.admit, runtime_identity=lambda path: {}).items():
                stack.enter_context(patch.object(gate, name, value))
            for name in ('generate_fixture', 'authenticate_fixture', 'run_case'):
                stack.enter_context(patch.object(gate, name, side_effect=AssertionError('v1 called for block')))
            stack.enter_context(patch.object(fixture, 'generate_fixture', self.generate))
            stack.enter_context(patch.object(execution, 'run_case', self.execute))
            stack.enter_context(patch.dict(os.environ, {'HF_HUB_OFFLINE': '1'}))
            return gate.run(self.args)

    def test_full_chain_uses_live_session_once_and_compact_receipts_only(self):
        summary, code = self.invoke()
        self.assertEqual(code, 0)
        self.assertEqual(self.events, ['transfer_block', 'admit_block', 'fresh_block', 'verify_live',
                                      'same_dut_block', 'verify_live', 'admit_block'])
        self.assertEqual(summary['status'], 'PASS_PRODUCTION_HOST_GDN_BLOCK')
        self.assertTrue(summary['canonical_block_pass']); self.assertTrue(summary['numerical_acceptance'])
        self.assertTrue(summary['native_full_block_gate_pass']); self.assertTrue(summary['overall_pass'])
        self.assertEqual(summary['pending_gates'], list(gate.BLOCK_PENDING_GATES))
        self.assertEqual({p.name for p in (self.args.output/'compact').iterdir()}, gate.COMPACT_FILES)

    def test_native_failure_preserves_verified_canonical_result_but_fails_ci(self):
        self.report = reference(False); self.result = result(self.report, self.ready)
        summary, code = self.invoke()
        self.assertEqual(code, 1)
        self.assertEqual(summary['status'], 'FAIL_PRODUCTION_HOST_GDN_BLOCK_NATIVE_ACCEPTANCE')
        self.assertEqual(summary['stage'], 'complete'); self.assertTrue(summary['canonical_block_pass'])
        self.assertTrue(summary['actual_dut_identity_verified']); self.assertFalse(summary['overall_pass'])
        self.assertFalse(summary['numerical_acceptance']); self.assertFalse(summary['native_full_block_gate_pass'])
        self.assertEqual(summary['native_full_block_metrics'], self.report['native_full_block_metrics'])
        saved = gate.read_json(self.args.output/'compact/summary.json')
        self.assertTrue(saved['canonical_block_pass']); self.assertFalse(saved['overall_pass'])

    def test_frozen_dense_operator_failure_also_runs_canonical_chain_and_fails_ci(self):
        self.report['frozen_operator_metrics'][0]['passed'] = False
        self.report.update(native_operator_gate_pass=False, native_full_block_gate_pass=False, native_full_block_status='FAIL')
        self.result = result(self.report, self.ready)
        summary, code = self.invoke()
        self.assertEqual(code, 1); self.assertIn('same_dut_block', self.events)
        self.assertTrue(summary['canonical_block_pass']); self.assertFalse(summary['native_operator_gate_pass'])

    def test_modes_and_time_budgets_fail_before_transfer_or_model(self):
        for mode, budget in [(m, 18000) for m in gate.CI_MODES[1:]] + [('pass', 18001), ('pass', 0)]:
            self.args.mode, self.args.timeout_seconds = mode, budget
            with self.subTest(mode=mode, budget=budget):
                summary, code = self.invoke(); self.assertEqual(code, 1); self.assertFalse(self.events)
                self.assertFalse(summary['canonical_block_pass'])

    def test_reference_counts_scope_thresholds_and_false_green_rejected_before_dut(self):
        original = copy.deepcopy(self.report)
        changes = [lambda r: r.update(commands_per_launch=8), lambda r: r.update(reference_head_jobs=66),
                   lambda r: r.update(actual_useful_dense_macs=16842752), lambda r: r.update(full_block_supported=False),
                   lambda r: r['layout'].update(actual_write_bytes=0),
                   lambda r: r['layout']['launches'][0].update(descriptor_records=215),
                   lambda r: r['native_full_block_metrics'][0]['checks']['residual2']['thresholds'].update(max_abs=.1),
                   lambda r: r['native_full_block_metrics'][0]['checks']['state'].update(atol=.01),
                   lambda r: r['native_full_block_metrics'][0]['checks']['state'].update(mismatches=1)]
        for change in changes:
            self.report = copy.deepcopy(original); change(self.report)
            summary, code = self.invoke(); self.assertEqual(code, 1); self.assertNotIn('same_dut_block', self.events)
            self.assertFalse(summary['canonical_block_pass'])

    def test_artifact_only_cross_profile_incomplete_and_forged_pass_fail(self):
        original = copy.deepcopy(self.result)
        changes = [lambda r: r.update(status='PASS_HOST_GDN_BLOCK_ARTIFACT_CHECK_ONLY'),
                   lambda r: r.update(scope=gate.CORE_SCOPE), lambda r: r.update(binary_sha256='0'*64),
                   lambda r: r.update(source_immutability_verified=False),
                   lambda r: r.update(actual_ack_history_state_carry=False),
                   lambda r: r.update(native_full_block_gate_pass=False), lambda r: r.update(overall_pass=False),
                   lambda r: r.update(runs=r['runs'][:1]), lambda r: r['runs'][1].update(committed_generation=1),
                   lambda r: r['runs'][0].update(commands=[{}]*8), lambda r: r['runs'][0].update(write_ack_bytes=0)]
        for change in changes:
            self.result = copy.deepcopy(original); change(self.result)
            summary, code = self.invoke(); self.assertEqual(code, 1)
            self.assertFalse(summary['canonical_block_pass']); self.assertFalse(summary['numerical_acceptance'])

    def test_timeout_and_final_identity_failure_revoke_all_acceptance(self):
        original = self.execute
        def timeout(*args, **kwargs): raise subprocess.TimeoutExpired('actual-block', 18000)
        self.execute = timeout
        summary, code = self.invoke(); self.assertEqual(code, 1)
        self.assertEqual(summary['status'], 'PENDING_INCOMPLETE_PRODUCTION_HOST_GDN_BLOCK')
        self.assertEqual(summary['stage'], 'actual_host_block_cold_carried')
        self.execute = original; admit = self.admit
        def changed(build, commit, *, profile):
            if 'same_dut_block' in self.events: raise ValueError('final source drift')
            return admit(build, commit, profile=profile)
        self.admit = changed
        summary, code = self.invoke(); self.assertEqual(code, 1)
        self.assertFalse(summary['canonical_block_pass']); self.assertFalse(summary['overall_pass'])


class BlockProfileTests(unittest.TestCase):
    def test_emitted_scope_requires_full_v3_geometry_and_false_numerical_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); build = root/'build'; (build/'generated').mkdir(parents=True)
            commit = 'a'*40; hf = root/'hardfloat'
            actual = dict(actual_elf=dict(kind='ELF', sha256='b'*64, version='Verilator 5.032'),
                          entrypoint=dict(sha256='c'*64))
            ready = dict(source_base_commit=commit, initial_verilation_exit=0, source_snapshot_manifest_sha256=None,
                         hardfloat_source=str(hf), actual_verilator=actual)
            scope = dict(experimental_bf16_gdn=True, experimental_gdn_core=True, experimental_gdn_block=True,
                default_enabled=False, scope=gate.BLOCK_SCOPE, policy_version=3, hidden=1024, ffn=3584,
                gdn_channels=6144, conv_kernel=4, max_tokens=1, heads=16, head_dim=128,
                managed_state_contexts=1, scalar_service_shared=True, softplus_enabled=True,
                recurrent_state_dtype='FP32', input_norm_dut=True, output_projection_supported=True,
                residual_supported=True, ffn_supported=True, full_block_supported=True,
                numerical_acceptance=False, burst_writes=False, logical_matrix_engines=1,
                physical_matrix_slices=8, pinned_idma_instances=1, timing_signoff=False)
            toolchain = dict(compiler_jars_verified_after_build=True, compiler_jars_sha256={},
                             hardfloat_source_sha256={}, idma_identity={},
                             tools=dict(verilator_backend=dict(version='Verilator 5.032', sha256='c'*64),
                                        firtool=dict(version='1.62.1')))
            for name, value in {'build_ready.json':ready, 'generated/SCOPE.json':scope,
                'source_scope.json':dict(scope='full', unrelated_helpers_bound=True), 'toolchain.json':toolchain,
                'compiler_jars.sha256.json':{}, 'hardfloat.sha256.json':{}, 'idma_identity.json':{},
                'actual_verilator_before.json':actual, 'actual_verilator_after.json':actual}.items():
                gate.save(build/name, value)
            (build/'build.exit').write_text('0'); (build/'source_base_commit.txt').write_text(commit)
            with contextlib.ExitStack() as stack:
                for name in ('_build_identity','validate_maps','verify_checkout','verify_all_build_sources'):
                    stack.enter_context(patch.object(gate, name, return_value={}))
                stack.enter_context(patch.object(gate, 'source_closure', return_value={'source.py':'d'*64}))
                stack.enter_context(patch.dict(os.environ, {'HARDFLOAT_SOURCE':str(hf)}))
                gate.build_admission(build, commit, profile='block')
                for key, value in [('policy_version',2), ('experimental_gdn_block',False), ('ffn',1024),
                    ('full_block_supported',False), ('max_tokens',True), ('numerical_acceptance',True),
                    ('residual_supported',False), ('recurrent_state_dtype','BF16'), ('physical_matrix_slices',1)]:
                    gate.save(build/'generated/SCOPE.json', dict(scope, **{key:value}))
                    with self.assertRaisesRegex(ValueError, 'build profile'):
                        gate.build_admission(build, commit, profile='block')

    def test_build_failures_keep_bounded_emit_log_and_exact_phase_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root/'work').mkdir()
            args = gate.parser().parse_args(['build','--profile','block','--output',str(root/'work/out')])
            def build(command, **kwargs):
                self.assertEqual(command[-1], 'block'); self.assertEqual(kwargs['timeout'], 6300)
                out = Path(command[-3]); out.mkdir()
                (out/'build_phase.txt').write_text('rtl_emit\n')
                (out/'scala_compile.exit').write_text('0\n'); (out/'rtl_emit.exit').write_text('137\n')
                (out/'build.exit').write_text('137\n'); (out/'emit.log').write_text('terminated by signal\n')
                raise subprocess.CalledProcessError(137, command)
            with patch.object(gate,'ROOT',root), patch.object(gate,'git_commit',return_value='a'*40), \
                 patch.object(gate,'source_closure',return_value={'source.py':'b'*64}), \
                 patch.object(gate,'verify_checkout'), patch.object(gate.subprocess,'run',side_effect=build), \
                 patch.dict(os.environ, {'BUILD_JOBS':'1'}):
                summary, code = gate.run(args)
            self.assertEqual(code,1); self.assertFalse(summary['canonical_block_pass'])
            self.assertFalse(summary['numerical_acceptance']); self.assertEqual(summary['last_build_phase'],'rtl_emit')
            self.assertEqual(summary['build_phase_exits'], dict(scala_compile=0,rtl_emit=137,build=137))
            self.assertIn('host_build/emit.log', summary['diagnostic_log_tail'])
            self.assertEqual({p.name for p in (args.output/'compact').iterdir()}, gate.COMPACT_FILES)

    def test_build_identity_is_explicit_and_cannot_cross_accept(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('obj/VHostBlockTop', 'generated/HostBlockTop.sv', 'sources.sha256.json', 'hardfloat.sha256.json'):
                path = root/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text('test '+name)
            ready = dict(status=gate.BLOCK_BUILD_STATUS, numerical_pass=False, build_profile='block',
                experimental_default_off=True, operations=['input_norm', 'dense_qkv', 'dense_z', 'dense_ab',
                'conv4_silu', 'input_prep', 'recurrent_fp32', 'gated_norm', 'dense_o', 'residual1', 'post_norm',
                'dense_gate', 'dense_up', 'silu_mul', 'dense_down', 'residual2', 'state_fence'],
                full_block_supported=True, scalar_service_shared=True, recurrent_state_supported=True,
                gated_norm_supported=True, input_norm_dut=True, o_projection_dut=True, residual_dut=True, ffn_dut=True,
                binary_sha256=gate.sha(root/'obj/VHostBlockTop'), rtl_sha256=gate.sha(root/'generated/HostBlockTop.sv'),
                source_manifest_sha256=gate.sha(root/'sources.sha256.json'))
            gate.save(root/'build_ready.json', ready)
            self.assertEqual(len(_build_identity(root, profile='block')), 5)
            for receiver in ('dense-conv', 'core'):
                with self.assertRaises(ValueError): _build_identity(root, profile=receiver)
            for key, value in [('full_block_supported', False), ('ffn_dut', False), ('numerical_pass', True),
                               ('build_profile', 'core'), ('operations', ready['operations'][:-1])]:
                gate.save(root/'build_ready.json', dict(ready, **{key: value}))
                with self.assertRaises(ValueError): _build_identity(root, profile='block')

    def test_source_closure_binds_c_include_both_drivers_and_all_block_helpers(self):
        sources = gate.source_closure(profile='block')
        expected = {gate.BLOCK_WORKFLOW, 'scripts/matrix_norm_rope_reference.c'}
        expected.update('chisel/continuous_prefill/'+name for name in (
            'scripts/gdn_dense_reference.c', 'scripts/gdn_dense_reference.py', 'scripts/gdn_rmsnorm_reference.py',
            'scripts/gdn_elementwise_reference.py', 'scripts/host_bf16_qkv_reference.py',
            'scripts/host_bf16_gdn_block_execution.py', 'scripts/pack_host_bf16_gdn_block_fixture.py',
            'scripts/host_bf16_gdn_block_descriptor.py', 'scripts/host_bf16_gdn_core_execution.py',
            'tests/host_bf16_gdn_block.cpp', 'tests/host_bf16_gdn_core.cpp',
            'config/host_bf16_gdn_block_descriptor_contract.json'))
        self.assertTrue(expected <= set(sources)); self.assertNotIn(gate.CORE_WORKFLOW, sources)
        self.assertEqual(gate.parser().parse_args(['build','--output','unused']).profile, 'dense-conv')

    def test_packages_require_receiver_profile_and_never_transfer_fixtures(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); build = root/'build'
            for name in gate.FILES:
                path = build/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text('test '+name)
            ready = dict(binary_sha256=gate.sha(build/'obj/VHostBlockTop'), rtl_sha256=gate.sha(build/'generated/HostBlockTop.sv'))
            for profile in gate.PROFILES:
                with patch.object(gate, 'build_admission', return_value=(ready, {'source.py':'a'*64}, {})):
                    archive = root/(profile+'.tar.gz'); digest, manifest = gate.package(build, archive, 'b'*40, profile=profile)
                self.assertFalse(manifest['numerical_pass']); self.assertEqual(set(manifest['files']), gate.FILES)
                for receiver in gate.PROFILES:
                    if receiver != profile:
                        with self.assertRaisesRegex(ValueError, 'receiver-selected'):
                            gate.validate_archive(archive, digest, 'b'*40, profile=receiver)

    def test_workflow_runs_one_complete_case_and_only_uploads_compact_receipts(self):
        workflow = yaml.load((gate.ROOT/gate.BLOCK_WORKFLOW).read_text(), Loader=yaml.BaseLoader)
        jobs = workflow['jobs']; self.assertEqual(set(jobs), {'build','block-canonical-native-pass','block-acceptance'})
        self.assertEqual(jobs['build']['timeout-minutes'], '120')
        self.assertEqual(jobs['block-canonical-native-pass']['timeout-minutes'], '340')
        self.assertEqual(jobs['block-acceptance']['needs'], ['build','block-canonical-native-pass'])
        self.assertEqual(jobs['block-acceptance']['if'], 'always()')
        self.assertEqual(workflow['concurrency']['cancel-in-progress'], 'false')
        commands = '\n'.join(step.get('run','') for job in jobs.values() for step in job['steps'])
        self.assertEqual(commands.count('run_host_bf16_gdn_fresh_gate.py run'), 1)
        for required in ('build --profile block', 'run --profile block', '--mode pass --timeout-seconds 18000',
                         'HostBlockCommandsGdnBlockSpec', 'HostBlockCommandsGdnCoreSpec', 'HostBlockCommandsGdnSpec',
                         'torch==2.10.0', 'numpy==2.3.5', '14e738b5d0cc69aa27a95dde272aea41fde44f2f'):
            self.assertIn(required, commands)
        for forbidden in ('collect_qwen35_layer3_payload', 'full128', '--mode reset-recovery', '--mode last-history-ack-error'):
            self.assertNotIn(forbidden, commands)
        for job in jobs.values():
            self.assertLessEqual(int(job['timeout-minutes']), 360)
            for step in job['steps']:
                if step.get('uses') == 'actions/checkout@v4': self.assertEqual(step['with']['ref'], '${{ github.sha }}')
                if step.get('uses') == 'actions/upload-artifact@v4':
                    self.assertTrue(all(p.endswith(('/host_gdn_build.tar.gz', '/compact/summary.json',
                        '/compact/source_input_hashes.json')) for p in step['with']['path'].splitlines()))


if __name__ == '__main__': unittest.main()
