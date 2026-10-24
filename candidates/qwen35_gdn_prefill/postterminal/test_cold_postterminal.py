"""Synthetic stdlib-only admission/mapping tests. No model/runtime/tensor imports."""
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock
HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[2]
FULL_DRIVER_SHA = '5' * 64
spec = importlib.util.spec_from_file_location('synthetic_cold_postterminal', HERE / 'cold_postterminal.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)

_audit_enabled = False

def deny_heavy(event, args):
    if not _audit_enabled:
        return
    if event == 'import' and args[0].split('.')[0] in ('numpy', 'torch', 'transformers', 'candidates', 'heteronpu'):
        raise RuntimeError('synthetic tests deny model/native imports')
    if event.startswith(('subprocess.', 'socket.')) or event in ('os.system', 'os.kill', 'os.killpg', 'os.fork', 'os.forkpty', 'os.exec', 'os.posix_spawn', 'os.posix_spawnp', 'ctypes.dlopen'):
        raise RuntimeError('synthetic tests deny process/native actions')
# Audit hooks cannot be removed. Keep this one inactive outside this module's
# unittest lifecycle, so later suites can launch their isolated smoke child.
sys.addaudithook(deny_heavy)

def setUpModule():
    global _audit_enabled
    _audit_enabled = True

def tearDownModule():
    global _audit_enabled
    _audit_enabled = False

WIDTHS = dict(input_norm=1024, qkv=6144, z=2048, ab=32, conv_silu=6144, conv_before_silu=6144, prep=6400, chunk=2048, gated_norm=2048, o=1024, attention_residual=1024, post_norm=1024, gate=3584, up=3584, silu_mul=3584, down=1024, output=1024)

def extent(role, rows):
    if role == 'history_staging':
        return 6144 * 4 * 2
    if role == 'state_staging':
        return 16 * 128 * 128 * 4
    return rows * WIDTHS[role] * (4 if role == 'prep' else 2)

def name(phase, role):
    return phase + '.' + role + '.actual.' + ('fp32le' if role in ('prep', 'state_staging') else 'bf16le')
FC = types.SimpleNamespace(ORDER=c.ORDER, ROLES=c.ROLES, PHASES=('cold128', 'carried128'), filename=name, byte_extent=extent)

def synthetic():
    hashes = {role: c.sha(('SYNTHETIC ONLY ' + role).encode()) for role in c.ROLES}
    identity = dict(rows=128, source_sha256={'candidates/qwen35_gdn_prefill/full_driver.py': FULL_DRIVER_SHA}, identity_file_sha256={'synthetic': '1' * 64}, input_sha256={'cold128': '2' * 64, 'carried128': '3' * 64}, authenticated_input_sha256={'synthetic': '4' * 64}, parameter_sha256={'synthetic': '5' * 64})
    identity.update({right: 'SYNTHETIC POLICY ' + right for _, right in c.POLICY_PAIRS})
    commands = []
    for i, role in enumerate(c.ORDER):
        commands.append(dict(phase='cold128', role=role, owner_tag=i + 1, complete=True, terminal_accepted=True, status=None, terminal_status=None, block_generation=int(i == 15), block_committed=i == 15, output_sha256=hashes[role], output_published=True))
    commands[4].update(staging_complete=True, history_staging_sha256=hashes['history_staging'], cold_history_initialization='internal_bf16_positive_zero', history_input_consumed=False, history_committed=False, generation_advanced=False, conv_before_silu_observation=dict(complete=True, output_sha256=hashes['conv_before_silu'], observed=128 * 6144, expected=128 * 6144, source='actual_ConvOwner_readonly_node_callback', numerical_replacement=False))
    commands[6].update(staging_complete=True, state_sha256=hashes['state_staging'], state_committed=False, history_committed=False, generation_advanced=False)
    roots = dict(generation=1, history=64, state=128, output=192, history_sha256=hashes['history_staging'], state_sha256=hashes['state_staging'])
    summary = dict(scope='QWEN35_L0_COMPLETE_TYPED_SOFTWARE_COORDINATOR', identity=identity, status='FAILED', full_block_executed=True, native_acceptance=False, source_initialization='raw_inputs_and_parameters_only_before_launch', carried_dependency='preceding_actual_committed_history_and_fp32_state', commands=commands, terminal_count=16, final_identity=dict({key: True for key in c.FINAL_REQUIRED}, identity_read_errors={}), output_files={name('cold128', k): dict(bytes=extent(k, 128), sha256=v) for k, v in hashes.items()}, roots=roots, response=dict(phase='carried128', status='Aborted', generation=1, output=None, history=64, state=128), window_inputs=[dict(phase='cold128', cold=True, expected_generation=0, history_sha256=None, state_sha256=None), dict(phase='carried128', cold=False, expected_generation=1, history_sha256=hashes['history_staging'], state_sha256=hashes['state_staging'])])
    summary.update({left: identity[right] for left, right in c.POLICY_PAIRS})
    return (summary, identity)

def progress_from(summary):
    return {k: copy.deepcopy(v) for k, v in summary.items() if k not in ('identity', 'status', 'terminal_count', 'final_identity', 'output_files')}

class Admission(unittest.TestCase):

    def setUp(self):
        self.summary, self.identity = synthetic()

    def admit(self):
        return c.admit_cold_metadata(self.summary, self.identity, FC, full_driver_sha256=FULL_DRIVER_SHA)

    def test_genuine_synthetic_summary(self):
        self.assertEqual(set(self.admit()), set(c.ROLES))

    def test_genuine_synthetic_progress(self):
        progress = progress_from(self.summary)
        self.assertEqual(set(c.admit_cold_metadata(progress, self.identity, FC, evidence_kind='progress', full_driver_sha256=FULL_DRIVER_SHA)), set(c.ROLES))
        self.assertNotIn('output_files', progress)
        self.assertNotIn('final_identity', progress)

    def test_every_policy_is_bound(self):
        for left, _ in c.POLICY_PAIRS:
            with self.subTest(left=left):
                changed = copy.deepcopy(self.summary)
                changed[left] = 'different'
                with self.assertRaises(ValueError):
                    c.admit_cold_metadata(changed, self.identity, FC, full_driver_sha256=FULL_DRIVER_SHA)

    def test_negative_mutations(self):
        mutations = {'missing16': lambda s: s['commands'].pop(), 'reordered': lambda s: s['commands'].reverse(), 'missing_accept': lambda s: s['commands'][0].pop('terminal_accepted'), 'failed_cold': lambda s: s['commands'][0].update(status='Failed'), 'wrong_tag': lambda s: s['commands'][1].update(owner_tag=9), 'boolean_tag': lambda s: s['commands'][0].update(owner_tag=True), 'early_commit': lambda s: s['commands'][1].update(block_committed=True), 'no_joint_commit': lambda s: s['commands'][15].update(block_committed=False), 'output_unpublished': lambda s: s['commands'][15].update(output_published=False), 'contradicting_owner': lambda s: s['commands'][4].update(owner={'status': 'Failed'}), 'numeric_fault': lambda s: s['commands'][1].update(numeric_fault='error'), 'window_bool_mismatch': lambda s: s['window_inputs'][0].update(cold=1), 'window_generation_bool': lambda s: s['window_inputs'][0].update(expected_generation=False), 'gen2': lambda s: s['roots'].update(generation=2), 'null_root': lambda s: s['roots'].update(output=0), 'alias_root': lambda s: s['roots'].update(output=64), 'root_unaligned': lambda s: s['roots'].update(output=193), 'root_bad_hash': lambda s: s['roots'].update(state_sha256='0' * 64), 'response_bad_pointer': lambda s: s['response'].update(history=999), 'response_fake_output': lambda s: s['response'].update(output=192), 'missing_carried_binding': lambda s: s['window_inputs'].pop(), 'bad_carried_binding': lambda s: s['window_inputs'][1].update(state_sha256='0' * 64), 'missing19': lambda s: s['output_files'].pop(name('cold128', 'conv_before_silu')), 'extra_cold_file': lambda s: s['output_files'].update({'cold128.fake.actual.bf16le': {}}), 'bad_extent': lambda s: s['output_files'][name('cold128', 'qkv')].update(bytes=64), 'bad_tensor_hash': lambda s: s['output_files'][name('cold128', 'qkv')].update(sha256='0' * 64), 'missing_staging': lambda s: s['commands'][4].update(staging_complete=False), 'missing_observation': lambda s: s['commands'][4].pop('conv_before_silu_observation'), 'partial_observation': lambda s: s['commands'][4]['conv_before_silu_observation'].update(observed=3), 'numeric_replacement': lambda s: s['commands'][4]['conv_before_silu_observation'].update(numerical_replacement=True), 'chunk_private_commit': lambda s: s['commands'][6].update(state_committed=True), 'unsealed_final': lambda s: s.pop('final_identity'), 'final_error': lambda s: s['final_identity'].update(identity_read_errors={'source': 'failed'}), 'final_false': lambda s: s['final_identity'].update(source_unchanged=False), 'RUNNING': lambda s: s.update(status='RUNNING'), 'COMPLETE': lambda s: s.update(status='ACTUAL_COMPLETE_UNCOMPARED'), 'native_acceptance': lambda s: s.update(native_acceptance=True), 'top_level_source_changed': lambda s: s.update(source_unchanged=False), 'top_level_fixture_changed': lambda s: s.update(fixture_unchanged=False), 'top_level_library_changed': lambda s: s.update(library_unchanged=False), 'top_level_vector_changed': lambda s: s.update(vector_library_unchanged=False), 'report_error': lambda s: s.update(report_error={'type': 'Error'})}
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                changed = copy.deepcopy(self.summary)
                mutate(changed)
                with self.assertRaises(ValueError):
                    c.admit_cold_metadata(changed, changed['identity'], FC, full_driver_sha256=FULL_DRIVER_SHA)

    def test_missing_receipt_hash_in_progress(self):
        progress = progress_from(self.summary)
        progress['commands'][6].pop('state_sha256')
        with self.assertRaisesRegex(ValueError, '19 genuine'):
            c.admit_cold_metadata(progress, self.identity, FC, evidence_kind='progress', full_driver_sha256=FULL_DRIVER_SHA)

    def test_original_comparison_phases_not_mutated(self):
        fake = copy.copy(FC)
        fake.PHASES = ('cold128',)
        with self.assertRaisesRegex(ValueError, 'inventory'):
            c.admit_cold_metadata(self.summary, self.identity, fake, full_driver_sha256=FULL_DRIVER_SHA)

    def test_original_failed_summary_companion(self):
        c.check_companion_summary(self.summary, progress_from(self.summary), self.identity, FC, full_driver_sha256=FULL_DRIVER_SHA)

    def test_integrity_failure_not_hidden_by_progress(self):
        progress = progress_from(self.summary)
        self.summary['final_identity']['source_unchanged'] = False
        with self.assertRaises(ValueError):
            c.check_companion_summary(self.summary, progress, self.identity, FC, full_driver_sha256=FULL_DRIVER_SHA)

    def test_root_contradiction_not_hidden(self):
        progress = progress_from(self.summary)
        progress['roots']['output'] = 256
        with self.assertRaisesRegex(ValueError, 'contradict'):
            c.check_companion_summary(self.summary, progress, self.identity, FC, full_driver_sha256=FULL_DRIVER_SHA)

    def test_original_running_placeholder_not_a_completion_seal(self):
        companion = dict(scope=self.summary['scope'], status='RUNNING', rows=128, public_command128_executed=False, rtl_executed=False)
        c.check_companion_summary(companion, progress_from(self.summary), self.identity, FC, full_driver_sha256=FULL_DRIVER_SHA)
        companion['final_identity'] = {'source_unchanged': False}
        with self.assertRaises(ValueError):
            c.check_companion_summary(companion, progress_from(self.summary), self.identity, FC, full_driver_sha256=FULL_DRIVER_SHA)

    def test_gate_failure_precedes_any_path_access_or_reference_import(self):
        with mock.patch.object(c, '_admit_gate', side_effect=ValueError('gate closed')), mock.patch.object(Path, 'read_bytes', side_effect=AssertionError('read before gate')), mock.patch.object(Path, 'exists', side_effect=AssertionError('stat before gate')), mock.patch.object(c.importlib, 'import_module', side_effect=AssertionError('import before gate')):
            with self.assertRaisesRegex(ValueError, 'gate closed'):
                c.run_diagnostic('NO_REAL_PATH', '0' * 64, 'NO_OUTPUT', config_path='NO_CONFIG', reviewed_config_sha='1' * 64, reviewed_code_sha='2' * 64)

    def test_local_gate_module_origin_and_code_pins_are_checked(self):
        pins = c.check_code(HERE / 'CODE_PINS.json', c.sha((HERE / 'CODE_PINS.json').read_bytes()))
        module = c._load_gate(pins)
        self.assertEqual(Path(module.__file__), HERE / 'terminal_gate.py')
        self.assertEqual(module.admit_terminal_manifest.__code__.co_filename, str(HERE / 'terminal_gate.py'))
        pins['terminal_gate.py']['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'source/origin mismatch'):
            c._load_gate(pins)

    def test_local_gate_does_not_use_poisoned_import_cache(self):
        fake = types.SimpleNamespace(__file__=str(HERE / 'terminal_gate.py'), admit_terminal_manifest=lambda: None)
        with mock.patch.dict(sys.modules, terminal_gate=fake):
            module = c._local_terminal_gate(c.sha((HERE / 'CODE_PINS.json').read_bytes()))
            self.assertIsNot(module, fake)

    def test_unknown_status_is_not_upgraded(self):
        self.assertIn("('FAILED', 'INCOMPLETE', 'UNKNOWN')", (HERE / 'cold_postterminal.py').read_text())

class FrozenPlanPins(unittest.TestCase):

    def test_streamed_plan_pins_and_original_compiler_alias_semantics(self):
        with tempfile.TemporaryDirectory(prefix='synthetic_cold_pin_') as directory:
            target = Path(directory) / 'target'
            target.write_bytes(b'SYNTHETIC FILE ONLY')
            alias = Path(directory) / 'alias'
            alias.symlink_to(target)
            record = dict(bytes=target.stat().st_size, sha256=c.sha(target.read_bytes()), resolved=str(target))
            plan = {'inputs': {str(alias): record}}
            c.verify_plan_inputs(plan)
            target.write_bytes(b'CHANGED SYNTHETIC')
            with self.assertRaises(ValueError):
                c.verify_plan_inputs(plan)

    def test_plan_policy_cannot_be_changed_to_another_supported_policy(self):
        identity = dict(rows=128, rms_policy='synthetic', projection_policy='synthetic', vector_exception_policy='synthetic', vector_fatal_mask=28, chunk_exp_policy='synthetic', chunk_cumsum_policy='synthetic', chunk_matmul_policy='synthetic', vector_arithmetic_backend={'backend': 'synthetic'})
        policy = {k: v for k, v in identity.items() if k != 'vector_arithmetic_backend'}
        policy['vector_backend'] = 'synthetic'
        c.bind_plan_policy(identity, {'policy': policy})
        identity['chunk_exp_policy'] = 'other supported policy'
        with self.assertRaises(ValueError):
            c.bind_plan_policy(identity, {'policy': policy})

class OriginalHelpers(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        raw = (REPOSITORY / 'candidates/qwen35_gdn_prefill/full_compare.py').read_bytes()
        assert c.sha(raw) == c.FULL_COMPARE_SHA
        cls.tree = ast.parse(raw)
        funcs = [node for node in cls.tree.body if isinstance(node, ast.FunctionDef) and node.name in ('bf16_metric', 'assigned_pass')]
        ns = {'ORDER': c.ORDER, 'MAX_ABS': 0.03125, 'MEAN_ABS': 0.005, 'require': c.need}
        exec(compile(ast.Module(body=funcs, type_ignores=[]), 'UNCHANGED_SOURCE_AST', 'exec'), ns)
        cls.ns = ns

    def test_exact_node_output_and_ulp_threshold_boundaries(self):
        for gate, ma, mean, ulp, passed in [('node', 0.03125, 0.005, 0, True), ('node', 0.03125001, 0.005, 0, False), ('node', 0.03125, 0.00500001, 0, False), ('output', 0.05, 0.01, 0, True), ('output', 0.050001, 0.01, 0, False), ('output', 0.05, 0.010001, 0, False), ('ulp', 100.0, 100.0, 1, True), ('ulp', 0.0, 0.0, 2, False)]:
            with self.subTest(gate=gate, ma=ma, mean=mean, ulp=ulp):
                self.ns['compare_finite_bf16'] = lambda a, b: dict(max_abs=ma, mean_abs=mean, max_bf16_ulp=ulp, expected_sha256='0' * 64)
                result = self.ns['bf16_metric'](b'a', b'b', gate=gate)
                self.assertIs(result['passed'], passed)

    def test_fp32_state_thresholds_source_unchanged(self):
        function = next((n for n in self.tree.body if isinstance(n, ast.FunctionDef) and n.name == 'state_metric'))
        call = next((n for n in ast.walk(function) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and (n.func.id == 'compare_state')))
        self.assertEqual({k.arg: ast.literal_eval(k.value) for k in call.keywords}, {'atol': 0.0001, 'rtol': 0.0001})

    def test_default_mapping_calls_only_original_cold_helpers(self):
        calls = []

        def metric(a, b, gate='node'):
            calls.append(('bf16', gate))
            return dict(passed=True, status='PASS')
        fake = types.SimpleNamespace(native_role=lambda t, case, role, rows: calls.append(('map', case, role, rows)) or b'expected', bf16_metric=metric, state_metric=lambda a, b: calls.append(('state',)) or dict(passed=True, status='PASS'), prep_diagnostic=lambda a, t, case, rows: calls.append(('prep', case, rows)) or dict(passed=None, thresholds=None), assigned_pass=self.ns['assigned_pass'], MissingNode=ValueError, captured_conv_reference=lambda *a, **k: self.fail('unselected Conv arithmetic'))
        result = c.cold_metrics(fake, {k: b'SYNTHETIC' for k in c.ROLES}, None, {}, include_conv=False, root=REPOSITORY)
        self.assertEqual(len([r for r in calls if r[0] == 'map']), 17)
        self.assertTrue(all((r[1] == 'cold128' and r[3] == 128 for r in calls if r[0] == 'map')))
        self.assertEqual([r for r in calls if r[0] == 'bf16'].count(('bf16', 'output')), 1)
        self.assertEqual([r for r in calls if r[0] == 'state'], [('state',)])
        self.assertIsNone(result['operator_gates_passed'])
        self.assertTrue(result['node_gates_passed'])
        self.assertEqual(result['operator_checks']['conv_same_actual_input']['status'], 'NOT_RUN_UNSELECTED')

    def test_selected_conv_uses_only_original_cold_helpers(self):
        calls = []
        values = {k: ('actual_' + k).encode() for k in c.ROLES}
        weight = b'original_weight'

        def bf16(a, b, gate='node'):
            calls.append(('metric', a, b, gate))
            return dict(passed=True, status='PASS')

        def captured(tensors, case, rows, raw, **kwargs):
            calls.append(('captured', case, rows, raw, kwargs))
            return (b'pure', {'source': 'original'})

        def conditioned(qkv, raw, rows, **kwargs):
            calls.append(('conditioned', qkv, raw, rows, kwargs))
            return ({'conv': b'conditioned_conv', 'silu': b'conditioned_silu'}, {'source': 'original'})
        fake = types.SimpleNamespace(native_role=lambda t, case, role, rows: b'native', bf16_metric=bf16, state_metric=lambda a, b: dict(passed=True, status='PASS'), prep_diagnostic=lambda *a: dict(passed=None, thresholds=None), assigned_pass=self.ns['assigned_pass'], MissingNode=ValueError, captured_conv_reference=captured, conv_reference=types.SimpleNamespace(native_conv=conditioned))
        result = c.cold_metrics(fake, values, None, {'linear_attn.conv1d.weight': weight}, include_conv=True, root=REPOSITORY)
        self.assertEqual([v for v in calls if v[0] == 'captured'], [('captured', 'cold128', 128, weight, {'root': REPOSITORY})])
        self.assertEqual([v for v in calls if v[0] == 'conditioned'], [('conditioned', values['qkv'], weight, 128, {'history_raw': None, 'root': REPOSITORY})])
        self.assertIn(('metric', values['conv_before_silu'], b'pure', 'node'), calls)
        self.assertIn(('metric', values['conv_before_silu'], b'conditioned_conv', 'ulp'), calls)
        self.assertIn(('metric', values['conv_silu'], b'conditioned_silu', 'ulp'), calls)
        self.assertTrue(result['operator_gates_passed'])

    def test_missing_native_node_cannot_pass(self):

        class Missing(ValueError):
            pass

        def native(t, case, role, rows):
            if role == 'chunk':
                raise Missing('synthetic missing')
            return b'expected'
        fake = types.SimpleNamespace(native_role=native, bf16_metric=lambda *a, **k: dict(passed=True, status='PASS'), state_metric=lambda *a: dict(passed=True, status='PASS'), prep_diagnostic=lambda *a: dict(passed=None, thresholds=None), assigned_pass=self.ns['assigned_pass'], MissingNode=Missing, missing_metric=lambda error, actual=None: dict(passed=False, status='MISSING'))
        result = c.cold_metrics(fake, {k: b'SYNTHETIC' for k in c.ROLES}, None, {}, root=REPOSITORY)
        self.assertFalse(result['node_gates_passed'])
        self.assertIsNone(result['operator_gates_passed'])
        self.assertEqual(result['checks']['chunk']['status'], 'MISSING')

    def test_source_has_no_full_entrypoint_call_no_phase_assignment(self):
        tree = ast.parse((HERE / 'cold_postterminal.py').read_bytes())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                self.assertNotIn(node.func.attr, ('compare_run', 'load_actual', 'kill', 'killpg', 'Popen'))
            if isinstance(node, ast.Assign):
                self.assertFalse(any((isinstance(t, ast.Attribute) and t.attr == 'PHASES' for t in node.targets)))

    def test_subprocess_and_signal_audits_are_denied_without_execution(self):
        for event in ('subprocess.Popen', 'os.kill', 'os.killpg', 'ctypes.dlopen'):
            with self.subTest(event=event):
                with self.assertRaisesRegex(RuntimeError, 'deny process'):
                    sys.audit(event, None)

    def test_global_acceptance_is_always_false(self):
        tree = ast.parse((HERE / 'cold_postterminal.py').read_bytes())
        result = next((n for n in ast.walk(tree) if isinstance(n, ast.Assign) and any((isinstance(t, ast.Name) and t.id == 'result' for t in n.targets)) and isinstance(n.value, ast.Call) and any((k.arg == 'combined_full_run_acceptance' for k in n.value.keywords))))
        fields = {k.arg: k.value for k in result.value.keywords}
        self.assertIsNone(ast.literal_eval(fields['passed']))
        for name in ('combined_full_run_acceptance', 'full_block_gate_pass'):
            self.assertIs(ast.literal_eval(fields[name]), False)

    def test_heavy_import_is_denied(self):
        with self.assertRaisesRegex(RuntimeError, 'deny model'):
            sys.audit('import', 'numpy')
if __name__ == '__main__':
    unittest.main()
