"""Bounded transaction specification for a proposed causal PV capture route.

This is NOT the existing owner/service and never runs arithmetic. Opaque 16-KiB
return bytes exercise identity, storage and ACK rules only. Operations below
are accepted events, not clocks; no latency or utilization is inferred.

One shared capture is drained per emitted return, rather than waiting for an
entire cohort. Otherwise interleaved cohorts can deadlock behind the FIFO head.
"""
from collections import Counter, deque
from dataclasses import dataclass

try:
    from . import model as geometry
except ImportError:
    import model as geometry


class ProtocolError(ValueError):
    pass


class BoundedFifo:
    def __init__(self, capacity):
        self.capacity = capacity
        self._items = deque()

    def __len__(self):
        return len(self._items)

    @property
    def head(self):
        return self._items[0] if self._items else None

    def push(self, item):
        if len(self) >= self.capacity:
            raise ProtocolError('FIFO capacity exceeded')
        self._items.append(item)

    def pop(self):
        if not self._items:
            raise ProtocolError('empty FIFO')
        return self._items.popleft()


@dataclass(frozen=True)
class Step:
    epoch: int
    group: int
    context: int
    cohort: int
    key: int
    last: bool
    final_rows: tuple

    @property
    def emit(self):
        return bool(self.final_rows)


@dataclass(frozen=True)
class Return:
    step: Step
    raw: bytes


@dataclass(frozen=True)
class Write:
    epoch: int
    group: int
    sequence: int
    context: int
    cohort: int
    row: int
    query: int
    head: int
    beat: int
    address: int
    data: bytes


class CaptureModel:
    """Five contexts, eight metadata entries, two wide results, one capture.

    The leaf scheduler releases a busy context only on accepted return. Thus
    this conservative specification reaches at most five live metadata entries
    despite preserving the real capacity of eight. Same-edge replacement is
    not timed. K/V and P readiness must be supplied as explicit committed flags;
    this model does not implement their loader or a physical SRAM lease.
    """
    def __init__(self, destination=0x100000):
        if type(destination) is not int or destination < 0 or destination % 64:
            raise ValueError('aligned destination required')
        if destination + 128 * 1536 * 4 > 1 << 56:
            raise ValueError('output outside 56-bit span')
        self.destination = destination
        self.epoch = 0
        self.group = 0
        self.state = 'idle'
        self.poison = False
        self.reason = None
        self.metadata = BoundedFifo(8)
        self.results = BoundedFifo(2)
        self.contexts = {}
        self.capture = None
        self.pending_write = None
        self.offered_write = None
        self.backend_done = False
        self.sequence = 0
        self.counts = Counter()
        self.highwater = Counter()

    def _reject(self, reason):
        self.poison = True
        self.reason = reason
        self.offered_write = None
        if self.pending_write is None:
            self.capture = None
        if self.state == 'idle':
            self.state = 'locked'
        raise ProtocolError(reason)

    def _check(self):
        conditions = (len(self.contexts) <= 5, len(self.metadata) <= 8,
                      len(self.results) <= 2,
                      self.capture is None or len(self.capture['raw']) == 16384,
                      self.pending_write is None or len(self.pending_write.data) == 64,
                      sum(c['busy'] for c in self.contexts.values()) == len(self.metadata))
        if not all(conditions):
            self._reject('fixed-resource invariant violated')
        self.highwater['metadata'] = max(self.highwater['metadata'], len(self.metadata))
        self.highwater['results'] = max(self.highwater['results'], len(self.results))
        self.highwater['capture'] = max(self.highwater['capture'], int(self.capture is not None))
        self.highwater['write'] = max(self.highwater['write'], int(self.pending_write is not None))

    def begin(self, tiles, *, kv_committed, probabilities_committed):
        tiles = tuple(tiles)
        if self.state != 'idle' or self.poison:
            self._reject('group admission before prior terminal/reset')
        if not 1 <= len(tiles) <= 5 or len({t.identity for t in tiles}) != len(tiles):
            self._reject('one to five distinct cohorts required')
        if len({t.kv_head for t in tiles}) != 1:
            self._reject('one committed KV head per group')
        if kv_committed is not True or probabilities_committed is not True:
            self._reject('uncommitted operands')
        for tile in tiles:
            if (type(tile.identity) is not int or tile.identity < 0 or
                    not 1 <= len(tile.rows) <= 32 or type(tile.kv_head) is not int or tile.kv_head not in (0, 1) or
                    any(not (type(q) is int and type(h) is int and
                             0 <= q < 128 and 0 <= h < 12 and h // 6 == tile.kv_head)
                        for q, h in tile.rows) or
                    tuple(sorted(tile.rows)) != tile.rows or len(set(tile.rows)) != len(tile.rows)):
                self._reject('invalid cohort geometry')
        coordinates = [coordinate for tile in tiles for coordinate in tile.rows]
        if len(set(coordinates)) != len(coordinates):
            self._reject('cohorts overlap output coordinates')
        self.group += 1
        self.state = 'running'
        self.backend_done = False
        self.contexts = {i: dict(tile=t, next=0, busy=False, last_returned=False,
                                 captured=set(), acknowledged=set())
                         for i, t in enumerate(tiles)}
        self.counts['groups'] += 1
        self._check()

    def can_issue(self, context):
        c = self.contexts.get(context)
        return bool(self.state == 'running' and not self.poison and c is not None and
                    not c['busy'] and c['next'] < c['tile'].keys and len(self.metadata) < 8)

    def issue(self, context, key=None, *, ready=True):
        if type(context) is not int or context not in self.contexts:
            self._reject('invalid context')
        c = self.contexts[context]
        if key is not None and (type(key) is not int or key != c['next']):
            self._reject('out-of-order key')
        if not self.can_issue(context) or not ready:
            return None
        k = c['next']
        step = Step(self.epoch, self.group, context, c['tile'].identity, k,
                    k + 1 == c['tile'].keys,
                    tuple(i for i, (q, _) in enumerate(c['tile'].rows) if q == k))
        self.metadata.push(step)
        c['busy'] = True
        c['next'] += 1
        self.counts['issues'] += 1
        self._check()
        return step

    @property
    def return_ready(self):
        step = self.metadata.head
        return bool(step is not None and (self.poison or not step.emit or len(self.results) < 2))

    def accept_return(self, step, raw, *, valid=True):
        if not valid:
            return False
        if not isinstance(step, Step) or step != self.metadata.head:
            self._reject('stale, duplicate or reordered return identity')
        if type(raw) is not bytes or len(raw) != 16384:
            self._reject('return must contain exactly one opaque wide value')
        if not self.return_ready:
            return False
        self.metadata.pop()
        c = self.contexts[step.context]
        c['busy'] = False
        c['last_returned'] = step.last
        if step.emit and not self.poison:
            self.results.push(Return(step, raw))
            self.counts['emitted_returns'] += 1
        self.counts['returns'] += 1
        self._check()
        return True

    def capture_next(self, *, ready=True):
        if self.poison or self.capture is not None or self.results.head is None or not ready:
            return False
        result = self.results.head
        step = result.step
        c = self.contexts[step.context]
        if step.epoch != self.epoch or step.group != self.group or c['tile'].identity != step.cohort:
            self._reject('capture lease identity mismatch')
        if any(row in c['captured'] for row in step.final_rows):
            self._reject('duplicate causal capture')
        # Only selected row-final bytes are copied to the sole physical capture.
        # Other entries stay poison; padded suffix values never become output.
        raw = bytearray(b'\xa5' * 16384)
        for row in step.final_rows:
            if c['tile'].rows[row][0] != step.key:
                self._reject('capture is not at causal row end')
            physical_row, first_column = geometry.physical_cell(row, 0)
            offset = physical_row * 1024 + first_column * 4
            raw[row * 512:(row + 1) * 512] = result.raw[offset:offset + 512]
        self.results.pop()
        c['captured'].update(step.final_rows)
        self.capture = dict(step=step, rows=step.final_rows, raw=raw, row_index=0, beat=0)
        self.counts['captured_rows'] += len(step.final_rows)
        self._check()
        return True

    @property
    def write_request(self):
        if self.poison or self.capture is None or self.pending_write is not None:
            return None
        if self.offered_write is None:
            cap = self.capture
            step = cap['step']
            row = cap['rows'][cap['row_index']]
            query, head = self.contexts[step.context]['tile'].rows[row]
            beat = cap['beat']
            offset = row * 512 + beat * 64
            self.offered_write = Write(self.epoch, self.group, self.sequence,
                step.context, step.cohort, row, query, head, beat,
                self.destination + (query * 1536 + head * 128 + beat * 16) * 4,
                bytes(cap['raw'][offset:offset + 64]))
        return self.offered_write

    def accept_write(self, *, ready=True):
        request = self.write_request
        if request is None or not ready:
            return None
        self.pending_write = request
        self.offered_write = None
        self.sequence += 1
        self.counts['writes'] += 1
        self._check()
        return request

    def accept_ack(self, request, *, nbytes=64, error=False):
        # A stale ACK cannot erase the current physical obligation. Abort still
        # waits for the matching real response; no timeout manufactures it.
        if self.pending_write is None or request != self.pending_write:
            self._reject('stale, duplicate or mismatched write ACK')
        if type(nbytes) is not int or nbytes != 64:
            self._reject('write ACK byte count mismatch')
        self.pending_write = None
        self.counts['write_acks'] += 1
        if error:
            self.poison = True
            self.reason = 'write ACK error'
        if self.poison:
            self.capture = None
            self.offered_write = None
        else:
            self.counts['acknowledged_bytes'] += 64
            cap = self.capture
            if cap['beat'] == 7:
                self.contexts[request.context]['acknowledged'].add(request.row)
                cap['row_index'] += 1
                cap['beat'] = 0
                if cap['row_index'] == len(cap['rows']):
                    self.capture = None
            else:
                cap['beat'] += 1
        self._check()

    def abort(self):
        if self.state != 'running':
            self._reject('abort outside active group')
        self.poison = True
        self.reason = 'local abort/reset requires real drain'
        self.offered_write = None
        if self.pending_write is None:
            self.capture = None

    def drain_result(self):
        if not self.poison:
            self._reject('cannot discard a successful result')
        if self.results.head is None:
            return False
        self.results.pop()
        self._check()
        return True

    @property
    def done_ready(self):
        """Readiness for a successful backend completion only.

        A caller holding a completion must use can_accept_done(error=...),
        since an error can terminate a group without a successful last step.
        """
        return self.can_accept_done(error=False)

    def can_accept_done(self, *, error=False):
        return bool(type(error) is bool and self.state == 'running' and
                    not self.backend_done and not len(self.metadata) and
                    not len(self.results) and (error or self.poison or
                        all(c['last_returned'] for c in self.contexts.values())))

    def accept_done(self, epoch, group, *, error=False):
        if ((epoch, group) != (self.epoch, self.group) or
                not self.can_accept_done(error=error)):
            self._reject('early, duplicate or stale MatrixDone')
        # Consume the sole backend completion even when its status differs
        # from sticky owner/writeback poison. These are independent domains.
        # An error done can also close an interrupted group without a last
        # step, once every accepted step/result obligation has really drained.
        if error:
            self.poison = True
            self.reason = 'backend MatrixDone error'
            self.offered_write = None
            if self.pending_write is None:
                self.capture = None
        self.backend_done = True
        self.counts['matrix_done'] += 1
        self.counts['backend_error_done'] += int(error)

    @property
    def terminal_ready(self):
        return bool(self.state == 'running' and self.backend_done and not len(self.metadata)
                    and not len(self.results) and self.capture is None and self.pending_write is None)

    def retire_group(self):
        if not self.terminal_ready:
            self._reject('terminal before all accepted work/ACKs drain')
        if not self.poison:
            for c in self.contexts.values():
                if c['acknowledged'] != set(range(len(c['tile'].rows))):
                    self._reject('terminal before every causal row ACK')
        self.counts['error_terminals' if self.poison else 'success_terminals'] += 1
        self.state = 'locked' if self.poison else 'idle'
        self.contexts = {}
        self._check()

    def coordinated_reset(self, *, backend_reset_confirmed):
        if (backend_reset_confirmed is not True or self.state != 'locked' or
                len(self.metadata) or len(self.results) or self.pending_write is not None or
                self.capture is not None):
            self._reject('reset cannot cancel accepted obligations')
        self.epoch += 1
        self.poison = False
        self.reason = None
        self.state = 'idle'
        self.backend_done = False
        self.contexts = {}

    def report(self):
        return dict(status='BEHAVIOR_SPEC_ONLY_CANDIDATE_BLOCKED',
                    fixed_contexts=5, metadata_capacity=8, result_capacity=2,
                    capture_bytes=16384, max_outstanding_write_beats=1,
                    state=self.state, poison=self.poison, counts=dict(self.counts),
                    highwater=dict(self.highwater), arithmetic_executed=False,
                    bit_exact=False, actual_rtl_run=False, source_interface_implemented=False,
                    hardware_cycles=None, hardware_utilization=None,
                    timing_model=False,
                    unresolved=['signed-zero and arithmetic/finite-check equivalence',
                                'physical SRAM lease, routing and bank-port implementation',
                                'production emit-last/length adapter and return identity routing',
                                'full-block performance and physical timing'])
