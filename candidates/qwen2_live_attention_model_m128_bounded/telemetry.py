"""Sparse read-only snapshots and bounded entry deadlines; no model monkeypatches."""
import json
import resource
import signal
import time
import traceback


class BudgetExceeded(TimeoutError):
    pass


class OuterTermination(RuntimeError):
    pass


def snapshot(context):
    """Read existing Python control/counter fields, without invoking any model method.

    Snapshots occur at entry stages or original Attention driver loop boundaries.
    They are diagnostic, not terminal evidence, and never replace accepted counters.
    """
    x, physical, service, shared = (context.get(n) for n in ('x', 'physical', 'service', 'shared'))
    result = dict(peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                  model_ticks_are_hardware_cycles=False, snapshot_is_acceptance=False)
    if x is not None:
        h, a, o = x.host, x.attention_owner, x.owner
        result['public'] = dict(pc=h.pc, completed=h.completed, jobs=h.jobs, state=h.state,
            status=h.status, events=sorted(h.events), published=[list(p) for p in h.published],
            launch_result_present=x.launch_result is not None, accepted=dict(x.counts))
        result['attention'] = dict(state=a.state, accepted=dict(a.counts),
            owner_clock=a.clock, ack_bytes=a.ack_bytes,
            matrix_requests=a.counts.get('matrix_requests', 0), matrix_results=a.counts.get('matrix_results', 0),
            functional_state_ticks=dict(a.functional_state_ticks))
        result['debts'] = dict(matrix_owned=service.owner is not None,
            scalar_owned=shared.client is not None, dma_pending=physical.pending is not None,
            owner_pending=o.pending is not None, owner_fifo=len(o.fifo),
            owner_read=o.read_active is not None, owner_a_hold=o.a_hold is not None,
            owner_a_rmw=o.a_rmw_pending is not None, accepted_write=o.accepted_write is not None,
            tile_lease=o.tiles.leased, tile_busy=not o.tiles.idle, a_lease=o.lease is not None,
            reduction_active=x.reduction is not None, prefix_not_idle=x.prefix_owner.state != 'idle',
            attention_not_idle=a.state != 'idle', attention_memory_pending=a.memory_pending,
            attention_abort_pending=a.abort_pending, attention_client_live=a.matrix_client is not None,
            attention_matrix_request=a.matrix_request is not None)
    if physical is not None:
        result['physical_accepted'] = dict(physical.counts)
        result['physical_outputs'] = {n: dict(written_bytes=len(r['written']) * 64,
            ack_bytes=len(r['acked']) * 64, terminal=r['terminal'], published=r['published'])
            for n, r in physical.regions.items() if not r['readonly']}
    if service is not None:
        result['matrix_accepted'] = dict(service.counts)
    if shared is not None:
        result['scalar_calls'] = dict(shared.calls)
    return result


class SparseTelemetry:
    def __init__(self, path, *, started, cpu, budget=900):
        self.path, self.started, self.cpu = path, started, cpu
        self.deadline = started + budget
        self.stage = 'preflight'; self.context = {}; self.history = []; self.samples = 0
        self.active = False; self.emitting = False

    def emit(self, reason, *, driver=None):
        if self.emitting:
            return
        self.emitting = True
        try:
            record = dict(schema=1, reason=reason, stage=self.stage,
                elapsed_seconds=time.monotonic() - self.started,
                cpu_seconds=time.process_time() - self.cpu, **snapshot(self.context))
            if driver is not None:
                record['driver'] = driver
            with self.path.open('a') as stream:
                stream.write(json.dumps(record, sort_keys=True, allow_nan=False) + '\n')
            self.samples += 1
        finally:
            self.emitting = False

    def mark(self, stage):
        self.stage = stage
        self.history.append(dict(stage=stage, elapsed_seconds=time.monotonic() - self.started))
        self.emit('stage')
        self.check()

    def check(self):
        if time.monotonic() >= self.deadline:
            raise BudgetExceeded('M128 bounded entry total wall budget exceeded')

    def _alarm(self, signum, frame):
        raise BudgetExceeded('M128 bounded entry total wall budget exceeded')

    def _terminate(self, signum, frame):
        raise OuterTermination('M128 bounded entry received supervisor termination')

    def start(self):
        if signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0):
            raise ValueError('existing timer cannot be replaced')
        self.previous = {s: signal.getsignal(s) for s in (signal.SIGALRM, signal.SIGTERM)}
        signal.signal(signal.SIGALRM, self._alarm)
        signal.signal(signal.SIGTERM, self._terminate)
        signal.setitimer(signal.ITIMER_REAL, max(.001, self.deadline - time.monotonic()))
        self.active = True

    def stop(self):
        if self.active:
            signal.setitimer(signal.ITIMER_REAL, 0)
            for signum, handler in self.previous.items():
                signal.signal(signum, handler)
            self.active = False

    def report(self):
        return dict(stage_history=list(self.history), samples=self.samples,
                    attention_loop_interval=131072, diagnostic_only=True,
                    signal_reads_model=False,
                    no_model_method_replacement=True, no_counter_writes=True)


def is_budget(error):
    return isinstance(error, BudgetExceeded) or str(error) in (
        'public FFN host budget exceeded', 'Attention memory driver exceeded host budget')


def stage_message(stage, error):
    return 'M128 ' + stage + ': ' + ('software wall deadline exceeded' if is_budget(error) else str(error))


def contextual_error(stage, error):
    return RuntimeError(stage_message(stage, error)) if is_budget(error) else error


def attach_failure(report, error, *, stage, started, cpu, gate, context):
    report.update(status='FAILED', acceptance_sealed=False, official_observed_node_pass=False,
        failure_stage=stage, error=repr(error), original_error_type=type(error).__name__,
        original_error_message=str(error), stage_error=stage_message(stage, error),
        failure_kind='BUDGET_EXCEEDED' if is_budget(error) else 'EXECUTION_FAILURE',
        traceback=traceback.format_exc(), host_wall_seconds=time.monotonic() - started,
        host_cpu_seconds=time.process_time() - cpu,
        peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        oracle_opened=gate.opened, oracle_reference_reads=list(gate.reference_reads), oracle_blocked_reads=gate.blocked)
    report['native_artifact_audit'] = list(getattr(gate, 'artifact_reads', []))
    try:
        report['failure_snapshot'] = snapshot(context)
    except Exception as capture_error:
        report['failure_snapshot_error'] = repr(capture_error)
    for key, obj in (('physical_memory', context.get('physical')), ('execution', context.get('x')),
                     ('matrix', context.get('service'))):
        if obj is not None:
            try:
                report['failed_' + key] = obj.report()
            except Exception as capture_error:
                report['failed_' + key + '_error'] = repr(capture_error)
    return report
