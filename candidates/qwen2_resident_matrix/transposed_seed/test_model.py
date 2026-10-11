"""Bounded physical-prefix control checks; no retained RTL arithmetic claim."""
import importlib.util
from pathlib import Path
import sys
import unittest
from dataclasses import replace

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);sys.modules[name]=mod;spec.loader.exec_module(mod);return mod

m=load('seed_owner_model',HERE/'model.py')
frozen=load('frozen_seed_protocol',HERE.parent/'seed_protocol_model.py')
oldtests=load('old_owner_model_tests',HERE.parent/'transposed_owner/test_model.py')
# Execute all inherited old owner tests against the NEW default-disabled model.
oldtests.model=m
for name in ('Job','ReadBeat','MatrixResult','MatrixDone','WriteAck'):setattr(oldtests,name,getattr(m,name))


class Harness:
    def __init__(self,n=160,output_bf16=False,m_rows=16):
        self.job=m.Job(m=m_rows,k=256,n=n,output_bf16=output_bf16)
        self.workspace=m.PrefixWorkspace(0x10000000,n//32*16384,7,128)
        self.owner=m.DenseOwnerModel(self.workspace);self.owner.tick(job=self.job)
        self.read=self.write=self.ack=self.seed_ack=None
        self.results=[];self.steps=[];self.prefix={};self.dest={};self.pending=[]
        self.seed_payload=[];self.response=None;self.groups=0;self.reads=[]

    def cycle(self,done=True,ack=True,**kw):
        o=self.owner;p=o.ports();args={}
        if self.read:
            cmd=self.read
            if cmd.kind=='prefix':
                assert o.prefix_valid and o.prefix_bytes==(o.n_base//32+o.contexts)*16384
                words=self.prefix[cmd.address]
            else:words=(0x3f80,)*(32 if (self.job.activation_bf16 if cmd.kind=='a' else self.job.weight_bf16) else 16)
            args['read_beat']=m.ReadBeat(cmd.tag,words,True)
        if self.results:args['result']=self.results[0]
        if done and o.group_started and not o.group_done and (o.error or (o.group_accepted_steps==(o.chunk_end-o.chunk_start)*o.contexts and o.results_received==o.contexts)):
            args['matrix_done']=m.MatrixDone(self.job.tag,bool(o.error))
        if ack and self.ack:args['write_ack']=self.ack
        if self.seed_ack:args['seed_ack']=self.seed_ack
        args.update(kw);e=o.tick(**args)
        if e['read_fire']:self.read=None
        if e['read_command_fire']:self.read=e['read_command'];self.reads.append(self.read)
        if e['group_fire']:self.groups+=1
        if e['step_fire']:
            s=e['step'];self.steps.append(s)
            if s.last:
                # Finite opaque physical tokens exercise physical save order.
                physical=tuple(tuple(0x3f000000+r*256+c for c in range(256)) for r in range(16))
                self.results.append(m.MatrixResult(s.context,physical))
        if e['result_fire']:self.results.pop(0)
        if e['write_command_fire']:self.write=(e['write_command'],0);self.pending=[]
        if e['write_data_fire']:
            cmd,i=self.write;self.pending.append((cmd.address+64*i,e['write_data'].words));self.write=(cmd,i+1)
            if e['write_data'].last:self.ack=m.WriteAck(cmd.tag,nbytes=cmd.beats*64)
        if e['write_ack_fire']:
            if not args['write_ack'].error and args['write_ack'].tag==self.write[0].tag:
                for addr,words in self.pending:
                    (self.prefix if self.workspace.base<=addr<self.workspace.base+self.workspace.extent else self.dest)[addr]=words
            self.ack=self.write=None;self.pending=[]
        if e['seed_beat_fire']:
            b=e['seed_beat'];self.seed_payload.append(b)
            if b.last:self.seed_ack=m.SeedAck(b.request)
        if e['seed_ack_fire']:self.seed_ack=None
        if e['response_fire']:self.response=e['response']
        return e

    def until(self,predicate,**kw):
        for _ in range(200000):
            if predicate():return
            self.cycle(**kw)
        raise AssertionError((self.owner.state,self.owner.error,self.owner.seed_state))


class PrefixTests(unittest.TestCase):
    def test_physical_dma_permutation(self):
        self.assertEqual(set(m.prefix_ddr_beat(i) for i in range(256)),set(range(256)))
        for i in range(256):
            s,q=divmod(i,32);offset=m.prefix_ddr_beat(i)*16
            self.assertEqual(offset,(q//2)*256+s*32+(q%2)*16)

    def test_all_five_save_restore_and_increasing_global_k(self):
        h=Harness();h.until(lambda:h.response is not None)
        self.assertEqual(h.response,(1,None,16*160*4));self.assertEqual(h.groups,2)
        self.assertEqual(len(h.prefix),1280);self.assertEqual(len(h.seed_payload),1280)
        self.assertEqual(h.owner.prefix_bytes,81920)
        for ctx in range(5):
            steps=[s for s in h.steps if s.context==ctx]
            self.assertEqual([s.k for s in steps],list(range(256)))
            self.assertEqual([s.k for s in steps if s.clear],[0])
            self.assertEqual([s.k for s in steps if s.last],[127,255])
        for b in h.seed_payload:
            ddr=h.workspace.base+b.request.context*16384+m.prefix_ddr_beat(b.index)*64
            self.assertEqual(b.words,h.prefix[ddr])

    def test_last_fifth_prefix_ack_error_never_publishes_or_restores(self):
        h=Harness();h.until(lambda:h.owner.written==4 and h.owner.write_prefix_index==255 and h.ack is not None)
        h.cycle(write_ack=m.WriteAck(h.ack.tag,error=True))
        h.until(lambda:h.response is not None)
        self.assertTrue(h.owner.error);self.assertFalse(h.owner.prefix_valid)
        self.assertEqual(h.groups,1);self.assertFalse(h.dest);self.assertFalse(h.seed_payload)
        self.assertFalse(any(x.kind=='prefix' for x in h.reads))

    def test_complete_prefix_ack_waits_matrix_done(self):
        h=Harness();h.until(lambda:h.owner.written==5,done=False)
        self.assertEqual(len(h.prefix),1280);self.assertFalse(h.owner.prefix_valid)
        for _ in range(9):h.cycle(done=False)
        self.assertEqual(h.groups,1);self.assertFalse(h.seed_payload)
        h.until(lambda:h.response is not None)
        self.assertEqual(h.groups,2)

    def test_mid_seed_read_failure_drains_and_locks(self):
        h=Harness();h.until(lambda:h.owner.restoring and len(h.seed_payload)==19 and h.read is not None)
        h.cycle(read_beat=m.ReadBeat(h.read.tag,(0,)*16,True,error=True))
        h.until(lambda:h.response is not None)
        self.assertTrue(h.owner.error);self.assertFalse(h.dest);self.assertEqual(h.owner.state,'locked')
        self.assertEqual(max(s.k for s in h.steps),127)

    def test_wrong_prefix_terminal_retires_obligation(self):
        for change in ('tag','last','nan'):
            with self.subTest(change=change):
                h=Harness(n=32);h.until(lambda:h.read is not None and h.read.kind=='prefix')
                beat=m.ReadBeat(h.read.tag+(change=='tag'),(0x7fc00000 if change=='nan' else 0,)*16,change!='last')
                h.cycle(read_beat=beat);self.assertIsNone(h.owner.read_active)
                h.until(lambda:h.response is not None);self.assertFalse(h.dest)

    def test_prefix_checks_all_physical_cells_even_m16_padding(self):
        h=Harness(n=32);h.until(lambda:bool(h.results))
        rows=[list(row) for row in h.results[0].value];rows[0][127]=0x7fc00000
        h.cycle(result=m.MatrixResult(0,tuple(map(tuple,rows))))
        h.until(lambda:h.response is not None)
        self.assertTrue(h.owner.error);self.assertFalse(h.prefix);self.assertFalse(h.dest)

    def test_prefix_finite_domain_ignores_final_bf16_threshold(self):
        h=Harness(n=32,output_bf16=True);h.until(lambda:bool(h.results))
        values=tuple((0x7f7fffff,)*256 for _ in range(16))
        h.cycle(result=m.MatrixResult(0,values))
        h.until(lambda:h.response is not None)
        self.assertIsNone(h.owner.error);self.assertEqual(len(h.prefix),256)
        self.assertTrue(all(word==0x7f7fffff for beat in h.seed_payload for word in beat.words))
        self.assertTrue(h.dest)

    def test_missing_seed_ack_or_dma_response_never_succeeds(self):
        h=Harness(n=32);h.until(lambda:h.seed_ack is not None)
        for _ in range(20):h.cycle(seed_ack=None)
        self.assertIsNone(h.response);self.assertFalse(h.dest)
        h=Harness(n=32);h.until(lambda:h.read is not None and h.read.kind=='prefix')
        for _ in range(20):h.cycle(read_beat=None)
        self.assertIsNone(h.response);self.assertFalse(h.dest)

    def test_workspace_validation_and_snapshot(self):
        j=m.Job(k=256)
        valid=m.PrefixWorkspace(0x10000000,16384,1,128)
        for w in (replace(valid,base=j.a),replace(valid,extent=16320),replace(valid,generation=0),replace(valid,split_k=64),replace(valid,base=2**56-64)):
            with self.subTest(w=w):
                with self.assertRaises(ValueError):w.validate(j)

    def test_seed_ack_backpressure_and_late_duplicate(self):
        h=Harness(n=32);h.until(lambda:h.seed_ack is not None)
        request=h.seed_ack
        h.cycle(seed_ack=m.SeedAck(replace(request.request,generation=99)))
        h.until(lambda:h.response is not None);self.assertFalse(h.dest)
        o=m.DenseOwnerModel();o.tick(seed_ack=request)
        self.assertTrue(o.error);self.assertFalse(o.ports()['job_ready'])

    def test_reset_requires_coordinated_backend_reset(self):
        h=Harness(n=32);h.until(lambda:len(h.seed_payload)==7)
        h.cycle(local_reset=True);h.until(lambda:h.response is not None)
        self.assertFalse(h.dest);self.assertEqual(h.owner.state,'locked')
        h.owner.tick(coordinated_reset=True)
        self.assertTrue(h.owner.ports()['job_ready']);self.assertFalse(h.owner.prefix_valid)


class ServiceLifecycleTests(unittest.TestCase):
    def seed(self,c,ctx,word=0):
        req=frozen.Request(group_tag=c.group_tag,group_sequence=c.group_sequence,context=ctx)
        self.assertTrue(c.begin(req));self.assertTrue(c.reserve())
        for i in range(256):self.assertTrue(c.beat(frozen.Beat.make(req,i,(word,)*16,i==255)))
        self.assertTrue(c.commit())
        for s in range(8):self.assertTrue(c.leaf_ack(s,frozen.Ack.make(req)))
        return req

    def test_seeded_first_step_requires_clear_false(self):
        c=frozen.SeedControllerModel();self.seed(c,0);self.assertTrue(c.take_response())
        self.assertFalse(c.first_step(0,True));self.assertTrue(c.first_step(0,False))
        self.assertTrue(c.first_step(1,True))

    def test_finite_fp32_zero_subnormal_and_large_prefix_allowed(self):
        for word in (0,0x80000000,1,0x80000001,0x7f7fffff,0xff7fffff):
            with self.subTest(word=word):
                c=frozen.SeedControllerModel();self.seed(c,0,word);c.take_response()
                self.assertEqual(set(c.banks[0]),{word})

    def test_held_success_ack_abort_suppresses_commit(self):
        c=frozen.SeedControllerModel();self.seed(c,0)
        offered=c.response();self.assertFalse(offered.error)
        self.assertFalse(c.take_response(ready=False));c.observe(abort=True)
        self.assertEqual(c.response(),offered);self.assertTrue(c.poison)
        self.assertTrue(c.take_response(abort=True));self.assertEqual(c.seeded,0)
        self.assertFalse(any(c.leaf_valid[0]))

    def test_finish_must_close_seeded_never_issued_context(self):
        service=m.MatrixSeedLifecycleModel()
        for ctx in range(5):self.assertTrue(service.commit_seed(ctx))
        for ctx in range(3):self.assertTrue(service.issue(ctx,False,last=True))
        self.assertFalse(service.issue(3,False,last=True,finish=True))
        self.assertEqual(service.accepted_steps,3);self.assertTrue(service.poison)
        service=m.MatrixSeedLifecycleModel()
        for ctx in range(5):self.assertTrue(service.commit_seed(ctx))
        for ctx in range(5):self.assertTrue(service.issue(ctx,False,last=True,finish=ctx==4))
        self.assertTrue(service.finished)

    def test_seed_mode_and_first_issue_admission(self):
        for options in ({'transposed':False},{'opcode':0x21},{'mask':127}):
            service=m.MatrixSeedLifecycleModel(**options)
            self.assertFalse(service.commit_seed(0));self.assertTrue(service.poison)
        service=m.MatrixSeedLifecycleModel()
        self.assertFalse(service.issue(0,True,begin_valid=True));self.assertEqual(service.accepted_steps,0)
        self.assertTrue(service.commit_seed(0));self.assertFalse(service.issue(0,True))
        self.assertEqual(service.accepted_steps,0)

    def test_busy_begin_concurrent_issue_and_late_ack_poison(self):
        c=frozen.SeedControllerModel();c.quiescent=False
        self.assertTrue(c.begin(frozen.Request()));self.assertTrue(c.poison)
        c=frozen.SeedControllerModel();c.unexpected_ack();self.assertTrue(c.poison)
        source=(HERE/'service_seed.patch').read_text()
        self.assertIn('&& !seedBlocks && !seedPoison',source)
        self.assertIn('val needsClock=if(enableAccumulatorSeed){seedBlocks || seedPoison',source)
        self.assertIn('!tags.io.deq.valid && !values.io.deq.valid',source)
        self.assertIn('arithmetic_busy_o.get.orR',source)


def load_tests(loader,tests,pattern):
    tests.addTests(loader.loadTestsFromModule(oldtests));return tests

if __name__=='__main__':unittest.main()
