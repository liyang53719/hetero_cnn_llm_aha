"""Opt-in shared real Banks + real KvAppend + unchanged live PV32 small check."""
import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import resource
import struct
import sys
import time
from .banks import LoanDenseOwner,banked_scratch,LoanFault
from .lease import SharedALoanRouter,SyntheticKvPublication
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent

def need(ok,message):
    if not ok:raise ValueError(message)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,x):Path(p).write_text(json.dumps(x,indent=2,sort_keys=True,allow_nan=False)+'\n')

def sources_now():
    from scripts import observe_qwen2_attention_model as base
    from candidates.qwen2_resident_matrix.official_bf16 import dense_silu
    import subprocess
    sources=base.verify_execution_sources()
    for module in tuple(sys.modules.values()):
        p=Path(getattr(module,'__file__','') or '/')
        if p.suffix=='.py' and p.is_relative_to(ROOT) and p.relative_to(ROOT).parts[0] in ('candidates','scripts','src'):
            sources[str(p.relative_to(ROOT))]=sha(p)
    for p in HERE.iterdir():
        if p.is_file():sources[str(p.relative_to(ROOT))]=sha(p)
    sources.update({p:sha(ROOT/p) for p in dense_silu.SOURCE_CLOSURE})
    external=[p for p in sources if not p.startswith('candidates/qwen2_attention_shared_a_integration/')]
    tracked=set(subprocess.run(['git','ls-files','--',*external],cwd=ROOT,capture_output=True,text=True,check=True).stdout.splitlines())
    need(tracked==set(external),'external dependencies must be tracked')
    return sources

def run(out):
    resource.setrlimit(resource.RLIMIT_CPU,(60,60));resource.setrlimit(resource.RLIMIT_AS,(2<<30,2<<30));resource.setrlimit(resource.RLIMIT_FSIZE,(31<<20,31<<20))
    out=Path(out);need(not out.exists(),'fresh output required');out.mkdir(parents=True)
    start=time.monotonic();cpu=time.process_time()
    from candidates.qwen2_resident_matrix.official_bf16 import dense_silu
    from candidates.qwen2_resident_matrix.official_bf16.owners import OfficialPrefixOwner
    from candidates.qwen2_resident_matrix.dense_block_reduce.matrix_binding import ProfiledMatrixService
    from candidates.qwen2_resident_matrix.dense_block_reduce.profile import QWEN2_QKV_PROFILE
    from candidates.qwen2_resident_matrix.ffn_public.prefix_arithmetic import ScalarService,word
    from candidates.qwen2_resident_matrix.ffn_public.prefix_owners import Job
    from candidates.qwen2_resident_matrix.ffn_public.test_prefix_owners import Harness
    from candidates.qwen2_live_attention_model_m128.pv32_owner import OfficialPV32AttentionOwner
    from candidates.qwen2_attention_resident_candidate.owner import ResidentPV32AttentionOwner
    from candidates.qwen2_attention_resident_candidate.observation import ResidentAttentionObservation
    sources=sources_now();snap=out/'executed_sources';snap.mkdir()
    for p in HERE.iterdir():
        if p.is_file():(snap/p.name).write_bytes(p.read_bytes())
    names=['M1_OLD','M1_BANKED','M2_OLD','M2_BANKED','M2_BANKED_STALLED',
      'abort_fill','abort_memory_read','abort_memory_write','abort_matrix','bank_port_fault','producer_changed']
    save(out/'PREREGISTRATION.json',dict(sources=sources,cases=names,
      limits=dict(cpu_seconds=60,address_space_bytes=2<<30,output_bytes=32<<20),
      arithmetic='UNCHANGED_LIVE_PV32',producer='ACTUAL_SYNTHETIC_KVAPPEND_ACK_PUBLICATION',public21='NOT_EXECUTED'))
    library,build=dense_silu.build_library(out/'build');cases=[]
    initial_accumulator=int(library.matrix_accumulator_address())
    def one(name,rows=1,*,banked=False,observe=False,stall=False,mode=None):
        need(library.td_reset()==0,'native reset');service=ProfiledMatrixService(library,QWEN2_QKV_PROFILE);scalar=ScalarService()
        prefix=OfficialPrefixOwner(scalar,max_tokens=128);ph=Harness(prefix)
        q=tuple(word((i%17-8)/32) for i in range(rows*1536));k=tuple(word((i%13-6)/32+.00031) for i in range(rows*256));v=tuple(word((i%19-9)/32+.0007) for i in range(rows*256))
        append=Job('KvAppend',0x110009,0x200000,0x300000,0x400000,rows,256,256,rows*2048)
        job=Job('Attention',0x11000c,0x100000,append.dst,0x500000,rows,1536,128,rows*6144,c=append.dst+rows*1024)
        ph.bus.input(job.a,q);ph.bus.input(append.a,k);ph.bus.input(append.b,v);ph.bus.output(append.dst,append.write_bytes);ph.bus.output(job.dst,job.write_bytes)
        result=ph.run(append);publication=SyntheticKvPublication(prefix,ph,append,result)
        need(ph.bus.raw(append.dst)==struct.pack('<%dI'%(len(k)+len(v)),*k,*v),'KvAppend produced exact original inputs')
        dense=router=scratch=None
        if banked:
            dense=LoanDenseOwner(enable_ffn_window=True,enable_ffn_tiles=True);scratch=banked_scratch(dense.a_banks)
            owner=ResidentPV32AttentionOwner(service,scalar,scratch=scratch,identity=publication.validate(job))
            router=SharedALoanRouter(dense,prefix,owner,publication);target=router
        else:owner=OfficialPV32AttentionOwner(service,scalar,max_tokens=128);target=owner
        for method in ('_attention','_matrix_step','_pv32_step','_op'):
            need(getattr(type(owner),method) is getattr(OfficialPV32AttentionOwner,method),'arithmetic function drift')
        h=Harness(target,ph.bus);read_start=len(h.bus.reads);scalar_before=dict(scalar.calls)
        capture=ResidentAttentionObservation(owner,source_sha256=sources) if observe else None
        from contextlib import nullcontext
        ticks=holds=0;injected=False;fault_debt_held=False;local_seen=None;remaining=0;external_denials=0
        def blocked():
            nonlocal external_denials
            before=dict(dense.a_banks.counts)
            for key in ('job','window','k_window','drain','tile_control','tile_read','tile_write','abort','local_reset'):
                e=dense.tick(**{key:object()});need(e['loan_blocked'] and not any(e[k] for k in ('job_fire','window_fire','k_window_fire')),'foreign offer escaped')
                external_denials+=1
            for fn in (lambda:dense.tiles.tick(control=object()),lambda:dense.a_banks.begin_cycle(),lambda:dense.a_banks.read(0,0),lambda:dense.a_banks.write(0,0,0)):
                try:fn()
                except LoanFault:external_denials+=1
                else:raise ValueError('direct Tile/Banks route escaped')
            need(dict(dense.a_banks.counts)==before,'rejected foreign traffic consumed bank edge')
        with capture if capture else nullcontext():
            need(h.tick(job=job)['job_fire'],'Attention acceptance')
            if banked:blocked()
            while owner.ports()['response'] is None:
                need(ticks<200000 and time.monotonic()-start<65,'bounded small execution')
                kw=dict(memory_ready=not stall or ticks%5!=0,matrix_request_ready=not stall or ticks%7!=0,
                  matrix_result_ready=not stall or ticks%11!=0,service_result_ready=not stall or ticks%13!=0,service_done_ready=not stall or ticks%17!=0)
                if banked:kw.update(cache_request_ready=not stall or ticks%3!=0,cache_response_ready=True)
                if banked and stall and scratch.pending is not None:
                    key=(scratch.pending.epoch,scratch.pending.serial)
                    if key!=local_seen:local_seen=key;remaining=2
                    if remaining:kw['cache_response_ready']=False;remaining-=1;holds+=1
                pending=h.bus.pending
                if mode and not injected:
                    trigger=(mode=='abort_fill' and scratch.pending is not None or
                      mode=='abort_memory_read' and pending is not None and not pending.write or
                      mode=='abort_memory_write' and pending is not None and pending.write or
                      mode=='abort_matrix' and owner.matrix_client is not None and service.counts['normal_steps']>0 and not owner.matrix_client.drained or
                      mode=='producer_changed' and scratch.pending is not None and not scratch.pending.write)
                    if trigger:
                        if mode=='producer_changed':h.bus.words[job.b]=bytes(64)
                        else:kw['local_reset']=True
                        kw.update(cache_response_ready=False,respond=False,matrix_result_ready=False,service_result_ready=False,service_done_ready=False)
                        injected=True
                        h.tick(**kw);ticks+=1
                        need(router.active and dense.a_banks.lease is router,'abort released A early');blocked()
                        need(owner.ports()['response'] is None,'accepted debt disappeared on abort')
                        fault_debt_held=True;continue
                    if mode=='bank_port_fault' and owner.ports()['cache_request'] is not None:
                        # Actual second-write port conflict before a fill ACK.
                        # No physical request/response is offered on this edge.
                        need(h.bus.pending is None and owner.ports()['memory'] is None,'bank fault edge carries external handshake')
                        original=dense.a_banks.write
                        def duplicate(bank,word,data):original(bank,word,data);original(bank,word,data)
                        dense.a_banks.write=duplicate
                        try:
                            h.tick(**kw)
                        except (ValueError,AssertionError):pass
                        else:raise ValueError('bank port conflict was not rejected')
                        finally:dense.a_banks.write=original
                        need(owner.poison and router.active and not dense.a_banks.in_edge and dense.a_banks.actor is None,'route fault did not poison/retain/restore scope')
                        injected=True;fault_debt_held=True;blocked();ticks+=1;continue
                h.tick(**kw);ticks+=1
            terminal=owner.ports()['response'];need(h.bus.pending is None,'terminal before DDR drain')
            if banked:
                need(router.active and scratch.pending is None and not owner.local_pending,'terminal changed lease/local debt');blocked()
            for _ in range(3):h.tick();need(owner.ports()['response']==terminal,'held terminal changed')
            need(h.tick(response_ready=True)['response_fire'],'terminal consume')
        need(service.owner is None and scalar.client is None and owner.matrix_client is None,'shared service debt at retirement')
        need(int(library.matrix_accumulator_address())==initial_accumulator and library.matrix_accumulator_bytes()==81920,'fixed existing Matrix accumulator')
        if banked:
            need(not router.active and dense.a_banks.lease is None and scratch.owner is None and not any(scratch.valid),'A not released after complete drain')
            before=dense.a_banks.counts['bank_edges'];need(dense.tick()['job_ready'],'Dense did not resume');need(dense.a_banks.counts['bank_edges']==before+1,'restored Dense clock')
        if mode:need(injected and fault_debt_held and terminal.status=='Protocol','fault not injected/drained')
        else:need(terminal.status is None and owner.ack_bytes==job.write_bytes,'full successful ACK')
        output=h.bus.raw(job.dst);reads=Counter()
        for a in h.bus.reads[read_start:]:reads['q' if job.a<=a<job.a+job.write_bytes else 'k' if job.b<=a<job.c else 'v']+=64
        item=dict(name=name,rows=rows,banked=banked,mode=mode,terminal=asdict(terminal),prefix_terminal=asdict(result),
          prefix_ack_bytes=prefix.ack_bytes,prefix_published_bytes=len(h.bus.outputs[append.dst]&h.bus.readable)*64,
          producer_sha256=publication.digest,output_sha256=hashlib.sha256(output).hexdigest(),
          owner=owner.report(),matrix=service.report(),scalar_calls=dict(scalar.calls),prefix_scalar_calls=scalar_before,
          read_bytes=dict(reads),ticks=ticks,local_hold_edges=holds,external_denials=external_denials,injected=injected,fault_debt_held=fault_debt_held,
          loan=router.report() if banked else None,output_published=False)
        fields={}
        if capture:
            item['observation']=capture.save(out/(name+'_observation'));need(item['observation']['status'].startswith('COMPLETE_'),'incomplete observation')
            fields={n:(capture._bytes(n),bytes(f['observed']),capture._bytes(n,'frequency')) for n,f in capture.fields.items()}
        cases.append(item);save(out/'PROGRESS.json',dict(cases=cases));return item,output,fields
    comparisons=[]
    try:
        for rows in (1,2):
            old,a,fa=one('M%d_OLD'%rows,rows,observe=True)
            new,b,fb=one('M%d_BANKED'%rows,rows,banked=True,observe=True)
            need(a==b and fa==fb,'full observed arithmetic/output bit mismatch')
            need(old['scalar_calls']==new['scalar_calls'] and old['matrix']['normal_fma_calls']==new['matrix']['normal_fma_calls'],'changed arithmetic graph counts')
            need(new['read_bytes']['k']==new['read_bytes']['v']==rows*1024,'KV not loaded exactly once')
            comparisons.append(dict(case='M%d'%rows,output_bit_diff_count=0,intermediate_bit_diff_count=0,observed_fields=len(fa),
              old_external_read_bytes=sum(old['read_bytes'].values()),banked_external_read_bytes=sum(new['read_bytes'].values()),
              old_kv_read_bytes=old['read_bytes']['k']+old['read_bytes']['v'],banked_kv_read_bytes=new['read_bytes']['k']+new['read_bytes']['v']))
            if rows==2:
                st,c,fc=one('M2_BANKED_STALLED',rows,banked=True,observe=True,stall=True)
                need(b==c and fb==fc and st['local_hold_edges']>0 and st['scalar_calls']==new['scalar_calls'],'stalled equivalence/coverage')
        for mode in ('abort_fill','abort_memory_read','abort_memory_write','abort_matrix','bank_port_fault','producer_changed'):one(mode,banked=True,mode=mode)
        need([x['name'] for x in cases]==names,'all predeclared cases')
        need(all(sha(ROOT/p)==v for p,v in sources.items()),'source drift')
        report=dict(status='PASS_SMALL_BANKED_KV_LOAN',sources=sources,build=build,cases=cases,comparisons=comparisons,
          host_cpu_seconds=time.process_time()-cpu,host_wall_seconds=time.monotonic()-start,max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
          m128_executed=False,fullblock_executed=False,rtl_executed=False,ci_executed=False,public21_executed=False,
          source_boundary='ACTUAL_SYNTHETIC_KVAPPEND_AND_LIVE_PV32_SHARED_EXISTING_BANKS')
        save(out/'RESULT.json',report);need(sum(p.stat().st_size for p in out.rglob('*') if p.is_file())<32<<20,'output bound')
        print(json.dumps(dict(status=report['status'],comparisons=comparisons,cpu_seconds=report['host_cpu_seconds'],cases=len(cases))))
    except Exception as error:
        save(out/'INCOMPLETE.json',dict(status='INCOMPLETE',error_type=type(error).__name__,error=str(error),completed_cases=[c['name'] for c in cases],sources_after=sources_now()))
        raise
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');p.add_argument('--out');a=p.parse_args()
    if a.execute:need(a.out is not None,'fresh work output required');run(a.out)
    else:print(json.dumps(dict(status='NOT_EXECUTED')))
