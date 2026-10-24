"""Actual zero-job observer I/O qualification, never a model substitute."""
from collections import Counter
from dataclasses import asdict
import hashlib
from pathlib import Path
import sys


def need(ok, message):
    if not ok:
        raise ValueError(message)


def observe_empty_lifecycle(*, Capture, owner, source_root, source_manifest,
                            out, trace_limits, dispatcher, gate):
    """Delegate the original constructor/enter/exit/save once on real objects.

    Native identity getters and the original source guards may execute. No
    owner/service transaction, producer, request or arithmetic is invoked here.
    An empty, sealed event stream is not complete algorithm observation.
    """
    root = Path(source_root).resolve()
    manifest = Path(source_manifest).resolve()
    candidate = manifest.parent
    destination = Path(out).resolve() / 'empty_attention_observer'
    need(not destination.exists(), 'fresh zero-job observer destination required')
    need(not gate.opened and not gate.reference_reads and not gate.provenance_reads,
         'zero-job qualification requires a closed, unread oracle')
    need(type(trace_limits['max_m']) is int and trace_limits['max_m'] == 128 and
         dispatcher is not None, 'actual M128-capable observer and dispatcher required')
    calls, active = [], [True]
    payloads = gate.input_paths | gate.raw_paths | gate.reference_paths

    def route_audit(event, args):
        if not active[0] or event != 'open' or not isinstance(args[0], (str, bytes)):
            return
        raw = args[0].decode() if isinstance(args[0], bytes) else args[0]
        path = Path(raw).absolute()
        need(path not in payloads, 'zero-job observer must not open any operand or reference payload')
        need(len(calls) < 4096 and len(raw) <= 4096, 'bounded observer route capture exceeded')
        frame = sys._getframe(1)
        site = None
        for _ in range(12):
            if frame is None:
                break
            filename = Path(frame.f_code.co_filename)
            if filename.is_absolute() and filename.is_relative_to(candidate):
                relative = str(filename.relative_to(candidate))
                if relative.startswith(('observation/', 'capture/')):
                    site = dict(source=relative, function=frame.f_code.co_name,
                                line=frame.f_lineno)
                    break
            frame = frame.f_back
        calls.append(dict(path=raw, mode=args[1], flags=args[2], site=site))

    sys.addaudithook(route_audit)
    capture = None
    try:
        capture = Capture(owner, root, manifest, destination,
                          trace_limits=trace_limits, trace_dispatcher=dispatcher)
        need(capture.owner is owner and capture.dispatcher is dispatcher and
             capture.started == 0 and capture.fields == {} and capture.job is None,
             'original zero-job observer constructor boundary changed')
        need(type(capture.loaded_checked) is int and capture.loaded_checked > 0,
             'real original loaded-identity guard must check source functions')
        with capture:
            need(capture.active and capture.started == 0 and capture.fields == {} and
                 capture.registration is not None,
                 'original observer did not register with the live dispatcher')
        need(capture.closed and not capture.active and capture.error is None,
             'observer exit/readonly revalidation failed')
        summary = capture.save(destination)
        need(capture.saved and capture.started == 0 and capture.fields == {} and
             capture.job is None and capture.terminal is None and capture.retirement is None,
             'zero-job observer invented model state')
        need(summary['status'] == 'INCOMPLETE' and summary['complete_observation'] is False and
             summary['observer_error'] is None and summary['fields'] == {} and
             summary['event_count'] == 0 and summary['job'] is None and
             summary['terminal'] is None and summary['accepted_retirement'] is None,
             'empty observer must explicitly remain incomplete')
        need(capture.stream_seal is not None and capture.stream_seal.records == 0 and
             capture.stream_seal.raw_bytes == 0 and capture.stream.count == 0,
             'empty event stream must have its real zero-record terminal seal')
        need(not gate.opened and not gate.reference_reads and not gate.provenance_reads and
             gate.blocked == 0, 'observer lifecycle crossed oracle/read admission')
    finally:
        active[0] = False

    counts = Counter(row['path'] for row in calls)
    selected = {str(path): counts[str(path)] for path in sorted(gate.selected_source_paths)}
    need(len(selected) == 9 and set(selected.values()) == {3},
         'all nine witnesses must be read by constructor, enter and exit')
    need(counts[str(manifest)] == 3, 'all three original closure manifests must be read')
    files = sorted(path.name for path in destination.iterdir())
    need(files == ['attention-events.lec1', 'summary.json'],
         'empty lifecycle must not create fabricated arrays or presence files')
    artifacts = {}
    for name in files:
        path = destination / name
        raw = path.read_bytes()
        artifacts[name] = dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    return dict(
        schema='fixed93-actual-zero-job-observer-read-route-v1',
        status='PASS_ACTUAL_EMPTY_OBSERVER_LIFECYCLE_ROUTES_ONLY',
        constructor_called_once=True, enter_called_once=True, exit_called_once=True,
        save_called_once=True, real_loaded_identity_guard=True,
        loaded_functions_checked=capture.loaded_checked,
        real_m128_capable_observer=True, real_wholeblock_dispatcher=True,
        same_owner_and_services=True, selected_source_read_counts=selected,
        closure_manifest_reads=counts[str(manifest)], actual_open_routes=calls,
        event_codec_seal=asdict(capture.stream_seal), artifacts=artifacts,
        observer_status=summary['status'], complete_observation=False,
        fields_created=0, observed_jobs=0, algorithm_arrays_created=False,
        observer_error=summary['observer_error'], oracle_payload_reads=0,
        reference_opened=False, model_arithmetic_executed_by_probe=False,
        native_identity_getters_may_execute=True, M128_execution=False,
        fullblock_acceptance=False, numerical_acceptance=False, RTL=False)
