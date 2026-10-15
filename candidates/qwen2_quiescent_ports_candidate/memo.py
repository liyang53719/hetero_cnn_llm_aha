"""Opt-in read-only port memoization. Every original model tick still executes."""
from collections import Counter
from types import MappingProxyType
from candidates.qwen2_attention_shared_a_integration.banks import LoanDenseOwner
from candidates.qwen2_exact64_projection_integration.kernel import need

_MISSING=object()
_NONE_FIELDS=('lease','error','read_active','a_hold','a_rmw_pending','pending','accepted_write',
 'window_request','window_result','drain_request','drain_result','drain_expected','final_value','seed_hold')
_FALSE_FIELDS=('restoring','seed_outstanding','group_started','group_done','drain_poison')
_IDLE_FIELDS=('state','write_state','seed_state','drain_phase','adapter_phase')
_POLICIES=('enable_ffn_window','enable_ffn_drain','enable_ffn_tiles','enable_k_window','enable_dense_drain')

class QuiescentPorts:
    """Temporary instance ports wrapper; never grants a lease or services a debt.

    The canonical original function is called for every nonquiet state. Cached
    values are scalar-only and privately immutable; every caller gets a copy.
    No tick, clock, reset, bank operation or input handshake is intercepted.
    """
    def __init__(self,dense):
        need(type(dense) is LoanDenseOwner,'exact existing guarded Dense owner')
        need(getattr(dense.ports,'__func__',None) is LoanDenseOwner.ports,'canonical original ports function')
        self.dense=dense;self.original=dense.ports;self.saved=dense.__dict__.get('ports',_MISSING)
        self.guard=dense.bank_guard;self.tiles=dense.tiles;self.delegate=self.tiles._delegate
        self.a=dense.a_banks;self.b=dense.b_banks;self.active=False;self.key=None;self.cache=None
        self.callback=self.ports;self.counts=Counter()
    def __enter__(self):
        need(not self.active and self.dense.__dict__.get('ports',_MISSING) is self.saved,'one unchanged instance scope')
        self.active=True;self.dense.ports=self.callback;return self
    def __exit__(self,*exc):
        try:
            need(self.dense.__dict__.get('ports') is self.callback,'instance ports changed inside memo scope')
        finally:
            if self.saved is _MISSING:self.dense.__dict__.pop('ports',None)
            else:self.dense.ports=self.saved
            self.active=False;self.key=self.cache=None
        return False
    def quiet_key(self):
        d=self.dense;v=d.__dict__;g=self.guard;t=self.delegate
        if not (d.bank_guard is g and d.a_banks is self.a is g and d.b_banks is self.b and
          d.tiles is self.tiles and self.tiles._delegate is t and t.banks is g and g.lease is not None):return None
        if any(v.get(n,_MISSING) is not None for n in _NONE_FIELDS):return None
        if any(v.get(n,_MISSING) is not False for n in _FALSE_FIELDS):return None
        if any(v.get(n,_MISSING)!='idle' for n in _IDLE_FIELDS):return None
        if v.get('fifo',_MISSING) is _MISSING or len(d.fifo)!=0:return None
        if t.pending is not None or t.response is not None or t.poison is not False:return None
        if any(x.live is not False or x.sealed is not False for x in t.tags):return None
        policies=tuple(v.get(n,_MISSING) for n in _POLICIES)
        if not all(type(x) is bool for x in policies):return None
        if type(d.clock) is not int or type(t.cycle) is not int:return None
        # No accepted SRAM operation is hidden by the memo. Bank operations
        # remain wholly owned by the original per-edge tick/port guards.
        if g.reads or g.writes or self.b.reads or self.b.writes:return None
        return (d.clock,t.cycle,id(g.lease),*policies)
    def ports(self):
        need(self.active,'ports memo outside its explicit scope')
        key=self.quiet_key()
        if key is None:
            self.key=self.cache=None;self.counts['fallbacks']+=1
            return self.original()
        if key!=self.key:
            value=self.original()
            # Fail back rather than retain a response, beat or mutable object.
            if any(x is not None and type(x) not in (bool,int,str) for x in value.values()):
                self.key=self.cache=None;self.counts['fallbacks']+=1;return value
            self.key=key;self.cache=MappingProxyType(dict(value));self.counts['misses']+=1
        else:self.counts['hits']+=1
        return dict(self.cache)
    def report(self):return dict(counts=dict(self.counts),active=self.active,cache_retained=self.cache is not None,
      original_ticks_skipped=0,hardware_cycles_saved=0,scope='SOFTWARE_READONLY_PORT_MEMO')
