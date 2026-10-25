"""pc12-only binding of existing direct owner, strict lanes and normal observer.

No replacement owner/client/service, no arithmetic implementation, no payload
provider and no whole-block acceptance. Called only by the real suffix dispatch.
"""
from pathlib import Path
import hashlib
import importlib
import sys


def need(ok, message):
    if not ok:
        raise ValueError(message)


def load_observer_runtime(profile):
    """Load the unchanged, source-pinned M1/M2 runtime helper modules normally."""
    root = Path(profile['observer_runtime_root']).resolve(strict=True)
    for name in ('harness.py', 'runtime_observer.py', 'reference_capture.py'):
        path = root / name
        need(hashlib.sha256(path.read_bytes()).hexdigest() == profile['files'][str(path)]['sha256'],
             'observer runtime source changed: ' + name)
    sys.path.insert(0, str(root))
    for name in ('runtime_observer', 'reference_capture', 'harness'):
        if name in sys.modules:
            need(Path(sys.modules[name].__file__).resolve() == root / (name + '.py'),
                 'foreign observer runtime module: ' + name)
    helper = importlib.import_module('harness')
    observer = importlib.import_module('runtime_observer')
    need(Path(helper.__file__).resolve() == root / 'harness.py' and
         Path(observer.__file__).resolve() == root / 'runtime_observer.py', 'runtime import origin')
    return helper, observer


def make_service_trace(observer, service, profile, bind, event_stream_path):
    from .service_trace import make_trace
    return make_trace(observer, service, profile, bind, event_stream_path)


def make_observation(monitor, owner, rows, base_fields, bindings, *, selective_lines=False):
    from .service_trace import capture_error, monitoring_enter, monitoring_stop
    class FullgraphObservation(monitor.Observation):
        # No _line/_return wrapper: sys._getframe(1) still sees the original DUT.
        def __enter__(self):
            try:
                need(not self.closed and self.tool is None and self.owner.state == 'idle' and
                     not self.owner.poison and sys.gettrace() is None, 'single-use idle observation')
                mon = sys.monitoring
                return monitoring_enter(self, 'ordered-fold-observer', (3, 4),
                    ((mon.events.LINE, self._line), (mon.events.PY_RETURN, self._return)),
                    self.codes.values(), self.monitor_masks())
            except BaseException as error:
                capture_error(self, error)
                self.stop()
                raise
        def stop(self):
            try:
                mon = sys.monitoring
                monitoring_stop(self, (mon.events.LINE, mon.events.PY_RETURN), self.codes.values())
            except BaseException as error:
                capture_error(self, error)
                self.closed = True
                if isinstance(error, KeyboardInterrupt):
                    raise
    # Original constructor/source binding errors intentionally remain fatal.
    return FullgraphObservation(owner, rows, base_fields, bindings, selective_lines=selective_lines)


def observe_driver(tracer, capture, run, state):
    """Only monitor lifetime failures fall back; original driver exceptions escape."""
    entered = []
    try:
        for context, key in ((tracer, 'service_error'), (capture, 'capture_error')):
            try:
                context.__enter__()
                entered.append((context, key))
            except KeyboardInterrupt:
                raise  # Explicit cancellation is not a monitor fallback promise.
            except BaseException as error:
                state[key] = type(error).__name__ + ': ' + str(error)
        return run()
    finally:
        original_error = sys.exc_info()
        cancellation = None
        for context, key in reversed(entered):
            try:
                context.__exit__(*original_error)
            except BaseException as error:
                if state[key] is None:
                    state[key] = type(error).__name__ + ': ' + str(error)
                if isinstance(error, KeyboardInterrupt) and original_error[0] is None and cancellation is None:
                    cancellation = error
        # Finish other distinct cleanup operations, then preserve cancellation.
        # An already active original driver/setup error always keeps its identity.
        if cancellation is not None:
            raise cancellation


def make_dispatch(profile, *, enabled=False, event_stream_path=None):
    """Return a pc12 callable and evidence holder; default does not bind anything."""
    need(type(enabled) is bool, 'explicit ordered fullgraph enable')
    state = {'invocations': 0, 'capture': None, 'capture_report': None,
             'capture_error': None, 'service_events': None, 'service_events_raw': None, 'service_error': None}
    if not enabled:
        return None, state
    need(profile['qk_profile'] == 2 and profile['pv_profile'] == 0 and
         profile['raw_kv_transport'] is False, 'QK-only profile2 / legacy PV0 / uncached direct required')
    need(event_stream_path is not None and 'event_stream_max_bytes' in profile and
         'event_stream_max_events' in profile,
         'independently admitted raw stream destination and byte budget required')
    helper, observer = load_observer_runtime(profile)
    from candidates.qwen2_resident_matrix.production_qk16_model import direct_transport, ordered_work
    exact = helper.load_exact(profile['exact_helper'])
    lanes = helper.lanes(ordered_work, exact)

    def dispatch(x, physical, job):
        need(state['invocations'] == 0 and (job.tag & 0xffff) == 12 and job.kind == 'Attention',
             'one actual public pc12 dispatch required')
        state['invocations'] += 1
        # Reuse the exact real direct binding BEFORE Observation needs its
        # installed schedule and ordered adapter. Never pre-bind then run(),
        # which would bind twice, or construct a synthetic owner.
        binding = direct_transport.bind(x, physical, job, ordered_fold=True, ordered_lanes=lanes)
        owner = x.attention_owner
        monitor, base = observer.load_observer(profile)
        capture = make_observation(monitor, owner, job.m, base.PackedFields, observer.bindings(owner, profile),
            selective_lines=profile.get('selective_observer_lines', False))
        tracer = make_service_trace(observer, x.matrix_service, profile, monitor.bind, event_stream_path)
        state['capture'] = capture
        try:
            report = observe_driver(tracer, capture,
                lambda: direct_transport.execute_attention_owner(x, physical, job,
                    final_ack_stall=5, enable_raw_kv=False), state)
        finally:
            # Keep partial raw evidence even if the original driver raises.
            # This is NOT a successful lifecycle seal or acceptance result.
            original_error = sys.exc_info()
            try:
                state['service_events_raw'] = tracer.raw_receipt()
            except BaseException as error:
                state['service_events_raw_error'] = type(error).__name__ + ': ' + str(error)
                if state['service_error'] is None:
                    state['service_error'] = state['service_events_raw_error']
                if isinstance(error, KeyboardInterrupt) and original_error[0] is None:
                    raise
        # These are the original DirectBinding postconditions, not an abstract
        # drain set. Original driver accepted final memory and owner ACKs.
        binding.check(x)
        need(physical.pending is None and x.matrix_service.owner is None,
             'direct pc12 terminal before physical/service retirement')
        try:
            need(state['capture_error'] is None, 'monitor lifetime failed: ' + str(state['capture_error']))
            state['capture_report'] = capture.seal()
        except Exception as error:
            state['capture_error'] = type(error).__name__ + ': ' + str(error)
        try:
            need(state['service_error'] is None, 'monitor lifetime failed: ' + str(state['service_error']))
            state['service_events'] = tracer.seal()
        except Exception as error:
            state['service_error'] = type(error).__name__ + ': ' + str(error)
        # Observer failures are acceptance failures, never injected owner faults.
        # Preserve the real driver result; the whole-launch registry rejects an
        # incomplete capture after the original suffix has retired normally.
        return report

    return dispatch, state
