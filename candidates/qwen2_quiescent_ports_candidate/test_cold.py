"""Original object, multiple state/debt and empty-edge equivalence; no native."""
import unittest
from candidates.qwen2_attention_shared_a_integration.banks import LoanDenseOwner
from .memo import QuiescentPorts,_NONE_FIELDS,_FALSE_FIELDS,_IDLE_FIELDS,_POLICIES

def owner():return LoanDenseOwner(enable_ffn_window=True,enable_ffn_tiles=True,enable_ffn_drain=True,enable_k_window=True,enable_dense_drain=True)
def edge(d):
    with d.bank_guard.edge():d.bank_guard.clock_only=True;return d.tick()
def state(d):return dict(clock=d.clock,cycle=d.tiles.cycle,state=d.state,error=d.error,lease=d.lease,
  guard_counts=dict(d.bank_guard.counts),tile_counts=dict(d.tiles.counters),a_reads=d.a_banks.reads,a_writes=d.a_banks.writes,
  b_reads=d.b_banks.reads,b_writes=d.b_banks.writes,tiles_pending=d.tiles.pending,tiles_response=d.tiles.response,
  drain_phase=d.drain_phase,window_request=d.window_request,drain_request=d.drain_request)
class Cold(unittest.TestCase):
    def test_quiet_read_copy_and_restore(self):
        d=owner();d.bank_guard.lease=object();original=d.ports()
        with QuiescentPorts(d) as m:
            self.assertEqual(d.ports(),original);v=d.ports();v['job_ready']=True
            self.assertEqual(d.ports(),original);self.assertEqual(m.counts['hits'],2)
            with self.assertRaises(TypeError):m.cache['job_ready']=True
        self.assertNotIn('ports',d.__dict__);self.assertEqual(d.ports(),original)
    def test_every_debt_forces_original_fallback(self):
        for name in _NONE_FIELDS:
            with self.subTest(name=name):
                d=owner();d.bank_guard.lease=object()
                with QuiescentPorts(d) as m:
                    d.ports();setattr(d,name,'Protocol' if name=='error' else object())
                    self.assertIsNone(m.quiet_key())
                    if name not in ('window_request','drain_request'):
                        self.assertEqual(d.ports(),m.original());self.assertEqual(m.counts['fallbacks'],1)
    def test_poison_and_state_never_cached(self):
        for name in _FALSE_FIELDS+_IDLE_FIELDS:
            with self.subTest(name=name):
                d=owner();d.bank_guard.lease=object()
                with QuiescentPorts(d) as m:
                    d.ports();setattr(d,name,True if name in _FALSE_FIELDS else 'locked')
                    self.assertIsNone(m.quiet_key());self.assertEqual(d.ports(),m.original())
    def test_fifo_tile_pending_response_and_poison(self):
        for name in ('fifo','pending','response','poison','live','sealed'):
            d=owner();d.bank_guard.lease=object()
            with QuiescentPorts(d) as m:
                d.ports()
                if name=='fifo':d.fifo.append(object())
                elif name in ('live','sealed'):setattr(d.tiles.tags[0],name,True)
                else:setattr(d.tiles,name,True if name=='poison' else object())
                self.assertIsNone(m.quiet_key());self.assertEqual(d.ports(),m.original())
    def test_lease_clock_policy_invalidate(self):
        d=owner();d.bank_guard.lease=object()
        with QuiescentPorts(d) as m:
            d.ports();miss=m.counts['misses']
            for change in (lambda:setattr(d,'clock',d.clock+1),lambda:setattr(d.tiles,'cycle',d.tiles.cycle+1),lambda:setattr(d.bank_guard,'lease',object()),
                           *(lambda n=n:setattr(d,n,not getattr(d,n)) for n in _POLICIES)):
                change();self.assertEqual(d.ports(),m.original());miss+=1;self.assertEqual(m.counts['misses'],miss)
            d.bank_guard.lease=None;self.assertEqual(d.ports(),m.original());self.assertIsNone(m.cache)
    def test_all_original_edges_and_side_effects_equal(self):
        a,b=owner(),owner();a.bank_guard.lease=object();b.bank_guard.lease=object()
        with QuiescentPorts(b) as m:
            for _ in range(50):
                self.assertEqual(a.ports(),b.ports());self.assertEqual(edge(a),edge(b));self.assertEqual(a.ports(),b.ports());self.assertEqual(state(a),state(b))
            self.assertEqual(a.clock,50);self.assertEqual(a.tiles.cycle,50);self.assertEqual(a.bank_guard.counts['bank_edges'],50)
            self.assertGreater(m.counts['hits'],m.counts['misses'])
    def test_direct_offers_are_still_denied_identically(self):
        a,b=owner(),owner();a.bank_guard.lease=object();b.bank_guard.lease=object()
        with QuiescentPorts(b):
            for name in ('job','window','drain','tile_read','tile_write','abort','read_beat','result','write_ack'):
                offer={name:object()};self.assertEqual(a.tick(**offer),b.tick(**offer));self.assertEqual(state(a),state(b))
    def test_lease_fields_are_not_original_ports_dependencies(self):
        from types import SimpleNamespace
        d=owner();d.bank_guard.lease=SimpleNamespace(tag=1,generation=1)
        with QuiescentPorts(d) as m:
            d.ports();d.bank_guard.lease.tag=2;d.bank_guard.lease.generation=3
            self.assertEqual(d.ports(),m.original());self.assertEqual(m.counts['hits'],1)
    def test_observer_and_cold_source_scope(self):
        from . import check_small as c
        from types import SimpleNamespace
        from pathlib import Path
        from unittest.mock import patch
        self.assertEqual(c.wire(['raw',SimpleNamespace(address=64,beats=1,tag=3),1]),['raw',{'address':64,'beats':1,'tag':3},1])
        with self.assertRaises(ValueError):c.wire(object())
        original=Path.read_bytes
        def read(p,*a,**kw):
            if p.is_relative_to(c.ROOT/'work'):raise AssertionError('private work cold dependency')
            return original(p,*a,**kw)
        with patch.object(Path,'read_bytes',read):self.assertGreater(len(c.sources_now()),70)
        self.assertEqual(len(c.CASES),4)
    def test_exception_restores_instance(self):
        d=owner();d.bank_guard.lease=object()
        with self.assertRaisesRegex(RuntimeError,'injected'):
            with QuiescentPorts(d):d.ports();raise RuntimeError('injected')
        self.assertNotIn('ports',d.__dict__);self.assertIs(d.ports.__func__,LoanDenseOwner.ports)
    def test_nested_or_prepatched_scope_rejected(self):
        d=owner()
        with QuiescentPorts(d):
            with self.assertRaises(ValueError):QuiescentPorts(d)
    def test_banks_and_identity_changes_fall_back(self):
        d=owner();d.bank_guard.lease=object()
        with QuiescentPorts(d) as m:
            d.ports();d.b_banks.reads[0]=0;self.assertIsNone(m.quiet_key());self.assertEqual(d.ports(),m.original())
            d.b_banks.reads.clear();d.a_banks=object();self.assertIsNone(m.quiet_key())
if __name__=='__main__':unittest.main()
