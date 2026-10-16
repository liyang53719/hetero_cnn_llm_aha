"""Explicit <=16-key QK tiles through M128; behavioral proposal only.

cv[12], acc[6], tmp[16], and Scratch dv[16] are proposed existing staging.
Output/scores are oracle-only observations and never arithmetic inputs.
No native, RTL, physical-register, 80% or 90% performance claim.
"""
import hashlib
from ..attention_bank_scratch.controller import Controller as Frozen, Packets
from ..attention_bank_multirow.profile import EventSink, SOURCE_PATH, SOURCE_SHA256
from ..attention_scheduled_numeric.controller import Timing, Result, NumericalFault
from ..attention_scheduled_numeric.ports import finite
from ..attention_scalar_schedule.model import fold_plan, softmax_plan
from .storage import Scratch

ADMITTED_SHAPES = (1, 2, 4, 8, 16, 17, 32, 128)


def admit(tokens):
    if type(tokens) is not int or tokens not in ADMITTED_SHAPES:
        raise ValueError('M128 admitted shapes are 1,2,4,8,16,17,32,128')


class Controller(Frozen):
    def __init__(self, *args, owner=None, bank_stalls=0, scratch_enabled=False, **kwargs):
        if hashlib.sha256(SOURCE_PATH.read_bytes()).hexdigest() != SOURCE_SHA256:
            raise ValueError('frozen bank controller source SHA256 mismatch')
        if type(scratch_enabled) is not bool:
            raise ValueError('canonical scratch enable')
        # Disable the frozen Scratch constructor: exactly one actual owner and
        # its original Banks allocation are installed below, never a replacement.
        super().__init__(*args, scratch_enabled=False, **kwargs)
        if scratch_enabled:
            self.scratch = Scratch(owner=owner, edge=self.bank_edge,
                                   stalls=bank_stalls, enabled=True)
        self.read_events = EventSink('read_events')
        self.ack_events = EventSink('ack_events')
        self.views = EventSink('views')

    def observation_summary(self):
        sinks = (self.read_events, self.ack_events, self.views)
        if self.scratch is not None:
            sinks += (self.scratch.events,)
        return {sink.kind: sink.summary() for sink in sinks}

    def qk_head(self, context, localhead, q, k, scores_all):
        """Commit ascending global keys, retaining only one tmp[16] tile.

        scores_all is an append-only oracle observer. This routine never reads
        it, and all later score consumers read the original owner's Banks.
        """
        self.scratch.require(context)
        if type(localhead) is not int or not 0 <= localhead < 6:
            raise ValueError('QK local head')
        token, kvhead, n = context.query, context.kv_head, context.keys
        head = 6*kvhead+localhead
        for first in range(0, n, 16):
            count = min(16, n-first)
            def qk_packet(step):
                left = q[token*1536+head*128+16*step:token*1536+head*128+16*step+16]
                right = tuple(k[(first+key)*256+kvhead*128+16*step+lane]
                              for key in range(count) for lane in range(16))+(0,)*(256-16*count)
                return left, right
            selected = tuple((s,16*key+s) for key in range(count) for s in range(16))
            tile = self.matrix_group(Packets(8,qk_packet), selected,255)
            def fold(send):
                self.tmp[:] = [0]*16
                for stripe in range(16):
                    self.tmp[:count] = send(range(count),tuple((self.tmp[key],tile[stripe*256+16*key+stripe]) for key in range(count)))
                self.tmp[:count] = send(range(count),tuple((self.bf(self.tmp[key]),0x3db504f3) for key in range(count)))
                for key in range(count): self.tmp[key] = self.bf(self.tmp[key])
                # Each packet reaches a matching bank ACK before its prefix is
                # published, and before the held joined QK slot is retired.
                self.scratch.write_score_packet(context,localhead,first,tuple(self.tmp[:count]))
                for key in range(count):
                    score, maximum = self.tmp[key], self.cv[localhead]
                    self.counts['max_comparisons'] += 1
                    less = ((bool(maximum >> 31) and bool((maximum|score)&0x7fffffff))
                            if (maximum >> 31) != (score >> 31) else
                            (maximum > score if maximum >> 31 else maximum < score))
                    if less: self.cv[localhead] = score
                    scores_all.append(score)
            self.scalar_phase({key:fold_plan() for key in range(count)},fold)

    def run(self, tokens, q, k, v):
        if self.scratch is None: raise ValueError('bank scratch profile disabled')
        admit(tokens)
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
                        self.qk_head(context, localhead, q, k, scores_all)
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
