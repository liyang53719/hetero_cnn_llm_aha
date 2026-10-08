#!/usr/bin/env python3
"""Source-only timing attribution for independently verified frozen tile16 traces.

This is an accounting/reporting consumer, NOT an arithmetic verifier or RTL gate.
Final reports require the runner's compressed-trace SHA and independent verifier
inventory. A provisional smoke report is deliberately a different binding mode.
No simulation, source mutation, payload copies, or per-cycle arrays are needed.
"""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_matrix_norm_rope_tile16_trace import MAIN, _record

ROOT = Path(__file__).resolve().parents[1]
VERIFIER_SOURCES = (
    'scripts/verify_matrix_norm_rope_tile16_trace.py',
    'scripts/verify_matrix_norm_rope_tensor_trace.py',
    'scripts/verify_matrix_norm_rope_trace.py',
)
# Include the verifier's transitive local imports, including those executed by
# heteronpu.__init__. Third-party/runtime packages are identified by versions.
ANALYSIS_SOURCES = ('scripts/analyze_matrix_norm_rope_tile16_phases.py', *VERIFIER_SOURCES,
                    *(f'src/heteronpu/{name}.py' for name in (
                        '__init__', 'model_geometry', 'qk_norm256_candidate', 'rope_bf16_candidate',
                        'cgra_sfu', 'command', 'config', 'kv_engine', 'matrix_engine',
                        'scheduler', 'dtypes', 'abi_validation')))


def require(condition, message):
    # Explicit checks must remain effective under python -O.
    if not condition:
        raise ValueError(message)


DMA_BUCKETS = {
    'activation': 'dma_activation_owner', 'weight': 'dma_weight_owner',
    'packed': 'ddr_packed_store_owner', 'norm': 'ddr_norm_store_owner',
    'rope': 'ddr_rope_store_owner',
}
BUCKETS = (
    'control_admission', 'descriptor_owner', *DMA_BUCKETS.values(),
    'matrix_operand_read_request', 'matrix_operand_read_owner_wait',
    'matrix_residual_input_control_pipeline', 'packed_producer_write_ack',
    'packed_output_control_admission', 'norm_input_read_request',
    'norm_input_read_owner_wait', 'norm_input_control_admission',
    'norm_compute_boundary_residual', 'norm_producer_write_ack',
    'norm_output_control_admission', 'rope_input_read_request',
    'rope_input_read_owner_wait', 'rope_input_control_admission',
    'rope_compute_boundary_residual', 'rope_producer_write_ack',
    'rope_output_control_admission', 'final_store_control_admission',
)
PRIMARY = {item[0] for item in MAIN}
CONVENTIONS = {
    'exclusive_interval': 'accepted_start through done, both endpoints included',
    'exclusive_equation': 'sum(exclusive_cycles.values()) == done - accepted_start + 1 == terminal.command_cycles',
    'service_owners': 'DMA, descriptor, and producer write ownership includes accepted request and response/ACK cycles. Read request is one cycle; read owner wait is request+1 through response inclusive.',
    'boundary_priority': 'On shared boundary cycles: DMA > producer write/ACK > read > descriptor > residual. Ties within a channel go to the already pending owner. Overlaps are counted separately.',
    'residuals': 'Residual cycles between observed boundaries include unlogged request admission, control, input handshakes and pipeline time. Read admission is not isolated from Matrix input/control. Read-owner waits include injected test-fabric response delays. These are not measurements of isolated compute latency or valid&&!ready stalls.',
    'matrix': 'Matrix input-fire timestamps are not recorded. Accepted input count comes from terminal/projection counters. matrix events are observed accepted OUTPUT handshakes, counted separately even when overlapping other owners.',
    'norm': 'Norm compute boundary is last gamma response+1 through recorded Norm result inclusive; its input-fire timestamp is unavailable.',
    'rope': 'RoPE compute boundary is last trig response+1 through first RoPE write-1. No separate RoPE result/input-fire event is recorded.',
    'overlapping_observables': 'Interval totals and handshake counts are diagnostics, overlap exclusive buckets and each other, and must never be added to the cycle denominator.',
    'environment': 'Randomized test-fabric request stalls and service/ACK delays, including the testbench 512-cycle RoPE-store delay. Not physical DDR bandwidth, isolated hardware compute latency, PPA, or a whole-block metric.',
    'denominator': 'Fixed 512 Matrix lanes times the complete accepted-to-done interval, including all waiting and serial Norm/RoPE time; never active-lane-normalized.',
    'reset': 'Reset-flushed commands have no done/terminal interval and are excluded from completed-command cycle aggregates.',
}


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def source_hashes():
    return {name: digest(ROOT / name) for name in ANALYSIS_SOURCES}


def add_interval(stats, name, first, last):
    require(last >= first - 1, 'negative observable interval: ' + name)
    n = last - first + 1
    v = stats.setdefault(name, {'count': 0, 'sum_cycles': 0, 'min_cycles': n, 'max_cycles': n})
    v['count'] += 1
    v['sum_cycles'] += n
    v['min_cycles'] = min(v['min_cycles'], n)
    v['max_cycles'] = max(v['max_cycles'], n)


def merge_intervals(target, source):
    for key, value in source.items():
        if key not in target:
            target[key] = dict(value)
        else:
            v = target[key]
            v['count'] += value['count']
            v['sum_cycles'] += value['sum_cycles']
            v['min_cycles'] = min(v['min_cycles'], value['min_cycles'])
            v['max_cycles'] = max(v['max_cycles'], value['max_cycles'])


class Command:
    """Account cycle groups without retaining payloads or allocating cycle arrays."""

    def __init__(self, begin):
        self.begin = begin
        self.started = self.done = self.previous = None
        self.phase = 'control_admission'
        self.pending = {}
        self.cycles = Counter({key: 0 for key in BUCKETS})
        self.events = Counter(begin=1)
        self.intervals = {}
        self.outputs_by_bucket = Counter()
        self.overlap_cycles = 0
        self.same_cycle_acks = 0
        self.projection = self.head = None
        self.boundary = {}
        self.read_counts = Counter()
        self.write_counts = Counter()
        self.read_bytes = self.write_bytes = self.completed_heads = 0
        self.projection_inputs = self.projection_outputs = 0
        self.last_matrix_response = None

    @staticmethod
    def owner_bucket(owner, cycle):
        if owner['channel'] == 'read':
            return owner['group'] + ('_read_request' if cycle == owner['cycle'] else '_read_owner_wait')
        return owner['bucket']

    def choose(self, owners, cycle, phase):
        if not owners:
            return phase
        priority = {'dma': 0, 'write': 1, 'read': 2, 'descriptor': 3}
        owner = min(owners, key=lambda o: (priority[o['channel']], o['cycle']))
        return self.owner_bucket(owner, cycle)

    def open_owner(self, channel, r, touched, **extra):
        require(channel not in self.pending, 'duplicate pending ' + channel)
        require(not self.pending, 'overlapping outstanding service owners')
        q = dict(r, channel=channel, **extra)
        self.pending[channel] = q
        touched.append(q)
        return q

    def close_owner(self, channel, r, key, interval):
        require(channel in self.pending, 'response/ACK without ' + channel + ' owner')
        q = self.pending.pop(channel)
        require(r[key] == q[key], 'response/ACK owner identity mismatch')
        require(r['cycle'] >= q['cycle'] + (channel != 'write'), 'response/ACK precedes request')
        add_interval(self.intervals, interval or q['interval'], q['cycle'], r['cycle'])
        return q

    def dma_name(self, r):
        b = self.begin
        if r['kind'] == 1:
            require(r['row_bytes'] in (2, 64), 'unknown DMA load geometry')
            return 'activation' if r['row_bytes'] == 2 else 'weight'
        require(r['kind'] == 3, 'unknown DMA kind')
        source = int(r['source'], 16)
        if source == b['norm_base']:
            return 'norm'
        if source == b['rope_base']:
            return 'rope'
        tiles = 16 if b['role'] == 0 else 8
        require(b['packed_base'] <= source < b['packed_base'] + tiles * 1024,
                'unclassified DMA store')
        return 'packed'

    def consume_cycle(self, records):
        cycle = records[0]['cycle']
        require(all(r['cycle'] == cycle for r in records), 'mixed cycle group')
        require(self.done is None, 'activity after done')
        if self.started is None:
            require(records[0]['event'] == 'accepted_start', 'activity before accepted_start')
            self.started = cycle
            self.previous = cycle - 1
        require(cycle > self.previous, 'non-increasing cycle groups')
        if cycle > self.previous + 1:
            key = self.choose(list(self.pending.values()), self.previous + 1, self.phase)
            self.cycles[key] += cycle - self.previous - 1
        phase_this_cycle = self.phase
        touched = list(self.pending.values())
        outputs = 0
        for r in records:
            event = r['event']
            self.events[event] += 1
            if event == 'accepted_start':
                require(self.events[event] == 1 and cycle == self.started, 'duplicate accepted_start')
            elif event == 'descriptor_request':
                self.open_owner('descriptor', r, touched, bucket='descriptor_owner', interval='descriptor_request_to_response')
            elif event == 'descriptor':
                self.close_owner('descriptor', r, 'index', None)
            elif event == 'dma':
                name = self.dma_name(r)
                self.open_owner('dma', r, touched, name=name, bucket=DMA_BUCKETS[name], interval='dma_' + name + '_request_to_ack')
            elif event == 'dma_ack':
                q = self.close_owner('dma', r, 'index', None)
                if not r['error']:
                    n = q['rows'] * q['row_bytes']
                    if q['kind'] == 1:
                        self.read_bytes += n
                    else:
                        self.write_bytes += n
                if q['name'] == 'weight' and not r['error']:
                    self.phase = 'matrix_residual_input_control_pipeline'
                    self.boundary['matrix_tile'] = cycle + 1
                    self.last_matrix_response = None
                elif q['name'] in ('activation', 'packed', 'rope') or r['error']:
                    self.phase = 'control_admission'
            elif event == 'dma_data':
                require('dma' in self.pending and self.pending['dma']['kind'] == 3 and
                        r['index'] == self.pending['dma']['index'], 'DMA data without store owner')
            elif event == 'projection_begin':
                require(self.projection is None, 'overlapping projections')
                self.projection = r
            elif event == 'projection_done':
                require(self.projection is not None, 'projection_done without begin')
                require(all(r[k] == self.projection[k] for k in ('head', 'batch_start', 'rows')), 'projection identity drift')
                require(r['matrix_inputs'] == r['matrix_outputs'], 'projection Matrix input/output counter drift')
                self.projection_inputs += r['matrix_inputs']
                self.projection_outputs += r['matrix_outputs']
                add_interval(self.intervals, 'projection_envelope', self.projection['cycle'], cycle)
                self.projection = None
            elif event == 'head_begin':
                require(self.head is None, 'overlapping heads')
                self.head = r
                self.read_counts.clear()
                self.write_counts.clear()
                self.phase = phase_this_cycle = 'norm_input_control_admission'
                self.boundary['norm_input'] = cycle
            elif event == 'head_done':
                require(self.head is not None and all(r[k] == self.head[k] for k in ('case', 'head', 'token', 'row')), 'head identity drift')
                add_interval(self.intervals, 'row_head_envelope', self.head['cycle'], cycle)
                self.completed_heads += 1
                self.head = None
                self.phase = 'control_admission'
            elif event == 'l2_read':
                region = r['region']
                require(region in (0, 1, 3, 4, 5, 6), 'unknown L2 read region')
                group = 'matrix_operand' if region in (5, 6) else 'norm_input' if region in (0, 3) else 'rope_input'
                if group == 'matrix_operand' and self.last_matrix_response is not None:
                    add_interval(self.intervals, 'matrix_operand_response_to_next_request_gap',
                                 self.last_matrix_response + 1, cycle - 1)
                    self.last_matrix_response = None
                self.open_owner('read', r, touched, group=group, interval=group + '_request_to_response')
                if group == 'rope_input' and 'rope_input' not in self.boundary:
                    self.boundary['rope_input'] = cycle
            elif event == 'l2_response':
                q = self.close_owner('read', r, 'byte_address', None)
                self.read_counts[q['region']] += 1
                if q['region'] in (5, 6):
                    self.last_matrix_response = cycle
                if q['region'] == 3 and self.read_counts[3] == 8:
                    require('norm_input' in self.boundary, 'Norm input boundary absent')
                    add_interval(self.intervals, 'norm_input_envelope', self.boundary.pop('norm_input'), cycle)
                    self.boundary['norm_compute'] = cycle + 1
                    self.phase = 'norm_compute_boundary_residual'
                if q['region'] == 4 and self.read_counts[4] == 2:
                    require('rope_input' in self.boundary, 'RoPE input boundary absent')
                    add_interval(self.intervals, 'rope_input_envelope', self.boundary.pop('rope_input'), cycle)
                    self.boundary['rope_compute'] = cycle + 1
                    self.phase = 'rope_compute_boundary_residual'
            elif event == 'matrix':
                outputs += 1
                require('matrix_tile' in self.boundary, 'Matrix output outside tile boundary')
                if r['last']:
                    add_interval(self.intervals, 'matrix_tile_after_weight_ack_to_last_output', self.boundary.pop('matrix_tile'), cycle)
                    if self.last_matrix_response is not None:
                        add_interval(self.intervals, 'matrix_last_operand_response_to_final_output',
                                     self.last_matrix_response + 1, cycle)
                        self.last_matrix_response = None
                    self.boundary['packed_output'] = cycle + 1
                    self.phase = 'packed_output_control_admission'
            elif event == 'norm':
                require('norm_compute' in self.boundary, 'Norm result before input boundary')
                add_interval(self.intervals, 'norm_last_input_to_result_boundary', self.boundary.pop('norm_compute'), cycle)
                self.boundary['norm_output'] = cycle + 1
                self.phase = 'norm_output_control_admission'
            elif event == 'l2_write':
                require(r['region'] in (0, 1, 2), 'unknown producer write region')
                name = ('packed', 'norm', 'rope')[r['region']]
                self.open_owner('write', r, touched, name=name, bucket=name + '_producer_write_ack', interval=name + '_write_request_to_ack')
                if name == 'rope' and self.write_counts[2] == 0:
                    require('rope_compute' in self.boundary, 'RoPE write before input boundary')
                    add_interval(self.intervals, 'rope_last_input_to_first_write_boundary', self.boundary.pop('rope_compute'), cycle - 1)
                    self.boundary['rope_output'] = cycle
                    self.phase = 'rope_output_control_admission'
            elif event == 'l2_ack':
                q = self.close_owner('write', r, 'byte_address', None)
                self.same_cycle_acks += int(q['cycle'] == cycle)
                region = q['region']
                self.write_counts[region] += 1
                last = (self.projection is not None and self.write_counts[0] % self.projection['rows'] == 0) if region == 0 else self.write_counts[region] == 8
                if last:
                    name = q['name']
                    require(name + '_output' in self.boundary, 'producer output boundary absent')
                    add_interval(self.intervals, name + '_producer_output_envelope', self.boundary.pop(name + '_output'), cycle)
                    if region == 1:
                        self.phase = 'rope_input_control_admission'
                    elif region == 2:
                        self.phase = 'final_store_control_admission'
            elif event == 'done':
                require(not self.pending, 'done with outstanding service owner')
                self.done = r
            else:
                raise ValueError('unexpected event in cycle group: ' + event)
        require(outputs <= 1, 'multiple Matrix output events on one cycle')
        # Different owners may meet on a cycle even though none is outstanding
        # simultaneously. Explicit priority makes these boundary cycles unique.
        self.overlap_cycles += int(len(touched) > 1)
        key = self.choose(touched, cycle, phase_this_cycle)
        self.cycles[key] += 1
        if outputs:
            self.outputs_by_bucket[key] += outputs
        self.previous = cycle

    def finish(self, terminal):
        self.events['terminal'] += 1
        require(self.done is not None and terminal['status'] == self.done['status'], 'terminal without matching done')
        n = self.done['cycle'] - self.started + 1
        require(terminal['command_cycles'] == n == sum(self.cycles.values()), 'accepted-to-done cycle denominator drift')
        for key, event in (('matrix_inputs', 'matrix'), ('matrix_outputs', 'matrix'), ('matrix_steps', 'matrix'),
                           ('dma_count', 'dma'), ('write_requests', 'l2_write'), ('write_acks', 'l2_ack'),
                           ('completed_heads', 'head_done')):
            require(terminal[key] == self.events[event], 'terminal counter drift: ' + key)
        require(terminal['ddr_read_bytes'] == self.read_bytes and terminal['ddr_write_bytes'] == self.write_bytes, 'terminal successful DMA bytes drift')
        require(self.events['dma'] == self.events['dma_ack'] and self.events['l2_read'] == self.events['l2_response'] and self.events['l2_write'] == self.events['l2_ack'], 'unfinished command service inventory')
        result = self.identity()
        result.update(status=terminal['status'], accepted_start=self.started, done=self.done['cycle'],
                      command_cycles=n, exclusive_cycles=dict(self.cycles), exclusive_cycle_sum=n,
                      overlapping_observable_intervals=self.intervals,
                      event_counts=dict(self.events), fixed_matrix_lanes=512,
                      accepted_matrix_input_count=terminal['matrix_inputs'],
                      observed_matrix_output_count=self.events['matrix'],
                      matrix_input_fire_timestamps_available=False,
                      observed_matrix_outputs_by_exclusive_bucket=dict(self.outputs_by_bucket),
                      service_owner_boundary_overlap_cycles=self.overlap_cycles,
                      same_cycle_producer_acks=self.same_cycle_acks,
                      ddr_read_bytes=self.read_bytes, ddr_write_bytes=self.write_bytes,
                      completed_heads=terminal['completed_heads'], completed_tokens=terminal['completed_tokens'],
                      valid_not_ready_stall_cycles_available=False, whole_block_metric=False)
        if terminal['status'] == 0:
            require(self.projection is None and self.head is None and not self.boundary, 'successful command has incomplete boundary')
            require(self.projection_inputs == self.projection_outputs == terminal['matrix_inputs'], 'successful projection counter inventory drift')
            heads, tiles = (8, 16) if self.begin['role'] == 0 else (2, 8)
            require(terminal['matrix_inputs'] == ((self.begin['token_count'] + 15) // 16) * heads * tiles * 1024, 'successful Matrix geometry drift')
            useful = self.begin['token_count'] * heads * tiles * 1024 * 32
            result.update(useful_fma=useful, candidate_useful_wall_fraction=useful / (512 * n))
        return result

    def identity(self):
        return {key: self.begin[key] for key in ('transaction', 'kind', 'name', 'case', 'role', 'start_token', 'token_count')}

    def reset_result(self):
        require(self.done is None and self.begin['kind'] == 'reset', 'invalid reset boundary')
        return dict(self.identity(), status=None, excluded_from_completed_cycle_aggregates=True,
                    reason='reset_flush has no done or terminal.command_cycles',
                    accepted_start=self.started, last_observed_cycle=self.previous,
                    reset_flush_timestamp_available=False,
                    observed_matrix_output_count=self.events['matrix'],
                    completed_heads=self.completed_heads, completed_tokens=0,
                    ddr_read_bytes=self.read_bytes, ddr_write_bytes=self.write_bytes)


def aggregate(commands):
    result = {'commands': len(commands), 'command_cycles': 0, 'exclusive_cycles': dict.fromkeys(BUCKETS, 0),
              'overlapping_observable_intervals': {}, 'accepted_matrix_input_count': 0,
              'observed_matrix_output_count': 0, 'observed_matrix_outputs_by_exclusive_bucket': {},
              'same_cycle_producer_acks': 0, 'fixed_matrix_lanes': 512, 'whole_block_metric': False}
    outputs = Counter()
    for c in commands:
        for k in ('command_cycles', 'accepted_matrix_input_count', 'observed_matrix_output_count', 'same_cycle_producer_acks'):
            result[k] += c[k]
        for k, v in c['exclusive_cycles'].items():
            result['exclusive_cycles'][k] += v
        outputs.update(c['observed_matrix_outputs_by_exclusive_bucket'])
        merge_intervals(result['overlapping_observable_intervals'], c['overlapping_observable_intervals'])
    result['observed_matrix_outputs_by_exclusive_bucket'] = dict(outputs)
    result['exclusive_cycle_sum'] = sum(result['exclusive_cycles'].values())
    require(result['exclusive_cycle_sum'] == result['command_cycles'], 'aggregate cycle sum drift')
    if commands and all(c['status'] == 0 for c in commands):
        useful = sum(c['useful_fma'] for c in commands)
        result.update(useful_fma=useful, candidate_useful_wall_fraction=useful / (512 * result['command_cycles']))
    return result


def analyze_records(records):
    """Structural accounting core. A result is unbound until analyze_trace binds it."""
    active = None
    group = []
    completed = []
    all_events = Counter()
    previous_cycle = -1
    for r in records:
        event = r['event']
        all_events[event] += 1
        if event == 'begin':
            require(active is None and not group, 'unterminated transaction')
            require(r['transaction'] == len(completed) + 1, 'transaction order drift')
            active = Command(r)
            continue
        require(active is not None and r['transaction'] == active.begin['transaction'], 'event outside/wrong transaction')
        if event == 'reset_flush':
            require('cycle' not in r, 'frozen reset_flush schema has no timestamp')
        if 'cycle' in r:
            require(r['cycle'] >= previous_cycle, 'trace time went backwards')
            previous_cycle = r['cycle']
            if group and group[0]['cycle'] != r['cycle']:
                active.consume_cycle(group)
                group = []
            group.append(r)
        elif event not in ('terminal', 'reset_flush'):
            raise ValueError('non-cycle event outside begin/terminal')
        if event in ('terminal', 'reset_flush'):
            if group:
                active.consume_cycle(group)
                group = []
            if event == 'reset_flush':
                active.events[event] += 1
            completed.append(active.finish(r) if event == 'terminal' else active.reset_result())
            active = None
    require(active is None and not group and bool(completed), 'missing complete transaction inventory')
    commands = [c for c in completed if c['status'] is not None]
    return {'commands': completed, 'events': dict(all_events), 'aggregates': {
        'all_completed_commands': aggregate(commands),
        'successful_primary_commands': aggregate([c for c in commands if c['status'] == 0 and c['name'] in PRIMARY]),
        'successful_primary_Q': aggregate([c for c in commands if c['status'] == 0 and c['name'] in PRIMARY and c['role'] == 0]),
        'successful_primary_K': aggregate([c for c in commands if c['status'] == 0 and c['name'] in PRIMARY and c['role'] == 1]),
        'successful_auxiliary_commands': aggregate([c for c in commands if c['status'] == 0 and c['name'] not in PRIMARY]),
        'failed_completed_commands': aggregate([c for c in commands if c['status'] != 0]),
    }}


def check_verified(result, verified):
    require(result['events'] == verified['events'], 'independent verifier event inventory drift')
    commands = result['commands']
    require(len(commands) == verified['transactions'] == len(verified['terminals']), 'independent verifier transaction inventory drift')
    for c, v in zip(commands, verified['terminals']):
        for key in ('kind', 'name', 'case', 'status', 'completed_heads', 'completed_tokens', 'ddr_read_bytes', 'ddr_write_bytes'):
            require(c[key] == v[key], 'independent verifier terminal drift: ' + key)
        require(c['observed_matrix_output_count'] == v['matrix_packets'], 'independent verifier Matrix count drift')
        if c['status'] is not None:
            require(c['command_cycles'] == v['accepted_to_done_cycles'] and v['fixed_matrix_lanes'] == 512, 'independent verifier denominator drift')
        if c['status'] == 0:
            require(c['useful_fma'] == v['useful_fma'] and c['candidate_useful_wall_fraction'] == v['candidate_useful_wall_fraction'], 'independent verifier useful work drift')


def analyze_trace(path, *, runner_summary=None, suite_key=None, provisional_verified_summary=None):
    """Bind final output to source/suite-specific runner SHA, or label smoke data."""
    path = Path(path)
    require((runner_summary is not None) != (provisional_verified_summary is not None), 'choose exactly one binding mode')
    sources = source_hashes()
    before = path.stat()
    trace_sha = digest(path)
    if runner_summary is not None:
        require(suite_key is not None, 'final runner binding requires suite_key, e.g. baseline_all')
        summary_path = Path(runner_summary)
        summary_bytes = summary_path.read_bytes()
        summary = json.loads(summary_bytes)
        require(summary['status'] in ('PASS_Q8_K2_TOKEN_TILE16_RTL', 'REJECTED_NATIVE_SOURCE_THRESHOLD_TILE16_RTL_MATCHED'), 'runner is not a completed tile16 RTL result')
        for name in VERIFIER_SOURCES:
            require(summary.get('source_sha256', {}).get(name) == sources[name], 'imported verifier source differs from final runner: ' + name)
        matches = [s for s in summary['rtl_suites'] if s['source'] + '_' + s['suite'] == suite_key]
        require(len(matches) == 1, 'runner suite missing/ambiguous')
        suite = matches[0]
        require(trace_sha == suite['trace_sha256'], 'trace SHA differs from completed final runner summary')
        verified = suite['independent_trace']
        binding = {'mode': 'final_runner_sha256', 'final_runner_bound': True, 'suite_key': suite_key,
                   'runner_summary_sha256': hashlib.sha256(summary_bytes).hexdigest(), 'runner_status': summary['status']}
    else:
        require(suite_key is None, 'suite_key requires final runner summary')
        summary_path = Path(provisional_verified_summary)
        summary_bytes = summary_path.read_bytes()
        verified = json.loads(summary_bytes)
        binding = {'mode': 'provisional_verified_inventory_only', 'final_runner_bound': False,
                   'verified_summary_sha256': hashlib.sha256(summary_bytes).hexdigest(),
                   'warning': 'Smoke/provisional inventory comparison only. The verifier summary does not bind trace content by SHA; this is not final-run evidence.'}
    opener = gzip.open if str(path).endswith('.gz') else open
    with opener(path, 'rt') as stream:
        def records():
            for lineno, line in enumerate(stream, 1):
                try:
                    yield _record(line)
                except (ValueError, KeyError, TypeError) as exc:
                    raise ValueError(f'trace line {lineno}: {exc}') from exc
        result = analyze_records(records())
    after = path.stat()
    require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), 'trace changed during analysis')
    require(digest(path) == trace_sha, 'trace content SHA changed during analysis')
    require(source_hashes() == sources, 'analyzer/imported source changed during analysis')
    check_verified(result, verified)
    return dict(schema_version=1, analysis='tile16_observed_cycle_phases', trace_sha256=trace_sha,
                analysis_source_sha256=sources, source_hashes_unchanged_after_analysis=True,
                trace_sha256_rechecked_after_analysis=True,
                runtime_versions={'python': sys.version, 'numpy': sys.modules['numpy'].__version__},
                binding=binding, conventions=CONVENTIONS, **result)


def analyze_run(runner_summary, trace_directory):
    """Analyze both completed runner suites without changing the frozen runner."""
    sources = source_hashes()
    summary_sha = digest(runner_summary)
    summary = json.loads(Path(runner_summary).read_text())
    keys = [s['source'] + '_' + s['suite'] for s in summary['rtl_suites']]
    require(len(keys) == 2 and set(keys) == {'baseline_all', 'avx2_main'}, 'completed runner must contain both expected suites')
    suites = {}
    for key in keys:
        report = analyze_trace(Path(trace_directory) / (key + '.jsonl.gz'),
                               runner_summary=runner_summary, suite_key=key)
        require(report['binding']['runner_summary_sha256'] == summary_sha, 'runner summary changed during analysis')
        require(report['analysis_source_sha256'] == sources, 'analysis source changed between suites')
        # One shared set of accounting conventions keeps the combined artifact compact.
        report.pop('conventions')
        suites[key] = report
    require(source_hashes() == sources, 'analysis source changed during combined report')
    require(digest(runner_summary) == summary_sha, 'runner summary changed during combined report')
    return {'schema_version': 1, 'analysis': 'tile16_observed_cycle_phases_both_sources',
            'runner_summary_sha256': summary_sha, 'final_runner_bound': True,
            'conventions': CONVENTIONS, 'suites': suites}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trace', type=Path, nargs='?')
    parser.add_argument('--trace-directory', type=Path, help='Analyze both final runner suites from this directory.')
    binding = parser.add_mutually_exclusive_group(required=True)
    binding.add_argument('--runner-summary', type=Path)
    binding.add_argument('--provisional-verified-summary', type=Path)
    parser.add_argument('--suite-key')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    require((args.trace is not None) != (args.trace_directory is not None), 'choose one trace or --trace-directory')
    if args.trace_directory is not None:
        require(args.runner_summary is not None and args.suite_key is None, 'batch mode needs --runner-summary and no --suite-key')
        result = analyze_run(args.runner_summary, args.trace_directory)
    else:
        result = analyze_trace(args.trace, runner_summary=args.runner_summary, suite_key=args.suite_key,
                               provisional_verified_summary=args.provisional_verified_summary)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'output': str(args.output),
                      'final_runner_bound': result.get('final_runner_bound', result.get('binding', {}).get('final_runner_bound')),
                      'suites': list(result.get('suites', {}))}))


if __name__ == '__main__':
    main()
