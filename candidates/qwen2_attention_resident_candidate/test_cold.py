import ast
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import unittest
from .scratch import SharedAScratch,ReadonlyKVIdentity,CacheFault

class Cold(unittest.TestCase):
    def new(self):
        s=SharedAScratch();o=object();j=SimpleNamespace(tag=7,b=0x200000,c=0x300000,m=128,dst=0x400000,write_bytes=786432)
        s.acquire(o,j,ReadonlyKVIdentity(9,9,1,1));return s,o,j
    def test_fixed_physical_mapping(self):
        cells=[cell for i in range(4096) for cell in SharedAScratch.cells(i)]
        self.assertEqual(len(set(cells)),8192)
        self.assertEqual(max(w for b,w in cells),511)
        self.assertTrue(all(a[0]!=b[0] for a,b in (SharedAScratch.cells(i) for i in range(4096))))
        s=SharedAScratch();self.assertEqual(len(s.storage),688*1024);self.assertEqual(len(s.valid),512)
    def test_fill_commit_then_delayed_held_read(self):
        s,o,j=self.new();data=bytes(range(64));r=s.make_request(o,j.b,1,data);s.accept(o,r)
        self.assertIsNone(s.response());self.assertFalse(s.present(0))
        with self.assertRaises(CacheFault):s.release(o)
        s.clock+=1;held=s.response();self.assertIs(s.response(),held);s.consume(o)
        self.assertTrue(s.present(0));s.accept(o,s.make_request(o,j.b,2))
        self.assertIsNone(s.response());s.clock+=1;self.assertEqual(s.response().data,data)
        s.consume(o);s.release(o);self.assertFalse(any(s.valid))
    def test_exclusive_lease_and_epoch(self):
        s,o,j=self.new();e=s.epoch
        with self.assertRaises(CacheFault):s.reserve_external(object())
        s.release(o);other=object();s.reserve_external(other)
        with self.assertRaises(CacheFault):s.acquire(o,j,ReadonlyKVIdentity(9,9,1,1))
        s.release_external(other);s.acquire(o,j,ReadonlyKVIdentity(9,9,2,2));self.assertGreater(s.epoch,e)
    def test_abort_and_producer_write_revoke(self):
        for mode in ('abort','write','producer'):
            s,o,j=self.new();s.accept(o,s.make_request(o,j.b,1,bytes(64)))
            if mode=='abort':s.revoke()
            elif mode=='write':s.notify_write(j.b,64)
            else:s.producer_changed(ReadonlyKVIdentity(9,9,2,2))
            s.clock+=1;s.consume(o,abort=True);self.assertFalse(s.present(0));s.release(o)
    def test_no_arithmetic_override_or_unbounded_cache(self):
        path=Path(__file__).with_name('owner.py');tree=ast.parse(path.read_text())
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='ResidentPV32AttentionOwner')
        names={n.name for n in cls.body if isinstance(n,ast.FunctionDef)}
        self.assertFalse(names & {'_attention','_matrix_step','_pv32_step','_op'})
        self.assertNotIn('dict(',Path(__file__).with_name('scratch.py').read_text().split('def report')[0])
    def test_direct_malformed_request_cannot_mutate(self):
        from .scratch import LocalRequest
        for change in ({'data':b'x'},{'data':bytearray(64)},{'data':True},{'serial':True},
                       {'epoch':True},{'address':True},{'line':True},{'line':4096},{'address':-64}):
            s,o,j=self.new();r=LocalRequest(s.epoch,1,j.b,0,bytes(64));r=replace(r,**change)
            before=(bytes(s.storage),bytes(s.valid),s.pending,s.held,dict(s.counts))
            with self.assertRaises(CacheFault):s.accept(o,r)
            self.assertEqual(before,(bytes(s.storage),bytes(s.valid),s.pending,s.held,dict(s.counts)))
    def test_acquire_alias_refused(self):
        s,o,j=self.new();s.release(o)
        for b,c,dst in ((3,j.c,j.dst),(j.b,j.b,j.dst),(j.b,j.c,j.b)):
            bad=SimpleNamespace(**dict(vars(j),b=b,c=c,dst=dst))
            with self.assertRaises(CacheFault):s.acquire(o,bad,ReadonlyKVIdentity(9,9,1,1))
            self.assertIsNone(s.owner)
    def test_malformed_packet_and_stale_epoch(self):
        s,o,j=self.new()
        with self.assertRaises(CacheFault):s.make_request(o,j.b,1,b'bad')
        r=s.make_request(o,j.b,1,bytes(64))
        with self.assertRaises(CacheFault):s.accept(o,replace(r,epoch=r.epoch-1))
        with self.assertRaises(CacheFault):s.make_request(o,j.b,True,bytes(64))
if __name__=='__main__':unittest.main()
