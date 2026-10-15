"""Original real objects and pure control/port edges; no native arithmetic."""
import unittest
from unittest.mock import patch
from . import dispatch as m
from candidates.qwen2_resident_matrix.dense_block_reduce.k_window_model import Job,ReadBeat,MatrixResult,PrefixWorkspace

LOAN=dict(window=None,loan_busy=True,loan_request=True,invalidate_lease=True)
def owner():return m.LoanDenseOwner(PrefixWorkspace(0x2000000,0x100000,8,2560),enable_ffn_window=True,enable_ffn_tiles=True,enable_ffn_drain=True,enable_k_window=True,enable_dense_drain=True)
def edge(d):
    with d.bank_guard.edge():d.bank_guard.clock_only=True;return d.tick()
def direct(d,*args,**kwargs):
    with d.bank_guard.edge(),d.bank_guard.scope('owner'):
        d.bank_guard.clock_only=True;return m._DRAIN.tick(d,*args,**kwargs)
def state(d):
    fields=set(m._NONE_FIELDS+m._FALSE_FIELDS+m._IDLE_FIELDS+('clock','job','write_bytes','issue_k','read_received','fifo'))
    return dict(dense={k:getattr(d,k,None) for k in fields},tiles={k:getattr(d.tiles,k) for k in ('cycle','pending','response','poison','reason','counters','tags')},
      a_reads=d.a_banks.reads,a_writes=d.a_banks.writes,b_reads=d.b_banks.reads,b_writes=d.b_banks.writes,
      a=d.a_banks.words,b=d.b_banks.words,counts=dict(d.bank_guard.counts),denials=dict(d.loan_denials))
def outcome(call):
    try:return ('ok',call())
    except Exception as exc:return ('error',type(exc),str(exc))

class Cold(unittest.TestCase):
    def pair(self):
        a,b=owner(),owner();a.bank_guard.lease=object();b.bank_guard.lease=object();return a,b
    def test_fifty_original_edges_preserved(self):
        a,b=self.pair()
        with m.IdleDrainScope(b) as scope:
            for _ in range(50):self.assertEqual(edge(a),edge(b));self.assertEqual(state(a),state(b))
            self.assertEqual(scope.counts['specialized_edges'],50)
        self.assertEqual(a.clock,50);self.assertEqual(a.tiles.cycle,50);self.assertEqual(a.bank_guard.counts['bank_edges'],50)
        self.assertIs(m._DRAIN.tick,m._ORIGINAL)
    def test_per_debt_or_nonidle_fallback_same_state_and_exception(self):
        for field in m._NONE_FIELDS+m._FALSE_FIELDS+m._IDLE_FIELDS:
            with self.subTest(field=field):
                a,b=self.pair();bad=True if field in m._FALSE_FIELDS else ('locked' if field in m._IDLE_FIELDS else ('Protocol' if field=='error' else object()))
                setattr(a,field,bad);setattr(b,field,bad)
                with m.IdleDrainScope(b) as scope:
                    self.assertEqual(outcome(lambda:edge(a)),outcome(lambda:edge(b)))
                    self.assertEqual(scope.counts['specialized_edges'],0);self.assertEqual(scope.counts['fallback_edges'],1)
                self.assertEqual(state(a),state(b))
    def test_tile_debts_poison_and_tags_fallback(self):
        for field in ('pending','response','poison','live','sealed','fifo'):
            a,b=self.pair();bad=object()
            for d in (a,b):
                if field=='fifo':d.fifo.append(bad)
                elif field in ('live','sealed'):setattr(d.tiles.tags[0],field,True)
                else:setattr(d.tiles,field,True if field=='poison' else bad)
            with m.IdleDrainScope(b) as scope:
                self.assertEqual(outcome(lambda:edge(a)),outcome(lambda:edge(b)))
                self.assertEqual(scope.counts['specialized_edges'],0);self.assertEqual(scope.counts['fallback_edges'],1)
            self.assertEqual(state(a),state(b))
    def test_exact_params_and_illegal_args_original_semantics(self):
        offers=[({'extra_unknown':object()},()),({'abort':True},()),({'abort':'bad'},()),({'local_reset':True},()),
          ({'coordinated_reset':True},()),({'read_beat':ReadBeat(0,(0,)*16,True)},()),
          ({'write_ack':m.drain.WriteAck(3)},()),({'result':MatrixResult(0,())},()),
          ({'job':Job(m=16)},()),({'window':object()},()),({'drain':object()},()),({},(object(),))]
        for extra,args in offers:
            a,b=self.pair();kw=dict(LOAN,**extra)
            with m.IdleDrainScope(b) as scope:
                self.assertEqual(outcome(lambda:direct(a,*args,**kw)),outcome(lambda:direct(b,*args,**kw)))
                self.assertEqual(scope.counts['specialized_edges'],0);self.assertEqual(scope.counts['fallback_edges'],1)
            self.assertEqual(state(a),state(b))
    def test_loan_flags_must_be_canonical_true(self):
        for name in ('loan_busy','loan_request','invalidate_lease'):
            for value in (False,None,1):
                a,b=self.pair();kw=dict(LOAN);kw[name]=value
                with m.IdleDrainScope(b) as scope:
                    self.assertEqual(outcome(lambda:direct(a,**kw)),outcome(lambda:direct(b,**kw)))
                    self.assertEqual(scope.counts['specialized_edges'],0)
                self.assertEqual(state(a),state(b))
    def test_idle_to_actual_job_and_read_abort_drain(self):
        a,b=self.pair()
        with m.IdleDrainScope(b) as scope:
            self.assertEqual(edge(a),edge(b));a.bank_guard.lease=b.bank_guard.lease=None
            j=Job(m=16,k=32,n=32,tag=13,activation_bf16=False,write_bytes=2048)
            self.assertEqual(a.tick(job=j),b.tick(job=j));self.assertEqual(a.state,'clear')
            for _ in range(20):
                if a.read_active is not None:break
                self.assertEqual(a.tick(),b.tick())
            self.assertIsNotNone(a.read_active)
            self.assertEqual(a.tick(abort=True),b.tick(abort=True));self.assertIsNotNone(a.read_active)
            count=0
            while a.read_active is not None:
                q,index=a.read_active;r=ReadBeat(q.tag,(0,)*16,index+1==q.beats)
                self.assertEqual(a.tick(read_beat=r),b.tick(read_beat=r));count+=1;self.assertLessEqual(count,32)
            self.assertEqual(a.tick(),b.tick());self.assertEqual(state(a),state(b))
            self.assertEqual(scope.counts['specialized_edges'],1)
    def test_after_hit_same_clock_late_ack_poison_reset_original(self):
        a,b=self.pair()
        with m.IdleDrainScope(b) as scope:
            self.assertEqual(edge(a),edge(b));a.bank_guard.lease=b.bank_guard.lease=None
            self.assertEqual(a.tick(write_ack=m.drain.WriteAck(8)),b.tick(write_ack=m.drain.WriteAck(8)))
            self.assertTrue(a.drain_poison);self.assertEqual(state(a),state(b))
            self.assertEqual(a.tick(coordinated_reset=True),b.tick(coordinated_reset=True));self.assertEqual(state(a),state(b))
            self.assertFalse(a.drain_poison);self.assertEqual(a.state,'idle')
    def test_external_direct_offers_still_blocked(self):
        a,b=self.pair()
        with m.IdleDrainScope(b):
            for name in ('job','window','drain','tile_read','tile_write','abort','read_beat','result','write_ack'):
                value=object();self.assertEqual(a.tick(**{name:value}),b.tick(**{name:value}));self.assertEqual(state(a),state(b))
    def test_other_owner_forwarding_no_transform(self):
        a,b=self.pair()
        with m.IdleDrainScope(b) as scope:
            marker=object();args=(marker,);kw={'bad':marker}
            expected=outcome(lambda:m._ORIGINAL(a,*args,**kw));actual=outcome(lambda:m._DRAIN.tick(a,*args,**kw))
            self.assertEqual(actual,expected);self.assertEqual(dict(scope.counts),{})
    def test_nested_scope_and_prepatched_method_rejected(self):
        a,b=self.pair()
        with m.IdleDrainScope(a):
            with self.assertRaises(ValueError):
                with m.IdleDrainScope(b):pass
        with patch.object(m._DRAIN,'tick',lambda *a,**k:None):
            with self.assertRaises(ValueError):
                with m.IdleDrainScope(a):pass
        self.assertIs(m._DRAIN.tick,m._ORIGINAL)
    def test_canonical_globals_and_instance_override_rejected(self):
        d=owner()
        with patch.object(m.drain,'window',object()):
            with self.assertRaises((ValueError,AttributeError)):
                with m.IdleDrainScope(d):pass
        d.ports=lambda:{}
        with self.assertRaises(ValueError):
            with m.IdleDrainScope(d):pass
    def test_exception_and_scope_mutation_restore(self):
        d=owner()
        with self.assertRaisesRegex(RuntimeError,'injected'):
            with m.IdleDrainScope(d):raise RuntimeError('injected')
        self.assertIs(m._DRAIN.tick,m._ORIGINAL);self.assertIsNone(m._ACTIVE)
        with self.assertRaises(ValueError):
            with m.IdleDrainScope(d):m._DRAIN.tick=lambda *a,**kw:None
        self.assertIs(m._DRAIN.tick,m._ORIGINAL);self.assertIsNone(m._ACTIVE)
    def test_source_code_canonical_check(self):m.check_canonical()
    def test_helper_drift_and_multithread_precondition_rejected(self):
        d=owner()
        with patch.object(m._DRAIN,'_read_command',lambda self:None):
            with self.assertRaises(ValueError):
                with m.IdleDrainScope(d):pass
        with patch.object(m.threading,'active_count',return_value=2):
            with self.assertRaises(ValueError):
                with m.IdleDrainScope(d):pass
    def test_harness_source_only_with_private_work_hidden(self):
        from . import check_small as c
        from pathlib import Path
        original=Path.read_bytes
        def read(path,*args,**kwargs):
            if path.is_relative_to(c.ROOT/'work'):raise AssertionError('private work dependency in cold entry')
            return original(path,*args,**kwargs)
        with patch.object(Path,'read_bytes',read):self.assertEqual(len(c.sources_now()),80)
        self.assertEqual(c.CASES,(('BASE_TWO_TILES',False,'two'),('LOCAL_TWO_TILES',True,'two'),
          ('BASE_ABORT_WRITE',False,'abort_write'),('LOCAL_ABORT_WRITE',True,'abort_write')))
if __name__=='__main__':unittest.main()
