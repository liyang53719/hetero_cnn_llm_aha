#!/usr/bin/env python3
"""Independent, fail-closed consumer for full-tensor Matrix/Norm/RoPE traces.

Checks every accepted arithmetic value and owner handshake, head/token order,
fixed SharedL2 staging, whole-tensor DDR geometry, and actual fabric store data.
A PASS string or terminal counter is never a substitute for accepted events.
Fresh materialized vectors must additionally be bound to their source receipt
by the caller. Guard readback remains an independent RTL testbench check.
"""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from verify_matrix_norm_rope_trace import (
    BASE_FIELDS, L2_BYTES, REJECTS as HEAD_REJECTS,
    SCHEMA as HEAD_SCHEMA, STRING_FIELDS, _hex, _packed, _unique_object,
    _root_record, _shape_record, require, head_trace, bf16_convert, pair_trace,
)

REJECTS = {('tensor_nonzero_head' if k == 'head_out_of_bounds' else
            'token_end_overflow' if k == 'selected_address_add_carry' else k):
           (4 if k == 'selected_address_add_carry' else v) for k, v in HEAD_REJECTS.items()}
REJECTS.update(zero_token_count=4, token_count_over128=4,
               DDR_norm_alias=5, DDR_rope_alias=5, DDR_norm_wrap=5,
               DDR_rope_wrap=5, DDR_norm_alignment=5, DDR_norm_future_head_alias=5,
               DDR_rope_future_token_alias=5)
FAULTS = {'final_output_DMA_error': ('dma_ack', 37, 6),
          'token_count128_admitted': ('dma_ack', 0, 6)}
SCHEMA = {k: set(v) for k, v in HEAD_SCHEMA.items()}
SCHEMA['begin'] |= {'role', 'start_token', 'token_count'}
SCHEMA['head_begin'] = {'cycle', 'case', 'head', 'token'}
SCHEMA['head_done'] = SCHEMA['head_begin'] | {'flags'}
SCHEMA['dma_data'] = {'cycle', 'index', 'source', 'destination', 'data'}
SCHEMA['terminal'] |= {'completed_heads', 'completed_tokens', 'total_tiles', 'flags'}
MAIN = (('cold_Q', 0, 0, 0, 2), ('cold_K', 8, 1, 0, 2),
        ('carried_Q', 20, 0, 126, 2), ('carried_K', 28, 1, 126, 2))


def _record(line):
    require(line.endswith('\n'), 'truncated trace record')
    r = json.loads(line, object_pairs_hook=_unique_object)
    require(type(r) is dict and type(r.get('event')) is str, 'bad trace event')
    event = r['event']
    require(event in SCHEMA, 'unknown trace event: ' + event)
    require(set(r) == SCHEMA[event] | {'event', 'transaction'},
            'trace field inventory drift: ' + event)
    for key, value in r.items():
        if key in STRING_FIELDS or (key == 'kind' and event == 'begin'):
            require(type(value) is str, 'trace string type drift: ' + key)
        else:
            require(type(value) is int and value >= 0, 'trace integer type/range drift: ' + key)
    if 'error' in r:
        require(r['error'] in (0, 1), 'invalid error bit')
    return r


def _case_id(role, token, head):
    require(role in (0, 1) and token in (0, 1, 126, 127)
            and 0 <= head < (8 if role == 0 else 2), 'head/token oracle identity drift')
    return (token if token < 2 else token - 124) * 10 + (0 if role == 0 else 8) + head


def load_case(root, case_id):
    require(type(case_id) is int and 0 <= case_id < 40, 'trace case identity drift')
    p = Path(root) / f'case{case_id}'
    columns = 512 if case_id % 10 < 8 else 256
    schema = {'projected_steps': (1024 * columns, 8), 'projected_fp32': (columns, 8),
              'projected': (columns, 4), 'norm': (256, 4), 'rope': (256, 4),
              'activation': (1024, 4), 'weight': (1024 * columns, 4),
              'norm_weight': (256, 4), 'trig': (64, 4)}
    values = {}
    for name, (count, digits) in schema.items():
        raw = (p / (name + '.memh')).read_text()
        lines = raw.splitlines()
        require(raw.endswith('\n') and len(lines) == count,
                'vector extent/truncation drift: ' + name)
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
    values['rope_flags'] = 0
    for i in range(32):
        result = pair_trace(rotated[i], rotated[i + 32],
                            int(values['trig'][i]) << 16, int(values['trig'][i + 32]) << 16)
        rotated[i], rotated[i + 32] = result[20:22]
        values['rope_flags'] |= result[24]
    require([v >> 16 for v in rotated] == values['rope'].tolist(), 'RoPE vector arithmetic drift')
    return values


def _suite_sequence(suite):
    require(suite in ('main', 'negative', 'fault', 'reset', 'boundary', 'all'), 'unknown trace suite')
    result = []
    if suite in ('main', 'all'):
        result.extend(('main', name, case) for name, case, *_ in MAIN)
    if suite in ('negative', 'all'):
        result.extend(('reject', name, 8) for name in REJECTS)
    if suite in ('fault', 'all'):
        result.extend(('fault', name, 8) for name in FAULTS)
        result.append(('recovery', 'recovery_after_fault_or_reset', 8))
    if suite in ('reset', 'all'):
        result.extend(('reset', name, 8) for name in ('reset_late_head', 'reset_late_token'))
        result.append(('recovery', 'recovery_after_fault_or_reset', 8))
    if suite in ('boundary', 'all'):
        result.append(('boundary', 'legal_exact_1p5MiB_end', 8))
    return result


def _bases(start_token=0, boundary=False):
    result = dict(zip(BASE_FIELDS, (0x40000, 0x60000, 0x80000, 0x2000,
                                    0x3000 + start_token * 128, 0x10000, 0x20000)))
    if boundary:
        result.update(packed_base=L2_BYTES - 512, norm_base=L2_BYTES - 1536,
                      rope_base=L2_BYTES - 1024)
    return result


def _descriptors(role, name):
    full = 4096 if role == 0 else 512
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
    def __init__(self, begin, cases):
        self.b, self.cases = begin, cases
        self.kind, self.name = begin['kind'], begin['name']
        self.role = begin['role']
        self.head_count = 8 if self.role == 0 else 2
        self.tiles = 16 if self.role == 0 else 8
        self.packets_per_head = 3 + 2 * self.tiles
        self.pending = dict.fromkeys(('descriptor', 'dma', 'read', 'write'))
        self.counts, self.local = Counter(), Counter()
        self.writes, self.acks = Counter(), Counter()
        self.errors, self.done, self.head = [], None, None
        self.completed_heads = 0
        self.expected_flags = 0
        self.weight_tile, self.dma_beats = -1, 0
        self.descriptors = _descriptors(self.role, self.name)
        self.descriptor_limit = {'bad_command': 0, 'malformed_descriptor': 1,
                                 'descriptor_fetch_error': 1, 'unsupported_FP32_output': 5}.get(self.name, 6)
        self.status = REJECTS[self.name] if self.kind == 'reject' else \
            FAULTS[self.name][2] if self.kind == 'fault' else 0
        require(begin['checking'] == 1, 'arithmetic checking disabled')
        require(all(begin[k] == v for k, v in _bases(begin['start_token'], self.kind == 'boundary').items()),
                'fixed staging/base address drift')
        require(self.role in (0, 1), 'command role drift')
        if self.kind == 'main':
            expected = next((m for m in MAIN if m[0] == self.name), None)
            require(expected is not None and (begin['case'], self.role, begin['start_token'],
                    begin['token_count']) == expected[1:], 'main command geometry drift')
        else:
            require(begin['case'] == 8 and self.role == 1 and begin['start_token'] == 0
                    and begin['token_count'] == (128 if self.name == 'token_count128_admitted' else
                                               2 if self.kind == 'reset' else 1),
                    'auxiliary command geometry drift')

    def idle(self):
        require(all(v is None for v in self.pending.values()), 'owner done/advance before response or ACK')

    def error(self, event, coordinate, r):
        target = FAULTS.get(self.name) if self.kind == 'fault' else None
        wanted = int(target is not None and target[:2] == (event, coordinate) and not self.errors)
        require(r['error'] == wanted, 'missing, spurious, or misrouted transport error')
        if r['error']:
            self.errors.append((event, coordinate))

    def read_coordinate(self, index):
        if index < self.tiles * 2048:
            tile, step = divmod(index, 2048)
            k, part = divmod(step, 2)
            return 5 + part, self.b['act_base' if part == 0 else 'wgt_base'] + k * 64, tile, k
        index -= self.tiles * 2048
        for region, count, base in ((0, self.tiles, 'packed_base'), (3, 8, 'gamma_base'),
                                    (1, 8, 'norm_base'), (4, 2, 'trig_base')):
            if index < count:
                address = self.b[base] + index * 64
                if region == 4:
                    address += (self.head['token'] - self.b['start_token']) * 128
                return region, address, None, index * 32
            index -= count
        raise ValueError('extra L2 read')

    def complete_head(self):
        self.idle()
        require(self.head is not None, 'head completion without active head')
        require(self.local['matrix'] == 1024 * self.tiles and self.local['norm'] == 1,
                'successful head arithmetic completion missing')
        require(self.writes == self.acks == Counter({0: self.tiles, 1: 8, 2: 8}),
                'head producer ACK coverage missing')
        require(self.local['dma'] == self.local['dma_ack'] == self.packets_per_head
                and self.local['dma_data'] == self.tiles + 16
                and self.local['l2_read'] == self.local['l2_response'] == self.tiles * 2048 + self.tiles + 18,
                'successful head transport/raw fabric coverage missing')

    def consume(self, r):
        event = r['event']
        require(self.done is None or event == 'terminal', 'activity after done or duplicate done')
        require(not self.errors or event in ('done', 'terminal'), 'activity after transport failure')
        if self.kind == 'reject':
            require(event in ('descriptor_request', 'descriptor', 'done', 'terminal'),
                    'rejection had side effects')
        if event == 'head_begin':
            self.idle()
            require(self.head is None and self.completed_heads < self.head_count * self.b['token_count'],
                    'overlapping or extra head begin')
            relative_token, head = divmod(self.completed_heads, self.head_count)
            token = self.b['start_token'] + relative_token
            case = _case_id(self.role, token, head)
            require((r['case'], r['head'], r['token']) == (case, head, token),
                    'missing/extra/reordered head or token')
            self.head, self.ex = r, self.cases[case]
            require(self.ex['columns'] == self.tiles * 32, 'oracle role/column mismatch')
            self.local, self.writes, self.acks = Counter(), Counter(), Counter()
            self.weight_tile = -1
        elif event == 'head_done':
            self.complete_head()
            require(r['flags'] == self.expected_flags, 'head cumulative arithmetic flags mismatch')
            require(all(r[k] == self.head[k] for k in ('case', 'head', 'token')), 'head done identity drift')
            self.completed_heads += 1
            self.head = None
        elif event == 'descriptor_request':
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
            require(self.head is not None and self.counts['descriptor'] == 6, 'DMA before head/descriptor snapshot')
            i = self.local[event]
            require(i < self.packets_per_head and r['index'] == self.counts[event], 'DMA order/count drift')
            token, head = self.head['token'], self.head['head']
            packed_stride, normalized_stride = (8192, 4096) if self.role == 0 else (1024, 1024)
            if i == 0:
                want = (1, 0x100000000 + token * 2048, self.b['act_base'], 2, 1024, 2, 64)
            elif i <= 2 * self.tiles and i % 2:
                tile = (i - 1) // 2
                require(self.local['matrix'] == tile * 1024, 'weight DMA before prior tile completion')
                want = (1, 0x200000000 + head * self.ex['columns'] * 2 + tile * 64,
                        self.b['wgt_base'], 64, 1024, packed_stride, 64)
            elif i <= 2 * self.tiles:
                tile = (i - 2) // 2
                require(self.acks[0] == tile + 1 and self.local['matrix'] == (tile + 1) * 1024,
                        'DDR store before projected producer ACK')
                want = (3, self.b['packed_base'] + tile * 64,
                        0x300000000 + token * packed_stride + head * self.ex['columns'] * 2 + tile * 64,
                        64, 1, 64, 64)
            else:
                region = i - 2 * self.tiles
                name, base, ddr = ('norm', 'norm_base', 0x400000000) if region == 1 else \
                                  ('rope', 'rope_base', 0x500000000)
                if self.kind == 'boundary':
                    ddr = (1 << 56) - (2048 if region == 1 else 1024)
                require(self.acks[region] == 8, 'DDR output store before producer ACK')
                want = (3, self.b[base], ddr + token * normalized_stride + head * 512, 64, 8, 64, 64)
            got = (r['kind'], _hex(r['source'], 16), _hex(r['destination'], 16),
                   r['row_bytes'], r['rows'], r['source_stride'], r['destination_stride'])
            require(got == want, 'DMA address/geometry mismatch')
            self.pending['dma'], self.dma_beats = r, 0
        elif event == 'dma_data':
            request = self.pending['dma']
            require(request is not None and request['kind'] == 3 and r['index'] == request['index'],
                    'raw fabric DMA data owner/index mismatch')
            beat = self.dma_beats
            require(beat < request['rows'] and _hex(r['source'], 16) == _hex(request['source'], 16) + beat * 64
                    and _hex(r['destination'], 16) == _hex(request['destination'], 16) + beat * 64,
                    'raw fabric DMA data address/order drift')
            i = self.local['dma'] - 1
            name, offset = ('projected', (i - 2) // 2 * 32) if i <= 2 * self.tiles else \
                           ('norm' if i == 2 * self.tiles + 1 else 'rope', beat * 32)
            require(_hex(r['data'], 128) == _packed(self.ex[name][offset:offset + 32]),
                    'independent raw fabric DDR store data mismatch')
            self.dma_beats += 1
        elif event == 'dma_ack':
            request = self.pending['dma']
            require(request is not None and r['index'] == request['index'], 'DMA ACK owner/index mismatch')
            self.error(event, r['index'], r)
            # An injected failing packet may have transferred only a prefix.
            if not r['error']:
                require(self.dma_beats == (request['rows'] if request['kind'] == 3 else 0),
                        'DMA ACK without complete raw fabric data')
            i = self.local['dma_ack']
            if 0 < i <= 2 * self.tiles and i % 2 and not r['error']:
                self.weight_tile = (i - 1) // 2
            self.pending['dma'] = None
        elif event == 'l2_read':
            self.idle()
            require(self.head is not None, 'L2 read outside head')
            region, address, tile, _ = self.read_coordinate(self.local[event])
            require(r['region'] == region and r['byte_address'] == address, 'L2 read order/region/address mismatch')
            require(0 <= address <= L2_BYTES - 64 and address % 64 == 0, 'L2 read aperture/alignment violation')
            if tile is not None:
                require(self.weight_tile == tile and self.local['dma_ack'] == 2 + tile * 2,
                        'Matrix read before acknowledged source DMA')
            else:
                require(self.local['dma_ack'] == 1 + self.tiles * 2 and self.acks[0] == self.tiles,
                        'Norm read before all projection/DMA ACKs')
                if region in (1, 4):
                    require(self.acks[1] == 8, 'RoPE read before acknowledged Norm producer')
            self.pending['read'] = r
        elif event == 'l2_response':
            request = self.pending['read']
            require(request is not None and r['byte_address'] == request['byte_address'], 'L2 response owner/address mismatch')
            region, _, tile, offset = self.read_coordinate(self.local[event])
            if region == 5:
                want = int(self.ex['activation'][offset])
            elif region == 6:
                start = offset * self.ex['columns'] + tile * 32
                want = _packed(self.ex['weight'][start:start + 32])
            else:
                name = {0: 'projected', 1: 'norm', 3: 'norm_weight', 4: 'trig'}[region]
                want = _packed(self.ex[name][offset:offset + 32])
            require(_hex(r['data'], 128) == want, 'independent L2 source/producer read mismatch')
            self.error(event, region, r)
            self.pending['read'] = None
        elif event == 'matrix':
            require(self.head is not None, 'Matrix output outside head')
            i = self.local[event]
            require(i < len(self.ex['steps']) and r['case'] == self.head['case'] and r['index'] == i
                    and r['context'] == 0 and r['last'] == int(i % 1024 == 1023), 'Matrix order/context/last mismatch')
            require(self.local['l2_response'] >= 2 * (i + 1) and self.weight_tile == i // 1024,
                    'Matrix result before acknowledged operands')
            require(_hex(r['fp32_row0'], 256) == _packed(self.ex['steps'][i], 4),
                    'independent sequential-FMA step mismatch')
        elif event == 'norm':
            self.idle()
            require(self.head is not None and self.local[event] == 0
                    and self.local['l2_response'] == self.tiles * 2048 + self.tiles + 8,
                    'duplicate or premature Norm result')
            expected = self.ex['norm_trace']
            require(r['status'] == 0 and _hex(r['mean_eps'], 8) == expected['mean_eps']
                    and _hex(r['inv'], 8) == expected['inverse'] and r['flags'] == expected['aggregate_flags'],
                    'Norm status/intermediate/flag mismatch')
            self.expected_flags |= expected['aggregate_flags']
            require(_hex(r['norm'], 1024) == _packed(self.ex['norm']), 'independent Norm result mismatch')
            gate = _packed(self.ex['projected'][256:]) if self.role == 0 else 0
            require(_hex(r['gate'], 1024) == gate, 'raw Q gate/K zero gate mismatch')
        elif event == 'l2_write':
            self.idle()
            require(self.head is not None, 'L2 write outside head')
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
                require(self.local['matrix'] == (self.writes[0] + 1) * 1024, 'store before final Matrix output')
            elif region == 1:
                require(self.local['norm'] == 1, 'store before Norm result')
            else:
                require(self.local['l2_response'] == self.tiles * 2048 + self.tiles + 18,
                        'RoPE write before complete acknowledged inputs')
            self.writes[region] += 1
            self.pending['write'] = r
        elif event == 'l2_ack':
            request = self.pending['write']
            require(request is not None and r['byte_address'] == request['byte_address'], 'L2 ACK owner/address mismatch')
            self.error(event, request['region'], r)
            self.acks[request['region']] += 1
            self.pending['write'] = None
            if request['region'] == 2 and self.acks[2] == 8:
                self.expected_flags |= self.ex['rope_flags']
        elif event == 'done':
            require(self.kind != 'reset', 'reset transaction completed before reset')
            self.idle()
            require(r['status'] == self.status, 'terminal status does not match required test')
            require(self.counts['descriptor'] == self.descriptor_limit, 'incomplete descriptor response inventory')
            require(self.counts['l2_read'] == self.counts['l2_response']
                    and self.counts['l2_write'] == self.counts['l2_ack']
                    and self.counts['dma'] == self.counts['dma_ack'], 'incomplete transport at done')
            require(len(self.errors) == int(self.kind == 'fault'), 'required fault was not observed')
            if self.status == 0:
                require(self.head is None and self.completed_heads == self.head_count * self.b['token_count'],
                        'missing successful head/token inventory')
            self.done = r
        elif event == 'terminal':
            require(r['flags'] == self.expected_flags, 'terminal cumulative arithmetic flags mismatch')
            require(self.done is not None and r['status'] == self.done['status'], 'terminal missing/mismatching actual done')
            require(r['matrix_inputs'] == r['matrix_outputs'] == self.counts['matrix']
                    and r['dma_count'] == self.counts['dma'] and r['write_requests'] == self.counts['l2_write']
                    and r['write_acks'] == self.counts['l2_ack'], 'terminal counters differ from accepted events')
            require(r['completed_heads'] == self.completed_heads
                    and r['completed_tokens'] == self.completed_heads // self.head_count,
                    'terminal head/token counters differ from accepted completions')
            require(r['total_tiles'] == (self.head_count * self.tiles if self.counts['dma'] else 0),
                    'terminal full-role tile count drift')
        elif event == 'reset_flush':
            require(self.kind == 'reset', 'unsolicited reset')
            stage = r['stage']
            expected_stage = 0 if self.name == 'reset_late_head' else 1
            target_head = 1 if expected_stage == 0 else 3
            request = self.pending['dma']
            reached = stage == expected_stage and self.completed_heads == target_head \
                and self.head is not None and request is not None \
                and request['index'] == (target_head + 1) * self.packets_per_head - 1 \
                and request['kind'] == 3 and _hex(request['source'], 16) == self.b['rope_base'] \
                and self.acks[2] == 8 and self.local['matrix'] == self.tiles * 1024
            require(reached, 'reset target stage/head/token was not reached')
        self.counts[event] += 1
        self.local[event] += 1


def verify_trace(path, vectors, *, required_main=None, suite='main'):
    """Verify the exact suite; neither a terminal claim nor required_main weakens it."""
    sequence = _suite_sequence(suite)
    inventory = Counter(sequence)
    expected_main = 4 if suite in ('main', 'all') else 0
    require(required_main is None or (type(required_main) is int and required_main == expected_main),
            'required_main conflicts with complete suite inventory')
    # Load lazily, since negative/fault-only suites do not consume all 40 heads.
    class Cases(dict):
        def __missing__(self, case):
            self[case] = load_case(vectors, case)
            return self[case]
    cases = Cases()
    active, seen, previous_cycle = None, 0, -1
    counts, completed, terminals = Counter(), Counter(), []
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
                    require(seen < len(sequence) and key == sequence[seen], 'unexpected/duplicate/reordered test identity')
                    active = _Transaction(r, cases)
                    seen += 1
                else:
                    require(active is not None and r['transaction'] == active.b['transaction'],
                            'trace event outside transaction or wrong owner')
                    active.consume(r)
                    if event in ('terminal', 'reset_flush'):
                        completed[(active.kind, active.name, active.b['case'])] += 1
                        terminals.append({'kind': active.kind, 'name': active.name, 'case': active.b['case'],
                                          'status': r.get('status'), 'matrix_outputs': active.counts['matrix'],
                                          'completed_heads': active.completed_heads})
                        active = None
                counts[event] += 1
            except (ValueError, KeyError, TypeError, IndexError) as exc:
                raise ValueError(f'trace line {lineno}: {exc}') from exc
    require(active is None, 'trace ended without completion/reset')
    require(completed == inventory, 'missing required suite test inventory')
    return {'suite': suite, 'events': dict(counts), 'transactions': seen, 'main_cases': expected_main,
            'bitexact_matrix_steps': counts['matrix'], 'terminals': terminals,
            'missing_extra_reordered_oracle_values': 0, 'actual_done_before_ack_checked': True,
            'raw_fabric_ddr_store_data_checked': True, 'cumulative_arithmetic_flags_checked': True, 'fabric_guard_readback_in_trace': False}
