"""Opt-in actual tiled Public transport; no automatic native test execution."""
import ctypes,hashlib,json,struct
from pathlib import Path
from ..attention_packed_public import prepare
LIB_SHA='1ba0b6aa738dd4a409b91adf93cafbcec63fc3c0df1590f9b91cf8f223f54811'

class ResponseHold:
    """Count only visible raw-response edges with ACK disabled."""
    def __init__(self):self.count=0;self.response=None
    def stall(self,response):
        if self.count>=7:return False
        if response is not None:
            if self.response is None:self.response=response
            elif response is not self.response:raise AssertionError('held raw response identity changed')
            self.count+=1
        return True

def actual_case(library,rows,*,fault=None,stalls=False):
    if type(rows) is not int or rows not in (17,32) or fault not in (None,'panel_abort','panel_ddr_error') or type(stalls) is not bool:raise ValueError('bounded explicit fixture')
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
    from .profile import PackedTiledProfile
    original=Path(__file__).parent.parent/'attention_packed_public/original_owner.source'
    expected=json.loads((Path(__file__).parent.parent/'attention_packed_public/pins.json').read_bytes())['sources'][prepare.ORACLE_SOURCE]
    if hashlib.sha256(original.read_bytes()).hexdigest()!=expected:raise ValueError('original oracle source drift')
    namespace=dict(_original_namespace)
    source_definitions(original,('_attention',),namespace,class_name='OfficialAttentionOwner')
    class OriginalOracle(Oracle):
        _attention=namespace['_attention']
    if hashlib.sha256(Path(library).read_bytes()).hexdigest()!=LIB_SHA:raise ValueError('qualified library mismatch')
    lib=configure_library(ctypes.CDLL(library));lib.td_reset();matrix=ProfiledMatrixService(lib,QWEN2_QKV_PROFILE)
    scalar=Scalar()
    from ..attention_bank_multirow.oracle import ScalarTrace
    scalar.trace=ScalarTrace(capture_scores=False)
    owner=OfficialAttentionOwner(matrix,scalar);parent=ParentLoan(enabled=True)
    data=fixture(rows);bases=(0x100000,0x200000,0x300000);dst=0x400000
    if fault=='selected_overflow':data=((0x7f7f0000,)*len(data[0]),(0x7f7f0000,)*len(data[1]),data[2])
    memory={base+4*i:x for base,words in zip(bases,data) for i,x in enumerate(words)}
    job=Job('Attention',0x10001,bases[0],bases[1],dst,rows,1536,128,rows*6144,c=bases[2])
    transport=PublicKvTransport(owner=owner,parent=parent,job=job,packed_profile=PackedTiledProfile())
    banks=parent.owner.a_banks;mux=transport.supply.scratch_mux
    pending=write=None;terminal=None;held=0;scores={};injected=False;reads=[];writes=[]
    panel_hold=ResponseHold();boundary_seen=False;boundary_identity=None
    for cycle in range(2000000):
        p=transport.ports();op=owner.ports();response=pending if not stalls or cycle%3 else None
        abort=False
        client=owner.matrix_client
        at_boundary=(client is not None and client.active and client.group.opcode==0x24 and client.index==16 and
          mux.active is not None and mux.active.operation=='read' and mux.active.query==16 and mux.active.kv_head==0 and mux.active.line==4145)
        raw_ready=not stalls or cycle%5!=0
        if at_boundary:
            boundary_seen=True
            identity=(id(matrix.owner),client.tag,client.group,client.index)
            if boundary_identity is None:boundary_identity=identity
            elif identity!=boundary_identity:raise AssertionError('PV context changed during panel wait')
            if panel_hold.stall(parent.raw.response):raw_ready=False
            if fault=='panel_abort' and not injected:abort=True;injected=True
        if fault=='panel_ddr_error' and not injected and pending is not None and write is None and client is not None and client.active and client.group.opcode==0x24 and client.index==16 and reads[-1]==job.c+16*256*4:
            response=MemoryResponse(pending.tag,pending.data,True);injected=True
        if not injected:
            if pending is not None and fault=='foreign_ddr':
                response=MemoryResponse(pending.tag+1,pending.data);injected=True
            elif write is not None and fault=='output_error':
                response=MemoryResponse(pending.tag,None,True);injected=True
            elif fault=='scratch_abort' and mux.active is not None:
                abort=True;injected=True
        edge=transport.tick(job=job if cycle==0 else None,memory_ready=not stalls or cycle%4!=0,
             memory_response=response,response_ready=p['response'] is not None and held>=3,
             raw_ack_ready=raw_ready,abort=abort,
             matrix_request_ready=not stalls or cycle%3!=0,matrix_result_ready=not stalls or cycle%4!=0,
             service_result_ready=not stalls or cycle%3!=0,service_done_ready=not stalls or cycle%4!=0)
        if parent.owner.clock!=cycle+1 or mux.edges!=cycle+1:raise AssertionError('one original parent edge')
        if parent.raw.banks is not banks or parent.owner.a_banks is not banks:raise AssertionError('bank allocation changed')
        if edge['scratch_fire']:
            a=op['scratch']
            if a.operation=='write' and a.line<4144:scores[(a.query,a.kv_head,(a.line-4096)//8,(a.line-4096)%8)]=a.words[:min(16,a.query+1-16*((a.line-4096)%8))]
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
                score=tuple(w for token in range(rows) for head in range(12) for block in range((token+16)//16) for w in scores[(token,head//6,head%6,block)])
                if actual!=expected or score!=oracle.scores()[1]:raise AssertionError('original numerical oracle mismatch')
                if transport.supply.counts['ddr_requests']!=32*rows or len(reads)!=128*rows:raise AssertionError('physical KV miss/Q request counts')
                groups=12*sum((n+15)//16 for n in range(1,rows+1))
                if mux.counts['raw_requests']!=4*groups or mux.counts['raw_acks']!=4*groups:raise AssertionError('scratch traffic')
                if not boundary_seen or panel_hold.count!=7:raise AssertionError('panel boundary stall not exercised')
                if int(lib.matrix_normal_fmas())!=4096*8*groups+2048*rows*(rows+1):raise AssertionError('all enabled cell FMA count')
                digest=lambda x:hashlib.sha256(struct.pack('<'+'I'*len(x),*x)).hexdigest()
                return dict(rows=rows,output_sha256=digest(actual),scores_sha256=digest(score),
                    panel_boundary_seen=boundary_seen,panel_ack_hold_edges=panel_hold.count,owner_edges=transport.ticks,parent_edges=parent.owner.clock,matrix=dict(matrix.counts),
                    kv=dict(transport.supply.counts),scratch=dict(mux.counts),ddr_reads=len(reads),ddr_writes=len(writes),
                    all_enabled_fmas=int(lib.matrix_normal_fmas()),owner_class=type(owner).__module__+'.'+type(owner).__name__)
            if terminal.status is None:raise AssertionError('false success after fault')
            if fault in ('selected_overflow','output_error') and any(dst<=a<dst+job.write_bytes for a in memory):raise AssertionError('bad output published')
            if not injected or not boundary_seen:raise AssertionError('targeted boundary fault not injected')
            if any(dst+16*1536*4<=a<dst+job.write_bytes for a in memory):raise AssertionError('failed query output published')
            return dict(fault=fault,drained=True,failed=True,panel_boundary_seen=True,parent_edges=parent.owner.clock,matrix=dict(matrix.counts),scratch=dict(mux.counts))
    raise AssertionError(('transport did not terminate',owner.state,owner.detail,transport.supply.state,mux.active,mux.response))
