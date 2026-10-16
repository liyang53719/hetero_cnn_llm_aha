"""Keep the existing joined Matrix result slot owned until scalar consumption.

No new tile copy: views read the actual held MatrixPort payload. Selected-cell
arithmetic/timing remain proposals; score/prob/input storage remains unplaced.
"""
from collections import Counter
from ..attention_scheduled_numeric.controller import Controller as Base, NumericalFault
from ..attention_scheduled_numeric.ports import MatrixPort, ScalarPort
from ..attention_scalar_schedule.model import Offer


class TileView:
    """Capability for a live joined result, never a detached words tuple."""
    __slots__ = ('controller', 'group')
    def __init__(self, controller, group):
        self.controller, self.group = controller, group

    def __getitem__(self, index):
        return self.controller.read_result(self.group, index)


class Controller(Base):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.slot = None
        self.read_events = []
        self.ack_events = []
        self.views = []
        self.peak_slots = 0

    def ordinary_owner_ready(self):
        return super().ordinary_owner_ready() and self.slot is None

    def clock(self):
        return self.ticks + (self.port.schedule.cycle if isinstance(self.port, ScalarPort) else 0)

    def invariant(self):
        occupied = int(self.slot is not None)
        if occupied not in (0, 1):
            raise ValueError('result credit')
        if self.slot is not None:
            port = self.slot['port']
            if port.pending is not None or port.held is None or port.retired or id(port.held.words) != self.slot['words_id']:
                raise ValueError('joined slot ownership')
        self.peak_slots = max(self.peak_slots, occupied)
        return dict(occupied=occupied, available=2-occupied)

    def hold_edge(self):
        self.invariant()
        if self.slot is not None:
            port = self.slot['port']
            before = (port.calls, port.conversions, port.held)
            out = port.tick()
            if out['response'] is not before[2] or out['ack_fire'] or (port.calls, port.conversions, port.held) != before:
                raise ValueError('held joined payload changed')
            self.counts['retained_result_hold_edges'] += 1

    def read_result(self, group, index):
        self.invariant()
        if self.slot is None or type(group) is not int or group != self.slot['port'].group or type(index) is not int or index not in self.slot['selected']:
            raise ValueError('stale/unselected result view')
        # PV output is deliberately consumed at one word/edge. QK may select
        # at most16 useful cells on the existing wide result bus per edge.
        # These mux/capture rates are explicit proposals, not measured timing.
        if self.slot['mask'] == 15:
            if self.port is not None:
                raise ValueError('PV capture during another compute phase')
            self.hold_edge()
            self.ticks += 1
        edge = self.clock()
        limit = 1 if self.slot['mask'] == 15 else 16
        if self.slot['reads_per_edge'][edge] >= limit:
            raise ValueError('result selector/capture bandwidth')
        self.slot['reads_per_edge'][edge] += 1
        self.slot['seen'].add(index)
        self.read_events.append((edge, group, index))
        self.counts['joined_result_word_reads'] += 1
        return self.slot['port'].held.words[index]

    def retire_slot(self, *, poison=False):
        self.invariant()
        if self.slot is None:
            raise ValueError('no retained result')
        if not poison and self.slot['seen'] != self.slot['selected']:
            raise ValueError('result consumed incompletely')
        port = self.slot['port']
        out = port.tick(ack=port.group, abort=poison)
        if not out['ack_fire'] or (not poison and not out['publish']) or (poison and out['publish']):
            raise ValueError('joined retirement')
        self.ack_events.append((self.clock(), port.group, poison))
        self.counts['matrix_result_acks'] += 1
        self.ticks += 2  # ACK edge plus explicit group-completion fence
        self.slot = None
        self.invariant()

    def matrix_group(self, payloads, selected, mask):
        if self.port is not None or self.slot is not None:
            raise ValueError('compute/result credit contention')
        self.counts['matrix_groups'] += 1
        port = MatrixPort(len(payloads), mask, selected, self.fma,
                          lambda x: self.operation('bf', x, 0),
                          latency=self.timing.matrix_latency, group=self.counts['matrix_groups'])
        self.port = port
        self.ticks += 1
        for payload in payloads:
            while port.pending is not None: port.tick()
            if port.poison: break
            for _ in range(self.timing.feed_stalls):
                before = port.calls + port.conversions
                out = port.tick(payload=payload)
                if out['accepted'] or before != port.calls + port.conversions:
                    raise ValueError('Matrix arithmetic before admission')
            if not port.tick(payload=payload, feed_ready=True)['accepted']:
                raise ValueError('Matrix step admission')
        while port.held is None: port.tick()
        self.ticks += port.cycle
        self.counts['matrix_steps'] += port.accepted
        self.counts['matrix_returns'] += port.returned
        self.counts['selected_fmas'] += port.calls
        self.counts['ingress_bf16_conversions'] += port.conversions
        self.counts['physical_slice_issues'] += port.accepted*(8 if mask == 255 else 4)
        self.port = None
        self.slot = dict(port=port, words_id=id(port.held.words), mask=mask,
                         selected={r*256+c for r,c in selected}, seen=set(), reads_per_edge=Counter())
        self.invariant()
        if port.poison:
            self.retire_slot(poison=True)
            raise NumericalFault('accepted Matrix failed')
        for _ in range(self.timing.result_stalls):
            self.hold_edge();self.ticks += 1
        view = TileView(self, port.group)
        self.views.append(view)
        return view

    def scalar_phase(self, plans, action):
        if self.port is not None or (self.slot is not None and self.slot['mask'] != 255):
            raise ValueError('compute/resource contention')
        port = ScalarPort(plans, self.operation, self.exponential)
        self.port = port
        def tick(**kwargs):
            self.hold_edge()
            return port.tick(**kwargs)
        tick(acquire='attention')
        def send(lanes, operands):
            offer, operands = Offer('attention', tuple(lanes)), tuple(operands)
            for _ in range(self.timing.feed_stalls):
                before = port.calls
                out = tick(offer=offer, operands=operands)
                if out['offer_fire'] or port.calls != before:
                    raise ValueError('arithmetic before admission')
            if not tick(offer=offer, operands=operands, feed_ready=True)['offer_fire']:
                raise ValueError('rejected planned scalar packet')
            while port.held is None: tick()
            held = port.held
            for _ in range(self.timing.result_stalls):
                before = port.calls
                out = tick(ack=0)
                if out['response'] != held or out['ack_fire'] or port.calls != before:
                    raise ValueError('held scalar numerical payload changed')
            out = tick(ack=held.packet)
            if not out['ack_fire']: raise ValueError('scalar retirement')
            if not out['publish']: raise NumericalFault('accepted scalar failed')
            return held.words
        successful = False
        try:
            value = action(send)
            if any(port.schedule.indices[name] != len(plan) for name,plan in plans.items()):
                raise ValueError('unconsumed scalar plan')
            successful = True
            return value
        finally:
            if port.schedule.pending is None:
                tick(release='attention')
                self.port = None
            self.ticks += port.schedule.cycle
            self.counts['scalar_packets'] += port.schedule.accepted
            self.counts['scalar_packet_acks'] += port.schedule.retired
            self.counts['scheduled_scalar_lane_calls'] += port.calls
            for pool,opcode,*_ in port.trace: self.counts[pool+'_'+opcode] += 1
            if self.slot is not None:
                self.retire_slot(poison=not successful)

    def bf(self, value):
        try:
            result = super().bf(value)
        except (ValueError, ArithmeticError):
            if self.slot is not None and self.slot['mask'] == 15:
                self.retire_slot(poison=True)
            raise
        if self.slot is not None and self.slot['mask'] == 15 and self.slot['seen'] == self.slot['selected']:
            self.retire_slot()
        return result
