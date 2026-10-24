"""Run unchanged existing client tests plus a synthetic host-event histogram.

Required: --source-root RAW_CHECKOUT. The shared test loader verifies all pinned
source bytes before extracting exact AST definitions. No original test, client,
owner, service implementation, or numerical policy is rewritten. ScriptedService
is explicitly a protocol test double. Host ticks below are NOT hardware cycles.
"""
from collections import Counter
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from routing_test_support import (arithmetic, client, definitions, drive_owner,
                                  make_owner, matrix, scripted)


_original = definitions('attention_packed_owner/test_client.py',
    ('pv', 'deliver', 'finish', 'ClientTests'), environment={
        **vars(matrix), **vars(client), 'ScriptedService': scripted.ScriptedService,
        'ArithmeticFault': arithmetic.ArithmeticFault, 'unittest': unittest})
# Exact, unchanged unittest class and original test fixtures/functions.
OriginalClientTests = _original.ClientTests
CONTROL_HISTOGRAM = None


class HostControlHistogramTests(unittest.TestCase):
    def test_m2_actual_owner_host_event_histogram(self):
        global CONTROL_HISTOGRAM
        _, service, _, owner, job = make_owner(2)
        actual_tick = owner.tick
        states, accepted, waits = Counter(), Counter(), Counter()
        ticks = 0
        fire_names = ('job_fire', 'memory_fire', 'memory_response_fire',
                      'matrix_request_fire', 'matrix_result_fire', 'response_fire',
                      'scratch_fire', 'scratch_response_fire')

        def observed_tick(**kwargs):
            nonlocal ticks
            result = actual_tick(**kwargs)
            ticks += 1
            states[result['state']] += 1
            for name in fire_names:
                accepted[name] += int(bool(result.get(name, False)))
            waits['no_owner_port_handshake_ticks'] += int(not any(
                result.get(name, False) for name in fire_names))
            waits['memory_request_backpressure_ticks'] += int(
                result['memory'] is not None and not result['memory_fire'])
            waits['memory_response_wait_ticks'] += int(
                result['memory_response_ready'] and not result['memory_response_fire'])
            waits['matrix_request_backpressure_ticks'] += int(
                result['matrix'] is not None and not result['matrix_request_fire'])
            waits['matrix_response_wait_ticks'] += int(
                result['state'] == 'matrix_wait' and not result['matrix_result_fire'])
            waits['terminal_backpressure_ticks'] += int(
                result['response'] is not None and not result['response_fire'])
            return result

        # Observe the actual method; do not alter its source or control flow.
        owner.tick = observed_tick
        result = drive_owner(owner, job, stall=True)
        self.assertIsNone(result.response.status)
        self.assertEqual(ticks, result.ticks + 1)  # Includes the admission tick.
        self.assertEqual(sum(states.values()), ticks)
        self.assertEqual(accepted['job_fire'], 1)
        self.assertEqual(accepted['response_fire'], 1)
        self.assertEqual(accepted['memory_fire'], 960)
        self.assertEqual(accepted['memory_response_fire'], 960)
        self.assertEqual(accepted['matrix_request_fire'], 504)
        self.assertEqual(accepted['matrix_result_fire'], 504)
        self.assertEqual(accepted['scratch_fire'], 0)
        self.assertEqual(accepted['scratch_response_fire'], 0)
        self.assertGreater(waits['no_owner_port_handshake_ticks'], 0)
        self.assertGreater(waits['memory_request_backpressure_ticks'], 0)
        self.assertGreater(waits['memory_response_wait_ticks'], 0)
        self.assertGreater(waits['matrix_request_backpressure_ticks'], 0)
        self.assertGreater(waits['matrix_response_wait_ticks'], 0)
        self.assertEqual(service.counts['owner_acquires'], 1)
        self.assertEqual(service.counts['owner_releases'], 1)
        CONTROL_HISTOGRAM = dict(
            scope='M2 synthetic words; unchanged composed owner/client control',
            units='host Python tick calls and pre-edge state/port observations',
            host_tick_calls=ticks,
            pre_edge_state_observations=dict(sorted(states.items())),
            accepted_owner_port_edges=dict(sorted(accepted.items())),
            wait_observations=dict(sorted(waits.items())),
            observations_may_overlap=True,
            no_handshake_is_not_a_hardware_idle_measure=True,
            hardware_cycles=False, hardware_utilization=False,
            native_arithmetic_executed=False)


if __name__ == '__main__':
    program = unittest.main(verbosity=2, exit=False)
    if CONTROL_HISTOGRAM is not None:
        print(json.dumps(CONTROL_HISTOGRAM, sort_keys=True))
    raise SystemExit(0 if program.result.wasSuccessful() else 1)
