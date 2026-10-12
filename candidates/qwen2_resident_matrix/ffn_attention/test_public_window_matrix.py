"""Shared Matrix window retirement on genuine public FFN owner edges."""
from array import array
import ctypes as C
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from candidates.qwen2_resident_matrix.ffn_attention import matrix_service as ms
from candidates.qwen2_resident_matrix.ffn_public import execute_numeric as e
from candidates.qwen2_resident_matrix.ffn_public.test_execute_numeric import make_execution, bits


class PublicWindowMatrixTests(unittest.TestCase):
    def make(self):
        path = os.environ.get('MATRIX_SERVICE_LIBRARY')
        self.assertTrue(path, 'use one reviewed precompiled combined library')
        library = ms.configure_library(C.CDLL(path))
        self.assertEqual(library.td_reset(), 0)
        self.assertEqual(library.sf_reset(), 0)
        library.sf_vector.argtypes, library.sf_vector.restype = [C.POINTER(C.c_uint32)] * 6, C.c_int
        _, x = make_execution()
        x.matrix_service = ms.MatrixService(library)
        x.start_group()
        n = e.numeric
        inputs = {'n1': array('I', [0]) * (128 * n.K),
                  'gate_weight': array('H', [0]) * (n.K * n.WIDTH),
                  'up_weight': array('H', [0]) * (n.K * n.WIDTH),
                  'down_weight': array('H', [0]) * (n.K * n.WIDTH)}
        for row in range(16):
            inputs['n1'][row*n.K + 17] = bits((row+1)/16)
        for col in range(160):
            inputs['gate_weight'][col*n.K + 17] = 0x3f00
            inputs['up_weight'][col*n.K + 17] = 0x3f80
        outputs = {r: array('I', [0xa5963cc3]) * (16*n.WIDTH) for r in ('gate', 'up')}
        return x, library, n.Memory(inputs, 16), outputs

    def test_real_gate_up_result_done_owner_retirement_order(self):
        x, lib, memory, outputs = self.make()
        events = []
        original_bridge = x.matrix_service.dense_library
        def adapter(owner):
            bridge = original_bridge(owner)
            for name in ('retire_result', 'retire_done'):
                original = getattr(bridge, name)
                def edge(*args, name=name, original=original, **kw):
                    events.append(name)
                    return original(*args, **kw)
                setattr(bridge, name, edge)
            return bridge
        original_terminal = x.matrix_service.retire_owner_response
        def terminal(owner):
            events.append('owner_terminal')
            self.assertIsNone(owner.ports()['window_result'])
            return original_terminal(owner)
        original_tick = x.coupled.tick
        late, terminal_edges = {}, []
        def tick(**inputs):
            for key in ('result', 'matrix_done'):
                if inputs.get(key) is not None:
                    late[key] = inputs[key]
            finishing = x.owner.ports()['window_result'] is not None
            if finishing:
                # Duplicate late pins on the actual terminal edge are not
                # accepted result/done handshakes and cannot retire twice.
                inputs.update(late)
            edge, ce = original_tick(**inputs)
            if finishing:
                self.assertTrue(ce['window_result_fire'])
                self.assertFalse(edge['result_fire'] or edge.get('matrix_done_fire'))
                terminal_edges.append(ce)
            return edge, ce
        with tempfile.TemporaryDirectory() as directory, patch.object(x.matrix_service, 'dense_library', adapter), \
                patch.object(x.matrix_service, 'retire_owner_response', terminal), \
                patch.object(x.coupled, 'tick', tick):
            r = e.execute_windows(x, lib, memory, outputs, Path(directory), window_limit=1)
        self.assertEqual(events, (['retire_result']*5 + ['retire_done', 'owner_terminal'])*2)
        self.assertEqual(x.matrix_service.report()['dense_fma_calls'], 1536*5*4096*2)
        self.assertIsNone(x.matrix_service.owner)
        self.assertIsNone(x.window_matrix_bridge)
        self.assertEqual(len(terminal_edges), 2)
        self.assertEqual(r['partial_synthetic_windows'], 1)
        self.assertEqual((x.host.completed, x.host.state), (0, 'waitDone'))
        for row in range(16):
            self.assertEqual(outputs['gate'][row*e.numeric.WIDTH], bits((row+1)/32))
            self.assertEqual(outputs['up'][row*e.numeric.WIDTH], bits((row+1)/16))

    def test_driver_exception_keeps_poisoned_owned_resource_and_adapter(self):
        x, lib, memory, outputs = self.make()
        class FaultMemory:
            act = memory.act
            def read64(self, address):
                raise ValueError('injected transport failure at actual accepted read')
        with tempfile.TemporaryDirectory() as directory, self.assertRaisesRegex(ValueError, 'injected transport'):
            e.execute_windows(x, lib, FaultMemory(), outputs, Path(directory), window_limit=1)
        self.assertIs(x.matrix_service.owner, x.owner)
        self.assertTrue(x.matrix_service.reset_required)
        self.assertIsNotNone(x.window_matrix_bridge)
        self.assertFalse(x.matrix_service.acquire(object(), 'normal', 42))
        self.assertEqual(x.matrix_service.counts['owner_responses'], 0)
        self.assertIsNone(x.host.result)
        self.assertEqual(x.host.published, [])
        with self.assertRaises(ms.MatrixProtocolError):
            x.matrix_service.release(x.owner)

    def test_early_done_with_last_result_same_edge_is_rejected_and_quarantined(self):
        x, lib, memory, outputs = self.make()
        original = x.coupled.tick
        injected = []
        def tick(**inputs):
            result = inputs.get('result')
            if result is not None and result.context == 4 and not injected:
                inputs['matrix_done'] = e.numeric.model.MatrixDone(x.coupled.call.gate.tag)
                injected.append(True)
            return original(**inputs)
        with tempfile.TemporaryDirectory() as directory, patch.object(x.coupled, 'tick', tick), \
                self.assertRaisesRegex(ValueError, 'matrix done before all accepted steps/results'):
            e.execute_windows(x, lib, memory, outputs, Path(directory), window_limit=1)
        self.assertEqual(injected, [True])
        self.assertTrue(x.matrix_service.reset_required)
        self.assertIs(x.matrix_service.owner, x.owner)
        self.assertIsNotNone(x.window_matrix_bridge)
        self.assertFalse(x.matrix_service.acquire(object(), 'normal', 43))
        self.assertEqual((x.host.completed, x.host.published), (0, []))


if __name__ == '__main__':
    unittest.main()
