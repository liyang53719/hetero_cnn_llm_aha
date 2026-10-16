"""Real owner tick/ports with synthetic services; no native arithmetic or model run."""
from collections import Counter
from types import SimpleNamespace
import unittest
from .attention_owner import AttentionOwner
from ..ffn_public.prefix_owners import Job, MemoryRequest, MemoryResponse
from candidates.qwen2_attention_resident_candidate.owner import ResidentPV32AttentionOwner
from candidates.qwen2_attention_resident_candidate.scratch import SharedAScratch, ReadonlyKVIdentity


class Scalar:
    def __init__(self): self.client=None; self.calls=Counter()
    def release(self, owner):
        if self.client is not owner: raise ValueError('wrong scalar owner')
        self.client=None


class Matrix:
    def __init__(self):
        self.owner=None; self.reset_required=False; self.counts=Counter()
        self.lib=SimpleNamespace(matrix_normal_fmas=lambda:0)
    def retire_owner_response(self, owner):
        if self.owner is not owner: raise ValueError('wrong Matrix owner')
    def release(self, owner):
        if self.owner is not owner: raise ValueError('wrong Matrix owner')
        self.owner=None


class DrainedClient:
    """No accepted arithmetic; abort/quiescent service control only."""
    state='idle'
    def ports(self): return {'drained':True, 'result':None}
    def tick(self, **inputs): return {'request_fire':False, 'result_fire':False}


class MemoryDebtTests(unittest.TestCase):
    def owner(self, cls=AttentionOwner, *, write=False, accepted=True):
        matrix=Matrix(); scalar=Scalar()
        kwargs={} if cls is AttentionOwner else {'scratch':SharedAScratch(),
             'identity':ReadonlyKVIdentity(1,2,3,4)}
        o=cls(matrix,scalar,**kwargs)
        o.job=Job('Attention',7,0x1000,0x4000,0x8000,1,1536,128,6144,c=0x5000)
        o.request=MemoryRequest(0x8000 if write else 0x1000,1,write,bytes(64) if write else None)
        o.memory_pending=accepted; o.state='wait' if accepted else 'issue'
        o.matrix_client=DrainedClient(); matrix.owner=o; scalar.client=o
        if cls is ResidentPV32AttentionOwner: o.scratch.acquire(o,o.job,o.kv_identity)
        return o

    def test_foreign_read_and_write_keep_debt_until_matching_response(self):
        for write in (False,True):
            for tag in (2, True, 1.0, -1, 1<<64):
                with self.subTest(write=write,tag=tag):
                    o=self.owner(write=write); request=o.request
                    edge=o.tick(memory_response=MemoryResponse(tag,None if write else bytes(64)),response_ready=True)
                    self.assertFalse(edge['memory_response_fire'])
                    self.assertFalse(edge['response_fire'])
                    self.assertTrue(o.memory_pending); self.assertIs(o.request,request)
                    self.assertEqual(o.state,'drain'); self.assertTrue(o.poison)
                    self.assertEqual(o.counts['memory_responses'],0);self.assertEqual(o.ack_bytes,0)
                    for _ in range(2):
                        self.assertFalse(o.tick(response_ready=True)['response_fire'])
                    edge=o.tick(memory_response=MemoryResponse(1,None if write else bytes(64)))
                    self.assertTrue(edge['memory_response_fire']);self.assertFalse(o.memory_pending)
                    self.assertEqual(o.result.status,'Protocol')
                    self.assertEqual(o.ack_bytes,64 if write else 0)
                    self.assertTrue(o.tick(response_ready=True)['response_fire'])
                    self.assertEqual(o.state,'locked')

    def test_matching_success_continues_generator_without_poison(self):
        for write in (False,True):
            o=self.owner(write=write);seen=[]
            def program():
                data=yield
                seen.append(data)
                yield (0x1040,None)
            o.program=program();next(o.program)
            edge=o.tick(memory_response=MemoryResponse(1,None if write else bytes(64)))
            self.assertTrue(edge['memory_response_fire']);self.assertFalse(o.poison)
            self.assertFalse(o.memory_pending);self.assertEqual(o.state,'issue')
            self.assertEqual(seen,[None if write else (0,)*16])
            self.assertEqual(o.ack_bytes,64 if write else 0)

    def test_matching_error_or_wrong_extent_retires_but_fails(self):
        for response in (MemoryResponse(1,error=True),MemoryResponse(1,nbytes=32)):
            o=self.owner(write=True);edge=o.tick(memory_response=response)
            self.assertTrue(edge['memory_response_fire']);self.assertFalse(o.memory_pending)
            self.assertEqual(o.ack_bytes,0);self.assertIn(o.result.status,('Memory','Protocol'))

    def test_reset_plus_foreign_waits_for_matching_debt(self):
        o=self.owner();q=o.request
        o.tick(local_reset=True,memory_response=MemoryResponse(2,bytes(64)))
        self.assertTrue(o.memory_pending);self.assertIs(o.request,q)
        o.tick(memory_response=MemoryResponse(1,bytes(64)))
        self.assertFalse(o.memory_pending);self.assertEqual(o.result.status,'Protocol')

    def test_reset_unaccepted_offer_creates_no_debt(self):
        o=self.owner(accepted=False)
        edge=o.tick(local_reset=True,memory_ready=True,memory_response=MemoryResponse(2,bytes(64)))
        self.assertFalse(edge['memory_fire']);self.assertFalse(edge['memory_response_fire'])
        self.assertFalse(o.memory_pending);self.assertEqual(o.state,'finish')

    def test_resident_lease_survives_foreign_until_terminal_consumed(self):
        o=self.owner(ResidentPV32AttentionOwner)
        o.tick(memory_response=MemoryResponse(2,bytes(64)),response_ready=True)
        self.assertTrue(o.memory_pending);self.assertIs(o.scratch.owner,o)
        self.assertTrue(o.scratch.revoked);self.assertIsNone(o.ports()['response'])
        o.tick(memory_response=MemoryResponse(1,bytes(64)))
        self.assertIs(o.scratch.owner,o)
        o.tick(response_ready=True)
        self.assertIsNone(o.scratch.owner)
        self.assertFalse(any(o.scratch.valid))


if __name__=='__main__': unittest.main()
