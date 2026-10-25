"""Pure schema/control fixtures, NOT an M16/M128 numerical execution.

All payload words are artificial zeros/sentinels. No source owner, arithmetic
recipe, native library, runner, reference, or hardware is imported or executed.
The canonical row extent only exercises registry dimensions and rejection.
"""
from array import array
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest

PATH = Path(__file__).with_name('registry.py')
SPEC = importlib.util.spec_from_file_location('_fullgraph_registry_schema_test', PATH)
r = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = r
SPEC.loader.exec_module(r)


class FakeSilu:
    """A counted fake return to test sequencing; never numeric evidence."""
    def __init__(self, rows):
        self.rows = rows
        self.calls = 0

    def seal(self, actual):
        self.calls += 1
        if len(actual) != self.rows * 8960 * 4:
            raise ValueError('fake act extent')
        return bytes(len(actual))


def fixture():
    rows = 16
    actual = {name: array('I', [0]) * (rows * width)
              for name, width in dict(r.STAGE_WIDTHS, **r.RAW_WIDTHS).items()}
    actual['kv'] = array('I', [0]) * (rows * 512)
    outputs = {}
    for name, values in actual.items():
        physical = name not in ('gate', 'up')
        outputs[name] = dict(bytes=len(values) * 4,
                             written_bytes=len(values) * 4 if physical else 0,
                             ack_bytes=len(values) * 4 if physical else 0,
                             terminal=physical, published=physical,
                             sha256=r._digest(values))
    for name in ('scores', 'probabilities'):
        outputs[name] = dict(bytes=12 * rows * rows * 4, written_bytes=0,
                             ack_bytes=0, terminal=False, published=False,
                             sha256='control_fixture_not_actual')
    host = dict(launch_result=dict(status=None, completed=21, jobs=17),
                completions=[dict(pc=pc, status=None) for pc in range(21)],
                accepted=dict(completion_fire=21, request_fire=17,
                              owner_result_fire=17, result_fire=1),
                events=list(range(22)), reset_required=False)
    report = dict(status='PUBLIC21_PC0_20_SOFTWARE_EXECUTED', host=host,
                  matrix=dict(reset_required=False), memory=dict(outputs=outputs),
                  full_block_executed=True, full_block_software_model_executed=True,
                  same_owner_and_banks=True, same_physical_memory_and_services=True,
                  reference_arithmetic_executed=False,
                  virtual_outputs=dict(unchanged=True, physical_writes=0,
                      initial_and_final_sha256=dict(gate='fixture', up='fixture')))
    scalar = NS(client=None)
    matrix = NS(owner=None, group=None, result=None, _done=None, _dense=None)
    physical = NS(pending=None, regions={'act': {'data': object()}})
    memory = NS(physical_memory=physical,
                workspace=NS(physical_memory=physical, finished=True),
                act=NS(data=physical.regions['act']['data']))
    metadata = NS(physical_memory=physical)
    x = NS(host=NS(state='idle', program=tuple(range(21)), pc=21, completed=21,
                   jobs=17, events=set(range(22))), launch_result=host['launch_result'],
           completions=host['completions'], counts=host['accepted'],
           owner=NS(state='idle', lease=None, tiles=NS(idle=True, leased=False)),
           prefix_owner=NS(state='idle', scalar=scalar), matrix_service=matrix,
           attention_owner=NS(state='idle', matrix=matrix, scalar=scalar,
               matrix_client=None, memory_pending=False, scratch_pending=False,
               scratch_leased=False, poison=False),
           frontend=NS(memory=metadata, port=NS(memory=metadata)))
    fields, summaries = {}, {}
    for name in r.ATTENTION_FIELDS:
        shape = ((12, rows, rows, 16) if name == 'dot_parts' else
                 (12, rows, 3) if name == 'normalizer' else
                 (12, rows, 128) if name in ('pv_raw', 'pv_bf16') else (12, rows, rows))
        count = 1
        for dimension in shape:
            count *= dimension
        f = dict(shape=shape, words=array('I', [r.SENTINEL]) * count,
                 observed=bytearray(count), frequency=array('H', [0]) * count,
                 writes=0, repeats=0)
        width = shape[-1] if name in ('dot_parts', 'normalizer', 'pv_raw', 'pv_bf16') else 1
        causal = name not in ('normalizer', 'pv_raw', 'pv_bf16')
        repeated = name in ('softmax_fp32', 'prob_bf16')
        for h in range(12):
            for token in range(rows):
                for key in range(token + 1) if causal else (None,):
                    start = ((h * rows + token) * rows + key) * width if causal else (h * rows + token) * width
                    for index in range(start, start + width):
                        f['words'][index] = 0
                        f['observed'][index] = 1
                        f['frequency'][index] = 8 if repeated else 1
                        f['writes'] += 1
                        f['repeats'] += 7 if repeated else 0
        fields[name] = f
        summaries[name] = dict(shape=shape, words=count, observed_words=f['writes'],
            raw_sha256=r._digest(f['words']), presence_sha256=r._digest(f['observed']),
            frequency_sha256=r._digest(f['frequency']), writes=f['writes'],
            identical_repeats=f['repeats'])
    capture = dict(status='COMPLETE_SOFTWARE_OBSERVATION_NOT_HARDWARE',
                   execution_provenance=r.NORMAL_PROVENANCE, fields=summaries,
                   terminal=dict(clean=True, same_services=True), packed_acks=192,
                   packed_done=192, observer_launches_native_or_rtl=False)
    args = dict(rows=rows, actual=actual, execution_report=report,
                capture_report=capture, capture_fields=fields, silu_library=FakeSilu(rows),
                terminal=r.terminal_snapshot(x, physical, memory, report))
    return args


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.args = fixture()

    def reject(self, message):
        with self.assertRaisesRegex(ValueError, message):
            r.seal_registry(**self.args)
        self.assertEqual(self.args['silu_library'].calls, 0,
                         'invalid prior evidence must not invoke SiLU seal')

    def test_complete_fixture_is_inventory_only_temp(self):
        output = r.seal_registry(**self.args)
        self.assertEqual(len(output['entries']), 32)
        self.assertEqual(output['original_stages'], list(r.STAGE_WIDTHS))
        self.assertEqual(output['numerical_status'], 'TEMP')
        self.assertFalse(output['numeric_acceptance'])
        self.assertFalse(output['native_acceptance'])
        self.assertFalse(output['hardware_acceptance'])
        self.assertEqual(output['fixed_physical_macs'], 4096)
        self.assertEqual(output['legacy_pv_upper_bound_percent'], 63.57)
        self.assertEqual(self.args['silu_library'].calls, 1)
        self.assertEqual(output['entries']['gate']['storage'], 'tile_read_audit_not_DDR')
        self.assertEqual(output['entries']['scores_bf16']['storage'], 'observer_only_not_DDR')
        self.assertEqual(output['entries']['cache_v']['parent'], 'kv')
        self.assertNotIn('raw_sha256', output['entries']['cache_v'])

    def test_missing_each_actual_output_is_rejected(self):
        for name in tuple(self.args['actual']):
            with self.subTest(name=name):
                value = self.args['actual'].pop(name)
                self.reject('inventory')
                self.args['actual'][name] = value

    def test_extra_actual_reference_cannot_fill_inventory(self):
        self.args['actual']['reference_scores'] = array('I', [0])
        self.reject('inventory')

    def test_missing_each_attention_field_is_rejected(self):
        for name in r.ATTENTION_FIELDS:
            with self.subTest(name=name):
                value = self.args['capture_fields'].pop(name)
                self.reject('exact ten')
                self.args['capture_fields'][name] = value

    def test_actual_shape_rejected(self):
        self.args['actual']['qraw'].pop()
        self.reject('word extent')

    def test_official_29_coverage_never_inferred_from_32_entries(self):
        output = r.seal_registry(**self.args)
        coverage = output['official_node_coverage']
        self.assertEqual(len(coverage['nodes']), 29)
        self.assertFalse(coverage['complete_official_29_node_coverage'])
        self.assertFalse(coverage['actual_registry_inventory_is_official_29_coverage'])
        self.assertEqual(set(coverage['missing_or_nonmaterialized_nodes']),
                         {'x', 'repeat_k', 'repeat_v', 'cos', 'sin', 'mask', 'logits'})
        self.assertEqual(coverage['partially_observed_nodes'], ['scores', 'prob', 'softmax_fp32'])
        self.assertFalse(coverage['values_reconstructed_to_fill_gaps'])
        self.assertIn('scale', coverage['unobserved_internal_diagnostics']['norm']['unobserved_locals'])
        self.assertIn('xc', coverage['unobserved_internal_diagnostics']['rope']['unobserved_locals'])

    def test_missing_capture_distinct_from_no_physical_tensor(self):
        coverage = r.official_coverage_plan()
        self.assertEqual(coverage['missing_actual_operand_capture_nodes'], ['cos', 'sin'])
        self.assertEqual(set(coverage['physically_nonmaterialized_semantic_nodes']),
                         {'repeat_k', 'repeat_v', 'logits', 'mask'})
        self.assertEqual(coverage['readonly_inputs_not_registered'], ['x'])
        for name in ('cos', 'sin'):
            self.assertEqual(coverage['nodes'][name]['status'], 'MISSING_ACTUAL_OPERAND_CAPTURE')
            self.assertIn('BF16_OPERANDS', coverage['nodes'][name]['physical_materialization'])
        for name in ('repeat_k', 'repeat_v', 'logits', 'mask'):
            self.assertEqual(coverage['nodes'][name]['status'], 'PHYSICALLY_NONMATERIALIZED_SEMANTIC_NODE')
            self.assertEqual(coverage['nodes'][name]['physical_materialization'], 'NO_INDEPENDENT_TENSOR_PRODUCER')
        self.assertEqual(coverage['nodes']['x']['status'], 'READONLY_INPUT_NOT_REGISTERED')
        self.assertTrue(all('physical_materialization' in n and 'actual_capture' in n
                            and not n['values_synthesized'] and not n['numeric_pass_inherited']
                            for n in coverage['nodes'].values()))

    def test_all_32_inventory_entries_map_without_extra_coverage_credit(self):
        output = r.seal_registry(**self.args)
        correspondence = output['actual_inventory_correspondence']
        self.assertEqual(set(correspondence), set(output['entries']))
        self.assertEqual(len(correspondence), 32)
        self.assertEqual(correspondence['kv']['official_semantic_nodes'], ['cache_k', 'cache_v'])
        self.assertEqual(correspondence['cache_k']['official_semantic_nodes'], ['cache_k'])
        self.assertEqual(correspondence['scores_bf16']['official_semantic_nodes'], ['scores'])
        self.assertNotIn('logits', correspondence['scores_bf16']['official_semantic_nodes'])
        for name in ('qraw', 'kraw', 'vraw', 'dot_parts', 'unrounded_dot_sum',
                     'dot_bf16', 'softmax_exp', 'normalizer', 'pv_raw'):
            self.assertEqual(correspondence[name]['official_semantic_nodes'], [])
        self.assertTrue(all(not n['official_node_pass_claimed'] for n in correspondence.values()))

    def test_historical_assigned_27_is_not_new_coverage_or_pass(self):
        policy = r.official_coverage_plan()['historical_assigned_27_reference_policy']
        self.assertEqual(policy['status'], 'NOT_IMPORTED_OR_VALIDATED_BY_THIS_REGISTRY')
        self.assertTrue(policy['reuse_must_be_explicit'])
        self.assertFalse(policy['new_node_coverage_inherited'])
        self.assertFalse(policy['numeric_pass_inherited'])
        self.assertFalse(policy['missing_actual_values_may_be_filled'])
        self.assertIn('raw_input_identities', policy['required_matching_evidence'])
        self.assertIn('node_semantics_and_layout', policy['required_matching_evidence'])
        self.assertIn('actual_presence_masks', policy['required_matching_evidence'])

    def test_missing_terminal_status_is_not_success(self):
        self.args['execution_report']['host']['launch_result'].pop('status')
        self.reject('whole terminal needs')

    def test_missing_completion_status_is_not_success(self):
        self.args['execution_report']['host']['completions'][20].pop('status')
        self.reject('duplicate public completion')

    def test_attention_shape_rejected(self):
        self.args['capture_fields']['normalizer']['shape'] = (12, 16, 2)
        self.reject('field shape')

    def test_attention_extent_rejected(self):
        self.args['capture_fields']['pv_raw']['words'].pop()
        self.reject('word extent')

    def test_incomplete_public_terminal_rejected_before_silu(self):
        self.args['execution_report']['host']['launch_result']['completed'] = 20
        self.reject('21 completions')

    def test_wrong_actual_job_count_rejected(self):
        self.args['execution_report']['host']['launch_result']['jobs'] = 21
        self.reject('17 actual jobs')

    def test_result_not_accepted_rejected(self):
        self.args['execution_report']['host']['accepted']['result_fire'] = 0
        self.reject('handshake')

    def test_duplicate_completion_rejected(self):
        self.args['execution_report']['host']['completions'][-1]['pc'] = 19
        self.reject('duplicate public completion')

    def test_live_service_debt_rejected(self):
        self.args['terminal'].execution.matrix_service._done = object()
        self.reject('service obligations')

    def test_workspace_not_finished_rejected(self):
        self.args['terminal'].memory.workspace.finished = False
        self.reject('workspace identity or obligations')

    def test_live_terminal_not_idle_rejected(self):
        self.args['terminal'].execution.host.state = 'finish'
        self.reject('live whole launch')

    def test_reference_actual_provenance_rejected(self):
        self.args['actual_provenance'] = 'EXISTING_AST_INDEPENDENT_REFERENCE_RECIPE'
        self.reject('actual provenance forbidden')

    def test_reference_capture_provenance_rejected(self):
        self.args['capture_report']['execution_provenance'] = 'EXISTING_AST_INDEPENDENT_REFERENCE_RECIPE'
        self.reject('Attention reference/AST')

    def test_ast_capture_provenance_rejected(self):
        self.args['capture_report']['execution_provenance'] = 'AST_DEFINITION_SOFTWARE_TEST_ONLY'
        self.reject('Attention reference/AST')

    def test_reference_arithmetic_flag_rejected(self):
        self.args['execution_report']['reference_arithmetic_executed'] = True
        self.reject('reference arithmetic')

    def test_duplicate_attention_capture_rejected(self):
        self.args['capture_fields']['dot_parts']['frequency'][0] = 2
        self.reject('duplicate Attention observation')

    def test_probability_missing_actual_reuse_rejected(self):
        self.args['capture_fields']['prob_bf16']['frequency'][0] = 1
        self.reject('duplicate Attention observation')

    def test_future_reference_fill_rejected(self):
        self.args['capture_fields']['scores_bf16']['words'][1] = 0
        self.reject('future causal field filled')

    def test_stale_report_digest_rejected(self):
        self.args['capture_report']['fields']['dot_parts']['raw_sha256'] = '0' * 64
        self.reject('digest mismatch')

    def test_gate_audit_cannot_be_ddr(self):
        self.args['execution_report']['memory']['outputs']['gate']['published'] = True
        self.reject('incorrectly treated as DDR')

    def test_attention_virtual_cannot_be_ddr(self):
        self.args['execution_report']['memory']['outputs']['scores']['ack_bytes'] = 64
        self.reject('virtual DDR materialized')

    def test_pv_must_equal_existing_ack_output(self):
        self.args['actual']['att'][0] = 1
        self.args['execution_report']['memory']['outputs']['att']['sha256'] = r._digest(self.args['actual']['att'])
        self.reject('PV differs')

    def test_wrong_silu_profile_rejected(self):
        self.args['silu_library'].rows = 128
        self.reject('SiLU observer')

    def test_duplicate_registry_seal_rejected(self):
        r.seal_registry(**self.args)
        with self.assertRaisesRegex(ValueError, 'fresh matching whole terminal'):
            r.seal_registry(**self.args)
        self.assertEqual(self.args['silu_library'].calls, 1)

    def test_native_backed_properties_not_read(self):
        class NativeTrap(NS):
            @property
            def done(self):
                raise AssertionError('registry must not call native-backed done')

            @property
            def reset_required(self):
                raise AssertionError('registry must not call native-backed reset')

            def ports(self):
                raise AssertionError('registry must not call native-backed ports')
        terminal = self.args['terminal']
        matrix = NativeTrap(**vars(terminal.execution.matrix_service))
        terminal.execution.matrix_service = matrix
        terminal.execution.attention_owner.matrix = matrix
        self.assertEqual(r.seal_registry(**self.args)['numerical_status'], 'TEMP')


if __name__ == '__main__':
    unittest.main()
