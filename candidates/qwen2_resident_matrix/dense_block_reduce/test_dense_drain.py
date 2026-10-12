"""New Dense admission over the unmodified actual DDR drain event contract."""
from dataclasses import replace
import unittest
from .dense_drain import DenseReductionOwner, DenseDrainRequest, Job, drain
from ..ffn_drain.test_model import Harness, produce_act, token


def request(rows=16, n=1536, cols=32, ng=0):
    return DenseDrainRequest(Job(m=rows,k=1536,n=n,tag=13,a=0x100000,b=0x400000,
        dst=0x4000000,activation_bf16=False,weight_bf16=True,write_bytes=rows*n*4),7,ng,cols)


def owner(enabled=True, workspace=None):
    return DenseReductionOwner(workspace or drain.PrefixWorkspace(0x10000000,786432,11),
        enable_dense_drain=enabled,enable_k_window=True,enable_ffn_drain=True,
        enable_ffn_window=True,enable_ffn_tiles=True)


class DenseDrainTests(unittest.TestCase):
    def test_original_full_dense_stride_and_real_ack_tail(self):
        for rows,n,cols in ((16,1536,160),(128,256,96)):
            q=request(rows,n,cols,n-cols);o=owner();h=Harness(q,o)
            physical=o.a_banks;h.submit()
            for _ in range(50000):
                final=h.ack is not None and len(h.memory)*4==rows*cols*4
                if final:
                    for _ in range(7):
                        e=h.cycle(ack=False)
                        self.assertFalse(e['drain_result_fire'])
                        self.assertTrue(o.tiles.tags[2].live)
                    break
                h.cycle()
            else:self.fail('no final ACK')
            r=h.finish()
            self.assertTrue(r.committed);self.assertEqual(r.ddr_write_bytes,rows*cols*4)
            self.assertEqual(h.memory,{q.job.dst+(row*n+q.ng+c)*4:token(row,q.ng+c)
                             for row in range(rows) for c in range(cols)})
            self.assertIs(physical,o.a_banks);self.assertIs(o.tiles.banks,physical)
            self.assertEqual((physical.depth,o.b_banks.depth),(1376,160))
            self.assertFalse(o.tiles.leased)

    def test_ordinary_dense_write_has_explicit_full_mask_across_guarded_module_identity(self):
        from ..ffn_public.fixture import make_qwen2_21_fixture
        from ..ffn_public import prefix_execution as physical
        from ..ffn_public import execute_numeric as public
        from types import SimpleNamespace
        f=make_qwen2_21_fixture(16);address=f.specs['o'][0]
        mem=physical.PhysicalMemory(f,{name:(lambda offset:bytes(64)) for name,v in f.allocations.items() if v.readonly})
        o=owner();o.job=Job(m=16,k=1536,n=1536,tag=13,a=0x100000,b=0x400000,dst=address,write_bytes=98304)
        o.final_value=[[0x3f800000]*256 for _ in range(16)]
        o.write_state='data';o.write_row=o.write_row_beat=o.write_index=o.write_context=0
        command=drain.down.WriteCommand(address,1,13<<32);o.accepted_write=command
        # The real inherited ordinary write producer has the same source but
        # a different guarded module/class identity from public PhysicalMemory.
        implicit=super(DenseReductionOwner,o)._write_data()
        self.assertIs(type(implicit),drain.down.WriteBeat)
        self.assertIs(type(implicit),public.numeric.model.down.WriteBeat)
        from ..ffn_drain import model as separate_drain
        foreign=separate_drain.down.WriteBeat(implicit.words,implicit.last)
        self.assertIsNot(type(foreign),public.numeric.model.down.WriteBeat)
        mem.write_event('command',command)
        with self.assertRaisesRegex(ValueError,'mask/last/extent'):mem.write_event('data',foreign)
        value=o._write_data()
        self.assertEqual((value.words,value.last),(implicit.words,implicit.last))
        self.assertEqual(value.mask,(1<<64)-1)
        for bad in (SimpleNamespace(words=value.words,last=True),replace(value,mask=(1<<32)-1)):
            with self.assertRaisesRegex(ValueError,'mask/last/extent'):mem.write_event('data',bad)
        mem.write_event('data',value);mem.write_event('ack',drain.WriteAck(command.tag,False,64))
        self.assertEqual(mem.regions['o']['written'],{address})
        self.assertFalse(mem.regions['o']['terminal']);self.assertFalse(mem.regions['o']['published'])

    def test_bad_full_job_rejected_before_any_write(self):
        q=request()
        for bad in (replace(q,job=replace(q.job,write_bytes=64)),
                    replace(q,job=replace(q.job,output_bf16=True)),
                    replace(q,job=replace(q.job,materialize_dense_output=True)),
                    replace(q,job=replace(q.job,weight_bf16=1)),
                    replace(q,job=replace(q.job,dst=q.job.b+4096)),
                    replace(q,identity=0),replace(q,ng=1),replace(q,cols=16)):
            o=owner();h=Harness(q,o);h.submit(bad);r=h.finish()
            self.assertFalse(r.committed);self.assertEqual(h.memory,{})
            self.assertEqual(r.ddr_write_bytes,0)

    def test_complete_dense_weight_span_workspace_overlap_rejected(self):
        q=request(n=256)
        # Outside the old Activation M*N subset but inside real Dense K*N.
        o=owner(workspace=drain.PrefixWorkspace(q.job.b+128*256*4,786432,11))
        h=Harness(q,o);h.submit();r=h.finish()
        self.assertFalse(r.committed);self.assertEqual(h.memory,{})
        self.assertIn('complete Dense span',r.status)

    def test_native_A_adjacent_workspace_uses_true_two_byte_span(self):
        q=request(n=32)
        q=replace(q,job=replace(q.job,k=32,activation_bf16=True))
        o=owner(workspace=drain.PrefixWorkspace(q.job.a+16*32*2,64,11))
        h=Harness(q,o);h.submit()
        self.assertTrue(h.finish().committed)

    def test_default_off_rejects_dense_while_legacy_activation_survives(self):
        q=request();h=Harness(q,owner(False));h.submit();self.assertFalse(h.finish().committed)
        from ..ffn_drain.test_model import request as old_request
        # The default-off extension delegates ordinary Activation untouched.
        old=old_request();h=Harness(old,owner(False));h.submit()
        self.assertTrue(h.finish().committed);h.assert_data(self)

    def test_last_ack_fault_reports_only_preceding_ack_bytes_no_publish(self):
        q=request();o=owner();h=Harness(q,o);h.submit()
        for _ in range(5000):
            if h.ack is not None and len(h.memory)*4==q.job.m*q.cols*4:break
            h.cycle()
        else:self.fail('final ACK')
        before=o.write_bytes;h.cycle(write_ack=replace(h.ack,error=True));r=h.finish()
        self.assertFalse(r.committed);self.assertEqual(r.ddr_write_bytes,before)
        self.assertTrue(o.tiles.tags[2].live)
        self.assertFalse(o.ports()['drain_ready'])


if __name__=='__main__':unittest.main()
