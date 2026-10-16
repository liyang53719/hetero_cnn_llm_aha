"""Cold protocol/resource checks; no RTL, native arithmetic, or heavy run."""
import unittest
from .storage import Scratch, Context, PANEL_RESOURCE_LEDGER, address
from ..attention_bank_scratch.port import Key, location
from ..raw_kv_parent.model import ParentLoan


def score(h,k): return 0x3f800001+257*h+3*k

def weight(h,k): return 0x3e000001+321*h+5*k


class StorageTests(unittest.TestCase):
    def make(self,keys=1,**kw):
        s=Scratch(enabled=True,**kw);s.acquire();return s,s.begin(keys-1,0,keys)

    def scores(self,s,c):
        for h in range(6):
            for first in range(0,c.keys,16):
                s.write_score_packet(c,h,first,tuple(score(h,k) for k in range(first,min(first+16,c.keys))))

    def qk(self,s,c):
        s.qk_complete(c,matrix_drained=True,scalar_drained=True,joined_drained=True)

    def softmax(self,s,c):
        for first in range(0,c.keys,16):
            s.load_score_panel(c,first)
            for key in range(first,min(first+16,c.keys)):
                self.assertEqual(s.read_scores(c,key),tuple(score(h,key) for h in range(6)))
                s.write_weights(c,key,tuple(weight(h,key) for h in range(6)))
            s.commit_weight_panel(c)

    def pv(self,s,c):
        s.begin_pv(c,reciprocal_acked=True,scalar_drained=True)
        for first in range(0,c.keys,16):
            s.load_weight_panel(c,first)
            for key in range(first,min(first+16,c.keys)):
                self.assertEqual(s.read_weights(c,key),tuple(weight(h,key) for h in range(6)))
                s.retire_pv_key(c,key,matrix_drained=True)
        s.end_context(c,matrix_drained=True,scalar_drained=True,joined_drained=True,outputs_acked=True)

    def test_same_banks_exact_4g_serialization_padding_and_raw_bits(self):
        for keys in (1,2,16,17,128):
            with self.subTest(keys=keys):
                p=ParentLoan(enabled=True);s,c=self.make(keys,owner=p.owner,stalls=2)
                self.assertIs(s.banks,p.owner.a_banks);self.assertIs(s.parent.raw.banks,s.banks)
                trace=[]
                def edge():
                    if s.parent.raw.pending is not None:
                        k=s.parent.raw.pending.key;trace.append((k.line,k.write))
                        lo,hi,_=location(k.line,scratch_enabled=True)
                        self.assertEqual(set(s.banks.writes if k.write else s.banks.reads),{lo,hi})
                s.edge=edge
                self.scores(s,c);self.qk(s,c);self.softmax(s,c);self.pv(s,c)
                g=6*((keys+15)//16)
                for counter,n in (('read_requests',2*g),('write_requests',2*g),('acks',4*g),
                    ('edges',1+20*g),('bank_reads',4*g),('bank_writes',4*g)):
                    self.assertEqual(s.counts[counter],n,counter)
                expected=[(address('score',h,f)[0],True) for h in range(6) for f in range(0,keys,16)]
                for f in range(0,keys,16):
                    expected.extend((address('score',h,f)[0],False) for h in range(6))
                    expected.extend((address('prob',h,f)[0],True) for h in range(6))
                expected.extend((address('prob',h,f)[0],False) for f in range(0,keys,16) for h in range(6))
                self.assertEqual(trace,expected)
                for h in range(6):
                    for f in range(0,keys,16):
                        lo,hi,w=location(address('prob',h,f)[0],scratch_enabled=True)
                        beat=s.banks.words[lo][w]|s.banks.words[hi][w]<<256
                        self.assertEqual(beat,sum(weight(h,k)<<(32*(k-f)) for k in range(f,min(f+16,keys))))
                self.assertEqual(s.normalized,[0]*6)
                self.assertTrue(all(w==0 for bank in s.banks.words for w in bank[:512]))
                self.assertIsNone(s.staging);self.assertIsNone(s.panel_tag);s.release()

    def test_explicit_resource_ledger_and_no_extra_payload(self):
        s=Scratch(enabled=True)
        self.assertEqual(len(s.panel_words),96);self.assertEqual(s.resource_ledger,PANEL_RESOURCE_LEDGER)
        for name,n in (('panel_payload_bytes',384),('additional_payload_words',0),('macs_per_cycle_denominator',4096)):
            self.assertEqual(s.resource_ledger[name],n)
        for name in ('legacy_dense_weights_retention_verified','physical_register_inventory_verified','v_placement_verified'):
            self.assertFalse(s.resource_ledger[name])
        self.assertEqual({k for k,v in vars(s).items() if isinstance(v,list)},
            {'score_written','weight_written','normalized','panel_words'})
        self.assertFalse(isinstance(s.events,list))

    def test_whole_job_lease_clear_and_competing_borrower_guards(self):
        s=Scratch(enabled=True);s.legacy_clear();self.assertTrue(s.foreign_borrower_allowed())
        for bad in (False,1,None):
            with self.assertRaises(ValueError):s.acquire(matrix_drained=bad)
        s.acquire()
        def check():
            self.assertTrue(s.lease_active);self.assertFalse(s.foreign_borrower_allowed())
            with self.assertRaises(ValueError):s.legacy_clear()
            out=s.tick()
            for k in ('dense_allowed','tile_allowed','clear_allowed'):self.assertFalse(out[k])
        check();c=s.begin(0,0,1);check();self.scores(s,c);self.qk(s,c);check()
        s.load_score_panel(c,0);check();s.read_scores(c,0);s.write_weights(c,0,(1,)*6)
        s.commit_weight_panel(c);check();s.begin_pv(c,reciprocal_acked=True,scalar_drained=True);check()
        s.load_weight_panel(c,0);s.read_weights(c,0);check();s.retire_pv_key(c,0,matrix_drained=True);check()
        s.end_context(c,matrix_drained=True,scalar_drained=True,joined_drained=True,outputs_acked=True);check()
        s.release();self.assertTrue(s.foreign_borrower_allowed());s.legacy_clear()

    def test_qk_all_heads_and_completion_barrier(self):
        s,c=self.make(17)
        with self.assertRaises(ValueError):s.load_score_panel(c,0)
        with self.assertRaises(ValueError):self.qk(s,c)
        for h in range(6):s.write_score_packet(c,h,0,tuple(score(h,k) for k in range(16)))
        with self.assertRaises(ValueError):self.qk(s,c)
        for h in range(6):s.write_score_packet(c,h,16,(score(h,16),))
        for missing in ('matrix_drained','scalar_drained','joined_drained'):
            flags=dict(matrix_drained=True,scalar_drained=True,joined_drained=True);flags[missing]=False
            with self.assertRaises(ValueError):s.qk_complete(c,**flags)
        self.qk(s,c)
        with self.assertRaises(ValueError):s.write_score_packet(c,0,0,(1,)*16)
        s.load_score_panel(c,0)

    def test_key_order_panel_overwrite_and_tail_guards(self):
        s,c=self.make(17);self.scores(s,c);self.qk(s,c)
        for first in (True,-1,1,16):
            with self.assertRaises(ValueError):s.load_score_panel(c,first)
        s.load_score_panel(c,0)
        for first in (0,16):
            with self.assertRaises(ValueError):s.load_score_panel(c,first)
        with self.assertRaises(ValueError):s.read_scores(c,1)
        with self.assertRaises(ValueError):s.write_weights(c,0,(1,)*6)
        s.read_scores(c,0)
        with self.assertRaises(ValueError):s.read_scores(c,0)
        for bad in ((1,)*5,[1]*6,(True,)*6,(-1,)*6):
            with self.assertRaises(ValueError):s.write_weights(c,0,bad)
        s.write_weights(c,0,(1,)*6)
        with self.assertRaises(ValueError):s.write_weights(c,0,(1,)*6)
        with self.assertRaises(ValueError):s.commit_weight_panel(c)
        for k in range(1,16):s.read_scores(c,k);s.write_weights(c,k,(k,)*6)
        s.commit_weight_panel(c)
        with self.assertRaises(ValueError):s.commit_weight_panel(c)
        with self.assertRaises(ValueError):s.load_score_panel(c,0)
        s.load_score_panel(c,16)
        self.assertEqual([s.panel_words[16*h+1:16*h+16] for h in range(6)],[[0]*15 for _ in range(6)])
        s.read_scores(c,16);s.write_weights(c,16,(99,)*6)
        with self.assertRaises(ValueError):s.read_scores(c,17)
        s.commit_weight_panel(c)

    def test_pv_reciprocal_accepted_step_and_final_joined_fences(self):
        s,c=self.make(17);self.scores(s,c);self.qk(s,c)
        with self.assertRaises(ValueError):s.begin_pv(c,reciprocal_acked=True,scalar_drained=True)
        self.softmax(s,c)
        for a,b in ((False,True),(True,False),(1,True)):
            with self.assertRaises(ValueError):s.begin_pv(c,reciprocal_acked=a,scalar_drained=b)
        s.begin_pv(c,reciprocal_acked=True,scalar_drained=True);s.load_weight_panel(c,0)
        with self.assertRaises(ValueError):s.load_weight_panel(c,16)
        with self.assertRaises(ValueError):s.retire_pv_key(c,0,matrix_drained=True)
        s.read_weights(c,0)
        with self.assertRaises(ValueError):s.read_weights(c,1)
        with self.assertRaises(ValueError):s.retire_pv_key(c,0,matrix_drained=False)
        with self.assertRaises(ValueError):s.load_weight_panel(c,16)
        s.retire_pv_key(c,0,matrix_drained=True)
        for k in range(1,16):s.read_weights(c,k);s.retire_pv_key(c,k,matrix_drained=True)
        s.load_weight_panel(c,16);s.read_weights(c,16);s.retire_pv_key(c,16,matrix_drained=True)
        for bad in ('matrix_drained','scalar_drained','joined_drained','outputs_acked'):
            flags=dict(matrix_drained=True,scalar_drained=True,joined_drained=True,outputs_acked=True);flags[bad]=False
            with self.assertRaises(ValueError):s.end_context(c,**flags)
        with self.assertRaises(ValueError):s.release()
        s.end_context(c,matrix_drained=True,scalar_drained=True,joined_drained=True,outputs_acked=True)
        with self.assertRaises(ValueError):s.release(joined_drained=False)
        s.release()

    def test_stale_context_and_disabled_perword_rmw_routes(self):
        s,c=self.make();self.scores(s,c)
        with self.assertRaises(ValueError):s.begin(0,1,1)
        with self.assertRaises(ValueError):s.transfer(c,address('score',0,0)[0])
        with self.assertRaises(ValueError):s.read_word(c,'score',0,0)
        with self.assertRaises(ValueError):s.write_probability(c,0,0,1)
        self.qk(s,c);self.softmax(s,c);self.pv(s,c);new=s.begin(0,1,1)
        self.assertNotEqual(c,new);self.assertFalse(s.initialized);self.assertEqual(s.score_written,[0]*6)
        for old in (c,Context(True,0,0,1)):
            with self.assertRaises(ValueError):s.load_score_panel(old,0)
        with self.assertRaises(ValueError):s.read_weights(new,0)

    def test_raw_weight_visibility_only_after_matching_clean_ack(self):
        s,c=self.make(stalls=2);self.scores(s,c);self.qk(s,c)
        s.load_score_panel(c,0);s.read_scores(c,0);s.write_weights(c,0,(123,)*6);observations=[]
        def edge():
            if s.active is not None and s.active[1].write and s.active[1].line>=4144:
                k=s.active[1];head=(k.line-4144)//8
                self.assertEqual(s.weight_written[head],0);self.assertNotIn(k.line,s.initialized)
                observations.append(head)
        s.edge=edge;s.commit_weight_panel(c)
        self.assertEqual(len(observations),30);self.assertEqual(s.weight_written,[1]*6)
        self.assertEqual(s.counts['raw_weight_head_commits'],6)

    def test_accepted_write_abort_on_accept_or_ack_never_publishes(self):
        for when in ('accept','ack'):
            with self.subTest(when=when):
                s,c=self.make();self.scores(s,c);self.qk(s,c)
                s.load_score_panel(c,0);s.read_scores(c,0);s.write_weights(c,0,(123,)*6)
                def edge():
                    if s.active is not None and s.active[1].write and s.active[1].line>=4144:
                        hit=s.parent.raw.pending is not None if when=='accept' else s.parent.raw.drained
                        if hit:
                            with self.assertRaises(ValueError):s.release()
                            s.abort()
                s.edge=edge
                with self.assertRaisesRegex(ValueError,'retired poisoned'):s.commit_weight_panel(c)
                self.assertTrue(s.parent.raw.drained);self.assertIsNone(s.active)
                self.assertIsNone(s.panel_tag);self.assertIsNone(s.staging)
                self.assertEqual(s.weight_written,[0]*6);self.assertNotIn(address('prob',0,0)[0],s.initialized)
                self.assertEqual(s.counts['acks'],13)
                with self.assertRaises(ValueError):s.begin_pv(c,reciprocal_acked=True,scalar_drained=True)
                s.edge=lambda:None;s.release();self.assertTrue(s.parent.raw.poison)

    def test_read_ack_abort_does_not_publish_panel(self):
        s,c=self.make();self.scores(s,c);self.qk(s,c)
        def edge():
            if s.active is not None and not s.active[1].write and s.parent.raw.drained:s.abort()
        s.edge=edge
        with self.assertRaisesRegex(ValueError,'retired poisoned'):s.load_score_panel(c,0)
        self.assertEqual(s.panel_load_valid,0);self.assertIsNone(s.panel_tag);self.assertIsNone(s.staging)
        self.assertTrue(s.parent.raw.drained);self.assertEqual(s.counts['panel_load_head_acks'],0)

    def test_foreign_ack_preserves_accepted_debt_and_payload(self):
        s,c=self.make(stalls=1);observed=[]
        def edge():
            if observed or s.active is None or s.parent.raw.response is None:return
            held=s.parent.raw.response;observed.append(held.key)
            wrong=Key(held.key.owner,held.key.tag+1,held.key.line,held.key.write)
            out=s.tick(ack=wrong)
            self.assertFalse(out['acked']);self.assertIs(s.parent.raw.response,held)
            self.assertIsNotNone(s.active);self.assertEqual(s.score_written,[0]*6)
            with self.assertRaises(ValueError):s.release()
        s.edge=edge;s.write_score_packet(c,0,0,(123,))
        self.assertEqual(len(observed),1);self.assertEqual(s.score_written,[1,0,0,0,0,0]);self.assertEqual(s.counts['acks'],1)


if __name__=='__main__':unittest.main()
