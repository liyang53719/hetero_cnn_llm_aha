"""Bounded M1/M2 cooperative Attention numerical/timing candidate.

Original per-output order, actual accepted callbacks and held results. One owner
and no Matrix/scalar overlap. Host storage remains unplaced; not an RTL model.
"""
from collections import Counter
from dataclasses import dataclass
from ..attention_scalar_schedule.model import Offer, fold_plan, softmax_plan, integer
from .ports import ScalarPort, MatrixPort, finite


class NumericalFault(ValueError):
    pass


@dataclass(frozen=True)
class Timing:
    matrix_latency: int
    divider_spacing: int
    feed_stalls: int
    result_stalls: int

    def __post_init__(self):
        integer(self.matrix_latency, 1, 1000)
        integer(self.divider_spacing, 3, 1000)
        integer(self.feed_stalls, 0, 20)
        integer(self.result_stalls, 0, 20)


@dataclass(frozen=True)
class Result:
    output: tuple
    scores: tuple
    counts: tuple
    hypothetical_ticks: int


class Controller:
    def __init__(self, operation, fma, exponential, *, timing):
        if type(timing) is not Timing:
            raise ValueError('explicit timing inputs')
        self.operation, self.fma, self.exponential, self.timing = operation, fma, exponential, timing
        self.counts = Counter()
        self.ticks = 0
        self.active = False
        self.port = None
        self.failed = False
        self.finished = False

    def ordinary_owner_ready(self):
        return not self.active and not self.failed and self.port is None

    def bf(self, value):
        self.counts['boundary_bf16_conversions'] += 1
        result = self.operation('bf', value, 0)
        if not finite(result) or result & 65535:
            raise NumericalFault('BF16 boundary')
        return result

    def scalar_phase(self, plans, action):
        if self.port is not None:
            raise ValueError('global resource contention')
        port = ScalarPort(plans, self.operation, self.exponential)
        self.port = port
        port.tick(acquire='attention')
        def send(lanes, operands):
            offer = Offer('attention', tuple(lanes))
            operands = tuple(operands)
            for _ in range(self.timing.feed_stalls):
                before = port.calls
                out = port.tick(offer=offer, operands=operands)
                if out['offer_fire'] or port.calls != before:
                    raise ValueError('arithmetic before admission')
            if not port.tick(offer=offer, operands=operands, feed_ready=True)['offer_fire']:
                raise ValueError('rejected planned scalar packet')
            while port.held is None:
                port.tick()
            held = port.held
            for _ in range(self.timing.result_stalls):
                before = port.calls
                out = port.tick(ack=0)
                if out['response'] != held or out['ack_fire'] or port.calls != before:
                    raise ValueError('held numerical payload changed')
            out = port.tick(ack=held.packet)
            if not out['ack_fire']:
                raise ValueError('scalar retirement')
            if not out['publish']:
                raise NumericalFault('accepted scalar failed')
            return held.words
        try:
            value = action(send)
            if any(port.schedule.indices[name] != len(plan) for name, plan in plans.items()):
                raise ValueError('unconsumed scalar plan')
            return value
        finally:
            if port.schedule.pending is None:
                port.tick(release='attention')
                self.port = None
            self.ticks += port.schedule.cycle
            self.counts['scalar_packets'] += port.schedule.accepted
            self.counts['scalar_packet_acks'] += port.schedule.retired
            self.counts['scheduled_scalar_lane_calls'] += port.calls
            for pool, opcode, *_ in port.trace:
                self.counts[pool+'_'+opcode] += 1

    def matrix_group(self, payloads, selected, mask):
        if self.port is not None:
            raise ValueError('global resource contention')
        self.counts['matrix_groups'] += 1
        port = MatrixPort(len(payloads), mask, selected, self.fma,
                          lambda x: self.operation('bf', x, 0),
                          latency=self.timing.matrix_latency, group=self.counts['matrix_groups'])
        self.port = port
        # Explicit command/admission edge, outside the step port.
        self.ticks += 1
        for payload in payloads:
            while port.pending is not None:
                port.tick()
            if port.poison:
                break
            for _ in range(self.timing.feed_stalls):
                before = port.calls + port.conversions
                out = port.tick(payload=payload)
                if out['accepted'] or before != port.calls + port.conversions:
                    raise ValueError('Matrix arithmetic before admission')
            if not port.tick(payload=payload, feed_ready=True)['accepted']:
                raise ValueError('Matrix step admission')
        while port.held is None:
            port.tick()
        held = port.held
        for _ in range(self.timing.result_stalls):
            before = port.calls + port.conversions
            out = port.tick(ack=0)
            if out['response'] != held or out['ack_fire'] or before != port.calls + port.conversions:
                raise ValueError('held Matrix numerical payload changed')
        out = port.tick(ack=held.group)
        if not out['ack_fire'] or port.pending is not None:
            raise ValueError('Matrix retirement')
        # Explicit joined-result retirement and group completion fence.
        self.ticks += port.cycle + 1
        self.counts['matrix_steps'] += port.accepted
        self.counts['matrix_returns'] += port.returned
        self.counts['matrix_result_acks'] += 1
        self.counts['selected_fmas'] += port.calls
        self.counts['ingress_bf16_conversions'] += port.conversions
        self.counts['physical_slice_issues'] += port.accepted * (8 if mask == 255 else 4)
        self.port = None
        if not out['publish']:
            raise NumericalFault('accepted Matrix failed')
        return held.words

    def run(self, tokens, q, k, v):
        integer(tokens, 1, 2)
        if self.active or self.finished or self.failed:
            raise ValueError('single bounded job')
        for data, count in ((q, tokens*1536), (k, tokens*256), (v, tokens*256)):
            if type(data) is not tuple or len(data) != count or not all(finite(x) for x in data):
                raise ValueError('synthetic input shape/finite words')
        self.active = True
        output = [None] * (tokens*1536)
        scores_all = []
        try:
            for token in range(tokens):
                for kvhead in range(2):
                    rows = []
                    n = token + 1
                    for localhead in range(6):
                        head = 6*kvhead + localhead
                        query = q[token*1536+head*128:token*1536+(head+1)*128]
                        keys = [k[key*256+kvhead*128:key*256+(kvhead+1)*128] for key in range(n)]
                        selected = tuple((stripe, 16*key+stripe) for key in range(n) for stripe in range(16))
                        payloads = []
                        for step in range(8):
                            left = query[16*step:16*step+16]
                            right = tuple(value for keyrow in keys for value in keyrow[16*step:16*step+16]) + (0,)*(256-16*n)
                            payloads.append((left, right))
                        tile = self.matrix_group(tuple(payloads), selected, 255)
                        def fold(send):
                            totals = (0,)*n
                            for stripe in range(16):
                                totals = send(range(n), tuple((totals[key], tile[stripe*256+16*key+stripe]) for key in range(n)))
                            scaled = send(range(n), tuple((self.bf(total), 0x3db504f3) for total in totals))
                            return tuple(self.bf(x) for x in scaled)
                        scores = self.scalar_phase({key: fold_plan() for key in range(n)}, fold)
                        rows.append(scores)
                        scores_all.extend(scores)
                    # Existing finite less-than bit ordering; no arithmetic call.
                    def less(a, b):
                        if (a >> 31) != (b >> 31):
                            return bool(a >> 31) and bool((a | b) & 0x7fffffff)
                        return a > b if a >> 31 else a < b
                    maxima = []
                    for row in rows:
                        maximum = 0xff800000
                        for score in row:
                            self.counts['max_comparisons'] += 1
                            if less(maximum, score): maximum = score
                        maxima.append(maximum)
                    # Full20 is a conservative reservation even for cutoff lanes;
                    # no branch prediction or free early reissue is assumed.
                    plans = {head: softmax_plan(n, self.timing.divider_spacing, (True,)*n) for head in range(6)}
                    def softmax(send):
                        sums = (0,)*6
                        probabilities = []
                        for key in range(n):
                            differences = send(range(6), tuple((rows[h][key], maxima[h]^0x80000000) for h in range(6)))
                            self.counts['full_exp_lanes'] += sum((x & 0x7fffffff) < 0x42a00000 for x in differences)
                            self.counts['cutoff_exp_lanes'] += sum((x & 0x7fffffff) >= 0x42a00000 for x in differences)
                            weights = send(range(6), tuple((x, 0) for x in differences))
                            probabilities.append(weights)
                            sums = send(range(6), tuple(zip(sums, weights)))
                        inverses = send(range(6), tuple((0x3f800000, total) for total in sums))
                        normalized = []
                        for weights in probabilities:
                            normalized.append(send(range(6), tuple(zip(weights, inverses))))
                        return normalized
                    normalized = self.scalar_phase(plans, softmax)
                    payloads = tuple((tuple(normalized[key])+(0,)*10,
                                      v[key*256+kvhead*128:key*256+(kvhead+1)*128]+(0,)*128) for key in range(n))
                    tile = self.matrix_group(payloads, tuple((h,c) for h in range(6) for c in range(128)), 15)
                    for h in range(6):
                        head = 6*kvhead+h
                        for col in range(128):
                            output[token*1536+head*128+col] = self.bf(tile[h*256+col])
            if any(x is None for x in output):
                raise ValueError('missing output')
            self.counts['exp_internal_fp32_nodes'] = 17*self.counts['full_exp_lanes'] + self.counts['cutoff_exp_lanes']
            self.counts['scheduled_fp32_primitive_nodes'] = self.counts['scheduled_scalar_lane_calls'] - self.counts['sfu16_exp'] + self.counts['exp_internal_fp32_nodes']
            self.finished = True
            return Result(tuple(output), tuple(scores_all), tuple(sorted(self.counts.items())), self.ticks)
        except (ValueError, ArithmeticError):
            self.failed = True
            raise
        finally:
            self.active = False
