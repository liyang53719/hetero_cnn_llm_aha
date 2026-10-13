"""Bounded same-memory H2048 RMS→K2048 prefix, actual shared C++ services."""
from dataclasses import replace
import time
import unittest

import numpy as np

from ..qwen35_gdn_prefill import test_projection_driver as original
from ..qwen35_gdn_prefill import typed_dense as dense
from ..qwen35_gdn_prefill.chunk.vector import Vector16, IEEE_POLICY
from ..qwen35_35b_rms.formula import formula
from . import prefix_driver as p


def setUpModule():
    original.setUpModule()


class PrefixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hidden = np.full((16, 2048), 0x3f00, '<u2').tobytes()
        cls.weight = bytes(4096)
        nk = np.zeros((8192, 2048), '<u2')
        for col in range(8192):
            nk[col, col % 1024] = 0x3e80 if col % 2 else 0xbe80
            nk[col, 1024 + col % 1024] = 0x3e00
        cls.nk = nk.tobytes()
        cls.profile = replace(original.PROFILE, identity='synthetic_h2048_prefix',
                              ranges=((0, 1024), (1024, 2048)))

    def setUp(self):
        self.assertEqual(original.LIB.td_reset(), 0)
        self.matrix = dense.MatrixService(original.LIB)
        self.vector = Vector16(original.VECTOR_PATH, exception_policy=IEEE_POLICY)

    def run_prefix(self, *, windows=(p.ColumnWindow(0, 32), p.ColumnWindow(2048, 32)), **kwargs):
        return p.execute_prefix(self.hidden, self.weight, self.nk,
            tokens=16, windows=windows, profile=self.profile, matrix=self.matrix,
            vector=self.vector, deadline=time.monotonic()+90, **kwargs)

    def test_actual_rms_three_disjoint_qkv_windows_ack_and_held_terminal(self):
        stalls = dict(ack=0, terminal=0)
        observed = []
        def controls(stage, i, d):
            if stage == 'input_norm':
                return dict(memory_ready=i % 3 != 0, memory_response_ready=i % 4 != 0)
            if d.pending_ack is not None and d.counts['write_data_bytes'] == d.job.write_bytes and stalls['ack'] < 4:
                self.assertFalse(d.output.published)
                self.assertEqual(len(observed), 1)
                stalls['ack'] += 1
                return dict(ack_ready=False, response_ready=False)
            if stage == 'qkv_columns_0' and stalls['terminal'] < 4:
                if d.coordinator.ports(d.services())['result'] is not None:
                    self.assertFalse(d.output.published)
                    self.assertEqual(len(observed), 1)
                    stalls['terminal'] += 1
                return dict(response_ready=False)
            return dict(read_ready=i % 3 != 0, step_ready=i % 5 != 0)
        def observe(stage, details, raw):
            self.assertTrue(details['output_published'])
            observed.append((stage, raw))
            return bytes(len(raw))  # Ignored observation cannot become an input.
        report, memory = self.run_prefix(windows=tuple(p.ColumnWindow(i, 160 if i == 0 else 32) for i in (0, 2048, 4096)),
                                         controls=controls, observe=observe)
        self.assertEqual(report['status'], 'PASS_TYPED_PREFIX_EXECUTION_ONLY')
        self.assertEqual(stalls, dict(ack=4, terminal=4))
        self.assertEqual(observed[0][1], formula(self.hidden, self.weight, 16)['output'])
        for name, raw in observed[1:]:
            columns = 160 if name == 'qkv_columns_0' else 32
            expected = np.tile(np.array([0xbe00, 0x3ec0], '<u2'), (16, columns//2)).tobytes()
            self.assertEqual(raw, expected, name)
        self.assertEqual(len(report['terminals']), 4)
        self.assertEqual(len([r for r in memory.regions.values() if r.published and not r.readonly]), 4)
        self.assertTrue(report['actual_rms_region_consumed'])
        self.assertEqual(report['scalar_operations'], dict(mul_ieee_rne=98320, add=68240, sqrt=16, div=16))
        for stage in report['stages'][1:]:
            self.assertEqual(stage['report']['counts']['ack_bytes'], 5120 if stage['stage'] == 'qkv_columns_0' else 1024)
            self.assertEqual(stage['report']['input_sha256'][0], report['actual_rms_output_sha256'])
        self.assertIsNone(report['hardware_cycles'])

    def test_rms_last_write_failure_stops_before_matrix_consumer(self):
        def controls(stage, _, d):
            self.assertEqual(stage, 'input_norm')
            return dict(ack_error=d.pending is not None and d.owner.request.write and
                        d.counts['write_bytes'] == len(self.hidden))
        report, memory = self.run_prefix(controls=controls)
        self.assertEqual(report['status'], 'FAILED')
        self.assertEqual(len(report['terminals']), 1)
        self.assertEqual(self.matrix.counts['owner_acquires'], 0)
        self.assertFalse(any(r.published for r in memory.regions.values() if not r.readonly))

    def test_projection_last_ack_failure_keeps_norm_but_blocks_next_consumer(self):
        def controls(stage, _, d):
            if stage == 'input_norm':
                return {}
            self.assertEqual(stage, 'qkv_columns_0')
            return dict(ack_error=d.pending_ack is not None and d.counts['write_data_bytes'] == d.job.write_bytes)
        report, memory = self.run_prefix(controls=controls)
        self.assertEqual(report['status'], 'FAILED')
        self.assertEqual(len(report['terminals']), 2)
        self.assertEqual(len([r for r in memory.regions.values() if r.published and not r.readonly]), 1)
        self.assertIsNone(self.matrix.owner)
        self.assertIsNone(self.vector.client)

    def test_abort_held_success_blocks_later_consumers(self):
        def controls(stage, _, d):
            if stage == 'input_norm':
                return {}
            self.assertEqual(stage, 'qkv_columns_0')
            held = d.coordinator.ports(d.services())['result'] is not None
            return dict(response_ready=held, abort=held)
        report, memory = self.run_prefix(controls=controls)
        self.assertEqual(report['status'], 'FAILED')
        self.assertEqual(len(report['terminals']), 2)
        self.assertEqual(len([r for r in memory.regions.values() if r.published and not r.readonly]), 1)

    def test_window_identity_profile_and_alias_reject_before_dma(self):
        for windows in ((p.ColumnWindow(0, 32), p.ColumnWindow(0, 32)),
                        (p.ColumnWindow(1, 32),), (p.ColumnWindow(8192, 32),),
                        (p.ColumnWindow(0, 31),), ()):
            with self.subTest(windows=windows), self.assertRaises(ValueError):
                self.run_prefix(windows=windows)
        self.profile = replace(self.profile, source_sha256='bad')
        with self.assertRaises(ValueError):
            self.run_prefix()
        self.assertEqual(self.matrix.counts['owner_acquires'], 0)

    def test_interruption_preserves_inflight_actual_output_and_never_publishes(self):
        memory = dense.TypedMemory()
        def controls(stage, _, d):
            if stage != 'input_norm' and d.pending_ack is not None:
                raise TimeoutError('test bounded interruption with real write outstanding')
            return {}
        with self.assertRaises(p.PrefixExecutionError) as raised:
            self.run_prefix(controls=controls, memory=memory)
        failure = raised.exception
        self.assertEqual(failure.execution_report['status'], 'INTERRUPTED')
        self.assertEqual(failure.snapshot['stage'], 'qkv_columns_0')
        self.assertTrue(failure.snapshot['shared_memory_pending'])
        self.assertTrue(failure.snapshot['pending_ack'])
        self.assertFalse(failure.snapshot['terminal_accepted'])
        self.assertFalse(failure.snapshot['output_published'])
        self.assertEqual(p.sha(failure.partial_output), failure.snapshot['partial_output_sha256'])
        self.assertEqual(len(failure.partial_output), 1024)
        self.assertEqual(len(failure.execution_report['terminals']), 1)


class ConvHandoffTests(unittest.TestCase):
    """Small synthetic N32 fixture only; actual 35B full geometry is a separate run."""
    setUpClass = classmethod(PrefixTests.setUpClass.__func__)
    setUp = PrefixTests.setUp
    def conv_case(self, **kwargs):
        from unittest.mock import patch
        weights = np.zeros((32,4), '<u2'); weights[:,3]=0x3f80
        with patch.object(p, 'OUTPUTS', 32):
            return p.execute_prefix(self.hidden, self.weight, self.nk[:32*2048*2],
                tokens=16, windows=(p.ColumnWindow(0,32),), profile=self.profile,
                matrix=self.matrix, vector=self.vector, deadline=time.monotonic()+90,
                conv_weights=weights.tobytes(), **kwargs)

    def test_conv_same_memory_scalar_and_unpublished_history(self):
        observed=[]; pre=[]
        report,memory=self.conv_case(observe=lambda *x: observed.append(x),
                                    conv_observe=lambda *x:pre.append(x))
        self.assertEqual(report['status'],'PASS_TYPED_PREFIX_EXECUTION_ONLY')
        self.assertTrue(report['actual_qkv_region_consumed'])
        self.assertEqual(len(report['terminals']),3)
        self.assertEqual([x[0] for x in observed],['input_norm','qkv_columns_0','conv4_silu','conv_history_staging'])
        self.assertEqual(len(pre),16*32)
        stage=report['conv_history_staging']
        self.assertFalse(stage['published']);self.assertFalse(stage['generation_advanced'])
        self.assertFalse(memory.regions[stage['address']].published)

    def test_conv_final_ack_failure_never_commits_history(self):
        def controls(stage,i,driver):
            if stage=='conv4_silu' and driver.pending is not None and driver.owner.request.write:
                return {'ack_error': driver.owner.ack_bytes+64==driver.job.write_bytes}
            return {}
        with self.assertRaises(p.PrefixExecutionError) as error:
            self.conv_case(controls=controls)
        self.assertEqual(error.exception.snapshot['stage'],'conv4_silu')
        self.assertFalse(error.exception.snapshot['output_published'])
        self.assertFalse(error.exception.snapshot['history_published'])
        self.assertEqual(len(error.exception.partial_history),32*8)


if __name__ == '__main__':
    unittest.main()
