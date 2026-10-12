"""Optional CPython 3.12 transport for the unchanged official-BF16 observer.

Only source-bound owner code receives LINE/PY_RETURN events. Irrelevant LINE
locations are disabled for this tool alone. The ten actual causal fields,
coverage checks and accepted-terminal seal come from observation.py. Nothing
here changes arithmetic, services, scheduling, publication or resource counts.

The caller must freeze this file in source_sha256 as well as the existing
observer closure. This candidate is not selected by any production runner.
API contract: https://docs.python.org/3.12/library/sys.monitoring.html
"""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import sys
import threading

from . import observation as original

MONITORING = 'candidates/qwen2_resident_matrix/official_bf16/observation_monitoring.py'


def verify_monitoring_dependencies(owner, sources):
    original.require(MONITORING in sources,
                     'snapshot must include the monitoring transport')
    count = original.verify_loaded_dependencies(owner)
    count += original._verify_module(sys.modules[__name__], MONITORING)
    return count


class OfficialAttentionMonitoringObservation(original.OfficialAttentionObservation):
    """Single-use, thread-bound capture; never replaces a tracer or used ID."""

    def __init__(self, owner, *, source_sha256):
        super().__init__(owner, source_sha256=source_sha256)
        self.loaded_functions_checked = verify_monitoring_dependencies(owner, self.sources)
        self.instrumentation_sha256 = original.base.sha(Path(__file__).read_bytes())
        self.tool_id = None
        self._tool_name = 'official-bf16-observation-' + str(id(self))
        self._registered = {}
        self._configured = {}
        self._line_callback = self._monitor_line
        self._return_callback = self._monitor_return
        self._target_lines = {
            self.codes['_attention']: frozenset(self.points[n] for n in ('score', 'exp', 'store')),
            self.codes['_matrix_step']: frozenset((self.points['matrix'],)),
        }

    def __enter__(self):
        original.require(threading.get_ident() == self.thread, 'observation thread changed')
        original.require(not self.active and not self.closed and self.started == 0,
                         'observer is single-use')
        original.require(sys.gettrace() is None, 'existing tracer must not be replaced')
        original.require(self.owner.state == 'idle' and not self.owner.poison and
                         self.owner.matrix.owner is None and not self.owner.matrix.reset_required and
                         self.owner.scalar.client is None, 'observe before an idle owner launch')
        original.verify_source_snapshot(self.sources)
        original.require(verify_monitoring_dependencies(self.owner, self.sources) ==
                         self.loaded_functions_checked, 'loaded dependencies changed before entry')
        monitor = sys.monitoring
        # Avoid the conventional debugger/coverage/profiler/optimizer slots.
        # use_tool_id performs the actual claim, including a racing claim check.
        for candidate in (3, 4):
            if monitor.get_tool(candidate) is not None:
                continue
            if monitor.get_events(candidate) or any(
                    monitor.get_local_events(candidate, code) for code in self.codes.values()):
                continue
            try:
                monitor.use_tool_id(candidate, self._tool_name)
            except ValueError:
                continue
            self.tool_id = candidate
            break
        original.require(self.tool_id is not None, 'no unused monitoring tool ID (3 or 4)')
        try:
            for event, callback in ((monitor.events.LINE, self._line_callback),
                                    (monitor.events.PY_RETURN, self._return_callback)):
                previous = monitor.register_callback(self.tool_id, event, callback)
                if previous is not None:
                    # free_tool_id does not clear stale callbacks. Restore one
                    # before refusing this slot; never silently take it over.
                    monitor.register_callback(self.tool_id, event, previous)
                    raise ValueError('monitoring tool ID retains an existing callback')
                self._registered[event] = callback
            for code in self._target_lines:
                monitor.set_local_events(self.tool_id, code, monitor.events.LINE)
                self._configured[code] = monitor.events.LINE
            monitor.set_local_events(self.tool_id, self.codes['tick'], monitor.events.PY_RETURN)
            self._configured[self.codes['tick']] = monitor.events.PY_RETURN
            self.active = True
        except BaseException:
            self._stop()
            self.closed = True
            raise
        return self

    def _stop(self):
        """Remove only this tool's events/callbacks; never touch sys.settrace."""
        self.disarmed = True
        if self.tool_id is None:
            return
        monitor, tool = sys.monitoring, self.tool_id
        if monitor.get_tool(tool) != self._tool_name:
            self.error = self.error or 'observer monitoring tool was replaced'
            self.tool_id = None
            return
        intact = monitor.get_events(tool) == 0
        for code, expected in self._configured.items():
            if monitor.get_local_events(tool, code) != expected:
                intact = False
            else:
                # Only unchanged registrations still belong to this observer.
                # Preserve a foreign replacement mask, just as its callback.
                monitor.set_local_events(tool, code, 0)
        for event, callback in self._registered.items():
            previous = monitor.register_callback(tool, event, None)
            if previous is not callback:
                intact = False
                monitor.register_callback(tool, event, previous)
        if not intact:
            self.error = self.error or 'observer monitoring registration was replaced'
        # A foreign registration or callback is left alone, just as an
        # externally replaced sys.settrace callback must be left alone.
        if intact:
            monitor.free_tool_id(tool)
        self._configured.clear()
        self._registered.clear()
        self.tool_id = None

    def _diagnostic_failure(self, error):
        self.error = self.error or str(error)
        try:
            self._stop()
        except Exception as cleanup_error:
            self.error += '; monitoring cleanup failed: ' + str(cleanup_error)

    def _monitor_line(self, code, line_number):
        targets = self._target_lines.get(code)
        if targets is None:
            return
        if line_number not in targets:
            # Source locations are owner-independent. Never disable a target
            # just because another owner/thread executed it first.
            return sys.monitoring.DISABLE
        if not self.active or self.disarmed or self.error is not None:
            return
        try:
            frame = sys._getframe(1)
            original.require(frame.f_code is code and frame.f_lineno == line_number,
                             'monitoring LINE frame mismatch')
            if frame.f_locals.get('self') is not self.owner:
                return
            original.require(threading.get_ident() == self.thread, 'observation thread changed')
            self._line(frame)
        except Exception as error:
            self._diagnostic_failure(error)

    def _monitor_return(self, code, instruction_offset, edge):
        if (code is not self.codes['tick'] or not self.active or self.disarmed or
                self.error is not None):
            return
        try:
            frame = sys._getframe(1)
            original.require(frame.f_code is code, 'monitoring PY_RETURN frame mismatch')
            if frame.f_locals.get('self') is not self.owner:
                return
            original.require(threading.get_ident() == self.thread, 'observation thread changed')
            if not isinstance(edge, dict):
                return
            if edge['job_fire']:
                self._start(edge)
            if edge['response_fire']:
                original.require(self.terminal is None and self.started == 1,
                                 'duplicate/unowned terminal')
                self.terminal = asdict(edge['response'])
                self.retirement = dict(state=self.owner.state, poison=self.owner.poison,
                    same_services=(self.owner.matrix is self.services[0] and self.owner.scalar is self.services[1]),
                    same_job=asdict(self.owner.job) == self.job,
                    matrix_released=self.owner.matrix.owner is None,
                    matrix_reset_required=self.owner.matrix.reset_required,
                    client_retired=self.owner.matrix_client is None,
                    memory_pending=self.owner.memory_pending,
                    scalar_released=self.owner.scalar.client is None)
                self._stop()
        except Exception as error:
            # Diagnostics cannot change or swallow an owner transition.
            self._diagnostic_failure(error)

    def __exit__(self, kind, error, traceback):
        wrong_thread = threading.get_ident() != self.thread
        if wrong_thread:
            self.error = self.error or 'observation thread changed'
        try:
            self._stop()
        finally:
            self.active, self.closed = False, True
        # Monitoring registrations are interpreter-wide, so a rejected close
        # from another thread must still release them and invalidate the seal.
        original.require(not wrong_thread, 'observation thread changed')
        if kind is not None:
            self.error = self.error or 'driver exited with an exception'
        if sys.gettrace() is not None:
            self.error = self.error or 'a tracer was installed during monitoring'
        try:
            original.require(original.verify_source_snapshot(self.sources) == self.execution_sources,
                             'execution inventory drift')
            original.require(verify_monitoring_dependencies(self.owner, self.sources) ==
                             self.loaded_functions_checked, 'loaded dependency inventory changed')
        except Exception as failure:
            self.error = self.error or str(failure)
            raise
        return False

    def report(self):
        report = super().report()
        report['trace_api'] = 'CPython sys.monitoring per-code LINE/PY_RETURN source-bound read-only local snapshots'
        report['capture_source_sha256'] = {original.OBSERVER: self.sources[original.OBSERVER]}
        report['monitoring_source_sha256'] = {MONITORING: self.sources[MONITORING]}
        return report
