"""Read-only packed field collection. No arithmetic service or reference calls.

The private buffers use the same ten numerical fields and causal presence mask
as the official observer. Frequencies describe actual packed events, never
fabricated copies of the eight legacy PV-column observations.
"""
from array import array
import hashlib
import json
from pathlib import Path
import sys

SENTINEL = 0xa5963cc3
VERSION = 'qwen2-packed-causal-observation-v1'
FIELDS = ('dot_parts', 'unrounded_dot_sum', 'dot_bf16', 'scores_bf16',
          'softmax_exp', 'softmax_fp32', 'prob_bf16', 'normalizer', 'pv_raw', 'pv_bf16')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def uint(word):
    return type(word) is int and 0 <= word < 1 << 32


class PackedFields:
    def __init__(self, rows):
        require(type(rows) is int and rows in (1, 2, 16), 'packed capture admits M1/M2/M16 only')
        self.rows = rows
        self.fields = {}
        self.pending_dot = None
        self.pending_prob = None
        for name in FIELDS:
            shape = ((12, rows, rows, 16) if name == 'dot_parts' else
                     (12, rows, 3) if name == 'normalizer' else
                     (12, rows, 128) if name in ('pv_raw', 'pv_bf16') else
                     (12, rows, rows))
            count = 1
            for n in shape:
                count *= n
            self.fields[name] = dict(shape=shape, words=array('I', [SENTINEL]) * count,
                observed=bytearray(count), frequency=array('H', [0]) * count, writes=0, repeats=0)

    def _put(self, name, coordinates, values):
        require(name in FIELDS, 'unknown capture field')
        field = self.fields[name]
        shape, offset = field['shape'], 0
        require(type(coordinates) is tuple and len(coordinates) == len(shape), 'capture rank')
        for i, n in zip(coordinates, shape):
            require(type(i) is int and 0 <= i < n, 'capture coordinate')
            offset = offset * n + i
        require(type(values) is tuple and 0 < len(values) <= shape[-1] - coordinates[-1],
                'capture vector crosses final dimension')
        if name not in ('normalizer', 'pv_raw', 'pv_bf16'):
            require(coordinates[2] <= coordinates[1], 'future causal key capture')
        require(all(uint(x) for x in values), 'capture word must be uint32')
        require(not any(field['observed'][offset:offset + len(values)]), 'duplicate packed capture')
        for i, value in enumerate(values, offset):
            field['words'][i], field['observed'][i], field['frequency'][i] = value, 1, 1
        field['writes'] += len(values)

    def begin_dot(self, local):
        require(self.pending_dot is None, 'unfinished dot scalar capture')
        h, t, k = local['head'], local['token'], local['key']
        lanes = tuple(local['lanes'][16*k:16*(k+1)])
        require(len(lanes) == 16, 'missing selected QK lanes')
        self.pending_dot = dict(coordinates=(h,t,k), total=local['total'], lanes=lanes, returns=[])

    def dot_return(self, operation, a, b, result):
        p = self.pending_dot
        require(p is not None and uint(a) and uint(b) and uint(result), 'unowned dot scalar return')
        sequence = p['returns']
        i = len(sequence)
        expected = (('bf', p['total'], 0) if i == 0 else
                    ('mul', sequence[0], 0x3db504f3) if i == 1 else
                    ('bf', sequence[1], 0) if i == 2 else None)
        require(expected == (operation,a,b), 'dot scalar operation/order changed')
        sequence.append(result)

    def end_dot(self, local):
        p = self.pending_dot
        require(p is not None and len(p['returns']) == 3 and
                p['coordinates'] == (local['head'],local['token'],local['key']) and
                local['total'] == p['total'] and local['score'] == p['returns'][2] and
                local['scores'][-1] == local['score'], 'incomplete dot scalar capture')
        c = p['coordinates']
        self._put('dot_parts', c + (0,), p['lanes'])
        for name,value in (('unrounded_dot_sum',p['total']), ('dot_bf16',p['returns'][0]),
                           ('scores_bf16',local['score'])):
            self._put(name, c, (value,))
        self.pending_dot = None

    def exponential(self, local):
        self._put('softmax_exp', (local['kv']*6+local['h'],local['token'],len(local['weights'])),
                  (local['weight'],))

    def inverse_return(self, local, operation, a, b, result):
        require((operation,a,b) == ('div',0x3f800000,local['total']), 'inverse scalar operation changed')
        self._put('normalizer', (local['kv']*6+local['h'],local['token'],0),
                  (local['maxima'][local['h']],local['total'],result))

    def begin_probability(self, local):
        require(self.pending_prob is None, 'unfinished probability scalar capture')
        self.pending_prob = dict(token=local['token'],kv=local['kv'],key=local['key'], returns=[])

    def probability_return(self, local, head, operation, a, b, result):
        p = self.pending_prob
        require(p is not None and uint(a) and uint(b) and uint(result) and type(head) is int and 0 <= head < 6 and
                (p['token'],p['kv'],p['key']) == (local['token'],local['kv'],local['key']),
                'unowned probability scalar return')
        sequence = p['returns']; index = len(sequence)
        require(index // 2 == head, 'probability head/order changed')
        expected = (('mul',local['panel'][head][p['key']],local['inverses'][head]) if index % 2 == 0
                    else ('bf',sequence[-1],0))
        require((operation,a,b) == expected, 'probability scalar operation/order changed')
        sequence.append(result)

    def end_probability(self, local):
        p = self.pending_prob
        require(p is not None and (p['token'],p['kv'],p['key']) == (local['token'],local['kv'],local['key']) and
                len(p['returns']) == 12 and len(local['a']) == 16 and
                tuple(local['a'][6:]) == (0,)*10, 'incomplete packed probability')
        for h in range(6):
            fp, bf = p['returns'][2*h:2*h+2]
            require(local['a'][h] << 16 == bf, 'packed BF16 probability differs from scalar return')
            c = (p['kv']*6+h,p['token'],p['key'])
            self._put('softmax_fp32',c,(fp,)); self._put('prob_bf16',c,(bf,))
        self.pending_prob = None

    def store(self, local):
        # LINE before the real _write. The normal terminal/ACK checks are still
        # required before these attempted stores can be sealed as acknowledged.
        c = (local['kv']*6+local['h'],local['token'],local['d'])
        raw = tuple(local['result'].value[local['h']][local['d']:local['d']+16])
        require(len(raw) == len(local['words']) == 16, 'incomplete packed PV store')
        self._put('pv_raw',c,raw)
        self._put('pv_bf16',c,tuple(local['words']))

    def _bytes(self, name, kind='words'):
        values = array('I' if kind == 'words' else 'H', self.fields[name][kind])
        if sys.byteorder != 'little':
            values.byteswap()
        return values.tobytes()

    def coverage(self):
        if self.pending_dot is not None or self.pending_prob is not None or set(self.fields) != set(FIELDS):
            return False
        m = self.rows
        for name, f in self.fields.items():
            shape = ((12,m,m,16) if name == 'dot_parts' else (12,m,3) if name == 'normalizer' else
                     (12,m,128) if name in ('pv_raw','pv_bf16') else (12,m,m))
            count = 1
            for n in shape: count *= n
            if (f['shape'] != shape or len(f['words']) != count or len(f['observed']) != count or
                    len(f['frequency']) != count or type(f['writes']) is not int or type(f['repeats']) is not int):
                return False
            for h in range(12):
                for t in range(m):
                    width = 3 if name == 'normalizer' else 128 if name in ('pv_raw','pv_bf16') else 16 if name == 'dot_parts' else 1
                    keys = (None,) if name in ('normalizer','pv_raw','pv_bf16') else range(m)
                    for k in keys:
                        start = ((h*m+t) if k is None else (h*m*m+t*m+k))*width
                        expected = int(k is None or k <= t)
                        for i in range(start,start+width):
                            if (f['observed'][i] != expected or f['frequency'][i] != expected or
                                    (not expected and f['words'][i] != SENTINEL)):
                                return False
            if f['writes'] != sum(f['observed']) or f['repeats'] != 0:
                return False
        return True

    def field_summary(self):
        return {name: dict(shape=f['shape'],words=len(f['words']),observed_words=sum(f['observed']),
                    raw_sha256=hashlib.sha256(self._bytes(name)).hexdigest(),
                    presence_sha256=hashlib.sha256(bytes(f['observed'])).hexdigest(),
                    frequency_sha256=hashlib.sha256(self._bytes(name,'frequency')).hexdigest(),
                    writes=f['writes'],identical_repeats=f['repeats']) for name,f in self.fields.items()}
