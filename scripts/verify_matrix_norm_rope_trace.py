#!/usr/bin/env python3
"""Fail-closed, independent consumer of accepted Matrix/Norm/RoPE events.

The caller must bind freshly generated vectors to the materializer receipt.
This consumer never trusts a DUT PASS marker, terminal counter, or a trace's
claim about which tests were required. It checks every emitted arithmetic
value and transport packet, actual done handshakes, and the requested suite.
SharedL2 guard readback is checked by the RTL testbench, not by this trace.
"""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from heteronpu.model_geometry import require
from heteronpu.qk_norm256_candidate import head_trace
from heteronpu.rope_bf16_candidate import bf16_convert, pair_trace

L2_BYTES = 1572864
BASE_FIELDS = ('packed_base', 'norm_base', 'rope_base', 'gamma_base',
               'trig_base', 'act_base', 'wgt_base')
REJECTS = {
    'bad_command': 2, 'bad_depth_shape': 4, 'unsupported_role': 4,
    'head_out_of_bounds': 4, 'token_out_of_bounds': 4, 'unsupported_policy': 4,
    'activation_1p5MiB_bounds': 5, 'weight_high_wrap': 5,
    'packed_1p5MiB_bounds': 5, 'norm_high_wrap': 5, 'rope_1p5MiB_bounds': 5,
    'trig_1p5MiB_bounds': 5, 'gamma_1p5MiB_bounds': 5, 'packed_alignment': 5,
    'active_region_overlap': 5, 'DDR_extent_overflow': 5,
    'malformed_descriptor': 2, 'unsupported_FP32_output': 4,
    'selected_address_add_carry': 5, 'token_extent_over128': 4,
    'DDR_output_weight_alias': 5,
}
# The observed error must occur on this precise owner and packet/region.
FAULTS = {
    'descriptor_fetch_error': ('descriptor', 1, 3),
    'activation_DMA_error': ('dma_ack', 0, 6),
    'weight_DMA_error': ('dma_ack', 1, 6),
    'packed_store_DMA_error': ('dma_ack', 2, 6),
    'Matrix_L2_read_error': ('l2_response', 5, 8),
    'Norm_L2_read_error': ('l2_response', 3, 8),
    'RoPE_L2_read_error': ('l2_response', 4, 8),
    'Matrix_L2_write_error': ('l2_ack', 0, 8),
    'Norm_L2_write_error': ('l2_ack', 1, 8),
    'RoPE_L2_write_error': ('l2_ack', 2, 8),
}
SCHEMA = {
    'begin': {'case', 'name', 'kind', 'checking', *BASE_FIELDS},
    'descriptor_request': {'cycle', 'index'},
    'descriptor': {'cycle', 'index', 'data', 'error'},
    'dma': {'cycle', 'index', 'kind', 'source', 'destination', 'row_bytes',
            'rows', 'source_stride', 'destination_stride'},
    'dma_ack': {'cycle', 'index', 'error'},
    'l2_read': {'cycle', 'byte_address', 'region'},
    'l2_response': {'cycle', 'byte_address', 'error', 'data'},
    'l2_write': {'cycle', 'byte_address', 'region', 'mask', 'data'},
    'l2_ack': {'cycle', 'byte_address', 'error'},
    'matrix': {'case', 'cycle', 'index', 'last', 'context', 'fp32_row0'},
    'norm': {'cycle', 'status', 'mean_eps', 'inv', 'flags', 'norm', 'gate'},
    'done': {'cycle', 'status'},
    'terminal': {'status', 'matrix_inputs', 'matrix_outputs', 'dma_count',
                 'write_requests', 'write_acks'},
    'reset_flush': {'stage'},
}
STRING_FIELDS = {'event', 'name', 'source', 'destination', 'data', 'mask',
                 'fp32_row0', 'mean_eps', 'inv', 'norm', 'gate'}


def _hex(value, digits):
    require(type(value) is str and re.fullmatch('[0-9a-f]{' + str(digits) + '}', value)
            is not None, 'trace hexadecimal encoding/width drift')
    return int(value, 16)


def _packed(words, width=2):
    return int.from_bytes(np.asarray(words, dtype=f'<u{width}').tobytes(), 'little')


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate JSON key: ' + key)
        result[key] = value
    return result


def _record(line):
    require(line.endswith('\n'), 'truncated trace record')
    r = json.loads(line, object_pairs_hook=_unique_object)
    require(type(r) is dict and type(r.get('event')) is str, 'bad trace event')
    event = r['event']
    require(event in SCHEMA, 'unknown trace event: ' + event)
    require(set(r) == SCHEMA[event] | {'event', 'transaction'}, 'trace field inventory drift: ' + event)
    for key, value in r.items():
        if key in STRING_FIELDS or (key == 'kind' and event == 'begin'):
            require(type(value) is str, 'trace string type drift: ' + key)
        else:
            require(type(value) is int and value >= 0, 'trace integer type/range drift: ' + key)
    if 'error' in r:
        require(r['error'] in (0, 1), 'invalid error bit')
    return r


def load_case(root, case_id):
    require(type(case_id) is int and 0 <= case_id < 4, 'trace case identity drift')
    p = Path(root) / f'case{case_id}'
    columns = 512 if case_id % 2 == 0 else 256
    schema = {'projected_steps': (1024 * columns, 8), 'projected_fp32': (columns, 8),
              'projected': (columns, 4), 'norm': (256, 4), 'rope': (256, 4),
              'activation': (1024, 4), 'weight': (1024 * columns, 4),
              'norm_weight': (256, 4), 'trig': (64, 4)}
    values = {}
    for name, (count, digits) in schema.items():
        raw = (p / (name + '.memh')).read_text()
        lines = raw.splitlines()
        require(raw.endswith('\n') and len(lines) == count, 'vector extent/truncation drift: ' + name)
        values[name] = np.asarray([_hex(word, digits) for word in lines], dtype=np.uint32)
    values['steps'] = values['projected_steps'].reshape(-1, 32)
    values['columns'] = columns
    final = values['steps'][1023::1024].reshape(-1)
    require(np.array_equal(final, values['projected_fp32']), 'final sequential-FMA vector link drift')
    require([bf16_convert(int(v))[0] >> 16 for v in final] == values['projected'].tolist(),
            'projected BF16 vector conversion drift')
    normalized = head_trace(tuple(int(v) << 16 for v in values['projected'][:256]),
                            tuple(int(v) << 16 for v in values['norm_weight']))
    require([v >> 16 for v in normalized['output_bf16']] == values['norm'].tolist(),
            'Norm vector arithmetic drift')
    values['norm_trace'] = normalized
    rotated = list(normalized['output_bf16'])
    for i in range(32):
        result = pair_trace(rotated[i], rotated[i + 32],
                            int(values['trig'][i]) << 16, int(values['trig'][i + 32]) << 16)
        rotated[i], rotated[i + 32] = result[20:22]
    require([v >> 16 for v in rotated] == values['rope'].tolist(), 'RoPE vector arithmetic drift')
    return values


def _suite_sequence(suite):
    require(suite in ('main', 'negative', 'fault', 'reset', 'boundary', 'all'), 'unknown trace suite')
    result = []
    if suite in ('main', 'all'):
        result.extend(('main', f'source_case{i}', i) for i in range(4))
    if suite in ('negative', 'all'):
        result.extend(('reject', name, 1) for name in REJECTS)
    if suite in ('fault', 'all'):
        result.extend(('fault', name, 1) for name in FAULTS)
        result.append(('recovery', 'recovery_after_fault_or_reset', 1))
    if suite in ('reset', 'all'):
        result.extend(('reset', f'reset_stage{i}', 1) for i in range(7))
        result.append(('recovery', 'recovery_after_fault_or_reset', 1))
    if suite in ('boundary', 'all'):
        result.append(('boundary', 'legal_exact_1p5MiB_end', 1))
    return result


def _bases(case, boundary=False):
    columns, full, head, token = (512, 4096, 7 if case == 2 else 0, 127 if case >= 2 else 0) \
        if case % 2 == 0 else (256, 512, 1 if case == 3 else 0, 127 if case >= 2 else 0)
    result = dict(zip(BASE_FIELDS, (0x40000 + token * full * 2 + head * columns * 2,
                  0x60000 + token * (4096 if case % 2 == 0 else 1024) + head * 512,
                  0x80000 + token * (4096 if case % 2 == 0 else 1024) + head * 512,
                  0x2000, 0x3000, 0x10000, 0x20000)))
    if boundary:
        result.update(packed_base=L2_BYTES - 512, norm_base=L2_BYTES - 1536,
                      rope_base=L2_BYTES - 1024)
    return result


def _root_record(index, base):
    return 1 | (index << 32) | ((base & ((1 << 48) - 1)) << 56) | (5 << 108) | ((base >> 48) << 120)


def _shape_record(rows, columns):
    return 2 | (rows << 56) | (columns << 74)


def _descriptors(case, name):
    full = 4096 if case % 2 == 0 else 512
    rows = 129 if name == 'token_extent_over128' else 128
    records = [_root_record(2, 0x100000000), _shape_record(rows, 1024),
               _root_record(4, 0x200000000), _shape_record(1024, full),
               _root_record(6, 0x300000000), _shape_record(rows, full)]
    if name == 'bad_depth_shape': records[3] = _shape_record(1000, 512)
    if name == 'DDR_extent_overflow': records[2] = _root_record(4, 0x00ffffffffffffc0)
    if name == 'malformed_descriptor': records[0] |= 1 << 8
    if name == 'unsupported_FP32_output': records[4] = (records[4] & ~(15 << 108)) | (7 << 108)
    if name == 'DDR_output_weight_alias': records[4] = _root_record(6, 0x200000040)
    return records


class _Transaction:
    def __init__(self, begin, expected):
        self.b, self.ex = begin, expected
        self.kind, self.name = begin['kind'], begin['name']
        self.tiles = expected['columns'] // 32
        self.pending = dict.fromkeys(('descriptor', 'dma', 'read', 'write'))
        self.counts = Counter()
        self.writes, self.acks = Counter(), Counter()
        self.errors = []
        self.done = None
        self.weight_tile = -1
        self.descriptors = _descriptors(begin['case'], self.name)
        self.descriptor_limit = {'bad_command': 0, 'malformed_descriptor': 1,
                                 'descriptor_fetch_error': 1, 'unsupported_FP32_output': 5}.get(self.name, 6)
        self.status = REJECTS[self.name] if self.kind == 'reject' else \
            FAULTS[self.name][2] if self.kind == 'fault' else 0
        require(begin['checking'] == 1, 'arithmetic checking disabled')
        require(all(begin[k] == v for k, v in _bases(begin['case'], self.kind == 'boundary').items()),
                'selected case/base address drift')

    def idle(self):
        require(all(v is None for v in self.pending.values()), 'owner done/advance before response or ACK')

    def error(self, event, coordinate, r):
        expected = self.kind == 'fault' and FAULTS[self.name][:2] == (event, coordinate)
        # Fault injection targets the first matching accepted packet only.
        wanted = int(expected and not self.errors)
        require(r['error'] == wanted, 'missing, spurious, or misrouted transport error')
        if r['error']:
            self.errors.append((event, coordinate))

    def read_coordinate(self, index):
        if index < self.tiles * 2048:
            tile, step = divmod(index, 2048)
            k, part = divmod(step, 2)
            region = 5 + part
            return region, self.b['act_base' if part == 0 else 'wgt_base'] + k * 64, tile, k
        index -= self.tiles * 2048
        for region, count, base in ((0, self.tiles, 'packed_base'), (3, 8, 'gamma_base'),
                                    (1, 8, 'norm_base'), (4, 2, 'trig_base')):
            if index < count:
                return region, self.b[base] + index * 64, None, index * 32
            index -= count
        raise ValueError('extra L2 read')

    def consume(self, r):
        event = r['event']
        require(self.done is None or event == 'terminal', 'activity after done or duplicate done')
        require(not self.errors or event in ('done', 'terminal'), 'activity after transport failure')
        if self.kind == 'reject':
            require(event in ('descriptor_request', 'descriptor', 'done', 'terminal'), 'rejection had side effects')
        if event == 'descriptor_request':
            self.idle()
            index = self.counts[event] + 1
            require(index <= self.descriptor_limit and r['index'] == index, 'descriptor request order/count drift')
            self.pending['descriptor'] = r
        elif event == 'descriptor':
            request = self.pending['descriptor']
            require(request is not None and r['index'] == request['index'], 'descriptor response owner mismatch')
            require(_hex(r['data'], 32) == self.descriptors[r['index'] - 1], 'descriptor data drift')
            self.error(event, r['index'], r)
            self.pending['descriptor'] = None
        elif event == 'dma':
            self.idle()
            require(self.counts['descriptor'] == 6, 'DMA before descriptor snapshot')
            i = self.counts[event]
            require(i <= 2 * self.tiles and r['index'] == i, 'DMA order/count drift')
            case = self.b['case']; token = 127 if case >= 2 else 0
            head = 7 if case == 2 else 1 if case == 3 else 0
            full = 4096 if case % 2 == 0 else 512
            if i == 0:
                want = (1, 0x100000000 + token * 2048, self.b['act_base'], 2, 1024, 2, 64)
            elif i % 2:
                tile = (i - 1) // 2
                require(self.counts['matrix'] == tile * 1024, 'weight DMA before prior tile completion')
                want = (1, 0x200000000 + head * self.ex['columns'] * 2 + tile * 64,
                        self.b['wgt_base'], 64, 1024, full * 2, 64)
            else:
                tile = (i - 2) // 2
                require(self.acks[0] == tile + 1 and self.counts['matrix'] == (tile + 1) * 1024,
                        'DDR store before projected producer ACK')
                want = (3, self.b['packed_base'] + tile * 64,
                        0x300000000 + token * full * 2 + head * self.ex['columns'] * 2 + tile * 64,
                        64, 1, 64, 64)
            got = (r['kind'], _hex(r['source'], 16), _hex(r['destination'], 16),
                   r['row_bytes'], r['rows'], r['source_stride'], r['destination_stride'])
            require(got == want, 'DMA address/geometry mismatch')
            self.pending['dma'] = r
        elif event == 'dma_ack':
            request = self.pending['dma']
            require(request is not None and r['index'] == request['index'], 'DMA ACK owner/index mismatch')
            self.error(event, r['index'], r)
            if r['index'] % 2 and not r['error']:
                self.weight_tile = (r['index'] - 1) // 2
            self.pending['dma'] = None
        elif event == 'l2_read':
            self.idle()
            region, address, tile, _ = self.read_coordinate(self.counts[event])
            require(r['region'] == region and r['byte_address'] == address, 'L2 read order/region/address mismatch')
            require(0 <= address <= L2_BYTES - 64 and address % 64 == 0, 'L2 read aperture/alignment violation')
            if tile is not None:
                require(self.weight_tile == tile and self.counts['dma_ack'] == 2 + tile * 2,
                        'Matrix read before acknowledged source DMA')
            else:
                require(self.counts['dma_ack'] == 1 + self.tiles * 2 and self.acks[0] == self.tiles,
                        'Norm read before all projection/DMA ACKs')
                if region in (1, 4):
                    require(self.acks[1] == 8, 'RoPE read before acknowledged Norm producer')
            self.pending['read'] = r
        elif event == 'l2_response':
            request = self.pending['read']
            require(request is not None and r['byte_address'] == request['byte_address'], 'L2 response owner/address mismatch')
            region, _, tile, offset = self.read_coordinate(self.counts[event])
            actual = _hex(r['data'], 128)
            if region == 5:
                want = int(self.ex['activation'][offset])
            elif region == 6:
                start = offset * self.ex['columns'] + tile * 32
                want = _packed(self.ex['weight'][start:start + 32])
            else:
                name = {0: 'projected', 1: 'norm', 3: 'norm_weight', 4: 'trig'}[region]
                want = _packed(self.ex[name][offset:offset + 32])
            require(actual == want, 'independent L2 source/producer read mismatch')
            self.error(event, region, r)
            self.pending['read'] = None
        elif event == 'matrix':
            i = self.counts[event]
            require(i < len(self.ex['steps']) and r['case'] == self.b['case'] and r['index'] == i
                    and r['context'] == 0 and r['last'] == int(i % 1024 == 1023), 'Matrix order/context/last mismatch')
            require(self.counts['l2_response'] >= 2 * (i + 1) and self.weight_tile == i // 1024,
                    'Matrix result before acknowledged operands')
            require(_hex(r['fp32_row0'], 256) == _packed(self.ex['steps'][i], 4),
                    'independent sequential-FMA step mismatch')
        elif event == 'norm':
            self.idle()
            require(self.counts[event] == 0 and self.counts['l2_response'] == self.tiles * 2048 + self.tiles + 8,
                    'duplicate or premature Norm result')
            expected = self.ex['norm_trace']
            require(r['status'] == 0 and _hex(r['mean_eps'], 8) == expected['mean_eps']
                    and _hex(r['inv'], 8) == expected['inverse'] and r['flags'] == expected['aggregate_flags'],
                    'Norm status/intermediate/flag mismatch')
            require(_hex(r['norm'], 1024) == _packed(self.ex['norm']), 'independent Norm result mismatch')
            gate = _packed(self.ex['projected'][256:]) if self.b['case'] % 2 == 0 else 0
            require(_hex(r['gate'], 1024) == gate, 'raw Q gate/K zero gate mismatch')
        elif event == 'l2_write':
            self.idle()
            region = 0 if self.writes[0] < self.tiles else 1 if self.writes[1] < 8 else 2
            offset = self.writes[region] * 32
            name, base = (('projected', 'packed_base'), ('norm', 'norm_base'), ('rope', 'rope_base'))[region]
            require(r['region'] == region and offset < len(self.ex[name])
                    and r['byte_address'] == self.b[base] + offset * 2, 'producer store order/address drift')
            require(r['byte_address'] % 64 == 0 and 0 <= r['byte_address'] <= L2_BYTES - 64,
                    'L2 store aperture/alignment violation')
            require(_hex(r['mask'], 16) == (1 << 64) - 1, 'unexpected store byte mask')
            require(_hex(r['data'], 128) == _packed(self.ex[name][offset:offset + 32]),
                    'independent projected/Norm/RoPE store mismatch')
            if region == 0:
                require(self.counts['matrix'] == (self.writes[0] + 1) * 1024, 'store before final Matrix output')
            elif region == 1:
                require(self.counts['norm'] == 1, 'store before Norm result')
            else:
                require(self.counts['l2_response'] == self.tiles * 2048 + self.tiles + 18,
                        'RoPE write before complete acknowledged inputs')
            self.writes[region] += 1
            self.pending['write'] = r
        elif event == 'l2_ack':
            request = self.pending['write']
            require(request is not None and r['byte_address'] == request['byte_address'], 'L2 ACK owner/address mismatch')
            self.error(event, request['region'], r)
            self.acks[request['region']] += 1
            self.pending['write'] = None
        elif event == 'done':
            require(self.kind != 'reset', 'reset transaction completed before reset')
            self.idle()
            require(r['status'] == self.status, 'terminal status does not match required test')
            require(self.counts['descriptor'] == self.descriptor_limit, 'incomplete descriptor response inventory')
            require(self.counts['l2_read'] == self.counts['l2_response'] and self.writes == self.acks
                    and self.counts['dma'] == self.counts['dma_ack'], 'incomplete transport at done')
            require(len(self.errors) == int(self.kind == 'fault'), 'required fault was not observed')
            if self.status == 0:
                require(self.counts['matrix'] == 1024 * self.tiles and self.counts['norm'] == 1,
                        'successful arithmetic completion missing')
                require(self.writes == Counter({0: self.tiles, 1: 8, 2: 8}), 'producer store coverage missing')
                require(self.counts['dma'] == 1 + 2 * self.tiles
                        and self.counts['l2_response'] == self.tiles * 2048 + self.tiles + 18,
                        'successful transport coverage missing')
            self.done = r
        elif event == 'terminal':
            require(self.done is not None and r['status'] == self.done['status'], 'terminal missing/mismatching actual done')
            require(r['matrix_inputs'] == r['matrix_outputs'] == self.counts['matrix']
                    and r['dma_count'] == self.counts['dma'] and r['write_requests'] == sum(self.writes.values())
                    and r['write_acks'] == sum(self.acks.values()), 'terminal counters differ from accepted events')
        elif event == 'reset_flush':
            require(self.kind == 'reset' and self.name == f"reset_stage{r['stage']}", 'unsolicited/wrong-stage reset')
            stage = r['stage']
            reached = (
                self.pending['descriptor'] is not None if stage == 0 else
                self.pending['dma'] is not None and self.pending['dma']['index'] == 0 if stage == 1 else
                self.weight_tile == 0 and self.counts['l2_response'] >= 16 if stage == 2 else
                self.counts['l2_response'] == self.tiles * 2048 + self.tiles + 8 and not self.counts['norm'] if stage == 3 else
                self.writes[1] == 1 and self.pending['write'] is not None if stage == 4 else
                self.counts['l2_read'] == self.tiles * 2048 + self.tiles + 18 if stage == 5 else
                self.writes[2] == 8 and self.pending['write'] is not None if stage == 6 else False)
            require(reached, 'reset target stage was not reached')
        self.counts[event] += 1


def verify_trace(path, vectors, *, required_main=None, suite='main'):
    """Verify exactly the named suite; required_main cannot weaken its inventory."""
    sequence = _suite_sequence(suite)
    inventory = Counter(sequence)
    expected_main = 4 if suite in ('main', 'all') else 0
    require(required_main is None or (type(required_main) is int and required_main == expected_main),
            'required_main conflicts with complete suite inventory')
    cases = {i: load_case(vectors, i) for i in range(4)}
    active = None
    counts, completed = Counter(), Counter()
    seen = 0
    terminals = []
    previous_cycle = -1
    with Path(path).open() as f:
        for lineno, line in enumerate(f, 1):
            try:
                r = _record(line)
                event = r['event']
                if 'cycle' in r:
                    require(r['cycle'] >= previous_cycle, 'trace time went backwards')
                    previous_cycle = r['cycle']
                if event == 'begin':
                    require(active is None, 'unterminated prior transaction')
                    require(r['transaction'] == seen + 1, 'duplicate/missing/reordered transaction')
                    key = (r['kind'], r['name'], r['case'])
                    require(seen < len(sequence) and key == sequence[seen],
                            'unexpected/duplicate/reordered test identity')
                    active = _Transaction(r, cases[r['case']])
                    seen += 1
                else:
                    require(active is not None and r['transaction'] == active.b['transaction'],
                            'trace event outside transaction or wrong owner')
                    active.consume(r)
                    if event in ('terminal', 'reset_flush'):
                        completed[(active.kind, active.name, active.b['case'])] += 1
                        terminals.append({'kind': active.kind, 'name': active.name, 'case': active.b['case'],
                                          'status': r.get('status'), 'matrix_outputs': active.counts['matrix']})
                        active = None
                counts[event] += 1
            except (ValueError, KeyError, TypeError, IndexError) as exc:
                raise ValueError(f'trace line {lineno}: {exc}') from exc
    require(active is None, 'trace ended without completion/reset')
    require(completed == inventory, 'missing required suite test inventory')
    return {'suite': suite, 'events': dict(counts), 'transactions': seen, 'main_cases': expected_main,
            'bitexact_matrix_steps': counts['matrix'], 'terminals': terminals,
            'missing_extra_reordered_oracle_values': 0,
            'actual_done_before_ack_checked': True, 'fabric_guard_readback_in_trace': False}
