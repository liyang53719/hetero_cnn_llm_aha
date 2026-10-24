from pathlib import Path
import sys,importlib.util,hashlib,types
import argparse,unittest,json
parser=argparse.ArgumentParser();parser.add_argument('--source-root',required=True,type=Path);parser.add_argument('--owner-root',required=True,type=Path);parser.add_argument('--buffer-source',required=True,type=Path)
args,rest=parser.parse_known_args();ROOT=args.source_root.resolve(strict=True)
P=args.owner_root.resolve(strict=True)
S=ROOT/'candidates/qwen2_ordered_schedule'
HERE=Path(__file__).resolve(strict=True).parent
def load(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);sys.modules[n]=m;s.loader.exec_module(m);return m
pins=json.loads((HERE/'SOURCE_PINS.json').read_text())
for key,sha in pins['test_bootstrap'].items():
    kind,rel=key.split('/',1);path=(P if kind=='owner' else ROOT)/rel
    if hashlib.sha256(path.read_bytes()).hexdigest()!=sha:raise ValueError('test bootstrap drift '+key)
if hashlib.sha256(args.buffer_source.read_bytes()).hexdigest()!=pins['buffer_sha256']:raise ValueError('buffer drift')
sys.argv=[sys.argv[0],'--source-root',str(ROOT)]
f=load('_obs_fixture',P/'test_owner.py')
b=load('_obs_buffer',args.buffer_source.resolve(strict=True))
pkg=types.ModuleType('_obs');pkg.__path__=[str(HERE)];sys.modules['_obs']=pkg
mon=load('_obs.monitor',HERE/'monitor.py')

def setup(m=1,words=None):
    o,service,scalar,job=f.make(m,words=words)
    paths={
    'run':(o.packed_schedule.run,S/'schedule.py','ProductionQk16Schedule','run'),
    'work':(o.ordered_adapter.tick,S/'ordered_work.py','OrderedFoldAdapter','tick'),
    'consume':(f.w.OrderedFoldWork.consume,S/'ordered_work.py','OrderedFoldWork','consume'),
    'matrix':(o._matrix_step,P/'postimage/ffn_attention/attention_owner.py','AttentionOwner','_matrix_step'),
    'op':(o._op,P/'postimage/ffn_attention/attention_owner.py','AttentionOwner','_op'),
    'tick':(o.tick,P/'postimage/ffn_attention/attention_owner.py','AttentionOwner','tick'),
    'client':(f.prior.client.PackedClient.tick,ROOT/'candidates/qwen2_resident_matrix/attention_packed_owner/client.py','PackedClient','tick')}
    bindings={k:(fn,p,hashlib.sha256(p.read_bytes()).hexdigest(),cl,n) for k,(fn,p,cl,n) in paths.items()}
    return o,service,scalar,job,mon.Observation(o,m,b.PackedFields,bindings,ast_definition_test=True)

def complete(m=1):
    o,s,sc,j,obs=setup(m)
    with obs:
        d=f.Driver(o,j);d.until(lambda:o.state=='finish');d.step(response_ready=True)
    if obs.error:raise ValueError(obs.error)
    return obs,d

class Tests(unittest.TestCase):
    def test_m1_m2_complete_real_owner_control(self):
        for m in (1,2):
            obs,d=complete(m);r=obs.seal()
            self.assertEqual(r['packed_acks'],12*m);self.assertEqual(r['packed_done'],12*m)
            self.assertEqual(len(r['fields']),10)
            self.assertEqual(r['fields']['softmax_fp32']['identical_repeats'],7*12*m*(m+1)//2)
            self.assertEqual(r['execution_provenance'],'AST_DEFINITION_SOFTWARE_TEST_ONLY')
            self.assertEqual(len(d.writes),96*m)
    def test_speculative_is_not_committed(self):
        o,s,sc,j,obs=setup(2)
        with obs:
            d=f.Driver(o,j);d.until(lambda:o.state=='ordered_fold' and o.ordered_work.count==2 and o.ordered_work.state=='retire')
            a=obs.data.work[id(o.ordered_work)]
            self.assertEqual(len(a['scale']),2);self.assertEqual(a['retired'],0)
            self.assertEqual(obs.data.fields['scores_bf16']['observed'][2],0)
            with self.assertRaises(ValueError):obs.seal()
    def test_later_fault_cannot_complete_or_fake_prefix(self):
        o,s,sc,j,obs=setup(2,{16:0x7fc00000})
        with obs:
            d=f.Driver(o,j);d.until(lambda:o.state=='ordered_fold' and o.ordered_work.count==2 and o.ordered_work.key==1 and o.ordered_work.state=='retire')
            a=obs.data.work[id(o.ordered_work)]
            self.assertEqual(a['retired'],1);self.assertNotIn(1,a['scale'])
            d.until(lambda:o.state=='finish');d.step(response_ready=True)
        self.assertEqual(o.status,'Numerical')
        with self.assertRaises(ValueError):obs.seal()
    def test_no_terminal_ack_rejects(self):
        o,s,sc,j,obs=setup()
        with obs:
            d=f.Driver(o,j);d.until(lambda:o.state=='finish')
        with self.assertRaises(ValueError):obs.seal()
    def test_early_done_rejects(self):
        o,s,sc,j,obs=setup()
        with obs:
            d=f.Driver(o,j);d.ordered();tag=o.matrix_client.packed.tag
            s._done=f.prior.matrix.MatrixDone(tag.group,False,tag.ticket,tag.epoch)
            d.until(lambda:o.state=='finish');d.step(response_ready=True)
        with self.assertRaises(ValueError):obs.seal()
    def test_missing_intermediate_rejects(self):
        obs,_=complete();obs.data.fields['dot_parts']['observed'][0]=0
        with self.assertRaises(ValueError):obs.seal()
    def test_missing_pv_reuse_rejects(self):
        obs,_=complete();obs.data.fields['prob_bf16']['frequency'][0]=7
        with self.assertRaises(ValueError):obs.seal()
    def test_future_tail_cells_untouched(self):
        obs,_=complete(2);obs.seal()
        f0=obs.data.fields['scores_bf16'];self.assertEqual(f0['words'][1],b.SENTINEL)
        f0['words'][1]=0
        with self.assertRaises(ValueError):obs.seal()
    def test_duplicate_intermediate_rejects(self):
        obs,_=complete()
        with self.assertRaises(ValueError):obs.data.single('scores_bf16',(0,0,0),(0,))
    def test_duplicate_scale_rejects(self):
        data=mon.Fields(b.PackedFields(1));w=object();data.bind(w,0,0,0,1);data.scale(w,0,0,0,0)
        with self.assertRaises(ValueError):data.scale(w,0,0,0,0)
    def test_duplicate_commit_rejects(self):
        data=mon.Fields(b.PackedFields(1));w=object();data.bind(w,0,0,0,1);data.scale(w,0,0,0,0)
        r=types.SimpleNamespace(work=w,key=0,score=0,error=None);data.consume(w,r,True);data.commit(w,r,[0])
        with self.assertRaises(ValueError):data.commit(w,r,[0])
    def test_pv_order_and_duplicate_reject(self):
        data=mon.Fields(b.PackedFields(1))
        with self.assertRaises(ValueError):data.probability(0,0,0,16,0,0)
        data.probability(0,0,0,0,0,0)
        with self.assertRaises(ValueError):data.probability(0,0,0,0,0,0)
        with self.assertRaises(ValueError):data.probability(0,0,0,16,1,0)
    def test_source_hash_drift_reject(self):
        o,s,sc,j,obs=setup();fn,path,sha,cls,name=obs.specs['run']
        with self.assertRaises(ValueError):mon.bind(fn,path,'0'*64,cls,name,True)
    def test_ast_mode_cannot_claim_runtime_source(self):
        o,s,sc,j,obs=setup();fn,path,sha,cls,name=obs.specs['run']
        with self.assertRaises(ValueError):mon.bind(fn,path,sha,cls,name,False)
    def test_missing_ack_rejects(self):
        obs,_=complete();obs.data.acks-=1
        with self.assertRaises(ValueError):obs.seal()
    def test_actual_abort_drain_never_seals(self):
        o,s,sc,j,obs=setup()
        with obs:
            d=f.Driver(o,j);d.ordered();d.step(local_reset=True)
            d.until(lambda:o.state=='finish');d.step(response_ready=True)
        with self.assertRaises(ValueError):obs.seal()
    def test_duplicate_consume_rejects(self):
        data=mon.Fields(b.PackedFields(1));w=object();data.bind(w,0,0,0,1);data.scale(w,0,0,0,0)
        r=types.SimpleNamespace(work=w,key=0,score=0,error=None);data.consume(w,r,True)
        with self.assertRaises(ValueError):data.consume(w,r,True)
    def test_out_of_order_commit_rejects(self):
        data=mon.Fields(b.PackedFields(2));w=object();data.bind(w,0,1,0,2);data.scale(w,1,0,0,0)
        r=types.SimpleNamespace(work=w,key=1,score=0,error=None)
        with self.assertRaises(ValueError):data.consume(w,r,True)
    def test_unknown_binding_role_rejects(self):
        o,s,sc,j,obs=setup();specs=dict(obs.specs);specs.pop('consume')
        with self.assertRaises(ValueError):mon.Observation(o,1,b.PackedFields,specs,ast_definition_test=True)
    def test_deleted_field_rejects(self):
        obs,_=complete();del obs.data.fields['dot_parts']
        with self.assertRaises(ValueError):obs.seal()
    def test_shape_drift_rejects(self):
        obs,_=complete();obs.data.fields['dot_parts']['shape']=(192,)
        with self.assertRaises(ValueError):obs.seal()
    def test_buffer_extent_drift_rejects(self):
        obs,_=complete();obs.data.fields['dot_parts']['words'].pop()
        with self.assertRaises(ValueError):obs.seal()
    def test_observer_does_not_change_actual_control(self):
        for m in (1,2):
            o,s,sc,j=f.make(m);d=f.Driver(o,j);d.until(lambda:o.state=='finish');d.step(response_ready=True)
            obs,watched=complete(m);wo=watched.owner
            self.assertEqual(watched.writes,d.writes);self.assertEqual(wo.clock,o.clock)
            self.assertEqual(wo.scalar.calls,sc.calls);self.assertEqual(wo.matrix.counts,s.counts)
            self.assertEqual(wo.matrix.events,s.events)
            self.assertEqual(wo.ordered_adapter.events,o.ordered_adapter.events)
    def test_capture_failure_does_not_change_dut(self):
        baseline,d0=complete();o,s,sc,j,obs=setup()
        # Intentional malformed audit buffer, not DUT state or input mutation.
        obs.data.fields['dot_parts']['observed'][0]=1
        with obs:
            d=f.Driver(o,j);d.until(lambda:o.state=='finish');d.step(response_ready=True)
        self.assertIsNotNone(obs.error)
        self.assertEqual(o.status,None);self.assertEqual(d.writes,d0.writes)
        self.assertEqual(o.clock,d0.owner.clock);self.assertEqual(s.events,d0.owner.matrix.events)
        self.assertEqual(s.counts,d0.owner.matrix.counts);self.assertEqual(sc.calls,d0.owner.scalar.calls)
        with self.assertRaises(ValueError):obs.seal()
    def test_retired_result_objects_are_not_retained(self):
        obs,_=complete(2);self.assertFalse(obs.data.work);self.assertFalse(obs.tag_work)
        self.assertEqual(len(obs.data.completed),24)
        self.assertTrue(all('object' not in a and 'scale' not in a for a in obs.data.completed))
    def test_no_monitor_leak(self):
        obs,_=complete();self.assertIsNone(obs.tool)

if __name__=='__main__':unittest.main(argv=[sys.argv[0],*rest])
