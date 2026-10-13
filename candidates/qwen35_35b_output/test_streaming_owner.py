"""Bounded address/control tests, real DDR/RMW ingress, no numeric projection."""
from dataclasses import replace
import unittest

from . import streaming_owner as s
from ..qwen35_35b_prefill import projection_owner as old


class StreamingOwnerTests(unittest.TestCase):
    def job(self, m=16, n=2048):
        return s.Job(m=m,k=4096,n=n,tag=71,a=0x100000,b=0x1000000,dst=0x3000000,
                     output_bf16=True,write_bytes=m*n*2)

    def owner(self):
        return s.StreamingProjectionOwner(s.NoPrefixWorkspace(0x100000000,16384,1))

    @staticmethod
    def value(row,k):
        return 0x3f00 | ((row*7 + k//128*13 + k) & 127)

    def load(self, block, *, ng=1920, cols=128):
        job = self.job()
        q = s.StreamingWindowRequest.from_full(job,101+block,ng,cols,block)
        owner = self.owner()
        untouched = tuple(tuple(bank[1024:]) for bank in owner.a_banks.words)
        event = owner.tick(window=q,group_ready=False)
        self.assertTrue(event['window_fire'])
        self.assertIs(owner.window_request,q)
        self.assertIs(q.job,job)
        self.assertEqual(owner.job.k,1024)
        self.assertIsNone(owner.lease)
        pending,addresses = None,[]
        for tick in range(20000):
            e = owner.tick(read_beat=pending,group_ready=False,
                           read_command_ready=tick%3 != 0)
            if e['read_fire']:
                pending = None
            if e['read_command_fire']:
                cmd = e['read_command']
                self.assertEqual((cmd.kind,cmd.beats),('a',1))
                self.assertIsNone(pending)
                addresses.append(cmd.address)
                row,k = divmod((cmd.address-job.a)//2,4096)
                self.assertTrue(0 <= row < 16 and q.k_begin <= k < q.k_end)
                pending = s.base.kw.ReadBeat(cmd.tag,tuple(self.value(row,k+i) for i in range(32)),True)
            self.assertIsNone(owner.error)
            if e.get('a_fence'):
                break
        else:
            self.fail('bounded actual slab ingress did not fence')
        self.assertIsNone(pending)
        expected = [job.a+(row*4096+q.k_begin+beat*32)*2 for row in range(16) for beat in range(32)]
        self.assertEqual(addresses,expected)
        self.assertEqual((owner.loaded_a_bytes,owner.rmw_commits,owner.k_a_fences),(32768,16384,1))
        self.assertEqual(owner.lease,s.StreamingALease.for_request(q))
        self.assertEqual(owner.lease.row_stride,8192)
        self.assertEqual(owner.lease.resident_k,1024)
        self.assertEqual(tuple(tuple(bank[1024:]) for bank in owner.a_banks.words),untouched)
        for row in range(16):
            for local in range(1024):
                bank,word,lane = s.down.a_address(local,row)
                self.assertLess(word,512)
                actual = (owner.a_banks.words[bank][word] >> (16*lane)) & 65535
                self.assertEqual(actual,self.value(row,q.k_begin+local))
        return owner,q

    def test_all_four_actual_strided_ingress_blocks_and_local_sram(self):
        for block in range(4):
            with self.subTest(block=block):
                owner,q = self.load(block)
                self.assertEqual(owner.contexts,4)  # Tail N128, not a fake N128 source.
                self.assertEqual(owner.n_base,1920)
                self.assertEqual((owner.issue_k,owner.load_k),(q.k_begin,q.k_begin))

    def test_pair_high_local_a_and_global_b_issue(self):
        owner,q = self.load(3)
        for ordinal,logical in ((0,3073),(1,3072),(1022,4095),(1023,4094)):
            owner.a_banks.begin_cycle()
            owner.b_banks.begin_cycle()
            owner.issue_k,owner.issue_context = q.k_begin+ordinal,0
            owner._issue_read()
            self.assertEqual(owner.pending[:3],(ordinal,logical,0))
            self.assertEqual(owner.a_banks.reads,{s.down.a_address(logical-q.k_begin,16*g)[0]:
                s.down.a_address(logical-q.k_begin,16*g)[1] for g in range(8)})
            self.assertTrue(all(word < 512 for word in owner.a_banks.reads.values()))
            step = owner._operand_response(owner.pending)
            self.assertEqual((step.k,step.logical_k,step.block_id),(ordinal,logical,4))
            self.assertEqual(step.clear,ordinal==0)
            self.assertEqual(step.last,ordinal==1023)
        owner.read_active = owner.a_hold = owner.a_rmw_pending = None
        owner.load_k,owner.load_depth,owner.load_beat = 3072,3,2
        owner.ready[:] = [False,False]
        cmd = owner._read_command()
        self.assertEqual(cmd.address,q.job.b+((3072+3)*2048+1920+2*32)*2)
        self.assertEqual((cmd.kind,cmd.beats),('b',1))

    def test_original_request_and_complete_source_geometry_not_shortened(self):
        for m in (16,128):
            job = self.job(m=m)
            for block in range(4):
                q = s.StreamingWindowRequest.from_full(job,100+block,1920,128,block)
                q.validate()
                self.assertIs(q.job,job)
                self.assertEqual((q.job.k,q.job.n),(4096,2048))
                self.assertEqual((q.resident_job().k,q.resident_job().n),(1024,2048))
                self.assertEqual(q.slot,0 if block==0 else 1)
                self.assertFalse(q.reuse_a)
        self.assertEqual(s.down.a_address(1023,127)[1],511)

    def test_malformed_blocks_identities_extents_and_full_aliases_rejected(self):
        q = s.StreamingWindowRequest.from_full(self.job(),101,1920,128,3)
        for kw in (dict(block_index=True),dict(block_index=4),dict(block_id=3),dict(k_begin=2048),
                   dict(k_end=4094),dict(pair_reverse=False),dict(reuse_a=True),dict(slot=0),
                   dict(identity=0),dict(identity=True),dict(ng=1921),dict(cols=160)):
            with self.subTest(kw=kw),self.assertRaises(ValueError):
                replace(q,**kw).validate()
        j = self.job()
        for changed in (replace(j,k=2048),replace(j,b=j.a+65536),replace(j,dst=j.a+65536),
                        replace(j,write_bytes=j.write_bytes-64),replace(j,activation_bf16=False)):
            with self.subTest(job=changed),self.assertRaises(ValueError):
                s.validate_full_job(changed)

    def test_bad_request_retires_as_error_without_resident_binding(self):
        q = replace(s.StreamingWindowRequest.from_full(self.job(),101,0,32,0),k_end=2048)
        owner = self.owner()
        event = owner.tick(window=q,group_ready=False)
        self.assertTrue(event['window_fire'])
        self.assertIsNotNone(owner.error)
        self.assertIsNone(owner.resident_descriptor)
        for _ in range(10):
            event = owner.tick(group_ready=False)
            if event.get('window_result_fire'):
                self.assertIsNotNone(event['window_result'].status)
                break
        else:
            self.fail('malformed window did not retire its error')

    def test_bad_dma_tag_cannot_mint_a_lease(self):
        owner = self.owner()
        q = s.StreamingWindowRequest.from_full(self.job(),101,0,32,2)
        owner.tick(window=q,group_ready=False)
        for _ in range(600):
            event = owner.tick(group_ready=False)
            if event['read_command_fire']:
                cmd = event['read_command']
                owner.tick(read_beat=s.base.kw.ReadBeat(cmd.tag+1,(0x3f80,)*32,True),group_ready=False)
                break
        else:
            self.fail('no actual A request')
        self.assertIsNotNone(owner.error)
        self.assertIsNone(owner.lease)
        self.assertEqual(owner.k_a_fences,0)

    def test_no_prefix_contract_does_not_relax_ordinary_seeded_job(self):
        workspace = s.NoPrefixWorkspace(0x100000000,64,1)
        workspace.validate(self.job())
        with self.assertRaises(ValueError):
            s.PrefixWorkspace(0x100000000,64,1,4096).validate(self.job())
        with self.assertRaises(ValueError):
            self.owner().tick(job=self.job())
        with self.assertRaises(ValueError):
            s.NoPrefixWorkspace(self.job().a,64,1).validate(self.job())

    def test_legacy_two_partial_request_keeps_default_full_resident_behavior(self):
        owner = self.owner()
        job = replace(self.job(n=32),k=2048)
        q = old.LargeKWindowRequest(job,111,0,32,0,False,
                k_begin=0,k_end=1024,block_id=1,pair_reverse=True)
        event = owner.tick(window=q,group_ready=False)
        self.assertTrue(event['window_fire'])
        self.assertIsNone(owner.error)
        self.assertIs(owner.job,job)
        self.assertEqual(owner.job.k,2048)
        self.assertIsNone(owner.resident_descriptor)
        self.assertIs(owner.tiles.banks,owner.a_banks)

    def test_streaming_drain_reaches_original_sealed_sum_admission(self):
        owner = self.owner()
        q = s.StreamingDrainRequest(self.job(),501,1920,128)
        event = owner.tick(drain=q)
        self.assertTrue(event['drain_fire'])
        self.assertIs(owner.drain_request,q)
        self.assertIn('sealed GDN sum slot',owner.error)
        self.assertEqual(owner.write_bytes,0)
        self.assertFalse(event['write_command_fire'])

    def test_streaming_drain_only_accepts_full_geometry(self):
        q = s.StreamingDrainRequest(self.job(),501,1920,128)
        q.validate()
        for changed in (replace(q,identity=0),replace(q,cols=160),replace(q,job=replace(q.job,k=1024))):
            with self.assertRaises(ValueError):
                changed.validate()


if __name__ == '__main__':
    unittest.main(verbosity=2)
