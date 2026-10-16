"""Opt-in +384 B six-head panel proposal, not established register reuse.

One persistent PV Matrix context is explicitly suspended for bank/Scalar work.
The upper96 panel is newly proposed storage; physical retention, routes, muxes,
lease wiring, and timing remain unproven. V is still a host-fed 128-word view:
no physical V stage, ingress cost, output write service, native or RTL claim.
"""
from collections import Counter
from ..attention_bank_m128.controller import Controller as Frozen, admit
from ..attention_retained_result.controller import TileView
from ..attention_scheduled_numeric.controller import Timing, Result, NumericalFault
from ..attention_scheduled_numeric.ports import MatrixPort, finite
from ..attention_scalar_schedule.model import Operation
from .storage import Scratch


class Controller(Frozen):
    def __init__(self, *args, owner=None, bank_stalls=0, panel_enabled=False, **kwargs):
        if type(panel_enabled) is not bool:
            raise ValueError('canonical panel enable')
        if kwargs.pop('scratch_enabled', False) is not False:
            raise ValueError('use explicit panel_enabled')
        self.pv_context = None
        self.pv_state = 'idle'
        super().__init__(*args, scratch_enabled=False, **kwargs)
        self.panel_enabled = panel_enabled
        if panel_enabled:
            self.scratch = Scratch(owner=owner,edge=self.bank_edge,stalls=bank_stalls,enabled=True)

    def ordinary_owner_ready(self):
        return (super().ordinary_owner_ready() and self.pv_context is None and
                (self.scratch is None or not self.scratch.lease_active))

    def _require_suspended(self):
        p = self.pv_context
        if p is not None and (self.pv_state != 'suspended' or p.pending is not None or
                              p.held is not None or p.poison or p.retired):
            raise ValueError('PV suspension requires drained unfinished Matrix context')

    def hold_edge(self):
        # Bank and inherited Scalar service invoke this once per service edge.
        # They own wall-time accounting; this tick only ages the same inactive
        # Matrix context and cannot perform an FMA or admit another step.
        if self.pv_context is not None:
            self._require_suspended()
            p = self.pv_context
            before = p.calls, p.conversions, p.accepted, p.returned
            p.tick()
            if before != (p.calls,p.conversions,p.accepted,p.returned):
                raise ValueError('arithmetic during suspended PV')
            self.counts['pv_suspended_edges'] += 1
        super().hold_edge()

    def bank_edge(self):
        self._require_suspended()
        super().bank_edge()

    def scalar_phase(self, plans, action):
        self._require_suspended()
        return super().scalar_phase(plans,action)

    def matrix_group(self, payloads, selected, mask):
        if self.pv_context is not None:
            raise ValueError('unfinished PV context owns Matrix')
        return super().matrix_group(payloads,selected,mask)

    def _pv_tick(self, **inputs):
        # Explicit issue/drain edges alone advance global time here. Never add
        # p.cycle at completion: it also includes bank/Scalar suspension edges.
        p = self.pv_context
        if p is None or self.port is not None or self.slot is not None:
            raise ValueError('PV issue arbitration')
        result = p.tick(**inputs)
        self.ticks += 1
        self.counts['pv_issue_drain_edges'] += 1
        return result

    def _pv_join(self):
        p = self.pv_context
        if p is None or p.pending is not None or p.held is None:
            raise ValueError('PV join before terminal return')
        self.counts['matrix_steps'] += p.accepted
        self.counts['matrix_returns'] += p.returned
        self.counts['selected_fmas'] += p.calls
        self.counts['ingress_bf16_conversions'] += p.conversions
        self.counts['physical_slice_issues'] += p.accepted*4
        self.slot = dict(port=p,words_id=id(p.held.words),mask=15,
                         selected={r*256+c for r,c in p.selected},seen=set(),reads_per_edge=Counter())
        # An actual terminal transition transfers ownership to joined slot.
        self.pv_context = None
        self.pv_state = 'idle'
        self.invariant()
        if p.poison:
            self.retire_slot(poison=True)
            raise NumericalFault('accepted PV Matrix failed')
        for _ in range(self.timing.result_stalls):
            self.hold_edge(); self.ticks += 1
        view = TileView(self,p.group)
        self.views.append(view)
        return view

    def pv_group(self, context, v):
        if self.port is not None or self.slot is not None or self.pv_context is not None:
            raise ValueError('PV acquisition contention')
        self.counts['matrix_groups'] += 1
        self.pv_context = MatrixPort(context.keys,15,
            tuple((h,col) for h in range(6) for col in range(128)),self.fma,
            lambda word:self.operation('bf',word,0),latency=self.timing.matrix_latency,
            group=self.counts['matrix_groups'])
        self.pv_state = 'suspended'
        self.ticks += 1
        p = self.pv_context
        try:
            for first in range(0,context.keys,16):
                self.scratch.load_weight_panel(context,first)
                for key in range(first,min(first+16,context.keys)):
                    self.acc[:] = self.scratch.read_weights(context,key)
                    def normalize(send):
                        self.acc[:] = send(range(6),tuple((self.acc[h],self.cv[6+h]) for h in range(6)))
                    self.scalar_phase({h:(Operation('sfu16','mul',3),) for h in range(6)},normalize)
                    # Existing unplaced host input path; no claimed free V stage.
                    payload = (tuple(self.acc)+(0,)*10,
                               v[key*256+context.kv_head*128:key*256+(context.kv_head+1)*128]+(0,)*128)
                    self.pv_state = 'issuing'
                    for _ in range(self.timing.feed_stalls):
                        before = p.calls+p.conversions
                        out = self._pv_tick(payload=payload)
                        if out['accepted'] or before != p.calls+p.conversions:
                            raise ValueError('PV arithmetic before admission')
                    if not self._pv_tick(payload=payload,feed_ready=True)['accepted']:
                        raise ValueError('PV step admission')
                    del payload
                    while p.pending is not None:
                        self._pv_tick()
                    if p.poison: raise NumericalFault('accepted PV Matrix failed')
                    self.scratch.retire_pv_key(context,key,matrix_drained=True)
                    self.pv_state = 'suspended' if p.held is None else 'terminal'
            return self._pv_join()
        except (ValueError,ArithmeticError):
            if self.pv_context is not None:
                self.pv_state = 'aborting'
                self._pv_tick(abort=True)
                while p.held is None: self._pv_tick(abort=True)
                try: self._pv_join()
                except NumericalFault: pass
            raise

    def softmax_panels(self, context):
        for first in range(0,context.keys,16):
            self.scratch.load_score_panel(context,first)
            count = min(16,context.keys-first)
            plan = (Operation('sfu16','add',3),Operation('sfu16','exp',20),Operation('sfu16','add',3))*count
            def action(send):
                for key in range(first,first+count):
                    self.acc[:] = self.scratch.read_scores(context,key)
                    self.acc[:] = send(range(6),tuple((self.acc[h],self.cv[h]^0x80000000) for h in range(6)))
                    self.counts['full_exp_lanes'] += sum((x&0x7fffffff)<0x42a00000 for x in self.acc)
                    self.counts['cutoff_exp_lanes'] += sum((x&0x7fffffff)>=0x42a00000 for x in self.acc)
                    self.acc[:] = send(range(6),tuple((x,0) for x in self.acc))
                    self.cv[6:] = send(range(6),tuple((self.cv[6+h],self.acc[h]) for h in range(6)))
                    self.scratch.write_weights(context,key,tuple(self.acc))
            self.scalar_phase({h:plan for h in range(6)},action)
            self.scratch.commit_weight_panel(context)
        def reciprocal(send):
            self.cv[6:] = send(range(6),tuple((0x3f800000,self.cv[6+h]) for h in range(6)))
        self.scalar_phase({h:(Operation('sfu16','div',self.timing.divider_spacing),) for h in range(6)},reciprocal)

    def run(self,tokens,q,k,v):
        if not self.panel_enabled: raise ValueError('panel profile disabled')
        admit(tokens)
        if tokens > 32: raise ValueError("panel M128 admission pending")
        if self.active or self.finished or self.failed: raise ValueError('single bounded job')
        for data,count in ((q,tokens*1536),(k,tokens*256),(v,tokens*256)):
            if type(data) is not tuple or len(data)!=count or not all(finite(x) for x in data):
                raise ValueError('synthetic input shape/finite words')
        self.active = True
        output,scores_all = [None]*(tokens*1536),[]
        try:
            self.scratch.acquire()
            for token in range(tokens):
                for kvhead in range(2):
                    context = self.scratch.begin(token,kvhead,token+1)
                    self.cv[:] = [0xff800000]*6+[0]*6
                    for h in range(6): self.qk_head(context,h,q,k,scores_all)
                    self.scratch.qk_complete(context,matrix_drained=self.port is None,
                        scalar_drained=self.port is None,joined_drained=self.slot is None)
                    self.softmax_panels(context)
                    self.scratch.begin_pv(context,reciprocal_acked=True,scalar_drained=self.port is None)
                    tile = self.pv_group(context,v)
                    for h in range(6):
                        for col in range(128):
                            output[token*1536+(6*kvhead+h)*128+col] = self.bf(tile[h*256+col])
                    self.scratch.end_context(context,matrix_drained=self.pv_context is None,
                        scalar_drained=self.port is None,joined_drained=self.slot is None,
                        outputs_acked=self.slot is None)
            if any(x is None for x in output): raise ValueError('missing output')
            self.scratch.release()
            for name,value in self.scratch.counts.items(): self.counts['scratch_'+name]=value
            self.counts['exp_internal_fp32_nodes']=17*self.counts['full_exp_lanes']+self.counts['cutoff_exp_lanes']
            self.counts['scheduled_fp32_primitive_nodes']=self.counts['scheduled_scalar_lane_calls']-self.counts['sfu16_exp']+self.counts['exp_internal_fp32_nodes']
            self.finished=True
            return Result(tuple(output),tuple(scores_all),tuple(sorted(self.counts.items())),self.ticks)
        except (ValueError,ArithmeticError):
            self.failed=True
            self.scratch.abort()
            if self.scratch.parent.raw.drained: self.scratch.tick()
            raise
        finally:
            self.active=False
