"""Optional scratch arbitration around the supplier's single parent edge.

This adapter allocates neither a ParentLoan nor Banks. KV and scratch share the
binding's physical owner ID. Scratch release retires only the virtual borrower;
KvSupply remains responsible for releasing the physical lease at terminal.
"""
from dataclasses import dataclass

from ..attention_packed_owner.protocol import ScratchAction, ScratchResponse
from ..attention_bank_scratch.port import RawKvPort, valid_key
from ..raw_kv.model import RawKvPort as OriginalRawKvPort, Key, Request, Response, uint
from ..raw_kv_parent.model import ParentLoan


@dataclass(frozen=True)
class _PreparedEdge:
    action: ScratchAction | None
    response: ScratchResponse | None
    response_ready: bool
    ready: bool
    held: Response | None
    owned: tuple
    clock: int
    counts: dict
    operation: str | None


class ScratchMux:
    """Exact typed, single-flight scratch client of an existing parent loan."""
    _STATES = frozenset(('idle', 'acquire', 'lookup', 'miss_req', 'miss_wait',
                         'fill_wait', 'read_issue', 'read_wait', 'ack_wait',
                         'error_response'))
    _RAW = frozenset(('acquire', 'release', 'request', 'ack', 'abort'))
    _EVENTS = ('acquired', 'accepted', 'acked', 'released')

    def __init__(self, parent, *, owner_id):
        if type(parent) is not ParentLoan or parent.enabled is not True:
            raise ValueError('enabled exact original ParentLoan required')
        if not uint(owner_id, 32, True):
            raise ValueError('canonical scratch owner ID')
        raw = parent.raw
        if (type(raw) is not OriginalRawKvPort or raw.enabled is not True or
                raw.banks is not parent.owner.a_banks or not raw.drained or
                raw.owner is not None or raw.poison or any(parent.debts().values())):
            raise ValueError('scratch install requires unused drained healthy original raw port')
        self.parent, self.owner_id = parent, owner_id
        self.banks = parent.owner.a_banks
        parent.raw = RawKvPort(self.banks, enabled=True, scratch_enabled=True)
        self.raw = parent.raw
        self.context = None
        self.valid = set()
        self.active = self.key = self.response = None
        self.leased = self.poison = False
        self.error_reason = None
        self.last_serial = self.last_generation = self.edges = 0
        self.counts = dict(actions=0, acquires=0, physical_acquires=0,
                           begins=0, reads=0, writes=0, releases=0,
                           raw_requests=0, raw_acks=0, responses=0,
                           response_fires=0, rejected_requests=0,
                           foreign_raw_responses=0)
        self._prepared = None
        self._observed_edge = None
        self._masked = ()

    @property
    def idle(self):
        return self.active is None and self.response is None

    @property
    def reset_required(self):
        return self.poison

    def ports(self):
        return dict(ready=self.idle, idle=self.idle, response=self.response)

    def _fault(self, reason):
        self.poison = True
        self.error_reason = self.error_reason or reason
        self.valid.clear()

    def _healthy(self):
        p = self.parent
        return not (self.poison or p.poison or self.raw.poison or
                    p.owner.error is not None or p.owner.tiles.poison or
                    p.owner.drain_poison)

    def _check_controls(self, controls):
        if type(controls) is not dict or not set(controls) <= self._RAW:
            raise ValueError('canonical supplier raw controls')
        for name in ('acquire', 'release'):
            value = controls.get(name)
            if value is not None and (not uint(value, 32, True) or value != self.owner_id):
                raise ValueError('supplier and scratch owner IDs differ')
        if 'abort' in controls and type(controls['abort']) is not bool:
            raise ValueError('canonical supplier abort')
        request = controls.get('request')
        if request is not None and (type(request) is not Request or
                not valid_key(request.key) or request.key.owner != self.owner_id or
                not uint(request.data, 512)):
            raise ValueError('canonical supplier KV request')
        ack = controls.get('ack')
        if ack is not None and (not valid_key(ack) or ack.owner != self.owner_id):
            raise ValueError('canonical supplier KV ACK')
        if sum(controls.get(k) is not None for k in ('acquire', 'release', 'request')) > 1:
            raise ValueError('multiple supplier raw operations')

    def _validate_action(self, a):
        if type(a) is not ScratchAction or not a.valid() or a.serial <= self.last_serial:
            raise ValueError('canonical monotonic scratch action')
        if a.operation == 'acquire':
            if self.leased:
                raise ValueError('scratch lease already acquired')
            if self.raw.owner not in (None, self.owner_id):
                raise ValueError('foreign physical raw lease')
        else:
            if not self.leased or self.raw.owner != self.owner_id:
                raise ValueError('scratch action without shared physical lease')
            if a.operation == 'begin' and a.generation <= self.last_generation:
                raise ValueError('scratch generation must advance')
            if a.operation in ('read', 'write'):
                if self.context != (a.generation, a.query, a.kv_head):
                    raise ValueError('stale scratch context')
                if a.operation == 'read' and a.line not in self.valid:
                    raise ValueError('unwritten scratch read')

    def prepare(self, *, controls, state, core_pending, ddr_pending,
                action=None, response_ready=False, abort=False, closing=False,
                raw_ack_ready=True):
        """Merge controls without clocking anything; observe must follow once."""
        if self._prepared is not None:
            raise ValueError('previous scratch edge has not been observed')
        if self.parent.raw is not self.raw or self.raw.banks is not self.banks:
            raise ValueError('installed shared raw port changed')
        if type(state) is not str or state not in self._STATES:
            raise ValueError('unknown supplier state')
        if not all(type(x) is bool for x in
                   (core_pending, ddr_pending, response_ready, abort, closing, raw_ack_ready)):
            raise ValueError('canonical scratch handshake controls')
        self._check_controls(controls)
        merged = dict(controls)
        counts = dict(self.counts)
        stop = abort or merged.get('abort', False) or not self._healthy()
        if stop:
            self._fault('scratch transaction aborted or parent requires reset')
            merged['abort'] = True
        raw_op = any(merged.get(k) is not None for k in ('acquire', 'release', 'request', 'ack'))
        # A response-consumption edge does not admit the next action. In
        # particular, no payload is copied into a hidden look-ahead queue.
        ready = (self.idle and state == 'idle' and not core_pending and
                 not ddr_pending and self.raw.drained and not raw_op)
        a = action if ready else None
        if a is not None:
            if type(a) is not ScratchAction or not a.valid():
                raise ValueError('canonical monotonic scratch action')
            if (stop or closing) and a.operation != 'release':
                ready = False
                a = None
        if a is not None:
            self._validate_action(a)
        owned = []
        held = self.raw.response
        operation = None
        if self.active is not None:
            if raw_op or state != 'idle' or core_pending or ddr_pending:
                raise ValueError('KV operation overlaps accepted scratch debt')
            if held is not None:
                canonical = (type(held) is Response and valid_key(held.key, scratch_enabled=True)
                             and uint(held.data, 512))
                if not canonical or held.key != self.key:
                    self._fault('foreign or malformed raw scratch response; debt retained')
                    self.counts['foreign_raw_responses'] += 1
                    merged['abort'] = True
                elif raw_ack_ready:
                    merged['ack'] = self.key
                    owned.append('acked')
        if a is not None:
            operation = a.operation
            if operation == 'acquire' and self.raw.owner is None:
                merged['acquire'] = self.owner_id
                owned.append('acquired')
            elif operation in ('read', 'write'):
                key = Key(self.owner_id, a.serial, a.line, operation == 'write')
                data = sum(word << (32 * i) for i, word in enumerate(a.words))
                merged['request'] = Request(key, data)
                owned.append('accepted')
            # begin and release are metadata-only. A virtual release never
            # removes the supplier's bank exclusion, even on a poisoned edge.
        if self.response is not None and raw_op:
            raise ValueError('KV operation overlaps held scratch response')
        if (self.leased or not self.idle) and merged.get('release') is not None:
            raise ValueError('supplier release before virtual scratch retirement')
        self._prepared = _PreparedEdge(a, self.response, response_ready, ready,
                                       held, tuple(owned), self.parent.owner.clock,
                                       counts, operation)
        self._observed_edge = None
        self._masked = ()
        return merged

    def _respond(self, a, *, words=(), error=False):
        if self.response is not None:
            raise ValueError('scratch consumer response overwrite')
        self.response = ScratchResponse(a, words, bool(error))
        self.counts['responses'] += 1

    def observe(self, edge):
        """Retire only events from the one actual ParentLoan.tick result."""
        frame = self._prepared
        if frame is None:
            raise ValueError('scratch observe without prepare')
        if self.parent.owner.clock != frame.clock + 1:
            raise ValueError('scratch requires exactly one parent edge')
        if type(edge) is not dict or type(edge.get('raw')) is not dict:
            raise ValueError('actual parent raw edge required')
        r = edge['raw']
        if any(type(r.get(name)) is not bool for name in self._EVENTS):
            raise ValueError('canonical actual raw events required')
        out = dict(ready=frame.ready, response=frame.response, accepted=False,
                   response_fire=False, clock_before=frame.clock,
                   clock_after=self.parent.owner.clock, counts_before=frame.counts)
        if frame.response is not None and frame.response_ready:
            if self.response is not frame.response:
                raise ValueError('held scratch response changed')
            self.response = None
            out['response_fire'] = True
            self.counts['response_fires'] += 1
        a = frame.action
        if a is not None:
            out['accepted'] = True
            self.last_serial = a.serial
            self.counts['actions'] += 1
            if a.operation in ('read', 'write'):
                self.counts['reads' if a.operation == 'read' else 'writes'] += 1
                if r['accepted']:
                    self.active = a
                    self.key = Key(self.owner_id, a.serial, a.line, a.operation == 'write')
                    self.counts['raw_requests'] += 1
                else:
                    self._fault('physical raw scratch request rejected')
                    self.counts['rejected_requests'] += 1
                    self._respond(a, words=(0,) * 16 if a.operation == 'read' else (), error=True)
            elif a.operation == 'acquire':
                ok = ((r['acquired'] if 'acquired' in frame.owned else True)
                      and self.raw.owner == self.owner_id and self._healthy())
                if ok:
                    self.leased = True
                    self.context = None
                    self.valid.clear()
                    self.counts['acquires'] += 1
                    self.counts['physical_acquires'] += int(r['acquired'])
                self._respond(a, error=not ok)
            elif a.operation == 'begin':
                ok = self._healthy() and self.raw.owner == self.owner_id and self.raw.drained
                if ok:
                    self.context = (a.generation, a.query, a.kv_head)
                    self.last_generation = a.generation
                    self.valid.clear()
                    self.counts['begins'] += 1
                self._respond(a, error=not ok)
            elif a.operation == 'release':
                ok = self.raw.drained and self.raw.owner == self.owner_id
                if ok:
                    self.leased = False
                    self.context = None
                    self.valid.clear()
                    self.counts['releases'] += 1
                self._respond(a, error=not ok)
        if r['acked'] and 'acked' in frame.owned:
            held, active = frame.held, self.active
            canonical = (type(held) is Response and valid_key(held.key, scratch_enabled=True)
                         and uint(held.data, 512))
            if (active is None or not canonical or held.key != self.key or
                    r.get('response') is not held or not self.raw.drained):
                self._fault('foreign raw ACK observation; scratch debt retained')
            else:
                bad = not self._healthy()
                words = tuple((held.data >> (32 * i)) & 0xffffffff for i in range(16)) if active.operation == 'read' else ()
                if active.operation == 'write' and not bad:
                    self.valid.add(active.line)
                self._respond(active, words=words, error=bad)
                self.active = self.key = None
                self.counts['raw_acks'] += 1
        self.edges += 1
        self._observed_edge, self._masked = id(edge), frame.owned
        self._prepared = None
        out['counts_after'] = dict(self.counts)
        out['idle'] = self.idle
        out['reset_required'] = self.poison
        return out

    def supply_raw(self, edge):
        """Hide scratch-owned handshakes from the KV state machine only."""
        if self._prepared is not None or self._observed_edge != id(edge):
            raise ValueError('scratch edge must be observed before supplier use')
        raw = dict(edge['raw'])
        for name in self._masked:
            raw[name] = False
        return raw
