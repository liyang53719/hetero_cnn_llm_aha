"""Chunk-major actual SRAM coordinates and prefix lifecycle; no RTL arithmetic."""
import importlib.util
from pathlib import Path
import sys,unittest
from dataclasses import replace
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('down_owner_model',HERE/'model.py')
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
class Harness:
    def __init__(self,n=160,output_bf16=False,m_rows=16,k=512,split_k=128,workspace_extent=None):
        self.job=m.Job(m=m_rows,k=k,n=n,output_bf16=output_bf16)
        self.workspace=m.PrefixWorkspace(0x10000000,n//32*16384 if workspace_extent is None else workspace_extent,7,split_k)
        self.owner=m.DenseOwnerModel(self.workspace);self.owner.tick(job=self.job)
        self.read=self.write=self.ack=self.seed_ack=self.seed_request=None
        self.results=[];self.steps=[];self.prefix={};self.dest={};self.pending=[]
        self.versions={};self.group_trace=[];self.step_trace=[];self.seed_trace=[]
        self.seed_payload=[];self.response=None;self.groups=0;self.reads=[]

    def cycle(self,done=True,ack=True,**kw):
        o=self.owner;p=o.ports();args={}
        chunk,n_base=o.chunk_index,getattr(o,"n_base",0)
        restored=o.restored_contexts
        if self.read:
            cmd=self.read
            if cmd.kind=='prefix':
                assert o.prefix_valid and o.committed_prefix_end==o.chunk_start
                assert self.versions[cmd.address]==o.chunk_index-1
                words=self.prefix[cmd.address]
            else:words=(0x3f80,)*(32 if (self.job.activation_bf16 if cmd.kind=='a' else self.job.weight_bf16) else 16)
            args['read_beat']=m.ReadBeat(cmd.tag,words,True)
        if self.results:args['result']=self.results[0]
        if done and o.group_started and not o.group_done and (o.error or (o.group_accepted_steps==(o.chunk_end-o.chunk_start)*o.contexts and o.results_received==o.contexts)):
            args['matrix_done']=m.MatrixDone(self.job.tag,bool(o.error))
        if ack and self.ack:args['write_ack']=self.ack
        if o.error and o.seed_outstanding and self.seed_ack is None:
            self.seed_ack=m.SeedAck(self.seed_request,error=True)
        if self.seed_ack:args['seed_ack']=self.seed_ack
        args.update(kw);e=o.tick(**args)
        if e['read_fire']:self.read=None
        if e['read_command_fire']:self.read=e['read_command'];self.reads.append(self.read)
        if e['group_fire']:
            self.groups+=1;self.group_trace.append((chunk,n_base,o.contexts))
        if e['step_fire']:
            s=e['step'];self.steps.append(s);self.step_trace.append((chunk,n_base,s.k,s.context,s.clear,s.last,s.finish))
            if s.last:
                # Finite opaque physical tokens exercise physical save order.
                physical=tuple(tuple(0x3f000000+chunk*0x10000+(n_base//32+s.context)*0x1000+r*256+c for c in range(256)) for r in range(16))
                self.results.append(m.MatrixResult(s.context,physical))
        if e['result_fire']:self.results.pop(0)
        if e['write_command_fire']:self.write=(e['write_command'],0);self.pending=[]
        if e['write_data_fire']:
            cmd,i=self.write;self.pending.append((cmd.address+64*i,e['write_data'].words));self.write=(cmd,i+1)
            if e['write_data'].last:self.ack=m.WriteAck(cmd.tag,nbytes=cmd.beats*64)
        if e['write_ack_fire']:
            if not args['write_ack'].error and args['write_ack'].tag==self.write[0].tag:
                for addr,words in self.pending:
                    if self.workspace.base<=addr<self.workspace.base+self.workspace.extent:
                        global_context=(addr-self.workspace.base)//16384
                        assert chunk==0 or global_context<restored
                        assert self.versions.get(addr,-1)==chunk-1
                        self.prefix[addr]=words;self.versions[addr]=chunk
                    else:self.dest[addr]=words
            self.ack=self.write=None;self.pending=[]
        if e['seed_begin_fire']:self.seed_request=e['seed_begin']
        if e['seed_beat_fire']:
            b=e['seed_beat'];self.seed_payload.append(b);self.seed_trace.append((chunk,n_base,b))
            if b.last:self.seed_ack=m.SeedAck(b.request)
        if e['seed_ack_fire']:self.seed_ack=self.seed_request=None
        if e['response_fire']:self.response=e['response']
        return e

    def until(self,predicate,**kw):
        for _ in range(2000000):
            if predicate():return
            self.cycle(**kw)
        raise AssertionError((self.owner.state,self.owner.error,self.owner.seed_state))


class DownTests(unittest.TestCase):
    def test_chunk_major_groups_and_same_allocation_versions(self):
        h=Harness(n=192);h.until(lambda:h.response is not None)
        self.assertEqual(h.response,(1,None,16*192*4))
        self.assertEqual(h.group_trace,[(c,n,x) for c in range(4) for n,x in ((0,5),(160,1))])
        self.assertEqual(h.owner.prefix_bytes,3*6*16384)
        self.assertEqual(h.owner.completed_prefix_sweeps,3)
        self.assertEqual(len(h.prefix),6*256)
        self.assertEqual(set(h.versions.values()),{2})
        for ng,contexts in ((0,5),(160,1)):
            for ctx in range(contexts):
                ss=[s for s in h.step_trace if s[1]==ng and s[3]==ctx]
                self.assertEqual([s[2] for s in ss],list(range(512)))
                self.assertEqual([s[2] for s in ss if s[4]],[0])
                self.assertEqual([s[2] for s in ss if s[5]],[127,255,383,511])
        for chunk,ng,b in h.seed_trace:
            expected_base=0x3f000000+(chunk-1)*0x10000+(ng//32+b.request.context)*0x1000
            offset=m.prefix_ddr_beat(b.index)*16
            self.assertEqual(b.words,tuple(expected_base+offset+i for i in range(16)))

    def test_k2560_bank_width_and_full_k_row_stride(self):
        self.assertEqual(m.a_address(2559,127),(8,1279,15))
        with self.assertRaises(ValueError):m.a_address(2560,0)
        j=m.Job(m=16,k=8960,n=32,a=0x1000000,b=0x2000000,dst=0x8000000,activation_bf16=False)
        o=m.DenseOwnerModel(m.PrefixWorkspace(0x10000000,16384,1));o.tick(job=j)
        o.chunk_index=1;o.state='a_load';o.a_row=3;o.a_beat=159
        cmd=o._read_command()
        self.assertEqual(cmd.address,j.a+(3*8960+2560+159*16)*4)
        o.a_beat=160;self.assertIsNone(o._read_command())
        for group in range(8):
            self.assertLess((2559//16)*8+group,1376)

    def test_final_n96_tail_control_all_48_contexts(self):
        # Full N shape, bounded arithmetic-free K512 synthetic control.
        h=Harness(n=1536);h.until(lambda:h.response is not None)
        self.assertEqual(h.groups,40)
        self.assertEqual(h.group_trace[-1],(3,1440,3))
        self.assertEqual(h.owner.prefix_bytes,3*48*16384)
        self.assertEqual(len(h.seed_payload),3*48*256)
        final=[s for s in h.step_trace if s[5] and s[6]]
        self.assertEqual(len(final),40)
        self.assertEqual(final[-1][1:4],(1440,511,2))
        self.assertEqual(h.response[2],16*1536*4)

    def test_missing_last_group_done_blocks_next_sweep(self):
        h=Harness(n=192);h.until(lambda:h.owner.n_base==160)
        h.until(lambda:h.owner.written==1,done=False)
        for _ in range(9):h.cycle(done=False)
        self.assertEqual(h.owner.chunk_index,0);self.assertFalse(h.owner.prefix_valid)
        h.until(lambda:h.response is not None);self.assertIsNone(h.response[1])

    def test_last_prefix_ack_error_never_publishes(self):
        h=Harness(n=32);h.until(lambda:h.owner.chunk_index==1 and h.owner.write_prefix_index==255 and h.ack is not None)
        h.cycle(write_ack=m.WriteAck(h.ack.tag,error=True));h.until(lambda:h.response is not None)
        self.assertTrue(h.owner.error);self.assertFalse(h.owner.prefix_valid);self.assertFalse(h.dest)
        self.assertEqual(h.owner.completed_prefix_sweeps,1)
        self.assertEqual(h.owner.state,'locked')

    def test_prefix_read_error_abort_and_coordinated_reset(self):
        h=Harness(n=32);h.until(lambda:h.read is not None and h.read.kind=='prefix')
        h.cycle(read_beat=m.ReadBeat(h.read.tag,(0,)*16,True,error=True));h.until(lambda:h.response is not None)
        self.assertFalse(h.dest);self.assertTrue(h.owner.error)
        h.owner.tick(local_reset=True);self.assertFalse(h.owner.ports()['job_ready'])
        h.owner.tick(coordinated_reset=True);self.assertTrue(h.owner.ports()['job_ready'])
        self.assertEqual(h.owner.committed_prefix_end,0)

    def test_late_seed_ack_poison_and_final_write_error(self):
        h=Harness(n=32);h.until(lambda:h.seed_ack is not None);late=h.seed_ack
        h.cycle();h.cycle(seed_ack=late);h.until(lambda:h.response is not None)
        self.assertTrue(h.owner.error);self.assertFalse(h.dest)
        h=Harness(n=32);h.until(lambda:h.owner.chunk_index==3 and h.ack is not None)
        h.cycle(write_ack=m.WriteAck(h.ack.tag,error=True));h.until(lambda:h.response is not None)
        self.assertTrue(h.response[1]);self.assertEqual(h.response[2],0)

    def test_backpressure_holds_raw_seed_and_no_timeout_success(self):
        h=Harness(n=32);h.until(lambda:h.owner.ports()['seed_beat'] is not None)
        held=h.owner.ports()['seed_beat']
        for _ in range(11):
            h.cycle(seed_beat_ready=False);self.assertEqual(h.owner.ports()['seed_beat'],held)
        h.until(lambda:h.seed_ack is not None)
        for _ in range(11):h.cycle(seed_ack=None)
        self.assertIsNone(h.response)
        h.until(lambda:h.response is not None);self.assertIsNone(h.response[1])

    def test_error_completion_waits_owned_seed_ack_after_matrix_done(self):
        h=Harness(n=32);h.until(lambda:h.read is not None and h.read.kind=='prefix')
        req=h.seed_request
        self.assertTrue(h.owner.seed_outstanding)
        h.cycle(read_beat=m.ReadBeat(h.read.tag,(0,)*16,True,error=True),seed_ack=None)
        for _ in range(11):h.cycle(seed_ack=None)
        self.assertTrue(h.owner.group_done);self.assertIsNone(h.response)
        self.assertEqual(h.owner.state,'drain');self.assertTrue(h.owner.ports()['seed_ack_ready'])
        h.cycle(seed_ack=m.SeedAck(req,error=True));h.until(lambda:h.response is not None)
        self.assertTrue(h.response[1]);self.assertFalse(h.owner.seed_outstanding)
        self.assertEqual(h.owner.state,'locked');self.assertFalse(h.owner.ports()['job_ready'])

    def test_single_chunk_compatible_dense_never_uses_prefix(self):
        h=Harness(n=192,k=1536,split_k=2560);h.until(lambda:h.response is not None)
        self.assertEqual(h.response,(1,None,16*192*4))
        self.assertEqual(h.group_trace,[(0,0,5),(0,160,1)])
        self.assertEqual(h.owner.prefix_bytes,0);self.assertEqual(h.owner.completed_prefix_sweeps,0)
        self.assertFalse(h.prefix);self.assertFalse(h.seed_payload)
        self.assertFalse(any(r.kind=='prefix' for r in h.reads))
        self.assertEqual(sum(s.clear for s in h.steps),6)
        self.assertEqual(sum(s.last for s in h.steps),6)

    def test_single_chunk_large_n_reuses_down_workspace_without_prefix(self):
        h=Harness(n=8960,k=32,split_k=2560,workspace_extent=786432)
        h.until(lambda:h.response is not None)
        self.assertEqual(h.response,(1,None,16*8960*4));self.assertEqual(h.groups,56)
        self.assertEqual(h.workspace.extent,786432);self.assertEqual(h.owner.prefix_bytes,0)
        self.assertFalse(h.prefix);self.assertFalse(h.seed_payload)
        self.assertEqual(h.owner.accepted_steps,32*280)

    def test_full_k_native_bf16_activation_and_short_last_chunk(self):
        h=Harness(n=32,k=8960,split_k=2560);h.until(lambda:h.response is not None)
        self.assertIsNone(h.response[1]);self.assertEqual(h.owner.rmw_commits,16*8960)
        self.assertEqual([x[2] for x in h.step_trace if x[5]],[2559,5119,7679,8959])
        self.assertEqual([x[2] for x in h.step_trace if x[4]],[0])
        self.assertEqual(len([r for r in h.reads if r.kind=='a']),16*8960//32)

    def test_matrix_done_error_and_early_terminal_poison(self):
        for early in (False,True):
            h=Harness(n=32)
            h.until(lambda:h.owner.group_started and (early or h.owner.written==1),done=False)
            h.cycle(matrix_done=m.MatrixDone(h.job.tag,error=not early))
            h.until(lambda:h.response is not None)
            self.assertTrue(h.response[1]);self.assertFalse(h.dest)
            self.assertFalse(h.owner.prefix_valid);self.assertEqual(h.owner.state,'locked')

    def test_middle_prefix_preserves_finite_fp32_outside_bf16_domain(self):
        h=Harness(n=32,output_bf16=True)
        for chunk in range(3):
            h.until(lambda:h.owner.chunk_index==chunk and bool(h.results))
            values=tuple((0x7f7fffff,)*256 for _ in range(16))
            h.cycle(result=m.MatrixResult(0,values))
        h.until(lambda:h.response is not None)
        self.assertIsNone(h.response[1])
        self.assertTrue(all(word==0x7f7fffff for b in h.seed_payload for word in b.words))

    def test_workspace_and_full_output_count_validation(self):
        j=m.Job(k=8960,n=1536,a=0x1000000,b=0x2000000,dst=0x8000000)
        good=m.PrefixWorkspace(0x10000000,48*16384,7)
        j.validate();good.validate(j)
        for bad in (replace(good,split_k=2688),replace(good,extent=48*16384-64),replace(good,base=j.a),replace(good,generation=0)):
            with self.assertRaises(ValueError):bad.validate(j)
        with self.assertRaises(ValueError):replace(j,write_bytes=128*160*4).validate()

if __name__=='__main__':unittest.main()
