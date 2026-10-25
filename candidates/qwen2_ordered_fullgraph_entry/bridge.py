"""pc12-only binding of existing direct owner, strict lanes and normal observer.

No replacement owner/client/service, no arithmetic implementation, no payload
provider and no whole-block acceptance. Called only by the real suffix dispatch.
"""
from contextlib import ExitStack
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


def make_service_trace(observer, service, profile, bind):
    from .service_trace import make_trace
    return make_trace(observer, service, profile, bind)


def make_dispatch(profile, *, enabled=False):
    """Return a pc12 callable and evidence holder; default does not bind anything."""
    need(type(enabled) is bool, 'explicit ordered fullgraph enable')
    state = {'invocations': 0, 'capture': None, 'capture_report': None,
             'capture_error': None, 'service_events': None, 'service_events_raw': (), 'service_error': None}
    if not enabled:
        return None, state
    need(profile['qk_profile'] == 2 and profile['pv_profile'] == 0 and
         profile['raw_kv_transport'] is False, 'QK-only profile2 / legacy PV0 / uncached direct required')
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
        capture = monitor.Observation(owner, job.m, base.PackedFields, observer.bindings(owner, profile))
        tracer = make_service_trace(observer, x.matrix_service, profile, monitor.bind)
        state['capture'] = capture
        try:
            with ExitStack() as stack:
                stack.enter_context(tracer)
                stack.enter_context(capture)
                report = direct_transport.execute_attention_owner(x, physical, job,
                    final_ack_stall=5, enable_raw_kv=False)
        finally:
            # Keep partial raw evidence even if the original driver raises.
            # This is NOT a successful lifecycle seal or acceptance result.
            state['service_events_raw'] = tuple(getattr(tracer, 'events', ()))
        # These are the original DirectBinding postconditions, not an abstract
        # drain set. Original driver accepted final memory and owner ACKs.
        binding.check(x)
        need(physical.pending is None and x.matrix_service.owner is None,
             'direct pc12 terminal before physical/service retirement')
        try:
            state['capture_report'] = capture.seal()
        except Exception as error:
            state['capture_error'] = type(error).__name__ + ': ' + str(error)
        try:
            state['service_events'] = tracer.seal()
        except Exception as error:
            state['service_error'] = type(error).__name__ + ': ' + str(error)
        # Observer failures are acceptance failures, never injected owner faults.
        # Preserve the real driver result; the whole-launch registry rejects an
        # incomplete capture after the original suffix has retired normally.
        return report

    return dispatch, state
