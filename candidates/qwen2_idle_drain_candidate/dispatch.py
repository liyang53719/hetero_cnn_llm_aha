"""Scoped loaded-code experiment: one redundant drain ports evaluation only."""
from collections import Counter
from pathlib import Path
from types import CodeType
import threading
from candidates.qwen2_attention_shared_a_integration.banks import LoanDenseOwner
from candidates.qwen2_resident_matrix.dense_block_reduce.k_window_model import drain
from candidates.qwen2_exact64_projection_integration.kernel import need

_WINDOW_MODULE=drain.window
_DOWN=drain.down
_TILES=drain.tiles
_DRAIN=drain.FfnDrainOwnerModel
_WINDOW=drain.window.FfnWindowOwnerModel
_ORIGINAL=_DRAIN.tick
_WINDOW_TICK=_WINDOW.tick
_MISSING=object()
_METHODS=tuple((cls,name,cls.__dict__.get(name,_MISSING)) for cls in LoanDenseOwner.__mro__
  for name in ('ports','_read_command','_write_command','_write_data'))
_ACTIVE=None
_NONE_FIELDS=('lease','error','read_active','a_hold','a_rmw_pending','pending','accepted_write',
 'window_request','window_result','drain_request','drain_result','drain_expected','final_value','seed_hold')
_FALSE_FIELDS=('restoring','seed_outstanding','group_started','group_done','drain_poison')
_IDLE_FIELDS=('state','write_state','seed_state','drain_phase','adapter_phase')

def canonical_code(function):
    """Compare loaded code with the corresponding unexecuted source compilation."""
    code=compile(Path(function.__code__.co_filename).read_bytes(),function.__code__.co_filename,'exec',dont_inherit=True)
    names=function.__qualname__.split('.')
    for name in names:
        choices=[c for c in code.co_consts if isinstance(c,CodeType) and c.co_name==name]
        need(len(choices)==1,'unique canonical source function');code=choices[0]
    need(code==function.__code__,'loaded method differs from its source code')

def check_canonical():
    need(_DRAIN.tick is _ORIGINAL and _WINDOW.tick is _WINDOW_TICK,'original class method identity')
    need(_ORIGINAL.__globals__ is drain.__dict__ and _WINDOW_TICK.__globals__ is drain.window.__dict__,
         'canonical function module globals')
    need(drain.window is _WINDOW_MODULE and drain.down is _DOWN and drain.tiles is _TILES and
      drain.FfnDrainOwnerModel is _DRAIN and drain.window.FfnWindowOwnerModel is _WINDOW and
      drain.down is drain.window.down and drain.tiles is drain.window.tiles and
      _ORIGINAL.__closure__[0].cell_contents is _DRAIN and _WINDOW_TICK.__closure__[0].cell_contents is _WINDOW,
      'canonical super/global authorities')
    for cls,name,function in _METHODS:
        need(cls.__dict__.get(name,_MISSING) is function,'canonical inherited ports/helper method')
        if function is not _MISSING:canonical_code(function)
    canonical_code(_ORIGINAL);canonical_code(_WINDOW_TICK)

class IdleDrainScope:
    """Single-owner, single-thread diagnostic class-method replacement.

    Other identities and every unrecognized invocation go to the exact saved
    original function with unchanged args/kwargs. No cross-call port snapshot.
    This changes loaded code and is not covered by any prior source-only run.
    """
    def __init__(self,dense):
        need(type(dense) is LoanDenseOwner,'exact existing public guarded owner')
        self.dense=dense;self.active=False;self.counts=Counter()
        self.guard=dense.bank_guard;self.tiles=dense.tiles;self.delegate=self.tiles._delegate
        self.a=dense.a_banks;self.b=dense.b_banks
        def dispatch(owner,*args,**kwargs):
            if owner is not self.dense:return _ORIGINAL(owner,*args,**kwargs)
            if self.eligible(args,kwargs):
                self.counts['specialized_edges']+=1
                # Exact super-call/defaults of the original no-drain branch.
                e=_WINDOW_TICK(owner,window=None,job=None,write_command_ready=True,write_data_ready=True,
                  write_ack=None,abort=False,local_reset=False,coordinated_reset=False,tile_control=None,
                  tile_write=None,tile_read=None,tile_response_ready=True,tile_accept_ready=True,
                  invalidate_lease=True,loan_busy=True,loan_request=True)
                return dict(e,drain_ready=False,drain_fire=False,drain_result_fire=False)
            self.counts['fallback_edges']+=1
            return _ORIGINAL(owner,*args,**kwargs)
        self.dispatch=dispatch
    def __enter__(self):
        global _ACTIVE
        need(_ACTIVE is None and not self.active,'one nonreentrant runtime dispatch scope')
        need(threading.active_count()==1,'single-thread process precondition')
        need('tick' not in self.dense.__dict__ and 'ports' not in self.dense.__dict__,'no instance method overrides')
        check_canonical();_ACTIVE=self;self.active=True;_DRAIN.tick=self.dispatch;return self
    def __exit__(self,*exc):
        global _ACTIVE
        try:need(_DRAIN.tick is self.dispatch and _ACTIVE is self,'scope authority changed')
        finally:_DRAIN.tick=_ORIGINAL;_ACTIVE=None;self.active=False
        return False
    def eligible(self,args,kw):
        if args or len(kw)!=4 or kw.get('window',_MISSING) is not None or kw.get('loan_busy') is not True or \
          kw.get('loan_request') is not True or kw.get('invalidate_lease') is not True:return False
        d=self.dense;g=self.guard;t=self.delegate
        if not (d.bank_guard is g and d.a_banks is self.a is g and d.b_banks is self.b and d.tiles is self.tiles and
          self.tiles._delegate is t and t.banks is g and g.lease is not None and g.in_edge and g.clock_only and
          g.actor=='owner' and g.begins==0):return False
        # Local idle branch proof, not a reconstructed/cached ports snapshot.
        if not (d.state=='idle' and d.write_state=='idle' and d.seed_state=='idle' and d.drain_phase=='idle' and
          d.adapter_phase=='idle' and d.lease is None and d.error is None and d.read_active is None and
          d.a_hold is None and d.a_rmw_pending is None and d.pending is None and d.accepted_write is None and
          d.window_request is None and d.window_result is None and d.drain_request is None and d.drain_result is None and
          d.drain_expected is None and d.final_value is None and d.seed_hold is None and not d.fifo and
          d.restoring is False and d.seed_outstanding is False and d.group_started is False and
          d.group_done is False and d.drain_poison is False):return False
        if t.pending is not None or t.response is not None or t.poison is not False:return False
        if any(tag.live is not False or tag.sealed is not False for tag in t.tags):return False
        return True
    def report(self):
        return dict(counts=dict(self.counts),active=self.active,runtime_class_method_replaced=True,
          scope='SINGLE_OWNER_NO_CONCURRENT_MODEL_EXECUTION',original_method_restored=_DRAIN.tick is _ORIGINAL,
          original_clock_edges_skipped=0,hardware_cycles_saved=0)
