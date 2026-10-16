"""Proposed scratch borrower on the actual Dense owner's sole A Banks.

One 64-byte transport/staging beat, no score/prob payload array. This is a
software routing variant; the existing Chisel range still rejects these lines.
"""
from dataclasses import dataclass
from collections import Counter
from ..raw_kv_parent.model import ParentLoan
from .port import RawKvPort, Key, Request, uint, location


@dataclass(frozen=True)
class Context:
    generation: int
    query: int
    kv_head: int
    keys: int


def valid_context(c):
    return (type(c) is Context and uint(c.generation, 32, True) and
            uint(c.query, 7) and uint(c.kv_head, 1) and
            type(c.keys) is int and 1 <= c.keys <= 128 and c.keys == c.query+1)


def address(plane, head, key):
    if plane not in ('score', 'prob') or type(head) is not int or not 0 <= head < 6 or type(key) is not int or not 0 <= key < 128:
        raise ValueError('scratch coordinate')
    return (4096 if plane == 'score' else 4144)+8*head+key//16, key%16


class Scratch:
    def __init__(self, *, owner=None, edge=None, stalls=0, enabled=False):
        if type(enabled) is not bool:
            raise ValueError("scratch enabled must be canonical bool")
        if type(stalls) is not int or not 0 <= stalls <= 1000:
            raise ValueError('scratch stalls')
        self.parent = ParentLoan(owner=owner, enabled=enabled)
        if any(self.parent.debts().values()) or not self.parent.raw.drained or self.parent.raw.owner is not None:
            raise ValueError('borrower installation requires drained original owner')
        self.parent.raw = RawKvPort(self.parent.owner.a_banks, enabled=enabled, scratch_enabled=enabled)
        self.banks = self.parent.owner.a_banks
        self.edge = edge or (lambda: None)
        self.stalls = stalls
        self.context = None
        self.generation = 0
        self.tag = 0
        self.owner_id = 1
        self.counts = Counter()
        self.events = []  # test trace only, no hardware storage assertion
        self.initialized = set()  # 96 bounded beat-valid bits; no payload
        self.score_written = [0]*6
        self.weight_written = [0]*6
        self.normalized = [0]*6
        self.staging = None  # single 512-bit read/RMW beat, proposed existing dv[16]
        self.abort_requested = False
        self.active = None  # accepted context/key, preserved through debt

    def tick(self, **inputs):
        if self.abort_requested: inputs['abort'] = True
        result = self.parent.tick(**inputs)['raw']
        self.counts['edges'] += 1
        self.edge()
        self.events.append((self.counts['edges'], tuple(sorted(self.banks.reads.items())),
                            tuple(sorted(self.banks.writes.items())), result['accepted'], result['acked']))
        self.counts['bank_reads'] += len(self.banks.reads)
        self.counts['bank_writes'] += len(self.banks.writes)
        return result

    def abort(self):
        self.abort_requested = True

    def acquire(self):
        if not self.tick(acquire=self.owner_id)['acquired']:
            raise ValueError('scratch lease denied')

    def begin(self, query, kv_head, keys):
        if not self.parent.raw.drained or self.active is not None or self.staging is not None or self.parent.raw.owner != self.owner_id or self.parent.raw.poison:
            raise ValueError('scratch context busy/poisoned')
        candidate = Context(self.generation+1, query, kv_head, keys)
        if not valid_context(candidate): raise ValueError('scratch context')
        self.context = candidate
        self.generation += 1
        self.initialized.clear()
        self.score_written[:] = [0]*6
        self.weight_written[:] = [0]*6
        self.normalized[:] = [0]*6
        return candidate

    def require(self, context):
        if not valid_context(context) or context != self.context:
            raise ValueError('stale scratch generation')
        if self.parent.raw.poison or self.parent.poison:
            raise ValueError('scratch poisoned')

    def transfer(self, context, line, *, write=False, data=0):
        self.require(context)
        if type(line) is not int or not 4096 <= line < 4192 or type(write) is not bool or not uint(data, 512):
            raise ValueError('scratch transfer')
        if self.active is not None or not self.parent.raw.drained:
            raise ValueError('scratch transaction debt')
        if not write and line not in self.initialized:
            raise ValueError('unwritten scratch beat')
        if self.tag == 0xffffffff: raise ValueError('tag exhaustion')
        self.tag += 1
        key = Key(self.owner_id, self.tag, line, write)
        self.active = (context, key)
        if not self.tick(request=Request(key, data))['accepted']:
            self.active = None
            raise ValueError('scratch request rejected')
        self.counts['write_requests' if write else 'read_requests'] += 1
        self.tick()  # synchronous result capture, cannot ACK this edge
        held = self.parent.raw.response
        if held is None or held.key != key: raise ValueError('missing scratch response')
        for _ in range(self.stalls):
            self.tick()
            if self.parent.raw.response is not held: raise ValueError('scratch response changed')
        # Capture the existing held transport payload into dv[16] before ACK.
        if not write: self.staging = held.data
        out = self.tick(ack=key)
        if not out['acked']: raise ValueError('scratch ACK rejected')
        self.counts['acks'] += 1
        self.active = None
        if self.parent.raw.poison or self.parent.poison:
            self.staging = None
            raise ValueError('accepted scratch retired poisoned')
        if write: self.initialized.add(line)
        return held.data

    def write_scores(self, context, head, words):
        self.require(context)
        if type(head) is not int or not 0 <= head < 6 or self.score_written[head] or len(words) != context.keys or any(not uint(x,32) for x in words):
            raise ValueError('score row sequence')
        for start in range(0, context.keys, 16):
            # At most16 score words; proposed tmp[16] owns the full-line write.
            beat = sum(words[i] << (32*(i-start)) for i in range(start, min(start+16,context.keys)))
            self.transfer(context, address('score',head,start)[0], write=True, data=beat)
            self.score_written[head] = min(start+16,context.keys)

    def read_word(self, context, plane, head, key, *, normalized=False):
        self.require(context)
        if type(normalized) is not bool: raise ValueError("normalization flag")
        line, offset = address(plane,head,key)
        if key >= context.keys: raise ValueError('inactive key')
        limit = self.score_written[head] if plane == 'score' else (self.normalized[head] if normalized else self.weight_written[head])
        if key >= limit: raise ValueError('unwritten scratch word')
        if plane == 'prob' and not normalized and key < self.normalized[head]:
            raise ValueError('weight overwritten by normalized probability')
        if self.staging is not None: raise ValueError('staging contention')
        self.staging = self.transfer(context,line)
        try: return (self.staging >> (32*offset)) & 0xffffffff
        finally: self.staging = None

    def write_probability(self, context, head, key, value, *, normalized=False):
        self.require(context)
        line, offset = address('prob',head,key)
        counters = self.normalized if normalized else self.weight_written
        if type(normalized) is not bool or key >= context.keys or key != counters[head] or not uint(value,32):
            raise ValueError('probability sequence')
        if normalized and self.weight_written[head] != context.keys:
            raise ValueError('normalization before complete sum')
        if self.staging is not None: raise ValueError('staging contention')
        # No six-line cache. Each scalar word update is an explicit full-beat
        # read-modify-write, except the first word of a previously unused beat.
        self.staging = self.transfer(context,line) if line in self.initialized else 0
        try:
            self.staging = (self.staging & ~(0xffffffff << (32*offset))) | (value << (32*offset))
            self.transfer(context,line,write=True,data=self.staging)
            counters[head] += 1
        finally: self.staging = None

    def release(self):
        if self.active is not None or self.staging is not None or not self.parent.raw.drained:
            raise ValueError('scratch release debt')
        if not self.tick(release=self.owner_id)['released']:
            raise ValueError('scratch release rejected')
        self.context = None
        self.initialized.clear()
