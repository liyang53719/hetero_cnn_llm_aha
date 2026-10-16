"""Bounded M1/M2 bank-backed score/probability placement proposal.

Arithmetic is the frozen original order. cv[12], acc[6], tmp[16] below are
proposed reuse of existing small staging, not newly proven physical registers.
Scratch owns a separate proposed dv[16] transport beat. Q/K/V input and output
placement remain out of scope. scores_all/output are oracle observations only;
neither ever feeds arithmetic. No per-key score/probability payload cache.
"""
from collections import Counter
from ..attention_retained_result.controller import Controller as Retained, TileView
from ..attention_scheduled_numeric.controller import Timing, Result, NumericalFault
from ..attention_scheduled_numeric.ports import MatrixPort, finite
from ..attention_scalar_schedule.model import integer, fold_plan, softmax_plan
from .storage import Scratch


class Packets:
    """Sized lazy feed: only the current packet is materialized."""
    def __init__(self, size, make):
        self.size, self.make = size, make
    def __len__(self):
        return self.size
    def __iter__(self):
        for index in range(self.size):
            yield self.make(index)


class Controller(Retained):
    def __init__(self, *args, owner=None, bank_stalls=0, scratch_enabled=False, **kwargs):
        super().__init__(*args, **kwargs)
        if type(scratch_enabled) is not bool: raise ValueError('canonical scratch enable')
        self.scratch = (Scratch(owner=owner, edge=self.bank_edge, stalls=bank_stalls, enabled=True)
                        if scratch_enabled else None)
        self.cv = [0]*12
        self.acc = [0]*6
        self.tmp = [0]*16

    def bank_edge(self):
        self.hold_edge()
        self.ticks += 1
        self.counts['scratch_edges'] += 1
        if self.slot is not None:
            self.counts['scratch_edges_with_retained_result'] += 1

    def ordinary_owner_ready(self):
        return (super().ordinary_owner_ready() and
                (self.scratch is None or (self.scratch.parent.raw.owner is None and self.scratch.parent.raw.drained)))

    def matrix_group(self, payloads, selected, mask):
        # Unlike the frozen for-loop, finish the prior accepted packet before
        # asking a lazy producer to gather the next key's six probability words.
        if self.port is not None or self.slot is not None:
            raise ValueError('compute/result credit contention')
        self.counts['matrix_groups'] += 1
        port = MatrixPort(len(payloads), mask, selected, self.fma,
                          lambda x: self.operation('bf', x, 0),
                          latency=self.timing.matrix_latency, group=self.counts['matrix_groups'])
        self.port = port
        self.ticks += 1
        failure = None
        try:
            source = iter(payloads)
            for _ in range(len(payloads)):
                while port.pending is not None: port.tick()
                if port.poison: break
                payload = next(source)
                for _ in range(self.timing.feed_stalls):
                    before = port.calls + port.conversions
                    out = port.tick(payload=payload)
                    if out['accepted'] or before != port.calls + port.conversions:
                        raise ValueError('Matrix arithmetic before admission')
                if not port.tick(payload=payload, feed_ready=True)['accepted']:
                    raise ValueError('Matrix step admission')
                del payload
            while port.held is None: port.tick()
        except (ValueError, ArithmeticError) as exc:
            failure = exc
            port.tick(abort=True)
            while port.held is None: port.tick(abort=True)
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
            if failure is not None: raise failure
            raise NumericalFault('accepted Matrix failed')
        for _ in range(self.timing.result_stalls):
            self.hold_edge(); self.ticks += 1
        view = TileView(self, port.group)
        self.views.append(view)
        return view

    def run(self, tokens, q, k, v):
        if self.scratch is None: raise ValueError('bank scratch profile disabled')
        integer(tokens, 1, 2)
        if self.active or self.finished or self.failed:
            raise ValueError('single bounded job')
        for data, count in ((q,tokens*1536), (k,tokens*256), (v,tokens*256)):
            if type(data) is not tuple or len(data) != count or not all(finite(x) for x in data):
                raise ValueError('synthetic input shape/finite words')
        self.active = True
        output, scores_all = [None]*(tokens*1536), []
        try:
            self.scratch.acquire()
            for token in range(tokens):
                for kvhead in range(2):
                    n = token+1
                    context = self.scratch.begin(token, kvhead, n)
                    self.cv[:] = [0xff800000]*6+[0]*6
                    for localhead in range(6):
                        head = 6*kvhead+localhead
                        def qk_packet(step):
                            left = q[token*1536+head*128+16*step:token*1536+head*128+16*step+16]
                            right = tuple(k[key*256+kvhead*128+16*step+lane]
                                          for key in range(n) for lane in range(16))+(0,)*(256-16*n)
                            return left, right
                        selected = tuple((s,16*key+s) for key in range(n) for s in range(16))
                        tile = self.matrix_group(Packets(8,qk_packet), selected,255)
                        def fold(send):
                            self.tmp[:] = [0]*16
                            for stripe in range(16):
                                self.tmp[:n] = send(range(n),tuple((self.tmp[key],tile[stripe*256+16*key+stripe]) for key in range(n)))
                            self.tmp[:n] = send(range(n),tuple((self.bf(self.tmp[key]),0x3db504f3) for key in range(n)))
                            for key in range(n): self.tmp[key] = self.bf(self.tmp[key])
                            # Commit while TileView's actual joined slot is held.
                            self.scratch.write_scores(context,localhead,tuple(self.tmp[:n]))
                            for key in range(n):
                                score, maximum = self.tmp[key], self.cv[localhead]
                                self.counts['max_comparisons'] += 1
                                less = ((bool(maximum >> 31) and bool((maximum|score)&0x7fffffff))
                                        if (maximum >> 31) != (score >> 31) else
                                        (maximum > score if maximum >> 31 else maximum < score))
                                if less: self.cv[localhead] = score
                                scores_all.append(score)
                        self.scalar_phase({key:fold_plan() for key in range(n)},fold)
                    plans = {h:softmax_plan(n,self.timing.divider_spacing,(True,)*n) for h in range(6)}
                    def softmax(send):
                        for key in range(n):
                            for h in range(6): self.acc[h] = self.scratch.read_word(context,'score',h,key)
                            self.acc[:] = send(range(6),tuple((self.acc[h],self.cv[h]^0x80000000) for h in range(6)))
                            self.counts['full_exp_lanes'] += sum((x&0x7fffffff)<0x42a00000 for x in self.acc)
                            self.counts['cutoff_exp_lanes'] += sum((x&0x7fffffff)>=0x42a00000 for x in self.acc)
                            self.acc[:] = send(range(6),tuple((x,0) for x in self.acc))
                            self.cv[6:] = send(range(6),tuple((self.cv[6+h],self.acc[h]) for h in range(6)))
                            for h in range(6): self.scratch.write_probability(context,h,key,self.acc[h])
                        self.cv[6:] = send(range(6),tuple((0x3f800000,self.cv[6+h]) for h in range(6)))
                        for key in range(n):
                            for h in range(6): self.acc[h] = self.scratch.read_word(context,'prob',h,key)
                            self.acc[:] = send(range(6),tuple((self.acc[h],self.cv[6+h]) for h in range(6)))
                            for h in range(6): self.scratch.write_probability(context,h,key,self.acc[h],normalized=True)
                    self.scalar_phase(plans,softmax)
                    def pv_packet(key):
                        for h in range(6): self.acc[h] = self.scratch.read_word(context,'prob',h,key,normalized=True)
                        return tuple(self.acc)+(0,)*10, v[key*256+kvhead*128:key*256+(kvhead+1)*128]+(0,)*128
                    tile = self.matrix_group(Packets(n,pv_packet),tuple((h,c) for h in range(6) for c in range(128)),15)
                    for h in range(6):
                        for col in range(128):
                            output[token*1536+(6*kvhead+h)*128+col] = self.bf(tile[h*256+col])
            if any(x is None for x in output): raise ValueError('missing output')
            self.scratch.release()
            for name,value in self.scratch.counts.items(): self.counts['scratch_'+name] = value
            self.counts['exp_internal_fp32_nodes'] = 17*self.counts['full_exp_lanes']+self.counts['cutoff_exp_lanes']
            self.counts['scheduled_fp32_primitive_nodes'] = self.counts['scheduled_scalar_lane_calls']-self.counts['sfu16_exp']+self.counts['exp_internal_fp32_nodes']
            self.finished = True
            return Result(tuple(output),tuple(scores_all),tuple(sorted(self.counts.items())),self.ticks)
        except (ValueError, ArithmeticError):
            self.failed = True
            self.scratch.abort()
            if self.scratch.parent.raw.drained: self.scratch.tick()
            raise
        finally:
            self.active = False
