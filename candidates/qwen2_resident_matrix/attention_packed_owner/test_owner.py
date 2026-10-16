"""Bounded original-owner physical IO tests; native library is explicit opt-in."""
import ctypes,hashlib,importlib.util,json,os,subprocess,sys,tempfile,unittest,time
from pathlib import Path
from unittest.mock import patch
from . import prepare
from .schedule import PackedSchedule
from .client import PackedConsumerAck
from .bridge import ScratchBridge
from ..attention_packed_native.check_native import load_service
from ..attention_matrix_batch.test_model import ExactScalar,fixture
from ..attention_bank_multirow.oracle import Oracle
from ..ffn_public.prefix_owners import Job,MemoryResponse

class Scalar(ExactScalar):
    def acquire(self,owner):
        if self.client is not None:return False
        self.client=owner;return True
    def release(self,owner):
        if self.client is not owner:raise ValueError('scalar owner')
        self.client=None

def owner_class(root,matrix_module):
    name='candidates.qwen2_resident_matrix.ffn_attention.attention_owner'
    spec=importlib.util.spec_from_file_location(name,root/prepare.TARGETS[0]);m=importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules,{"candidates.qwen2_resident_matrix.ffn_attention.matrix_service":matrix_module}):spec.loader.exec_module(m)
    name2='candidates.qwen2_resident_matrix.official_bf16.owners'
    with patch.dict(sys.modules,{name:m}):
        spec=importlib.util.spec_from_file_location(name2,root/prepare.TARGETS[1]);n=importlib.util.module_from_spec(spec);spec.loader.exec_module(n)
    return n.OfficialAttentionOwner

def execute(root,libpath,rows,enabled,*,stalls=False,fault=None,reuse=None):
    if reuse is None:
        m=load_service(root);lib=m.configure_library(ctypes.CDLL(str(libpath)));lib.td_reset();matrix=m.MatrixService(lib)
        cls=owner_class(root,m);o=cls(matrix,Scalar(),packed_schedule=PackedSchedule() if enabled else None)
        bridge=ScratchBridge() if enabled else None
    else:o,bridge=reuse
    initial_edges=bridge.edges if bridge else 0
    data=fixture(rows)
    if fault=='selected_overflow':data=((0x7f7f0000,)*len(data[0]),(0x7f7f0000,)*len(data[1]),data[2])
    bases=(0x100000,0x200000,0x300000);dst=0x400000
    memory={base+4*i:x for base,words in zip(bases,data) for i,x in enumerate(words)}
    j=Job('Attention',0x10001,bases[0],bases[1],dst,rows,1536,128,rows*1536*4,c=bases[2])
    pending=None;pending_write=None;terminal=None;held=0;reads=[];writes=[];injected=False;scores={};delay=0
    for cycle in range(20000):
        p=o.ports();bp=bridge.ports() if bridge else dict(ready=False,response=None)
        response=pending if not stalls or cycle%3 else None
        if pending is not None and not injected and fault in ('read_error','foreign_ddr'):
            response=MemoryResponse(pending.tag if fault=='read_error' else pending.tag+1,pending.data,error=fault=='read_error');injected=True
        local_reset=False
        if pending_write is not None and not injected and fault in ('output_error','foreign_output','late_output_ack'):
            injected=True
            if fault=='late_output_ack':local_reset=True;delay=5;response=None
            else:response=MemoryResponse(pending.tag if fault=='output_error' else pending.tag+1,None,error=fault=='output_error')
        if delay:response=None;delay-=1
        scratch_ready=bp['ready'] and (not stalls or cycle%4!=0)
        if not injected:
            if fault and fault.startswith('unaccepted_') and p['scratch'] is not None:
                _,operation,ready_mode=fault.split('_')
                if p['scratch'].operation==operation:
                    local_reset=True;injected=True;scratch_ready=ready_mode=='ready'
            active=bridge.active if bridge else None
            if ((fault=='scratch_write_pending' and active is not None and active.operation=='write') or
                (fault=='scratch_read_pending' and active is not None and active.operation=='read') or
                (fault=='held_result_ack' and type(p['matrix']) is PackedConsumerAck) or
                (fault=='scratch_write_ack' and bp['response'] is not None and bp['response'].action.operation=='write')):
                local_reset=True;injected=True
        terminal_ready=p['response'] is not None and held>=3
        out=o.tick(job=j if cycle==0 else None,memory_ready=not stalls or cycle%4!=0,memory_response=response,
                   scratch_ready=scratch_ready,scratch_response=bp['response'],
                   response_ready=terminal_ready,local_reset=local_reset,matrix_request_ready=not stalls or cycle%3!=0,
                   matrix_result_ready=not stalls or cycle%4!=0,service_result_ready=not stalls or cycle%3!=0,
                   service_done_ready=not stalls or cycle%4!=0)
        if bridge:
            a=p['scratch'] if out['scratch_fire'] else None
            if a is not None and a.operation=='release' and (o.memory_pending or not o.matrix_client.ports()['drained']):raise AssertionError('release before complete accepted debt drain')
            if a is not None and a.operation=='write' and a.line<4144:
                scores[(a.query,a.kv_head,(a.line-4096)//8)]=a.words[:a.query+1]
            bridge.tick(action=a,response_ready=out['scratch_response_fire'],abort=o.poison)
            if bridge.edges!=initial_edges+cycle+1:raise AssertionError('one parent edge')
        if out['memory_response_fire']:
            if pending.tag!=response.tag:raise AssertionError('memory ACK tag')
            if pending_write is not None and not response.error:
                address,words=pending_write
                for i,x in enumerate(words):memory[address+4*i]=x
            pending=None;pending_write=None
        if out['memory_fire']:
            q=p['memory'];reads.append(q.address) if not q.write else writes.append(q.address)
            if pending is not None:raise AssertionError('two memory debts')
            if q.write:
                import struct
                words=struct.unpack('<16I',q.data)
                pending_write=(q.address,words)
                pending=MemoryResponse(q.tag,None)
            else:pending=MemoryResponse(q.tag,tuple(memory[q.address+4*i] for i in range(16)))
        if p['response'] is not None:
            if terminal is None:terminal=p['response']
            if p['response'] is not terminal:raise AssertionError('held terminal changed')
            held+=1
        if out['response_fire']:
            if fault is None and terminal.status is not None:raise AssertionError(('owner failure',terminal,o.detail))
            if fault is not None and terminal.status is None:raise AssertionError('fault falsely succeeded')
            if bridge and (bridge.parent.raw.owner is not None or not bridge.parent.raw.drained):raise AssertionError('early terminal')
            if fault=='output_error' and any(dst<=address<dst+rows*1536*4 for address in memory):raise AssertionError('failed output ACK published data')
            score_words=tuple(x for token in range(rows) for head in range(12) for x in scores.get((token,head//6,head%6),()))
            output=tuple(memory[dst+4*i] for i in range(rows*1536)) if fault is None else None
            return output,o,bridge,reads,writes,score_words
    raise AssertionError(('owner did not terminate',o.state,o.detail, o.matrix_client.state if o.matrix_client else None))

class OwnerTests(unittest.TestCase):
    def test_schedule_ownership_and_context_types(self):
        from .protocol import ScratchAction
        schedule=PackedSchedule();owner=object();schedule.bind(owner);schedule.bind(owner)
        with self.assertRaises(ValueError):schedule.bind(object())
        self.assertFalse(ScratchAction(True,'write',1,0,0,4096,(0,)*16).valid())
        self.assertFalse(ScratchAction(1,'begin',1,0,0,False).valid())
        self.assertFalse(ScratchAction(1,'write',1,0,0,4192,(0,)*16).valid())
    def test_bridge_foreign_context_and_written_validity(self):
        from .protocol import ScratchAction
        b=ScratchBridge();a=ScratchAction(1,'acquire',0,0,0)
        self.assertTrue(b.tick(action=a)['accepted']);b.tick(response_ready=True)
        begin=ScratchAction(2,'begin',1,0,0);b.tick(action=begin);b.tick(response_ready=True)
        with self.assertRaises(ValueError):b.tick(action=ScratchAction(3,'read',1,0,0,4096))
        a=ScratchAction(4,'write',1,0,0,4096,(0,)*16)
        b.tick(action=a);self.assertNotIn(4096,b.valid)
        b.tick();self.assertNotIn(4096,b.valid)
        b.tick();self.assertIn(4096,b.valid);b.tick(response_ready=True)
        with self.assertRaises(ValueError):b.tick(action=ScratchAction(5,'read',2,0,0,4096))

    def test_source_projection(self):
        with tempfile.TemporaryDirectory() as t:
            root=prepare.compose(Path(t)/'source')
            code="import sys;sys.path.insert(0,sys.argv[1]);from candidates.qwen2_resident_matrix.attention_packed_owner import hooks,bridge;from candidates.qwen2_resident_matrix.official_bf16.owners import OfficialAttentionOwner;from pathlib import Path;assert Path(hooks.__file__).is_relative_to(sys.argv[1]);assert Path(bridge.__file__).is_relative_to(sys.argv[1])"
            imports=subprocess.run([sys.executable,'-I','-c',code,str(root)],capture_output=True,text=True)
            self.assertEqual(imports.returncode,0,imports.stderr)
            result=subprocess.run(['patch','--batch','--fuzz=0','-R','-p1','-i',str(prepare.HERE/'owner.patch')],cwd=root,capture_output=True)
            self.assertEqual(result.returncode,0)
            for n in prepare.TARGETS:self.assertEqual((root/n).read_bytes(),(prepare.ROOT/n).read_bytes())
    def test_native_m1_m2_original_owner(self):
        env=os.environ.get('PACKED_OWNER_NATIVE_LIBRARY')
        if not env:self.skipTest('explicit existing native library required')
        library=Path(env)
        self.assertEqual(hashlib.sha256(library.read_bytes()).hexdigest(),'1ba0b6aa738dd4a409b91adf93cafbcec63fc3c0df1590f9b91cf8f223f54811')
        before=prepare.snapshot();started=time.monotonic();reports=[]
        with tempfile.TemporaryDirectory() as t:
            root=prepare.compose(Path(t)/'source')
            for rows in (1,2):
                oracle=Oracle(rows,*fixture(rows));expected=oracle.run()
                baseline,old,_,_,_,_=execute(root,library,rows,False)
                actual,o,b,reads,writes,scores=execute(root,library,rows,True,stalls=True)
                self.assertEqual(baseline,expected);self.assertEqual(actual,expected);self.assertEqual(scores,oracle.scores()[1])
                self.assertEqual(o.__class__.__name__,'OfficialAttentionOwner');self.assertIs(o.matrix.owner,None)
                self.assertEqual(len(writes),rows*96);self.assertEqual(o.ack_bytes,rows*1536*4)
                self.assertIs(b.banks,b.parent.owner.a_banks)
                self.assertEqual(o.matrix.counts['normal_steps'],96*rows+rows*(rows+1))
                self.assertEqual(o.matrix.counts['normal_groups'],14*rows)
                self.assertEqual(o.counts['matrix_results'],14*rows)
                self.assertEqual(o.counts['packed_consumer_retirements'],14*rows)
                self.assertEqual(o.counts['packed_nonfinal_accept_completions'],o.matrix.counts['normal_steps']-14*rows)
                self.assertEqual(old.matrix.counts['normal_steps'],96*rows*(rows+1))
                self.assertTrue(all(address%64==0 for address in reads+writes))
                def words_hash(words):return hashlib.sha256(b''.join(x.to_bytes(4,'little') for x in words)).hexdigest()
                reports.append(dict(rows=rows,output_sha256=words_hash(actual),scores_sha256=words_hash(scores),owner_type=o.__class__.__name__,
                    parent_edges=b.edges,owner_edges=o.clock,one_parent_edge_per_owner_edge=b.edges==o.clock,
                    owner_counts=dict(o.counts),matrix_counts=dict(o.matrix.counts),all_enabled_fmas=o.executed_macs,useful_selected_fmas=o.useful_macs,
                    ddr_reads=len(reads),ddr_writes=len(writes),output_ack_bytes=o.ack_bytes,
                    same_parent_banks=b.banks is b.parent.owner.a_banks,terminal_after_bank_release=b.parent.raw.owner is None))
        prepare.check();self.assertEqual(prepare.snapshot(),before)
        receipt=os.environ.get('PACKED_OWNER_RECEIPT')
        if receipt:
            Path(receipt).write_text(json.dumps(dict(status='PASS_BOUNDED_ORIGINAL_PACKED_OWNER',cases=reports,source_sha256=before,
                library_sha256=hashlib.sha256(library.read_bytes()).hexdigest(),reused_qualified_library=True,new_compilation=False,
                elapsed_seconds=time.monotonic()-started,full_public_admission=False,rtl_execution=False),indent=2,sort_keys=True)+'\n')


    def test_native_faults_drain_active_lease(self):
        env=os.environ.get('PACKED_OWNER_NATIVE_LIBRARY')
        if not env:self.skipTest('explicit existing native library required')
        with tempfile.TemporaryDirectory() as t:
            root=prepare.compose(Path(t)/'source')
            for fault in ('read_error','foreign_ddr','selected_overflow','scratch_write_pending','scratch_read_pending','held_result_ack','scratch_write_ack','output_error','foreign_output','late_output_ack',*(f'unaccepted_{op}_{ready}' for op in ('acquire','begin','write') for ready in ('ready','blocked'))):
                _,o,b,_,writes,_=execute(root,Path(env),1,True,stalls=True,fault=fault)
                self.assertTrue(o.poison);self.assertEqual(o.state,'locked')
                self.assertFalse(o.scratch_leased);self.assertFalse(o.scratch_pending)
                self.assertIsNone(b.parent.raw.owner);self.assertTrue(b.parent.raw.drained)
                if fault in ('output_error','foreign_output','late_output_ack'):
                    self.assertEqual(len(writes),1);self.assertEqual(o.ack_bytes,0 if fault=='output_error' else 64)
                else:self.assertEqual(writes,[])
                if fault=='selected_overflow':self.assertEqual(o.status,'Numerical')


    def test_two_jobs_and_idle_reset_reuse(self):
        env=os.environ.get('PACKED_OWNER_NATIVE_LIBRARY')
        if not env:self.skipTest('explicit existing native library required')
        with tempfile.TemporaryDirectory() as t:
            root=prepare.compose(Path(t)/'source');lib=Path(env)
            expected,o,b,_,_,_=execute(root,lib,1,True)
            first_serial=b.last_serial
            actual,o,b,_,_,_=execute(root,lib,1,True,reuse=(o,b));self.assertEqual(actual,expected);self.assertGreater(b.last_serial,first_serial)
            selected=o.packed_schedule;o.tick(reset=True);b.tick();self.assertIs(o.packed_schedule,selected)
            actual,o,b,_,_,_=execute(root,lib,1,True,reuse=(o,b));self.assertEqual(actual,expected)

if __name__=='__main__':unittest.main()
