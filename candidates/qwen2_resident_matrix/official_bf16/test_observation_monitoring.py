"""Bounded synthetic M1/M2 transport parity; never compile or use model weights.

MATRIX_SERVICE_LIBRARY must name the existing receipt-verified host library.
Wall times printed here measure Python instrumentation, not RTL performance.
"""
from contextlib import nullcontext
from dataclasses import replace
import hashlib
import json
import sys
import threading
import time
import unittest
from unittest.mock import patch

from . import observation as old
from . import observation_monitoring as new
from . import test_observation as fixture


def snapshot():
    sources = fixture.snapshot()
    sources[new.MONITORING] = hashlib.sha256((old.ROOT / new.MONITORING).read_bytes()).hexdigest()
    return sources


class MonitoringObservationTests(unittest.TestCase):
    make = fixture.OfficialObservationTests.make

    @classmethod
    def setUpClass(cls):
        cls.library = fixture.verified_library()

    def capture(self, harness):
        return new.OfficialAttentionMonitoringObservation(harness.owner, source_sha256=snapshot())

    def assert_released(self, capture, tool):
        self.assertTrue(capture.disarmed)
        self.assertIsNone(capture.tool_id)
        self.assertIsNone(sys.monitoring.get_tool(tool))
        self.assertEqual(sys.monitoring.get_events(tool), 0)
        for code in capture.codes.values():
            self.assertEqual(sys.monitoring.get_local_events(tool, code), 0)
        for event in (sys.monitoring.events.LINE, sys.monitoring.events.PY_RETURN):
            self.assertIsNone(sys.monitoring.register_callback(tool, event, None))

    def execute(self, tokens, transport):
        h, job, data = self.make(tokens)
        capture = transport(h.owner, source_sha256=snapshot()) if transport else None
        edges = hashlib.sha256()
        with capture if capture else nullcontext():
            start = time.perf_counter()
            for tick in range(30000):
                edge = h.tick(job=job if tick == 0 else None, memory_ready=tick % 3 != 0,
                    respond=tick % 5 != 0, matrix_request_ready=tick % 7 != 0,
                    matrix_result_ready=tick % 11 != 0, service_result_ready=tick % 13 != 0,
                    service_done_ready=tick % 17 != 0, response_ready=tick % 19 == 0)
                edges.update(repr(tuple((key, edge[key]) for key in sorted(edge))).encode())
                if edge['response_fire']:
                    result = edge['response']
                    self.assertIsNone(result.status)
                    self.assertFalse(h.bus.outputs[job.dst].intersection(h.bus.readable))
                    h.bus.publish(h.owner, job)
                    break
            else:
                self.fail('small actual Attention watchdog')
            elapsed = time.perf_counter() - start
        return dict(h=h, job=job, data=data, result=result, edges=edges.hexdigest(),
                    capture=capture, steps=tick + 1, seconds=elapsed)

    def test_m1_m2_off_trace_monitoring_identical_all_edges_counts_fields_hashes(self):
        timings = {}
        for tokens in (1, 2):
            baseline = self.execute(tokens, None)
            traced = self.execute(tokens, old.OfficialAttentionObservation)
            monitored = self.execute(tokens, new.OfficialAttentionMonitoringObservation)
            for result in (traced, monitored):
                self.assertEqual(result['edges'], baseline['edges'])
                self.assertEqual(result['steps'], baseline['steps'])
                self.assertEqual(result['result'], baseline['result'])
                self.assertEqual(result['h'].bus.trace, baseline['h'].bus.trace)
                self.assertEqual(result['h'].owner.report(), baseline['h'].owner.report())
                self.assertEqual(result['h'].owner.matrix.report(), baseline['h'].owner.matrix.report())
                self.assertEqual(result['h'].bus.raw(result['job'].dst),
                                 baseline['h'].bus.raw(baseline['job'].dst))
                self.assertEqual(result['capture'].report()['status'],
                                 'COMPLETE_OWNER_OBSERVATION_NOT_NATIVE_ACCEPTED')
            previous, current = traced['capture'], monitored['capture']
            self.assertEqual(current.fields, previous.fields)
            self.assertEqual(len(current.fields), 10)
            for key in ('job', 'terminal', 'accepted_retirement', 'observer_error', 'fields'):
                self.assertEqual(current.report()[key], previous.report()[key])
            report = current.report()
            for key in ('future_scores_observed', 'full_29_node_gate', 'whole_block_terminal_observed',
                        'physical_publication_observed', 'hardware_simulation'):
                self.assertFalse(report[key])
            self.assertEqual(report['native_acceptance'], 'NOT_EVALUATED_BY_OBSERVER')
            self.assertEqual(report['instrumentation_sha256'], snapshot()[new.MONITORING])
            timings[str(tokens)] = dict(steps=baseline['steps'], edge_sha256=baseline['edges'],
                off_seconds=baseline['seconds'], settrace_seconds=traced['seconds'],
                monitoring_seconds=monitored['seconds'], fields=report['fields'])
        print('\nSOFTWARE_INSTRUMENTATION_ONLY ' + json.dumps(timings, sort_keys=True), flush=True)

    def test_matrix_done_final_ack_and_held_terminal_do_not_seal(self):
        h, job, _ = self.make()
        with self.capture(h) as capture:
            tool = capture.tool_id
            h.tick(job=job)
            h.until(lambda: h.owner.matrix_client.state == 'wait_done', service_done_ready=False)
            for _ in range(3):
                h.tick(service_done_ready=False)
                self.assertIsNone(capture.terminal)
                self.assertEqual(h.bus.writes, [])
            h.until(lambda: h.bus.pending is not None and h.bus.pending.write
                    and h.owner.ack_bytes == job.write_bytes - 64)
            for _ in range(3):
                h.tick(respond=False)
                self.assertIsNone(capture.terminal)
            h.until(lambda: h.owner.ports()['response'] is not None)
            for _ in range(3):
                h.tick()
                self.assertIsNone(capture.terminal)
                self.assertFalse(capture.disarmed)
            self.assertTrue(h.tick(response_ready=True)['response_fire'])
            self.assert_released(capture, tool)
            before = {name: field['writes'] for name, field in capture.fields.items()}
            h.tick(local_reset=True)
            self.assertEqual(before, {name: field['writes'] for name, field in capture.fields.items()})
        self.assertEqual(capture.report()['status'], 'COMPLETE_OWNER_OBSERVATION_NOT_NATIVE_ACCEPTED')

    def test_failed_final_ack_wrong_done_and_resets_cannot_seal(self):
        for mode in ('last_ack', 'wrong_done', 'active_reset', 'held_terminal_reset'):
            with self.subTest(mode=mode):
                h, job, _ = self.make()
                with self.capture(h) as capture:
                    tool = capture.tool_id
                    h.tick(job=job)
                    if mode == 'last_ack':
                        h.until(lambda: h.bus.pending is not None and h.bus.pending.write
                                and h.owner.ack_bytes == job.write_bytes - 64)
                        h.tick(response=fixture.p.MemoryResponse(h.bus.pending.tag, error=True))
                    elif mode == 'wrong_done':
                        h.until(lambda: h.owner.matrix_client.state == 'wait_done', service_done_ready=False)
                        h.tick(done_override=replace(h.owner.matrix.done, tag=h.owner.matrix.done.tag + 1))
                    elif mode == 'active_reset':
                        h.until(lambda: h.owner.matrix_client.state == 'wait_result')
                        h.tick(local_reset=True)
                    else:
                        h.until(lambda: h.owner.ports()['response'] is not None)
                        self.assertFalse(h.tick(local_reset=True, response_ready=True)['response_fire'])
                    h.until(lambda: h.owner.ports()['response'] is not None)
                    result = h.tick(response_ready=True)['response']
                    self.assert_released(capture, tool)
                self.assertEqual(result.status, 'Memory' if mode == 'last_ack' else 'Protocol')
                self.assertEqual(capture.report()['status'], 'INCOMPLETE')

    def test_missing_duplicate_and_diagnostic_exception_cannot_seal_or_change_owner(self):
        for mode in ('missing', 'duplicate', 'error'):
            with self.subTest(mode=mode):
                h, job, _ = self.make()
                with self.capture(h) as capture:
                    tool = capture.tool_id
                    if mode == 'missing':
                        capture.points['score'] = -1
                    else:
                        put_actual = capture._put
                        def put(name, coordinates, values):
                            put_actual(name, coordinates, values)
                            if name == 'scores_bf16':
                                if mode == 'error':
                                    raise RuntimeError('diagnostic failure')
                                put_actual(name, coordinates, values)
                        capture._put = put
                    self.assertIsNone(h.run(job).status)
                    self.assert_released(capture, tool)
                self.assertEqual(capture.report()['status'], 'INCOMPLETE')

    def test_idle_prefix_and_other_owner_are_not_observed(self):
        h, job, _ = self.make()
        other, other_job, _ = self.make()
        prefix = fixture.Harness(fixture.owners.OfficialPrefixOwner(h.owner.scalar))
        bias = fixture.p.Job('Bias', 99, 0x500000, 0x600000, 0x700000, 1, 256, 256, 1024)
        for address in (bias.a, bias.b):
            prefix.bus.input(address, (0x3f810000,) * 256)
        prefix.bus.output(bias.dst, bias.write_bytes)
        with self.capture(h) as capture:
            self.assertIsNone(prefix.run(bias).status)
            self.assertIsNone(other.run(other_job).status)
            self.assertEqual(capture.started, 0)
            self.assertEqual(capture.fields, {})
            self.assertIsNone(h.run(job).status)
        self.assertEqual(capture.report()['status'], 'COMPLETE_OWNER_OBSERVATION_NOT_NATIVE_ACCEPTED')

    def test_close_before_accepted_terminal_stays_incomplete(self):
        h, job, _ = self.make()
        with self.capture(h) as capture:
            tool = capture.tool_id
            h.tick(job=job)
            h.until(lambda: h.owner.ports()['response'] is not None)
            self.assertIsNone(capture.terminal)
            with self.assertRaisesRegex(ValueError, 'close the observer'):
                capture.report()
        self.assert_released(capture, tool)
        self.assertEqual(capture.report()['status'], 'INCOMPLETE')
        self.assertTrue(h.tick(response_ready=True)['response_fire'])
        self.assertIsNone(capture.terminal)
        self.assertEqual(capture.report()['status'], 'INCOMPLETE')

    def test_source_and_loaded_transport_mutations_rejected(self):
        h, _, _ = self.make()
        for name in (new.MONITORING, old.OBSERVER, old.OWNER, old.SERVICE,
                     next(iter(old.base.verify_execution_sources()))):
            sources = snapshot()
            sources.pop(name)
            with self.subTest(omitted=name), self.assertRaises(ValueError):
                new.OfficialAttentionMonitoringObservation(h.owner, source_sha256=sources)
        sources = snapshot()
        sources[new.MONITORING] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'source drift'):
            new.OfficialAttentionMonitoringObservation(h.owner, source_sha256=sources)
        for name in ('_monitor_line', '_monitor_return', '_stop', 'report'):
            with patch.object(new.OfficialAttentionMonitoringObservation, name, lambda *args: None):
                with self.assertRaisesRegex(ValueError, 'function changed'):
                    self.capture(h)
        capture = self.capture(h)
        with patch.object(new.OfficialAttentionMonitoringObservation, '_monitor_line', lambda *args: None):
            with self.assertRaisesRegex(ValueError, 'function changed'):
                capture.__enter__()
        self.assertIsNone(capture.tool_id)

    def test_occupied_slots_stale_callbacks_and_existing_trace_are_preserved(self):
        h, _, _ = self.make()
        def existing(*args):
            return None
        capture = self.capture(h)
        sys.settrace(existing)
        try:
            with self.assertRaisesRegex(ValueError, 'existing tracer'):
                capture.__enter__()
            self.assertIs(sys.gettrace(), existing)
        finally:
            sys.settrace(None)
        for tool in (3, 4):
            sys.monitoring.use_tool_id(tool, 'test-existing-' + str(tool))
        try:
            with self.assertRaisesRegex(ValueError, 'no unused monitoring'):
                capture.__enter__()
            self.assertEqual(sys.monitoring.get_tool(3), 'test-existing-3')
            self.assertEqual(sys.monitoring.get_tool(4), 'test-existing-4')
        finally:
            for tool in (3, 4):
                sys.monitoring.free_tool_id(tool)
        event = sys.monitoring.events.LINE
        sys.monitoring.register_callback(3, event, existing)
        try:
            with self.assertRaisesRegex(ValueError, 'existing callback'):
                capture.__enter__()
            self.assertIs(sys.monitoring.register_callback(3, event, None), existing)
            self.assertIsNone(sys.monitoring.get_tool(3))
        finally:
            sys.monitoring.register_callback(3, event, None)

    def test_exception_cleanup_and_later_tracer_are_preserved(self):
        h, _, _ = self.make()
        with self.assertRaisesRegex(RuntimeError, 'driver stopped'):
            with self.capture(h) as capture:
                tool = capture.tool_id
                raise RuntimeError('driver stopped')
        self.assert_released(capture, tool)
        self.assertIn('exception', capture.report()['observer_error'])
        def existing(*args):
            return None
        try:
            with self.capture(h) as capture:
                tool = capture.tool_id
                sys.settrace(existing)
            self.assertIs(sys.gettrace(), existing)
            self.assert_released(capture, tool)
            self.assertIn('tracer', capture.report()['observer_error'])
        finally:
            sys.settrace(None)

    def test_unrelated_monitor_coexists_and_is_not_restarted_or_removed(self):
        monitor, tool = sys.monitoring, 3
        calls = []
        def sample():
            return 7
        def existing(code, offset, result):
            calls.append((code, result))
            return monitor.DISABLE
        monitor.use_tool_id(tool, 'unrelated-monitor')
        monitor.register_callback(tool, monitor.events.PY_RETURN, existing)
        monitor.set_local_events(tool, sample.__code__, monitor.events.PY_RETURN)
        try:
            sample()
            self.assertEqual(len(calls), 1)
            h, job, _ = self.make()
            with self.capture(h) as capture:
                self.assertEqual(capture.tool_id, 4)
                self.assertEqual(monitor.get_events(4), 0)
                self.assertEqual(monitor.get_local_events(4, capture.codes['tick']),
                                 monitor.events.PY_RETURN)
                for name in ('_attention', '_matrix_step'):
                    self.assertEqual(monitor.get_local_events(4, capture.codes[name]), monitor.events.LINE)
                self.assertIsNone(h.run(job).status)
                self.assert_released(capture, 4)
            sample()
            self.assertEqual(len(calls), 1)
            self.assertEqual(monitor.get_tool(tool), 'unrelated-monitor')
            self.assertEqual(monitor.get_local_events(tool, sample.__code__), monitor.events.PY_RETURN)
            self.assertIs(monitor.register_callback(tool, monitor.events.PY_RETURN, None), existing)
            self.assertEqual(capture.report()['status'], 'COMPLETE_OWNER_OBSERVATION_NOT_NATIVE_ACCEPTED')
        finally:
            monitor.set_local_events(tool, sample.__code__, 0)
            monitor.register_callback(tool, monitor.events.PY_RETURN, None)
            monitor.free_tool_id(tool)

    def test_callback_replacement_is_rejected_without_destroying_foreign_callback(self):
        h, _, _ = self.make()
        def foreign(*args):
            return None
        with self.capture(h) as capture:
            tool = capture.tool_id
            sys.monitoring.register_callback(tool, sys.monitoring.events.LINE, foreign)
        try:
            self.assertEqual(capture.report()['status'], 'INCOMPLETE')
            self.assertIn('replaced', capture.report()['observer_error'])
            self.assertIs(sys.monitoring.register_callback(tool, sys.monitoring.events.LINE, None), foreign)
            for code in capture.codes.values():
                self.assertEqual(sys.monitoring.get_local_events(tool, code), 0)
        finally:
            sys.monitoring.register_callback(tool, sys.monitoring.events.LINE, None)
            sys.monitoring.free_tool_id(tool)

    def test_owner_on_another_thread_is_incomplete_and_cleans_up(self):
        h, job, _ = self.make()
        results = []
        with self.capture(h) as capture:
            tool = capture.tool_id
            worker = threading.Thread(target=lambda: results.append(h.run(job)))
            worker.start()
            worker.join(timeout=10)
            self.assertFalse(worker.is_alive())
            self.assertEqual(len(results), 1)
            self.assertIsNone(results[0].status)
            self.assert_released(capture, tool)
        self.assertEqual(capture.report()['status'], 'INCOMPLETE')
        self.assertIn('thread changed', capture.report()['observer_error'])

    def test_exit_rechecks_loaded_transport_after_releasing_events(self):
        h, _, _ = self.make()
        capture = self.capture(h)
        capture.__enter__()
        tool = capture.tool_id
        with patch.object(new.OfficialAttentionMonitoringObservation, '_monitor_line', lambda *args: None):
            with self.assertRaisesRegex(ValueError, 'function changed'):
                capture.__exit__(None, None, None)
        self.assert_released(capture, tool)
        self.assertEqual(capture.report()['status'], 'INCOMPLETE')
        with self.assertRaisesRegex(ValueError, 'single-use'):
            capture.__enter__()

    def test_wrong_thread_exit_releases_global_registration_and_rejects_seal(self):
        h, _, _ = self.make()
        capture = self.capture(h)
        capture.__enter__()
        tool = capture.tool_id
        failures = []
        def close_elsewhere():
            try:
                capture.__exit__(None, None, None)
            except Exception as error:
                failures.append(error)
        worker = threading.Thread(target=close_elsewhere)
        worker.start()
        worker.join(timeout=10)
        self.assertFalse(worker.is_alive())
        self.assertEqual(len(failures), 1)
        self.assertIsInstance(failures[0], ValueError)
        self.assertIn('thread changed', str(failures[0]))
        self.assert_released(capture, tool)
        self.assertTrue(capture.closed)
        self.assertFalse(capture.active)
        self.assertEqual(capture.report()['status'], 'INCOMPLETE')
        self.assertIn('thread changed', capture.report()['observer_error'])

    def test_replaced_local_mask_is_preserved_and_rejects_seal(self):
        h, _, _ = self.make()
        with self.capture(h) as capture:
            tool = capture.tool_id
            code = capture.codes['_attention']
            sys.monitoring.set_local_events(tool, code, sys.monitoring.events.PY_RETURN)
        try:
            self.assertTrue(capture.closed)
            self.assertFalse(capture.active)
            self.assertEqual(capture.report()['status'], 'INCOMPLETE')
            self.assertIn('replaced', capture.report()['observer_error'])
            self.assertEqual(sys.monitoring.get_local_events(tool, code), sys.monitoring.events.PY_RETURN)
            self.assertIsNotNone(sys.monitoring.get_tool(tool))
            for name in ('_matrix_step', 'tick'):
                self.assertEqual(sys.monitoring.get_local_events(tool, capture.codes[name]), 0)
            for event in (sys.monitoring.events.LINE, sys.monitoring.events.PY_RETURN):
                self.assertIsNone(sys.monitoring.register_callback(tool, event, None))
        finally:
            sys.monitoring.set_local_events(tool, code, 0)
            sys.monitoring.free_tool_id(tool)


if __name__ == '__main__':
    unittest.main()
