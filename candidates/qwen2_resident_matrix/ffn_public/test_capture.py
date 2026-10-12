"""Synthetic wrapper/boundary tests only; no compiler or official payload IO."""
from array import array
from copy import deepcopy
from dataclasses import replace
import importlib.util
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('public_capture_wrapper_tests', HERE / 'check_numeric.py')
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


class CaptureWrapperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.execution, cls.fixtures, cls.public = check.runtime()
        cls.numeric = cls.execution.numeric

    def layout(self, rows=16):
        fixture = self.fixtures.make_ffn4_fixture(rows, 7)
        spans = [(base, limit, name) for name, base, limit in fixture.physical_spans()
                 if name not in ('command_table', 'descriptor_table')]
        w = fixture.config.regions[3]
        owner = SimpleNamespace(workspace=SimpleNamespace(base=w.base, extent=w.limit-w.base,
                                                          generation=8, split_k=2560))
        return fixture, SimpleNamespace(spans=spans), owner

    def test_all_eleven_full_spans_match_for_both_supported_rows(self):
        for rows in (16, 128):
            fixture, memory, owner = self.layout(rows)
            spans = check.validate_layout(fixture, memory, owner)
            self.assertEqual(len(spans), 11)
            self.assertEqual(dict((name, end-start) for start, end, name in spans)['n1'], rows*1536*4)
            identity = check.metadata_identity(fixture)
            self.assertEqual(identity, json.loads(check.encoded(identity)))
            self.assertEqual(identity['tables']['command']['count'], 4)
            self.assertEqual(identity['tables']['descriptor']['count'], 43)
            self.assertEqual(len(identity['tables']['command']['record_hex']), 4)

    def test_metadata_cannot_alias_payload_or_workspace(self):
        fixture, memory, owner = self.layout()
        for target in (fixture.specs['n1'][0], owner.workspace.base):
            with self.subTest(target=target):
                fixture.config = replace(fixture.config, command=replace(fixture.config.command,
                                          base=target, limit=target+64))
                with self.assertRaisesRegex(ValueError, 'full spans alias'):
                    check.validate_layout(fixture, memory, owner)

    def test_actual_span_and_epoch_must_match_raw_fixture(self):
        fixture, memory, owner = self.layout()
        memory.spans[0] = (memory.spans[0][0], memory.spans[0][1]+64, memory.spans[0][2])
        with self.assertRaisesRegex(ValueError, 'allocation spans differ'):
            check.validate_layout(fixture, memory, owner)
        fixture, memory, owner = self.layout()
        owner.workspace.generation += 1
        with self.assertRaisesRegex(ValueError, 'workspace differs'):
            check.validate_layout(fixture, memory, owner)

    def test_source_closure_includes_transitive_encoder_and_original_models(self):
        sources = set(check.source_paths())
        for path in ('src/heteronpu/command.py', 'src/heteronpu/descriptor_chain.py',
                     'src/heteronpu/gemmini_descriptor_v2.py', 'src/heteronpu/abi_validation.py',
                     'src/heteronpu/gemmini_rocc_lowering.py',
                     'candidates/qwen2_resident_matrix/ffn_public/fixture.py',
                     'candidates/qwen2_resident_matrix/ffn_public/execute_numeric.py',
                     'candidates/qwen2_resident_matrix/ffn_fullgroup/down_driver.py',
                     'candidates/qwen2_resident_matrix/transposed_down/numeric_smoke.cpp'):
            self.assertIn(path, sources)
        self.assertFalse(any(path.endswith(('.f32le', '.bin', '.so')) for path in sources))
        self.assertFalse(any('test_' in Path(path).name or 'receipt' in Path(path).name or
                             'delivery_manifest' in path for path in sources))
        self.assertNotIn('chisel/continuous_prefill/src/main/scala/heteronpu/continuous/GdnRmsNormOwner.scala', sources)

    def test_task_local_venv_is_tooling_but_repo_imports_remain_strict(self):
        prefix = check.ROOT/'work/synthetic_venv'
        module = ModuleType('synthetic_third_party')
        module.__file__ = str(prefix/'lib/python3.12/site-packages/synthetic/__init__.py')
        with patch.object(check.sys, 'prefix', str(prefix)):
            self.assertIsNone(check.repository_source_path(module.__file__))
            self.assertEqual(check.imported_python_paths([module]), check.imported_python_paths([]))
            for path in ('src/heteronpu/config.py', 'candidates/other/model.py',
                         'scripts/new_dependency.py', 'work/actual_helper.py'):
                self.assertEqual(check.repository_source_path(check.ROOT/path), path)
        identity = check.host_tool_identity()
        self.assertEqual(identity['python_version'], check.sys.version)
        self.assertTrue(identity['python_executable'])

    def test_prepare_freezes_sources_and_raw_metadata_without_numeric_io(self):
        before = check.file_sha(check.ROOT / check.PRECISION_PATH)
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(self.numeric.drain_check, 'checked_file', side_effect=AssertionError('payload IO')), \
                patch.object(self.numeric.drain_check, 'build_library', side_effect=AssertionError('compile')), \
                patch.object(self.numeric, 'compare_after_terminal', side_effect=AssertionError('reference')):
            # A successor CI commit tests its own checkout; production prepare
            # keeps its fixed published baseline default and all source checks.
            head = check.subprocess.check_output(['git', 'rev-parse', 'HEAD'],
                                                  cwd=check.ROOT, text=True).strip()
            path, snapshot = check.prepare(Path(tmp)/'prepared', 16, expected_head=head)
            verified = check.verify_snapshot(path, check.file_sha(path))
            self.assertEqual(verified, snapshot)
            self.assertFalse(snapshot['tensor_payloads_read'])
            self.assertFalse(snapshot['compilation_executed'])
            self.assertEqual(snapshot['status'], 'PREPARED_NOT_EXECUTED')
            self.assertIn('candidates/qwen2_resident_matrix/ffn_fullgroup/down_driver.py',
                          snapshot['changed_predecessor_sources'])
            new_pins = json.loads((path.parent/'precision_pins.json').read_text())
            self.assertFalse(new_pins['predecessor_numeric_acceptance_inherited'])
            self.assertEqual(len(snapshot['metadata']['physical_spans']), 11)
            self.assertEqual((path.parent/'command_table.bin').stat().st_size, 64)
            self.assertEqual(check.file_sha(check.ROOT/check.PRECISION_PATH), before)
            with self.assertRaisesRegex(ValueError, 'snapshot hash mismatch'):
                check.verify_snapshot(path, '0'*64)
            table = path.parent/'command_table.bin'
            original = table.read_bytes()
            table.write_bytes(b'\xff'*len(original))
            with self.assertRaisesRegex(ValueError, 'frozen metadata changed'):
                check.verify_snapshot(path, check.file_sha(path))
            table.write_bytes(original)
            helper = path.parent/'frozen_sources/src/heteronpu/abi_validation.py'
            helper.write_bytes(helper.read_bytes()+b'\n# synthetic tamper\n')
            with self.assertRaisesRegex(ValueError, 'frozen source changed'):
                check.verify_snapshot(path, check.file_sha(path))

    def test_reference_gate_rejects_saved_open_and_independent_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'synthetic_reference.f32le'
            path.write_bytes(b'synthetic comparison only')
            pins = {'comparison_only': {'gate': {'path': str(path)}}}
            lib = SimpleNamespace(td_step=Mock(return_value=17), fw_reference=Mock(return_value=23))
            with check.reference_gate(pins) as gate:
                guarded = gate.library(lib)
                self.assertEqual(guarded.td_step(), 17)
                with self.assertRaisesRegex(ValueError, 'before public final ACK'):
                    path.read_bytes()
                with self.assertRaisesRegex(ValueError, 'before public final ACK'):
                    guarded.fw_reference()
                lib.fw_reference.assert_not_called()
                gate.opened = True
                self.assertEqual(path.read_bytes(), b'synthetic comparison only')
                self.assertEqual(guarded.fw_reference(), 23)

    def test_metadata_reads_are_actual_frontend_records(self):
        fixture = self.fixtures.make_ffn4_fixture(16)
        frontend = self.public.PublicFrontend(fixture.memory, fixture.config)
        host = self.public.group.HostControl(enabled=True)
        self.assertTrue(frontend.launch(host))
        for _ in range(1000):
            if host.ports()['group_request'] is not None:
                break
            host.tick()
        self.assertIsNotNone(host.ports()['group_request'])
        report = check.metadata_observations(frontend)
        self.assertGreater(report['physical_read_bytes'], 0)
        self.assertEqual(report['physical_read_bytes'], 64*len(fixture.memory.reads))
        self.assertEqual(report['accepted_records'], frontend.port.trace)
        self.assertEqual(report['command_reads'], frontend.command_reads)
        self.assertFalse(report['model_ticks_are_hardware_cycles'])
        frontend.memory.reads.append(fixture.config.command.base)
        with self.assertRaisesRegex(ValueError, 'metadata physical read record mismatch'):
            check.metadata_observations(frontend)

    def terminal_fixture(self):
        # Deliberately fabricated only to exercise the wrapper's validation;
        # never passed to run(), execution, comparison or a capture report.
        rows = 16
        act = array('I', [0])*(rows*8960)
        down = array('I', [0])*(rows*1536)
        act_bytes, down_bytes = len(act)*4, len(down)*4
        outputs = dict(act=act, down=down)
        memory = SimpleNamespace(act=SimpleNamespace(validate_full=lambda:
                                  (act.tobytes(), dict(ack_bytes=act_bytes))))
        owner = SimpleNamespace(state='idle', lease=None, tiles=SimpleNamespace(leased=False),
                                ports=lambda: dict(reset_required=False))
        evidence = dict(full_ffn_host_model_executed=True, same_owner_and_banks=True,
            host=dict(launch_result=dict(status=None, completed=4, jobs=2, write_bytes=act_bytes+down_bytes),
                accepted=dict(result_fire=1, completion_fire=4, owner_result_fire=2), reset_required=False,
                completions=[dict(pc=pc, status=None) for pc in range(4)]),
            group=dict(windows=[{} for _ in range(56)]),
            coordinator=dict(accepted=dict(window_result_fire=112, drain_result_fire=56),
                             terminal=dict(status=None, write_bytes=act_bytes)),
            down=dict(completed=True, same_owner_and_banks=True, owner_resets=0,
                accepted=dict(response_handshakes=1), completion=[3, None, down_bytes], synthetic_geometry=False,
                final_ack_fence=dict(held_ticks=3, final_ack_tick=10, terminal_tick=11,
                                     terminal_strictly_after_final_ack=True),
                ddr=dict(bytes=down_bytes, ack_bytes=down_bytes, data_bytes=down_bytes,
                         sha256=check.sha(down.tobytes())), physical_traffic=dict(down_ack_bytes=down_bytes),
                actual_act_source=dict(sha256=check.sha(act.tobytes()), actual_prior_ack_written=True)))
        return evidence, memory, owner, outputs, rows

    def test_reference_boundary_needs_public_final_ack_and_same_owner(self):
        args = self.terminal_fixture()
        result = check.validate_terminal(*args)
        self.assertTrue(result['all_actual_final_acks_and_terminals_before_comparison'])
        mutations = (
            lambda e: e['host']['completions'].pop(),
            lambda e: e['host']['accepted'].update(result_fire=0),
            lambda e: e['host'].update(reset_required=True),
            lambda e: e['group']['windows'].pop(),
            lambda e: e['down']['final_ack_fence'].update(terminal_tick=10),
            lambda e: e['down'].update(same_owner_and_banks=False),
            lambda e: e['down'].update(synthetic_geometry=True),
            lambda e: e['down']['ddr'].update(ack_bytes=0),
            lambda e: e['down']['actual_act_source'].update(sha256='0'*64),
        )
        for mutation in mutations:
            bad = deepcopy(args[0])
            mutation(bad)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                check.validate_terminal(bad, *args[1:])

    def test_input_loader_slices_only_frozen_n1_and_reads_no_comparisons(self):
        pins = {'inputs': {name: dict(path=name, sha256='synthetic-full-'+name) for name in
                          ('n1', 'gate_weight', 'up_weight', 'down_weight')},
                'comparison_only': {'gate': dict(path='FORBIDDEN')}}
        raw = {'n1': array('I', range(128*1536)).tobytes(),
               'gate_weight': b'\0\0', 'up_weight': b'\0\0', 'down_weight': b'\0\0'}
        read = Mock(side_effect=lambda spec: raw[spec['path']])
        with patch.object(self.numeric.drain_check, 'checked_file', read):
            inputs, report = check.load_inputs(self.numeric, pins, 16)
        self.assertEqual(read.call_count, 4)
        self.assertEqual(len(inputs['n1']), 16*1536)
        self.assertEqual(inputs['n1'].tobytes(), raw['n1'][:16*1536*4])
        self.assertEqual(report['n1']['source_sha256'], 'synthetic-full-n1')
        self.assertEqual(report['n1']['sha256'], check.sha(raw['n1'][:16*1536*4]))


if __name__ == '__main__':
    unittest.main()
