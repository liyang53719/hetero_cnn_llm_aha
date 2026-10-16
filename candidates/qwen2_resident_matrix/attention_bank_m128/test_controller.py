"""Cold M1/M2 and isolated 17-key tile-boundary evidence; no full M17+ run."""
import unittest
from unittest.mock import patch
from .controller import Controller, Timing, admit, ADMITTED_SHAPES
from .storage import Scratch, address
from ..attention_bank_scratch.controller import Controller as Frozen
from ..attention_bank_scratch.storage import Scratch as FrozenScratch
from ..attention_bank_scratch.port import location
from ..attention_bank_multirow.profile import EventSink
from ..attention_matrix_batch.test_model import ExactScalar, fixture, ref_fma, exp_negative, expected_qk, exact
from ..raw_kv_parent import model as parent_model


class ControllerTests(unittest.TestCase):
    def make(self, cls=Controller, **kwargs):
        scalar = ExactScalar(object())
        kwargs.setdefault('scratch_enabled', True)
        return cls(scalar, ref_fma, lambda a: exp_negative(scalar, scalar.client, a),
                   timing=Timing(2,3,1,2), **kwargs)

    def test_whitelist_and_default_off(self):
        self.assertEqual(ADMITTED_SHAPES, (1,2,4,8,16,17,32,128))
        for n in ADMITTED_SHAPES: admit(n)
        for n in (0,3,15,18,64,127,129,True,1.0,'2',None):
            with self.assertRaisesRegex(ValueError,'admitted shapes'): admit(n)
        c = self.make(scratch_enabled=False)
        self.assertIsNone(c.scratch)
        with self.assertRaisesRegex(ValueError,'disabled'): c.run(1,*fixture(1))
        self.assertEqual(c.ticks,0)

    def test_single_original_owner_allocation(self):
        with patch.object(parent_model,'DenseReductionOwner', wraps=parent_model.DenseReductionOwner) as make:
            c = self.make()
            self.assertEqual(make.call_count,1)
        self.assertIs(c.scratch.banks,c.scratch.parent.owner.a_banks)
        self.assertIs(c.scratch.banks,c.scratch.parent.raw.banks)
        with patch.object(parent_model,'DenseReductionOwner', wraps=parent_model.DenseReductionOwner) as make:
            other = self.make(owner=c.scratch.parent.owner)
            self.assertEqual(make.call_count,0)
        self.assertIs(other.scratch.banks,c.scratch.banks)
        self.assertIs(Scratch.write_scores,FrozenScratch.write_scores)
        self.assertIs(Controller.matrix_group,Frozen.matrix_group)
        self.assertIs(Controller.scalar_phase,Frozen.scalar_phase)

    def test_m1_m2_bit_count_tick_and_streaming_trace_equivalence(self):
        for n in (1,2):
            with self.subTest(tokens=n):
                old, new = self.make(Frozen,bank_stalls=1), self.make(bank_stalls=1)
                data = fixture(n)
                want, got = old.run(n,*data), new.run(n,*data)
                self.assertEqual(got,want)
                for name in ('read_events','ack_events','views','scratch.events'):
                    records = old.scratch.events if name == 'scratch.events' else getattr(old,name)
                    sink = EventSink(name)
                    for event in records: sink.append(event)
                    self.assertEqual(new.observation_summary()[name],sink.summary())
                self.assertEqual((len(new.tmp),len(new.cv),len(new.acc)),(16,12,6))
                self.assertTrue(new.ordinary_owner_ready())
                self.assertIsNone(new.scratch.staging)
                self.assertIsNone(new.slot)

    def test_n17_packet_prefix_ack_and_samebank_mapping(self):
        s=Scratch(enabled=True,stalls=2); s.acquire(); c=s.begin(16,1,17)
        writes=[]
        def edge():
            if s.active:
                context,key=s.active
                self.assertEqual(s.score_written[2],0 if key.line==4112 else 16)
                if s.banks.writes:
                    writes.append(tuple(sorted(s.banks.writes.items())))
        s.edge=edge
        for args in ((2,16,(99,)),(2,0,(1,)*15),(2,0,(1,)*17),(True,0,(1,)*16),(2,True,(1,)*16)):
            with self.assertRaises(ValueError): s.write_score_packet(c,*args)
        s.write_score_packet(c,2,0,tuple(range(16)))
        self.assertEqual(s.score_written[2],16)
        with self.assertRaises(ValueError): s.read_word(c,'score',2,16)
        with self.assertRaises(ValueError): s.write_score_packet(c,2,0,(1,)*16)
        with self.assertRaises(ValueError): s.write_score_packet(c,2,16,(1,2))
        s.write_score_packet(c,2,16,(0x80000000,))
        self.assertEqual(s.score_written[2],17)
        self.assertEqual(writes,[((0,514),(1,514)),((2,514),(3,514))])
        self.assertEqual(location(address('score',2,16)[0],scratch_enabled=True),(2,3,514))
        s.edge=lambda:None
        self.assertEqual(tuple(s.read_word(c,'score',2,i) for i in range(17)),tuple(range(16))+(0x80000000,))
        tail=s.transfer(c,address('score',2,16)[0]); s.staging=None
        self.assertEqual(tail,0x80000000)
        self.assertIs(s.banks,s.parent.owner.a_banks)
        self.assertEqual(s.counts['acks'],s.counts['write_requests']+s.counts['read_requests'])
        s.release()

    def test_packet_abort_never_publishes_prefix(self):
        s=Scratch(enabled=True); s.acquire(); c=s.begin(16,0,17)
        s.write_score_packet(c,0,0,(1,)*16)
        def edge():
            if s.active is not None: s.abort()
        s.edge=edge
        with self.assertRaisesRegex(ValueError,'retired poisoned'):
            s.write_score_packet(c,0,16,(2,))
        self.assertEqual(s.score_written[0],16)
        self.assertNotIn(address('score',0,16)[0],s.initialized)
        self.assertTrue(s.parent.raw.drained)
        self.assertIsNone(s.active)

    def test_isolated_n17_onehead_exact_fold_and_causal_padding(self):
        # Only QK for one head of query16, not a full M17 execution. Include
        # future key17 in the input and prove no packet consumes it.
        q,k,_ = fixture(18)
        c=self.make(); s=c.scratch; s.acquire(); context=s.begin(16,1,17)
        c.cv[:]=[0xff800000]*6+[0]*6
        packets, commits, observations=[],[],[]
        original_group, original_write=c.matrix_group,s.write_score_packet
        def group(payloads,selected,mask):
            def packet(step):
                payload=payloads.make(step)
                packets.append(payload)
                return payload
            from ..attention_bank_scratch.controller import Packets
            self.assertEqual(len(payloads),8)
            self.assertEqual(len(selected),256 if not packets else 16)
            return original_group(Packets(8,packet),selected,mask)
        def write(context,head,first,words):
            self.assertIsNotNone(c.slot)
            self.assertEqual(c.slot['mask'],255)
            self.assertLessEqual(len(words),16)
            original_write(context,head,first,words)
            self.assertIsNotNone(c.slot)
            self.assertTrue(s.parent.raw.drained)
            commits.append((first,len(words)))
        c.matrix_group=group; s.write_score_packet=write
        c.qk_head(context,2,q,k,observations)
        expected=expected_qk(q[16*1536+8*128:16*1536+9*128],
                             tuple(k[key*256+128:key*256+256] for key in range(17)))[1]
        self.assertEqual(tuple(observations),expected)
        self.assertEqual(c.cv[2],max(expected,key=exact))
        self.assertEqual(commits,[(0,16),(16,1)])
        self.assertEqual(len(packets),16)
        for step,(_,right) in enumerate(packets[8:]):
            self.assertEqual(right[:16],k[16*256+128+16*step:16*256+144+16*step])
            self.assertEqual(right[16:],(0,)*240)
        self.assertEqual(tuple(s.read_word(context,'score',2,key) for key in range(17)),expected)
        self.assertEqual(c.counts['selected_fmas'],17*128)
        self.assertEqual(c.counts['max_comparisons'],17)
        self.assertIsNone(c.slot)
        self.assertIsNone(s.staging)
        s.release()


if __name__=='__main__': unittest.main()
