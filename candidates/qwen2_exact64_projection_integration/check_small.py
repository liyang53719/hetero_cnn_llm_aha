"""Opt-in bounded synthetic Memory/ACK/reservation check; no public21 execution."""
import argparse
from array import array
from collections import Counter
import ctypes as C
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import resource
import struct
import subprocess
import sys
import time
from types import SimpleNamespace
from .kernel import Exact64Kernel,compile_library,source_check,need
from .owner import Exact64ProjectionOwner,MemoryResponse
from .driver import Exact64PublicDriver
from candidates.qwen2_resident_matrix.ffn_public.prefix_owners import Job
from candidates.qwen2_resident_matrix.ffn_public.prefix_execution import PhysicalMemory
from candidates.qwen2_resident_matrix.ffn_public.fixture import PhysicalAllocation
from candidates.qwen2_attention_shared_a_integration.banks import LoanDenseOwner,LoanFault
from candidates.qwen2_resident_matrix.official_bf16 import dense_silu
from candidates.qwen2_resident_matrix.ffn_attention.matrix_service import MatrixService
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
CASES=(('Q1',1,1536,None),('K2',2,256,None),('K1_STALLED',1,256,'stalled'),
       ('ABORT_READ',1,256,'abort_read'),('FOREIGN_READ',1,256,'foreign_read'),
       ('ABORT_WRITE',1,256,'abort_write'),('FOREIGN_WRITE',1,256,'foreign_write'),
       ('SHORT_FINAL_ACK',1,256,'short_final_ack'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,x):Path(p).write_text(json.dumps(x,sort_keys=True,indent=2,allow_nan=False)+'\n')
def sources_now():
    sources=source_check()
    for module in tuple(sys.modules.values()):
        path=Path(getattr(module,'__file__','') or '/')
        if path.suffix=='.py' and path.is_relative_to(ROOT):sources[str(path.relative_to(ROOT))]=sha(path)
    for p in HERE.iterdir():
        if p.is_file():sources[str(p.relative_to(ROOT))]=sha(p)
    sources.update({p:sha(ROOT/p) for p in dense_silu.SOURCE_CLOSURE})
    external={p for p in sources if not p.startswith(str(HERE.relative_to(ROOT))+'/')}
    tracked=set(subprocess.run(['git','ls-files','--',*sorted(external)],cwd=ROOT,text=True,capture_output=True,check=True).stdout.splitlines())
    need(external==tracked,'only tracked external source dependencies')
    return sources

def stimulus(rows,width):
    # Fixed before pilot: finite BF16 values, cancellation, exponent variation,
    # signed zero and BF16 subnormals. These bytes are synthetic input providers.
    def half(i,salt):
        v=((i+salt)*1664525+1013904223)&0xffffffff
        if i%251==0:return (v>>16)&0x8000
        if i%509==0:return 1|((v>>16)&0x8000)
        return ((v>>16)&0x8000)|((120+((v>>24)%10))<<7)|((v>>9)&127)
    a=array('I',(half(i,17)<<16 for i in range(rows*1536)))
    w=array('H',(half(i,29) for i in range(1536*width)))
    need(sys.byteorder=='little','fixed little-endian test machine')
    return a.tobytes(),w.tobytes()

def physical_fixture(j,a,w):
    table=lambda at:SimpleNamespace(base=at)
    alloc=lambda at,shape,dtype,readonly:PhysicalAllocation(at,shape,dtype,((shape[0]*shape[1]*(2 if dtype==5 else 4)+63)//64)*64,readonly)
    fixture=SimpleNamespace(scope='SYNTHETIC_MEMORY_ONLY_NO_PUBLIC21',validate_spans=lambda:None,
      allocations={'n0':alloc(j.a,(j.m,1536),7,True),'w':alloc(j.b,(1536,j.n),5,True),
                   'raw':alloc(j.dst,(j.m,j.n),7,False)},
      config=SimpleNamespace(command=table(0x3000000),descriptor=table(0x3000040)),
      memory=SimpleNamespace(mappings={0x3000000:bytes(64),0x3000040:bytes(64)}))
    return PhysicalMemory(fixture,{'n0':lambda i:a[i:i+64],'w':lambda i:w[i:i+64]})

def control(lib,a,w,rows,width):
    # Independent after-terminal control: the included frozen full-array graph.
    f=C.POINTER(C.c_float);h=C.POINTER(C.c_uint16);u=C.POINTER(C.c_uint64)
    lib.candidate_project_raw.argtypes=[f,h,C.c_int,C.c_int,f,u,u,C.POINTER(C.c_uint)]
    lib.candidate_project_raw.restype=C.c_int
    ax=(C.c_float*(len(a)//4)).from_buffer_copy(a);wx=(C.c_uint16*(len(w)//2)).from_buffer_copy(w)
    out=(C.c_float*(rows*width))();fm=C.c_uint64();ad=C.c_uint64();peak=C.c_uint()
    need(lib.candidate_project_raw(ax,wx,width,rows,out,C.byref(fm),C.byref(ad),C.byref(peak))==0,'frozen control')
    return bytes(out),dict(fmas=fm.value,adds=ad.value,peak=peak.value)

def run(out):
    resource.setrlimit(resource.RLIMIT_CPU,(60,60));resource.setrlimit(resource.RLIMIT_AS,(2<<30,2<<30))
    resource.setrlimit(resource.RLIMIT_FSIZE,(31<<20,31<<20))
    out=Path(out);need(not out.exists(),'fresh namespace');out.mkdir(parents=True)
    initial=sources_now();save(out/'PREREGISTRATION.json',dict(sources=initial,cases=CASES,
      limits=dict(cpu_seconds=60,address_space_bytes=2<<30,output_bytes=32<<20),
      public21='NOT_EXECUTED',profiled_dense_binding='NOT_EXECUTED',reservation_service='ORIGINAL_BASE_MATRIX_SERVICE',
      matrix_arithmetic='RESERVATION_ONLY_ZERO_MATRIX_ISSUES',
      arithmetic='FROZEN_EXACT64_GRAPH_STREAMED_FROM_ACCEPTED_MEMORY_BYTES'))
    snap=out/'executed_sources';snap.mkdir()
    for p in HERE.iterdir():
        if p.is_file():(snap/p.name).write_bytes(p.read_bytes())
    start=time.monotonic();cpu=time.process_time()
    build=compile_library(out/'exact64.so');native,native_build=dense_silu.build_library(out/'matrix_build')
    cases=[]
    for name,rows,width,mode in CASES:
        need(time.process_time()-cpu<45,'bounded small CPU admission')
        need(native.td_reset()==0,'actual Matrix reset')
        service=MatrixService(native)
        dense=LoanDenseOwner(enable_ffn_window=True,enable_ffn_tiles=True)
        kernel=Exact64Kernel(out/'exact64.so');owner=Exact64ProjectionOwner(kernel)
        j=Job('Dense',0x110001 if width==1536 else 0x110004,0x100000,0x200000,0x1000000,
              rows,width,1536,rows*width*4,weight_bf16=True)
        a,w=stimulus(rows,width);memory=physical_fixture(j,a,w);pending=None;terminal=None
        ticks=0;injected=False;drain_seen=False;last_ack=None;held=0;terminal_tick=None
        native_before=(int(native.matrix_dense_fmas()),int(native.matrix_normal_fmas()))
        need(service.acquire(owner,'dense',j.tag),'real Matrix reservation');g=dense.bank_guard;g.lease=owner
        # Actual direct entry denial, not only filtering scheduler offers.
        for field in ('job','window','drain','tile_read','tile_write','abort'):
            need(dense.tick(**{field:object()})['loan_blocked'],'foreign Dense admission')
        for fn in (lambda:dense.tiles.tick(control=object()),lambda:g.read(0,0),lambda:g.write(0,0,0)):
            try:fn()
            except LoanFault:pass
            else:raise ValueError('foreign bank route accepted')
        while terminal is None:
            need(ticks<500000 and time.monotonic()-start<65,'bounded small total')
            bp=owner.ports();kwargs=dict(job=j if ticks==0 else None,memory_ready=mode!='stalled' or ticks%5!=0)
            if pending is not None:
                q,data=pending;response=MemoryResponse(q.tag,data)
                final=q.write and owner.ack_bytes+64==j.write_bytes
                if final and held<5 and mode in (None,'stalled'):
                    held+=1;response=None;need(bp['response'] is None,'no success before final ACK')
                trigger=(not injected and ((mode in ('abort_read','foreign_read') and not q.write) or
                         (mode in ('abort_write','foreign_write') and q.write) or
                         (mode=='short_final_ack' and final)))
                if trigger:
                    injected=True
                    if mode.startswith('abort'):kwargs['abort']=True;response=None;service.abort(owner)
                    elif mode.startswith('foreign'):response=MemoryResponse(q.tag^1,data)
                    else:response=MemoryResponse(q.tag,None,nbytes=32)
                kwargs['memory_response']=response
            else:response=None
            kwargs['response_ready']=True
            with g.edge():g.clock_only=True;dense.tick()
            edge=owner.tick(**kwargs)
            if injected and owner.state=='drain' and pending is not None:
                need(owner.request is pending[0] and owner.ports()['response'] is None,'fault retained accepted memory debt');drain_seen=True
            if edge['memory_response_fire']:
                q,_=pending
                if q.write and response.nbytes==64 and not response.error:
                    memory.write_event('ack',SimpleNamespace(tag=response.tag,error=False,nbytes=64));last_ack=ticks
                elif q.write:
                    # Failed ACK cannot clear PhysicalMemory.pending. Preserve
                    # this quarantine receipt; never publish or claim release.
                    pass
                pending=None
            if edge['memory_fire']:
                need(pending is None,'single accepted memory debt');q=edge['memory']
                if q.write:
                    memory.write_event('command',SimpleNamespace(address=q.address,beats=1,tag=q.tag))
                    memory.write_event('data',SimpleNamespace(words=q.words,mask=q.mask,last=True));data=None
                else:data=memory.read_bytes64(q.address)
                pending=(q,data)
            if edge['response_fire']:terminal=edge['response'];terminal_tick=ticks
            ticks+=1
        success=terminal.status is None
        if success:
            need(pending is None and memory.pending is None and held==5 and terminal_tick>last_ack,'success after physical ACK')
            memory.terminal(j,terminal)
            expected,stats=control(kernel.lib,a,w,rows,width);actual=memory.raw(j.dst,j.write_bytes)
            need(actual==expected,'stream differs from frozen exact64 full graph')
            need(owner.report()['kernel_delta']==dict(fmas=rows*width*1536,adds=rows*width*64),'real operation counts')
            bitdiff=sum(x!=y for (x,),(y,) in zip(struct.iter_unpack('<I',actual),struct.iter_unpack('<I',expected)))
            (out/(name+'_actual.f32le')).write_bytes(actual);(out/(name+'_control.f32le')).write_bytes(expected)
        else:
            need(injected and terminal.status=='Protocol','planned protocol failure required')
            if mode in ('abort_read','foreign_read','abort_write','foreign_write'):
                need(drain_seen,'fault must retain accepted debt before terminal')
            expected_fmas=0 if mode in ('abort_read','foreign_read') else 393216 if mode=='short_final_ack' else 98304
            need(owner.report()['kernel_delta']['fmas']==expected_fmas,'fault injection arithmetic boundary')
            bitdiff=None;stats=None
        quarantined=memory.pending is not None
        need(quarantined==(mode=='short_final_ack'),'only malformed actual ACK retains physical debt')
        if not quarantined:
            service.retire_owner_response(owner);service.release(owner);g.lease=None
            need(dense.tick()['job_ready'],'Dense A admission restores after drain')
        need((int(native.matrix_dense_fmas()),int(native.matrix_normal_fmas()))==native_before,'no invented Matrix arithmetic')
        report=dict(name=name,rows=rows,width=width,mode=mode,terminal=asdict(terminal),owner=owner.report(),
          ticks=ticks,bit_diff_count=bitdiff,control=stats,final_ack_hold_ticks=held,
          terminal_tick=terminal_tick,last_successful_ack_tick=last_ack,fault_injected=injected,drain_observed=drain_seen,
          physical_pending_retained=quarantined,matrix_lease_retained=service.owner is owner,a_lease_retained=g.lease is owner,
          physical=memory.report(),matrix=service.report(),input_sha256={'n0':hashlib.sha256(a).hexdigest(),'w':hashlib.sha256(w).hexdigest()})
        cases.append(report);save(out/'PROGRESS.json',dict(cases=cases))
    need(initial==sources_now(),'execution source drift')
    total=sum(p.stat().st_size for p in out.rglob('*') if p.is_file());need(total<32<<20,'total output budget')
    result=dict(scope='DIAGNOSTIC_SOFTWARE_OWNER',public21='NOT_EXECUTED',hardware_mapping='NOT_IMPLEMENTED',performance='NO_GO',
      profiled_dense_binding='NOT_EXECUTED',reservation_service='ORIGINAL_BASE_MATRIX_SERVICE',
      sources=initial,build=build,native_build=native_build,cases=cases,cpu_seconds=time.process_time()-cpu,
      wall_seconds=time.monotonic()-start,max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,output_bytes=total)
    save(out/'RESULT.json',result)
    print(json.dumps(dict(status='COMPLETED',cases=len(cases),cpu_seconds=result['cpu_seconds'],wall_seconds=result['wall_seconds'])))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');p.add_argument('--out');args=p.parse_args()
    if args.execute:need(args.out is not None,'output required');run(args.out)
    else:print(json.dumps({'status':'NOT_EXECUTED','case_count':len(CASES),'source_count':len(sources_now())}))
