from dataclasses import replace
from types import SimpleNamespace
import unittest
from .banks import LoanDenseOwner,BankByteView,banked_scratch,LoanFault
from candidates.qwen2_attention_resident_candidate.scratch import ReadonlyKVIdentity

class Cold(unittest.TestCase):
    def new(self):
        d=LoanDenseOwner(enable_ffn_window=True,enable_ffn_tiles=True)
        return d,banked_scratch(d.a_banks)
    def test_same_original_payload_and_no_second_array(self):
        d,s=self.new();self.assertIs(d.tiles.banks,d.a_banks);self.assertIs(s.storage.banks,d.a_banks)
        self.assertIsInstance(s.storage,BankByteView);self.assertEqual(len(s.storage),704512)
        self.assertEqual(len(s.valid),512);self.assertEqual(d.a_banks.depth,1376)
    def test_foreign_dense_window_tile_bank_blocked(self):
        d,s=self.new();g=d.a_banks;g.lease=object();before=g.words
        for key in ('job','window','k_window','drain','tile_control','tile_write','tile_read'):
            edge=d.tick(**{key:object()});self.assertTrue(edge['loan_blocked']);self.assertFalse(edge['job_ready'])
        for fn in (lambda:d.tiles.tick(control=object()),lambda:g.begin_cycle(),lambda:g.read(0,0),lambda:g.write(0,0,1)):
            with self.assertRaises(LoanFault):fn()
        self.assertEqual(before,g.words);self.assertFalse(g.in_edge);self.assertIsNone(g.actor)
    def test_two_bank_route_same_cells_and_one_clock(self):
        d,s=self.new();g=d.a_banks;who=object();g.lease=who
        job=SimpleNamespace(tag=7,b=0x200000,c=0x300000,m=1,dst=0x400000,write_bytes=6144)
        s.acquire(who,job,ReadonlyKVIdentity(1,1,1,1));data=bytes(range(64))
        with g.edge():
            g.clock_only=True;d.tick();g.clock_only=False
            with g.scope('cache'):s.accept(who,s.make_request(who,job.b,1,data))
            self.assertEqual(g.writes,{0:0,1:0});self.assertEqual(g.begins,1)
            with g.scope('owner'):
                with self.assertRaises(LoanFault):g.begin_cycle()
        self.assertEqual(g.words[0][0].to_bytes(32,'little')+g.words[1][0].to_bytes(32,'little'),data)
        s.clock+=1;s.consume(who)
        with g.edge():
            g.clock_only=True;d.tick();g.clock_only=False
            with g.scope('cache'):s.accept(who,s.make_request(who,job.b,2))
            self.assertEqual(g.reads,{0:0,1:0})
        s.clock+=1;self.assertEqual(s.consume(who).data,data);s.release(who);g.lease=None
        self.assertTrue(d.tick()['job_ready'])
    def test_scope_restored_after_fault_no_lease_release(self):
        d,s=self.new();g=d.a_banks;owner=object();g.lease=owner
        with self.assertRaises(RuntimeError):
            with g.edge():
                with g.scope('cache'):raise RuntimeError('injected')
        self.assertIsNone(g.actor);self.assertFalse(g.in_edge);self.assertIs(g.lease,owner)
        self.assertTrue(d.tick(job=object())['loan_blocked'])
    def test_read_only_snapshot_and_slice_bounds(self):
        d,s=self.new()
        with self.assertRaises(TypeError):d.a_banks.words[0][0]=1
        for index in (slice(0,64),slice(1,33),slice(-32,0),slice(0,32,1)):
            with self.assertRaises(LoanFault):s.storage[index]
    def test_internal_clock_rejects_any_external_payload(self):
        d,s=self.new();g=d.a_banks;g.lease=object()
        for key in ('job','window','k_window','drain','tile_read','abort','local_reset','loan_busy'):
            with g.edge():
                g.clock_only=True
                with self.assertRaises(LoanFault):d.tick(**{key:object()})
                self.assertEqual(g.begins,0)
        self.assertFalse(g.clock_only);self.assertFalse(g.in_edge);self.assertIsNone(g.actor)
    def test_frozen_scratch_control_fields_exact(self):
        from candidates.qwen2_attention_resident_candidate.scratch import SharedAScratch
        d,s=self.new();original=SharedAScratch()
        self.assertEqual(vars(s).keys(),vars(original).keys())
        for k in vars(s):
            if k!='storage':self.assertEqual(getattr(s,k),getattr(original,k))
    def test_loan_flags_preserved_by_call_scope(self):
        d,s=self.new();g=d.a_banks
        before=(d.ports()['job_ready'],d.lease)
        self.assertFalse(d.tick(loan_busy=True)['job_ready'])
        self.assertEqual((d.ports()['job_ready'],d.lease),before)
        g.lease=object()
        with g.edge():g.clock_only=True;d.tick()
        self.assertIsNone(g.actor);self.assertFalse(g.clock_only)
        g.lease=None
        self.assertEqual((d.tick()['job_ready'],d.lease),before)
    def test_duplicate_ports_and_malformed_words_fail_before_mutation(self):
        d,s=self.new();g=d.a_banks;g.lease=object()
        with g.edge():
            g.clock_only=True;d.tick();g.clock_only=False
            with g.scope('cache'):
                g.read(0,0);g.write(0,0,7)
                for args in ((0,1),(True,0),(16,0),(1,-1),(1,1376),(1,False)):
                    before=(g.words,g.reads,g.writes,dict(g.counts))
                    with self.assertRaises(LoanFault):g.read(*args)
                    self.assertEqual(before,(g.words,g.reads,g.writes,dict(g.counts)))
                for args in ((0,1,8),(1,0,-1),(1,0,1<<256),(1,0,True),(True,0,0),(1,False,0),(1,1376,0)):
                    before=(g.words,g.reads,g.writes,dict(g.counts))
                    with self.assertRaises(LoanFault):g.write(*args)
                    self.assertEqual(before,(g.words,g.reads,g.writes,dict(g.counts)))
                g.reads.clear();g.writes.clear()
                with self.assertRaises(LoanFault):g.read(0,2)
                with self.assertRaises(LoanFault):g.write(0,2,9)

    def test_accepted_dense_operand_hold_blocks_admission_and_continuation(self):
        from .lease import SharedALoanRouter
        d,s=self.new();r=SharedALoanRouter.__new__(SharedALoanRouter)
        r.dense=d;r.guard=d.a_banks;r.bank_identity=d.a_banks.payload_identity
        r.prefix=object();r.attention=object();r.guard.lease=r
        r._assert_exclusive()
        hold=object();d.a_hold=hold
        with self.assertRaises(LoanFault):r.quiescent()
        with self.assertRaises(LoanFault):r._assert_exclusive()
        self.assertIs(d.a_hold,hold);self.assertIs(r.guard.lease,r)

    def test_all_explicit_entry_debts_rejected(self):
        # Predicate-only unit. The executable small gate supplies actual native
        # Matrix/Scalar and producer objects, never this test double.
        from .lease import SharedALoanRouter
        d,s=self.new();native=SimpleNamespace(state=0);native.matrix_state=lambda:native.state
        a=SimpleNamespace(state='idle',poison=False,memory_pending=False,abort_pending=False,
          matrix_client=None,matrix_request=None,local_pending=False,scratch=s,
          scalar=SimpleNamespace(client=None),matrix=SimpleNamespace(owner=None,reset_required=False,lib=native))
        r=SharedALoanRouter.__new__(SharedALoanRouter);r.dense=d;r.attention=a
        r.prefix=SimpleNamespace(state='idle',poison=False,ports=lambda:{'response':None})
        r.publication=SimpleNamespace(pending=lambda:None)
        r.quiescent()
        for obj,name,bad in ((d,'accepted_write',object()),(d,'a_hold',object()),(a,'memory_pending',True),
          (a,'abort_pending',True),(a,'matrix_client',object()),(a,'matrix_request',object()),(native,'state',8)):
            old=getattr(obj,name);setattr(obj,name,bad)
            with self.assertRaises(LoanFault):r.quiescent()
            self.assertIs(getattr(obj,name),bad);setattr(obj,name,old)
        r.guard=d.a_banks;r.bank_identity=d.a_banks.payload_identity;r.guard.lease=r
        d.accepted_write=object()
        with self.assertRaises(LoanFault):r._assert_exclusive()

class PublicationCold(unittest.TestCase):
    def produced(self,rows=1,dst=0x400000):
        from candidates.qwen2_resident_matrix.official_bf16.owners import OfficialPrefixOwner
        from candidates.qwen2_resident_matrix.ffn_public.prefix_owners import Job
        from candidates.qwen2_resident_matrix.ffn_public.test_prefix_owners import Harness
        from .lease import SyntheticKvPublication
        p=OfficialPrefixOwner(max_tokens=128);h=Harness(p)
        j=Job('KvAppend',0x110009,0x100000,0x200000,dst,rows,256,256,rows*2048)
        h.bus.input(j.a,[0x3f800000]*(rows*256));h.bus.input(j.b,[0xbf800000]*(rows*256));h.bus.output(j.dst,j.write_bytes)
        self.assertTrue(h.tick(job=j)['job_fire']);h.until(lambda:p.ports()['response'] is not None)
        r=p.ports()['response'];self.assertTrue(h.tick(response_ready=True)['response_fire']);h.bus.publish(p,j)
        return p,h,j,r,SyntheticKvPublication(p,h,j,r)
    def test_real_kvappend_binding_and_active_pending(self):
        p,h,j,r,seal=self.produced();a=SimpleNamespace(b=j.dst,c=j.dst+1024,m=1)
        identity=seal.validate(a);h.bus.pending=SimpleNamespace(write=False,address=j.dst)
        self.assertEqual(seal.validate(a),identity)
        h.bus.pending=None
        old=h.bus.words[j.dst];h.bus.words[j.dst]=bytes(64)
        with self.assertRaises(LoanFault):seal.validate(a)
        h.bus.words[j.dst]=old;h.bus.acked.remove(j.dst)
        with self.assertRaises(LoanFault):seal.validate(a)
    def test_public_continuous_validator_actual_physical_write_pending(self):
        # Isolated ongoing-validator unit, deliberately NOT a public-prefix
        # constructor success. The full constructor rejects this unit host.
        from candidates.qwen2_resident_matrix.ffn_public.fixture import make_qwen2_21_fixture
        from candidates.qwen2_resident_matrix.ffn_public.prefix_execution import PhysicalMemory
        from .lease import PublicKvPublication
        f=make_qwen2_21_fixture(rows=16);physical=PhysicalMemory(f,{})
        kv=physical.regions['kv'];p,h,j,r,seal=self.produced(16,kv['base'])
        for address in sorted(h.bus.outputs[j.dst]):
            raw=h.bus.words[address]
            physical.write_event('command',SimpleNamespace(address=address,beats=1,tag=1))
            physical.write_event('data',SimpleNamespace(words=__import__('struct').unpack('<16I',raw),mask=(1<<64)-1,last=True))
            physical.write_event('ack',SimpleNamespace(tag=1,error=False,nbytes=64))
        physical.terminal(j,r);host=SimpleNamespace(published=[(j.dst,j.dst+j.write_bytes)],status=None)
        physical.publish(j,host)
        a=SimpleNamespace(b=j.dst,c=j.dst+16*1024,m=16)
        x=SimpleNamespace(host=host)
        with self.assertRaises(LoanFault):PublicKvPublication(x,physical,a)
        check=PublicKvPublication.__new__(PublicKvPublication)
        check.x=x;check.physical=physical;check.job=a;check.region=kv;check.epoch=f.config.epoch;check.digest=physical.published_hashes['kv']
        identity=check.validate(a)
        att=physical.regions['att'];physical.write_event('command',SimpleNamespace(address=att['base'],beats=1,tag=2))
        physical.write_event('data',SimpleNamespace(words=(0,)*16,mask=(1<<64)-1,last=True))
        self.assertIsNotNone(physical.pending);self.assertEqual(check.validate(a),identity)
        physical.write_event('ack',SimpleNamespace(tag=2,error=False,nbytes=64))
        with self.assertRaises(ValueError):physical.write_event('command',SimpleNamespace(address=kv['base'],beats=1,tag=3))
        self.assertIsNone(physical.pending)

if __name__=='__main__':unittest.main()
