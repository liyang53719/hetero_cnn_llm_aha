"""Public four-command FFN orchestration over the existing physical models.

This file implements no arithmetic, memory, owner or counter model. It clocks
the public Host on the same edges as the original owner/coordinator, and uses
the original numeric drivers. The caller freezes sources before loading real
inputs and owns any post-terminal independent comparisons. Model ticks and
observed host FMAs are not hardware cycles or measured utilization.
"""
from array import array
from collections import Counter
from dataclasses import asdict, dataclass
import importlib.util
import json
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
from candidates.qwen2_resident_matrix.ffn_public.model import group as public_group


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


numeric = load_module('public_ffn_original_numeric', HERE.parent / 'ffn_fullgroup/check_numeric.py')
down_driver = load_module('public_ffn_original_down', HERE.parent / 'ffn_fullgroup/down_driver.py')
require = numeric.require


@dataclass(frozen=True)
class ErrorTerminal:
    """Field view of a genuine rejected owner response, without fake totals.

    Host rejects status before inspecting arithmetic counters. A successful
    terminal must instead use the completed driver's observed counters.
    """
    tag: int
    status: str
    write_bytes: int


class PublicExecution:
    """Handshake bridge; no request, successful terminal or total is invented.

    Completion/result ready default low so callers can observe and backpressure
    every public response. ``ordinary_edge`` is the optional original Down
    driver's callback and invokes this exact owner once per call.
    """
    def __init__(self, frontend, owner, trace, deadline, *, host=None, prefix_owner=None,
                 attention_owner=None, matrix_service=None):
        self.frontend, self.owner, self.trace, self.deadline = frontend, owner, trace, deadline
        self.host = host if host is not None else public_group.HostControl(enabled=True)
        require(frontend.launch(self.host), 'public raw frontend launch rejected')
        workspace, region = owner.workspace, frontend.config.regions[3]
        require(frontend.config.transposed_down and workspace is not None and
                workspace.base == region.base and workspace.base + workspace.extent <= region.limit and
                workspace.generation == frontend.config.epoch + 1,
                'original owner workspace differs from raw launch configuration')
        require(owner.state == 'idle' and not owner.ports()['reset_required'] and
                owner.tiles.banks is owner.a_banks and owner.tiles.idle and not owner.tiles.leased,
                'public launch requires the quiescent original owner/banks')
        self.counts, self.completions, self.requests = Counter(), [], []
        self.completion_ready = self.result_ready = False
        self.coupled = self.down_job = self.down_terminal = self.launch_result = None
        self.down_terminal_tick = self.down_start_tick = None
        self.bank_ids = (id(owner), id(owner.a_banks), id(owner.b_banks), id(owner.tiles.banks))
        self.last_host_edge = None
        self.prefix_owner = prefix_owner
        self.attention_owner, self.matrix_service = attention_owner, matrix_service
        if attention_owner is not None:
            require(prefix_owner is not None and attention_owner.scalar is prefix_owner.scalar
                    and attention_owner.matrix is matrix_service,
                    'Attention and prefix must share the identical scalar and Matrix services')
        self.prefix_jobs = self.prefix_results = 0
        self.attention_jobs = self.attention_results = 0
        self.ordinary_history = []
        self.window_matrix_bridge = None

    def reset_required(self):
        reset = self.owner.ports().get('reset_required', False)
        if self.coupled is not None:
            reset = reset or self.coupled.c.poison or self.coupled.services().error
        if self.prefix_owner is not None:
            reset = reset or self.prefix_owner.ports()['reset_required']
        if self.attention_owner is not None:
            reset = reset or self.attention_owner.ports()['reset_required']
        if self.matrix_service is not None:
            reset = reset or self.matrix_service.reset_required
        return bool(reset)

    def ports(self):
        return self.host.ports(reset_required=self.reset_required())

    def _host_edge(self, *, request_ready=False, owner_result=None, reset_required=False):
        require(time.monotonic() <= self.deadline, 'public FFN host budget exceeded')
        require(self.bank_ids == (id(self.owner), id(self.owner.a_banks),
                id(self.owner.b_banks), id(self.owner.tiles.banks)), 'public path replaced owner/banks')
        before = self.host.state
        raw_reset = bool(reset_required or self.reset_required())
        edge = self.host.tick(request_ready=request_ready, owner_result=owner_result,
            completion_ready=self.completion_ready,
            result_ready=self.result_ready, reset_required=raw_reset)
        self.counts['host_model_ticks'] += 1
        for name in ('request_fire', 'owner_result_fire', 'completion_fire', 'result_fire'):
            self.counts[name] += bool(edge[name])
        if edge['request_fire']:
            request = edge['group_request'] or edge['ordinary_request']
            require(request is not None, 'Host accepted no public request')
            self.requests.append(dict(kind='group' if edge['group_request'] else 'ordinary',
                                      request=asdict(request), tick=self.counts['host_model_ticks']))
        if edge['completion_fire']:
            self.completions.append(dict(**asdict(edge['completion']), tick=self.counts['host_model_ticks']))
        if edge['result_fire']:
            self.launch_result = dict(edge['launch_result'])
        if before != self.host.state or any(edge[k] for k in
                ('request_fire', 'owner_result_fire', 'completion_fire', 'result_fire')):
            self.trace.event(dict(kind='public_host', tick=self.counts['host_model_ticks'],
                edge=edge, state_after=self.host.state, events=sorted(self.host.events),
                published=self.host.published, virtual=self.host.virtual))
        self.last_host_edge = edge
        return edge

    def idle_edge(self, *, owner_result=None, **inputs):
        """An actual owner edge followed by the Host edge; no implicit request."""
        before_reset = self.reset_required()
        edge = self.owner.tick(**inputs)
        self.counts['idle_owner_edges'] += 1
        self._host_edge(owner_result=owner_result, reset_required=before_reset)
        return edge

    def prefix_edge(self, **inputs):
        """One existing Host edge coupled to a source-bound prefix memory owner.

        The Matrix owner stays in this same execution instance, idle between
        Dense commands. No opaque successful prefix terminal is accepted here.
        """
        require(self.prefix_owner is not None, 'prefix backend not attached')
        require(self.owner.state == 'idle' and self.owner.lease is None and
                self.owner.tiles.idle and not self.owner.ports()['response'],
                'prefix scalar/memory owner conflicts with Matrix obligations')
        hp, pp = self.ports(), self.prefix_owner.ports()
        before_reset = self.reset_required()
        if 'job' in inputs:
            decoded = hp['ordinary_request']
            require(decoded is inputs['job'] and hp['group_request'] is None and
                    decoded.kind in ('Norm', 'Bias', 'Rope', 'KvAppend', 'Add'),
                    'prefix backend must accept the original public job object')
        require('response_ready' not in inputs, 'prefix result readiness is owned by Host')
        inputs['response_ready'] = hp['owner_result_ready']
        edge = self.prefix_owner.tick(**inputs)
        self.owner.tick()
        accepted = bool(edge.get('job_fire'))
        terminal = pp['response'] if edge.get('response_fire') else None
        self.prefix_jobs += accepted
        self.prefix_results += terminal is not None
        self._host_edge(request_ready=accepted, owner_result=terminal, reset_required=before_reset)
        require(bool(self.last_host_edge['request_fire']) == accepted and
                bool(self.last_host_edge['owner_result_fire']) == (terminal is not None),
                'public/prefix request or terminal handshake disagreement')
        return edge

    def retire_ordinary_bookkeeping(self):
        """Retire one Dense driver association after its public completion fires."""
        require(self.down_job is not None and self.down_terminal is not None and
                self.host.state in ('decode', 'finish') and
                self.host.pc == (self.down_job.tag & 0xffff) + 1 and
                self.host.status is None and self.owner.state == 'idle',
                'Dense bookkeeping retirement before public completion')
        self.ordinary_history.append(dict(job=asdict(self.down_job),
            terminal=list(self.down_terminal), owner_terminal_tick=self.down_terminal_tick,
            owner_start_tick=self.down_start_tick))
        self.down_job = self.down_terminal = None
        self.down_start_tick = self.down_terminal_tick = None

    def attention_edge(self, **inputs):
        """Couple the real legacy Attention backend to this same public launch.

        Its Matrix packets go through the same acquired service used by Dense.
        Host counts consume only the backend's accepted terminal after DDR ACKs.
        """
        backend = self.attention_owner
        require(backend is not None and backend.matrix is self.matrix_service,
                'Attention backend/shared Matrix service not attached')
        require(self.owner.state == 'idle' and self.owner.lease is None and self.owner.tiles.idle
                and self.owner.ports()['response'] is None and self.prefix_owner.state == 'idle',
                'Attention conflicts with retained Dense/prefix obligations')
        hp, pp = self.ports(), backend.ports()
        before_reset = self.reset_required()
        if 'job' in inputs:
            decoded = hp['ordinary_request']
            require(decoded is inputs['job'] and decoded.kind == 'Attention'
                    and hp['group_request'] is None,
                    'Attention must accept this original fused public owner job')
        require('response_ready' not in inputs, 'Attention result readiness belongs to Host')
        inputs['response_ready'] = hp['owner_result_ready']
        edge = backend.tick(**inputs)
        self.owner.tick()
        accepted = bool(edge.get('job_fire'))
        terminal = pp['response'] if edge.get('response_fire') else None
        self.attention_jobs += accepted
        self.attention_results += terminal is not None
        self._host_edge(request_ready=accepted, owner_result=terminal, reset_required=before_reset)
        require(bool(self.last_host_edge['request_fire']) == accepted and
                bool(self.last_host_edge['owner_result_fire']) == (terminal is not None),
                'public/Attention request or terminal handshake disagreement')
        return edge

    def advance_to_request(self, limit=4096):
        for _ in range(limit):
            ports = self.ports()
            if ports['group_request'] is not None or ports['ordinary_request'] is not None:
                return ports
            require(self.host.status is None and self.host.state not in ('finish', 'locked'),
                    'Host failed before public backend issue: ' + str(self.host.reason))
            self.idle_edge()
        raise ValueError('public metadata decode/scan did not terminate within bound')

    def start_group(self):
        ports = self.advance_to_request()
        request = ports['group_request']
        require(request is not None and self.coupled is None, 'expected one actual public group request')
        self.coupled = PublicCoupled(self, request)
        _, edge = self.coupled.tick(start=True)
        require(edge['request_fire'] and self.last_host_edge['request_fire'] and
                self.coupled.call is self.host.group, 'public/coordinator group handshake mismatch')
        return self.coupled

    def ordinary_edge(self, **inputs):
        """Clock the original owner once; stage its real terminal for counters.

        Successful FMA observations are owned by execute_down and only become
        available when it returns. Until then the Host remains in waitDone,
        including on the owner's final response edge. Raw poison is visible
        throughout, and no completion may be published while it is outstanding.
        """
        ports = self.ports()
        before_reset = self.reset_required()
        before_clock = self.owner.clock
        if 'job' in inputs:
            decoded = ports['ordinary_request']
            require(decoded is not None and ports['group_request'] is None and self.down_job is None,
                    'ordinary owner issue before original public request')
            require(all(getattr(inputs['job'], key) == value for key, value in asdict(decoded).items()),
                    'ordinary Down differs from public decoded job')
        require(self.down_job is not None or 'job' in inputs, 'ordinary edge without public job admission')
        edge = self.owner.tick(**inputs)
        self.counts['ordinary_owner_edges'] += 1
        accepted = ('job' in inputs and edge['job_ready'] and self.owner.job is inputs['job'])
        if accepted:
            self.down_job, self.down_start_tick = inputs['job'], before_clock
        rejected = None
        if edge.get('response_fire'):
            require(self.down_terminal is None, 'duplicate ordinary terminal')
            self.down_terminal, self.down_terminal_tick = edge['response'], self.owner.clock
            if self.down_terminal[1] is not None:
                rejected = ErrorTerminal(*self.down_terminal)
        self._host_edge(request_ready=accepted, owner_result=rejected, reset_required=before_reset)
        require(bool(self.last_host_edge['request_fire']) == bool(accepted),
                'public/ordinary request handshake mismatch')
        require(not self.last_host_edge['completion_fire'] and not self.last_host_edge['result_fire'],
                'public completion before original Down driver retired')
        return edge

    def accept_down_terminal(self, report):
        require(self.down_terminal is not None and list(self.down_terminal) == report['completion'],
                'Down report has no matching accepted original owner terminal')
        require(report['completed'] and report['same_owner_and_banks'] and
                report['accepted']['response_handshakes'] == 1 and
                report['physical_traffic']['down_ack_bytes'] == self.down_terminal[2],
                'Down report is not completed accepted-traffic evidence')
        require(self.owner.state == 'idle' and not self.reset_required(), 'Down terminal not quiescent')
        terminal = numeric.group.OwnerResult(*self.down_terminal,
            report['protocol_model_ticks'], report['useful_macs'], report['executed_macs'])
        self.idle_edge(owner_result=terminal)
        require(self.last_host_edge['owner_result_fire'], 'Host did not accept actual Down terminal')

    def publish_completions(self, expected_pcs, *, stall_edges=3):
        for pc in expected_pcs:
            held = self.ports()['completion']
            require(held is not None and held.pc == pc and held.status is None,
                    'original Host completion identity/status/order')
            before = (set(self.host.events), list(self.host.published), self.host.completed)
            self.completion_ready = False
            for _ in range(stall_edges):
                self.idle_edge()
                require(self.ports()['completion'] == held and
                        before == (set(self.host.events), list(self.host.published), self.host.completed),
                        'held Host completion changed or published early')
                self.counts['completion_backpressure_edges'] += 1
            self.completion_ready = True
            self.idle_edge()
            self.completion_ready = False
            require(self.last_host_edge['completion_fire'], 'Host completion did not handshake')

    def finish(self, *, stall_edges=3):
        held = self.ports()['launch_result']
        require(held is not None and held['status'] is None, 'no successful public launch result')
        for _ in range(stall_edges):
            self.idle_edge()
            require(self.ports()['launch_result'] == held, 'held Host launch result changed')
            self.counts['result_backpressure_edges'] += 1
        self.result_ready = True
        self.idle_edge()
        self.result_ready = False
        require(self.launch_result == held and self.host.state == 'idle', 'Host launch result not retired')
        return self.launch_result

    def report(self):
        return dict(accepted=dict(self.counts), requests=self.requests, completions=self.completions,
            launch_result=self.launch_result, events=sorted(self.host.events),
            published=self.host.published, virtual=self.host.virtual,
            reset_required=self.reset_required(), same_owner_and_banks=True,
            down_terminal_tick=self.down_terminal_tick, trace=self.trace.report(),
            counters_source='Original accepted coordinator terminal and original Down driver successful td_step observations; no shape-derived totals.',
            model_ticks_are_hardware_cycles=False)


class PublicCoupled(numeric.Coupled):
    """Original Coupled implementation, with one matching public Host edge."""
    def __init__(self, execution, request):
        super().__init__(execution.owner, request, execution.trace, execution.deadline)
        self.execution = execution

    def tick(self, *, start=False, group_result_ready=False, **inputs):
        x = self.execution
        hp, cp = x.ports(), self.c.ports(self.services())
        before_reset = x.reset_required()
        if start:
            require(hp['group_request'] is self.call and cp['request_ready'],
                    'coordinator start has no matching offered public group')
        edge, ce = super().tick(start=start,
            group_result_ready=hp['owner_result_ready'], **inputs)
        bridge = x.window_matrix_bridge
        if bridge is not None:
            # Match the real owner/Matrix handshakes. A C return only offers a
            # result; the shared resource stays owned through accepted done
            # and the coordinator's genuine window terminal.
            if edge.get('result_fire'):
                bridge.retire_result(inputs['result'], ticket=bridge.ticket, epoch=bridge.epoch)
            if inputs.get('matrix_done') is not None and edge.get('matrix_done_ready'):
                bridge.retire_done(inputs['matrix_done'], ticket=bridge.ticket, epoch=bridge.epoch)
            if ce['window_result_fire']:
                x.matrix_service.retire_owner_response(x.owner)
                x.matrix_service.release(x.owner)
        he = x._host_edge(request_ready=ce['request_fire'],
            owner_result=cp['result'] if ce['result_fire'] else None,
            reset_required=before_reset)
        require(he['request_fire'] == ce['request_fire'] and
                he['owner_result_fire'] == ce['result_fire'],
                'Host/coordinator request or terminal handshake disagreement')
        return edge, ce


def execute_windows(execution, lib, memory, outputs, out, *, window_limit=56):
    """Orchestrate unchanged window/SiLU/drain helpers, optionally partial tests."""
    require(1 <= window_limit <= 56, 'invalid bounded window count')
    h, owner = execution.coupled, execution.owner
    require(h is not None and h.call is execution.host.group, 'no accepted public group')
    tile_trace = numeric.CappedTrace(Path(out) / 'silu_events_prefix.jsonl')
    reports, retained = [], None
    def window(ng, role):
        if execution.matrix_service is None:
            return numeric.execute_window(h, lib, memory, ng, role)
        require(execution.window_matrix_bridge is None, 'overlapping public Matrix window')
        request = h.next_request('window_request')
        require(execution.matrix_service.acquire(owner, 'dense', request.job.tag),
                'FFN window could not acquire the shared Matrix')
        bridge = execution.matrix_service.dense_library(owner)
        execution.window_matrix_bridge = bridge
        try:
            result = numeric.execute_window(h, bridge, memory, ng, role)
            require(execution.matrix_service.owner is None,
                    'FFN window returned before genuine Matrix/owner retirement')
            execution.window_matrix_bridge = None
            return result
        except Exception:
            # A host-driver exception is not an accepted hardware terminal.
            # Quarantine and retain the adapter so existing result/done/seed
            # obligations can still be drained; never clear ownership here.
            if execution.matrix_service.owner is owner:
                execution.matrix_service.abort(owner)
            raise
    try:
        for ng in range(0, window_limit * numeric.WINDOW, numeric.WINDOW):
            gate = window(ng, 'gate')
            current = numeric.tile_check.bank_region_hash(owner.a_banks.words, 0, 768)
            retained = current if retained is None else retained
            require(current == retained, 'later public Gate changed retained A')
            up = window(ng, 'up')
            silu = numeric.execute_silu(h, lib, ng, outputs, tile_trace)
            drain = numeric.execute_drain(h, memory.act, ng)
            require(numeric.tile_check.bank_region_hash(owner.a_banks.words, 0, 768) == retained,
                    'public Up/SiLU/drain changed retained A')
            reports.append(dict(ng=ng, gate=gate, up=up, silu=silu, drain=drain))
            with (Path(out) / 'completed_window_receipts.jsonl').open('a') as stream:
                stream.write(json.dumps(reports[-1], sort_keys=True, separators=(',', ':')) + '\n')
            (Path(out) / 'progress.json').write_text(json.dumps(dict(windows=len(reports),
                host_state=execution.host.state, coordinator_state=h.c.state,
                accepted_act_ack_bytes=memory.act.ack_bytes)) + '\n')
        return dict(windows=reports, retained_a_sha256=retained,
                    silu_trace=tile_trace.report(), partial_synthetic_windows=window_limit if window_limit < 56 else None)
    finally:
        tile_trace.close()


def execute_program(frontend, lib, memory, owner, out, deadline):
    """Execute Gate, Up, SiLU and Down from raw public metadata.

    Return (actual_outputs, evidence). No input loading, source freezing or
    reference access occurs here. The caller supplies the existing owner with
    the frozen workspace and the unchanged arithmetic library.
    """
    out = Path(out)
    trace = numeric.CappedTrace(out / 'public_host_events_prefix.jsonl')
    down_trace = numeric.CappedTrace(out / 'down_events_prefix.jsonl')
    execution = PublicExecution(frontend, owner, trace, deadline)
    try:
        require(len(execution.host.program) == 4, 'public numeric scope is exactly four FFN commands')
        require(owner.workspace.split_k == 2560, 'public full FFN requires original Down split2560')
        h = execution.start_group()
        rows = h.call.gate.m
        outputs = {role: array('I', [numeric.drain_check.SENTINEL_WORD]) * (rows * numeric.WIDTH)
                   for role in ('gate', 'up')}
        report = dict(scope='RAW_PUBLIC_FOUR_COMMAND_FFN_HOST_PORT_NUMERIC_MODEL_ONLY')
        report['group'] = execute_windows(execution, lib, memory, outputs, out)
        for _ in range(16):
            if h.terminal is not None:
                break
            h.tick()
        require(h.terminal is not None and h.terminal.status is None and
                h.c.state == 'idle' and owner.lease is None, 'actual public group did not retire')
        raw, report['act_ddr'] = memory.act.validate_full()
        outputs['act'] = array('I'); outputs['act'].frombytes(raw)
        require(h.terminal.write_bytes == memory.act.ack_bytes and
                h.terminal.useful_macs == sum(r['useful_macs'] for r in h.window_reports) and
                h.terminal.executed_macs == sum(r['executed_macs'] for r in h.window_reports),
                'public coordinator terminal differs from actual accepted traffic')
        report['coordinator'] = dict(accepted=dict(h.counts), terminal=asdict(h.terminal),
            window_terminals=h.window_reports, drain_terminals=h.drain_reports, handoffs=h.handoffs)
        execution.publish_completions((0, 1, 2))
        require(execution.host.completed == 3 and memory.act.ack_bytes == memory.act.extent,
                'Down before all three original public completions and actual act ACKs')
        ports = execution.advance_to_request()
        require(ports['ordinary_request'] is not None and ports['group_request'] is None,
                'Down was not offered by original ordinary Host path')
        job = numeric.decode_job(ports['ordinary_request'])
        report['down'], outputs['down'] = down_driver.execute_down(numeric.model, owner, lib,
            memory, job, out, deadline, down_trace, owner_tick=execution.ordinary_edge)
        execution.accept_down_terminal(report['down'])
        execution.publish_completions((3,))
        execution.finish()
        report['host'] = execution.report()
        require(report['host']['launch_result']['completed'] == 4 and
                report['host']['launch_result']['jobs'] == 2 and
                report['host']['launch_result']['write_bytes'] == h.terminal.write_bytes + report['down']['ddr']['ack_bytes'],
                'Host original terminal/completion totals disagree')
        report['virtual_outputs_after_down'] = memory.check_virtual()
        report.update(down_trace=down_trace.report(), same_owner_and_banks=True,
            full_ffn_host_model_executed=True, full_block_executed=False,
            public_host_python_model_executed=True, scala_host_executed=False,
            rtl_executed=False, actual_idma=False, protocol_model_ticks_are_hardware_cycles=False,
            native_m128_and_fp32_final_acceptance='UNCHANGED_FAIL_POLICY_PENDING')
        for role, words in outputs.items():
            (out / ('actual_' + role + '.f32le')).write_bytes(words.tobytes())
        return outputs, report
    finally:
        down_trace.close()
        trace.close()
