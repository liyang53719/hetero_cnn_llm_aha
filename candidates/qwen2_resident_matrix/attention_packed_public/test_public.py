"""Cold admission/source tests plus opt-in actual M1/M2 Public transport."""
import ctypes,hashlib,json,os,struct,subprocess,sys,tempfile,unittest
from pathlib import Path
from . import prepare
LIB_SHA='1ba0b6aa738dd4a409b91adf93cafbcec63fc3c0df1590f9b91cf8f223f54811'

def actual_case(library,rows,*,fault=None,stalls=False):
    # Invoked in an isolated composed tree: all classes have original canonical
    # module identities, with no replacement class or sys.modules shim.
    from ..ffn_attention.matrix_service import MatrixService,configure_library
    from ..official_bf16.owners import OfficialAttentionOwner
    from ..dense_block_reduce.matrix_binding import ProfiledMatrixService
    from ..dense_block_reduce.profile import QWEN2_QKV_PROFILE
    from ..ffn_public.prefix_owners import Job,MemoryResponse
    from ..attention_packed_owner.test_owner import Scalar
    from ..attention_matrix_batch.test_model import fixture
    from ..attention_bank_multirow.oracle import Oracle
    from ..attention_matrix_batch.test_model import source_definitions,_original_namespace
    from ..raw_kv_parent.model import ParentLoan
    from ..raw_kv_public.model import PublicKvTransport
    from .profile import PackedPublicProfile
    original=Path(__file__).with_name('original_owner.source')
    expected=json.loads((Path(__file__).with_name('pins.json')).read_bytes())['sources'][prepare.ORACLE_SOURCE]
    if hashlib.sha256(original.read_bytes()).hexdigest()!=expected:raise ValueError('original oracle source drift')
    namespace=dict(_original_namespace)
    source_definitions(original,('_attention',),namespace,class_name='OfficialAttentionOwner')
    class OriginalOracle(Oracle):
        _attention=namespace['_attention']
    if hashlib.sha256(Path(library).read_bytes()).hexdigest()!=LIB_SHA:raise ValueError('qualified library mismatch')
    lib=configure_library(ctypes.CDLL(library));lib.td_reset();matrix=ProfiledMatrixService(lib,QWEN2_QKV_PROFILE)
    owner=OfficialAttentionOwner(matrix,Scalar());parent=ParentLoan(enabled=True)
    data=fixture(rows);bases=(0x100000,0x200000,0x300000);dst=0x400000
    if fault=='selected_overflow':data=((0x7f7f0000,)*len(data[0]),(0x7f7f0000,)*len(data[1]),data[2])
    memory={base+4*i:x for base,words in zip(bases,data) for i,x in enumerate(words)}
    job=Job('Attention',0x10001,bases[0],bases[1],dst,rows,1536,128,rows*6144,c=bases[2])
    transport=PublicKvTransport(owner=owner,parent=parent,job=job,packed_profile=PackedPublicProfile())
    banks=parent.owner.a_banks;mux=transport.supply.scratch_mux
    pending=write=None;terminal=None;held=0;scores={};injected=False;reads=[];writes=[]
    for cycle in range(30000):
        p=transport.ports();op=owner.ports();response=pending if not stalls or cycle%3 else None
        abort=False
        if not injected:
            if pending is not None and fault=='foreign_ddr':
                response=MemoryResponse(pending.tag+1,pending.data);injected=True
            elif write is not None and fault=='output_error':
                response=MemoryResponse(pending.tag,None,True);injected=True
            elif fault=='scratch_abort' and mux.active is not None:
                abort=True;injected=True
        edge=transport.tick(job=job if cycle==0 else None,memory_ready=not stalls or cycle%4!=0,
             memory_response=response,response_ready=p['response'] is not None and held>=3,
             raw_ack_ready=not stalls or cycle%5!=0,abort=abort,
             matrix_request_ready=not stalls or cycle%3!=0,matrix_result_ready=not stalls or cycle%4!=0,
             service_result_ready=not stalls or cycle%3!=0,service_done_ready=not stalls or cycle%4!=0)
        if parent.owner.clock!=cycle+1 or mux.edges!=cycle+1:raise AssertionError('one original parent edge')
        if parent.raw.banks is not banks or parent.owner.a_banks is not banks:raise AssertionError('bank allocation changed')
        if edge['scratch_fire']:
            a=op['scratch']
            if a.operation=='write' and a.line<4144:scores[(a.query,a.kv_head,(a.line-4096)//8)]=a.words[:a.query+1]
        if edge['memory_response_fire']:
            if response is None or pending is None or response.tag!=pending.tag:raise AssertionError('foreign DDR retirement')
            if write is not None and not response.error:
                address,words=write
                for i,w in enumerate(words):memory[address+4*i]=w
            pending=write=None
        if edge['memory_fire']:
            q=edge['memory']
            if pending is not None:raise AssertionError('multiple external DDR debts')
            if q.write:
                writes.append(q.address);write=(q.address,struct.unpack('<16I',q.data));pending=MemoryResponse(q.tag,None)
            else:
                reads.append(q.address);pending=MemoryResponse(q.tag,struct.pack('<16I',*(memory[q.address+4*i] for i in range(16))))
        if p['response'] is not None:
            if terminal is None:terminal=p['response']
            if terminal is not p['response']:raise AssertionError('held terminal identity')
            if parent.raw.blocked or not parent.raw.drained or mux.leased or not mux.idle or pending is not None:raise AssertionError('premature transport terminal')
            held+=1
        if edge['response_fire']:
            if fault is None:
                if terminal.status is not None:raise AssertionError(('owner failure',owner.detail))
                actual=tuple(memory[dst+4*i] for i in range(rows*1536))
                oracle=OriginalOracle(rows,*data);expected=oracle.run()
                score=tuple(w for token in range(rows) for head in range(12) for w in scores[(token,head//6,head%6)])
                if actual!=expected or score!=oracle.scores()[1]:raise AssertionError('original numerical oracle mismatch')
                if transport.supply.counts['ddr_requests']!=32*rows or len(reads)!=128*rows:raise AssertionError('physical KV miss/Q request counts')
                if mux.counts['raw_requests']!=48*rows or mux.counts['raw_acks']!=48*rows:raise AssertionError('scratch traffic')
                digest=lambda x:hashlib.sha256(struct.pack('<'+'I'*len(x),*x)).hexdigest()
                return dict(rows=rows,output_sha256=digest(actual),scores_sha256=digest(score),
                    owner_edges=transport.ticks,parent_edges=parent.owner.clock,matrix=dict(matrix.counts),
                    kv=dict(transport.supply.counts),scratch=dict(mux.counts),ddr_reads=len(reads),ddr_writes=len(writes),
                    all_enabled_fmas=int(lib.matrix_normal_fmas()),owner_class=type(owner).__module__+'.'+type(owner).__name__)
            if terminal.status is None:raise AssertionError('false success after fault')
            if fault in ('selected_overflow','output_error') and any(dst<=a<dst+job.write_bytes for a in memory):raise AssertionError('bad output published')
            return dict(fault=fault,drained=True,failed=True,parent_edges=parent.owner.clock)
    raise AssertionError(('transport did not terminate',owner.state,owner.detail,transport.supply.state,mux.active,mux.response))

class PreparationTests(unittest.TestCase):
    def test_closed_composition_and_default_projection(self):
        from ..raw_kv_public import prepare as prior
        with tempfile.TemporaryDirectory() as d:
            out=prepare.compose(Path(d)/'source')
            self.assertEqual((out/prepare.ORACLE_COPY).read_bytes(),(prepare.ROOT/prepare.ORACLE_SOURCE).read_bytes())
            reverse=subprocess.run(['patch','--batch','--fuzz=0','-R','-p1','-i',str(prepare.HERE/'public.patch')],cwd=out,capture_output=True)
            self.assertEqual(reverse.returncode,0,reverse.stderr)
            base=Path(d)/'prior';prior.prepare(base)
            for n in prior.TARGETS:self.assertEqual((out/n).read_bytes(),(base/n).read_bytes())
            for n in prepare.TARGETS[2:]:self.assertEqual((out/n).read_bytes(),(prepare.ROOT/n).read_bytes())
    def test_full_numeric_closed(self):
        from .profile import authorize_full_numeric
        for n in (1,2,16,128):
            with self.assertRaises(ValueError):authorize_full_numeric(rows=n)

    def test_isolated_runtime_import_closure_and_canonical_admission(self):
        with tempfile.TemporaryDirectory() as d:
            root=prepare.compose(Path(d)/'source')
            code="""import sys
sys.path.insert(0,sys.argv[1])
from types import SimpleNamespace
from candidates.qwen2_resident_matrix.attention_packed_public.profile import PackedPublicProfile
from candidates.qwen2_resident_matrix.raw_kv_public.model import PublicKvTransport
from candidates.qwen2_resident_matrix.raw_kv_parent.model import ParentLoan
from candidates.qwen2_resident_matrix.ffn_attention.matrix_service import MatrixService
from candidates.qwen2_resident_matrix.dense_block_reduce.matrix_binding import ProfiledMatrixService
from candidates.qwen2_resident_matrix.official_bf16.owners import OfficialAttentionOwner
from candidates.qwen2_resident_matrix.ffn_public.prefix_owners import Job
from candidates.qwen2_resident_matrix.attention_packed_owner.test_owner import Scalar
# Exact class, cold control fields only. No native library is loaded or used.
m=ProfiledMatrixService.__new__(ProfiledMatrixService);m.owner=None;m.lib=SimpleNamespace(matrix_state=lambda:0)
o=OfficialAttentionOwner(m,Scalar());p=ParentLoan(enabled=True);raw=p.raw
for rows,version in ((16,1),(128,1),(True,1),(1,True),(1,2)):
 j=Job('Attention',65537,1048576,2097152,4194304,rows,1536,128,int(rows)*6144,c=3145728)
 try: PublicKvTransport(owner=o,parent=p,job=j,packed_profile=PackedPublicProfile(version))
 except ValueError: pass
 else: raise AssertionError('invalid explicit profile admitted')
 assert p.raw is raw and o.packed_schedule is None and p.owner.clock==0
j=Job('Attention',65537,1048576,2097152,4194304,1,1536,128,6144,c=3145728)
t=PublicKvTransport(owner=o,parent=p,job=j)
assert t.packed_profile is None and t.supply.scratch_mux is None and p.raw is raw
assert t.check_packed_binding() is None
assert all(str(root.__file__).startswith(sys.argv[1]) for root in (sys.modules[PublicKvTransport.__module__],sys.modules[OfficialAttentionOwner.__module__],sys.modules[MatrixService.__module__]))
"""
            r=subprocess.run([sys.executable,'-I','-c',code,str(root)],capture_output=True,text=True,timeout=5)
            self.assertEqual(r.returncode,0,r.stderr)

    def test_helper_source_drift_and_generated_overlay_fail_closed(self):
        from unittest.mock import patch
        import shutil
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'copy';root.mkdir()
            for n in (*prepare.inputs(),*prepare.OWN,prepare.PREFIX+'pins.json'):
                q=root/n;q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(prepare.ROOT/n,q)
            name='candidates/qwen2_resident_matrix/raw_kv_attention/numeric_bridge.py'
            with (root/name).open('a') as f:f.write('\n# drift\n')
            with patch.object(prepare,'ROOT',root),self.assertRaises(ValueError):prepare.check()
        with tempfile.TemporaryDirectory() as d:
            out=prepare.compose(Path(d)/'source')
            n=prepare.TARGETS[-1];(out/n).write_text((out/n).read_text()+'\n# generated drift\n')
            self.assertNotEqual(prepare.digest(out/n),prepare.check()['generated'][n])

    @unittest.skipUnless(os.environ.get('PACKED_OWNER_NATIVE_LIBRARY'),'explicit qualified native library required')
    def test_actual_public_transport_m1_m2_and_faults(self):
        library=os.environ['PACKED_OWNER_NATIVE_LIBRARY']
        with tempfile.TemporaryDirectory() as d:
            root=prepare.compose(Path(d)/'source')
            code="import sys,json;sys.path.insert(0,sys.argv[1]);from candidates.qwen2_resident_matrix.attention_packed_public.test_public import actual_case;print(json.dumps([actual_case(sys.argv[2],1),actual_case(sys.argv[2],2,stalls=True)]+[actual_case(sys.argv[2],1,fault=f) for f in ('selected_overflow','foreign_ddr','output_error','scratch_abort')],sort_keys=True))"
            r=subprocess.run([sys.executable,'-I','-c',code,str(root),library],capture_output=True,text=True,timeout=20)
            self.assertEqual(r.returncode,0,r.stderr)
            report=json.loads(r.stdout);self.assertEqual([x['rows'] for x in report[:2]],[1,2])
            if os.environ.get('PACKED_PUBLIC_RECEIPT'):
                Path(os.environ['PACKED_PUBLIC_RECEIPT']).write_text(json.dumps(dict(status='PASS_BOUNDED_PUBLIC_TRANSPORT',cases=report,source_sha256=prepare.snapshot(),library_sha256=LIB_SHA,new_compilation=False,full_public_graph=False,rtl=False),sort_keys=True,indent=2)+'\n')
