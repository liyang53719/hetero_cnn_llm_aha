"""Opt-in actual live PV32 vs resident supply on bounded synthetic inputs."""
import argparse
from collections import Counter
from dataclasses import asdict,replace
import hashlib
import json
import os
from pathlib import Path
import resource
import struct
import sys
import time
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent

def need(ok,message):
    if not ok:raise ValueError(message)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,x):Path(p).write_text(json.dumps(x,indent=2,sort_keys=True,allow_nan=False)+'\n')

def run(out):
    resource.setrlimit(resource.RLIMIT_CPU,(60,60));resource.setrlimit(resource.RLIMIT_AS,(2<<30,2<<30));resource.setrlimit(resource.RLIMIT_FSIZE,(31<<20,31<<20))
    out=Path(out);need(not out.exists(),'fresh output required');out.mkdir(parents=True)
    start=time.monotonic();cpu=time.process_time()
    from candidates.qwen2_resident_matrix.official_bf16 import dense_silu
    from candidates.qwen2_resident_matrix.dense_block_reduce.matrix_binding import ProfiledMatrixService
    from candidates.qwen2_resident_matrix.dense_block_reduce.profile import QWEN2_QKV_PROFILE
    from candidates.qwen2_resident_matrix.ffn_public.prefix_arithmetic import ScalarService,word
    from candidates.qwen2_resident_matrix.ffn_public.prefix_owners import Job
    from candidates.qwen2_resident_matrix.ffn_public.test_prefix_owners import Harness
    from candidates.qwen2_live_attention_model_m128.pv32_owner import OfficialPV32AttentionOwner
    from candidates.qwen2_attention_resident_candidate.owner import ResidentPV32AttentionOwner
    from candidates.qwen2_attention_resident_candidate.scratch import SharedAScratch,ReadonlyKVIdentity
    from candidates.qwen2_attention_resident_candidate.observation import ResidentAttentionObservation
    from scripts import observe_qwen2_attention_model as base
    # Original observer has a checked, tracked source inventory, not old tensors.
    sources=base.verify_execution_sources()
    for module in tuple(sys.modules.values()):
        p=Path(getattr(module,'__file__','') or '/')
        if p.suffix=='.py' and p.is_relative_to(ROOT) and p.relative_to(ROOT).parts[0] in ('candidates','scripts','src'):
            sources[str(p.relative_to(ROOT))]=sha(p)
    for p in HERE.iterdir():
        if p.is_file():sources[str(p.relative_to(ROOT))]=sha(p)
    sources.update({p:sha(ROOT/p) for p in dense_silu.SOURCE_CLOSURE})
    import subprocess
    external=[p for p in sources if not p.startswith('candidates/qwen2_attention_resident_candidate/')]
    tracked=set(subprocess.run(['git','ls-files','--',*external],cwd=ROOT,capture_output=True,text=True,check=True).stdout.splitlines())
    need(tracked==set(external),'all external code/evidence dependencies must be tracked')
    save(out/'PREREGISTRATION.json',dict(sources=sources,cases=['M1_OLD','M1_CACHED','M2_OLD','M2_CACHED','M2_CACHED_STALLED'],
      negative_modes=['fill_abort','hit_abort','hit_wrong_epoch','hit_wrong_data','producer_change','region_write','memory_wrongtag','memory_error','memory_short'],
      limits=dict(cpu_seconds=60,address_space_bytes=2<<30,output_bytes=32<<20),arithmetic='UNMODIFIED_LIVE_PV32'))
    library,build=dense_silu.build_library(out/'build');cases=[]
    import numpy as np
    runtime_paths=(Path(np.__file__),Path(np._core._multiarray_umath.__file__),Path(sys.executable).resolve())
    runtime_identity={str(p):sha(p) for p in runtime_paths}
    initial_accumulator=int(library.matrix_accumulator_address())
    def one(name,rows=1,*,cached=False,observe=False,stall=False,mode=None):
        need(time.monotonic()-start<65,'bounded small run deadline');need(library.td_reset()==0,'native reset')
        service=ProfiledMatrixService(library,QWEN2_QKV_PROFILE);scalar=ScalarService();scratch=SharedAScratch()
        identity=ReadonlyKVIdentity(31,31,5,5)
        owner=ResidentPV32AttentionOwner(service,scalar,scratch=scratch,identity=identity) if cached else OfficialPV32AttentionOwner(service,scalar,max_tokens=128)
        for method in ('_attention','_matrix_step','_pv32_step','_op'):
            need(getattr(type(owner),method) is getattr(OfficialPV32AttentionOwner,method),'original arithmetic function identity')
        h=Harness(owner);job=Job('Attention',0x11000c,0x100000,0x200000,0x400000,rows,1536,128,rows*1536*4,c=0x300000)
        q=tuple(word((i%17-8)/32) for i in range(rows*1536));k=tuple(word((i%13-6)/32+.00031) for i in range(rows*256))
        v=tuple(word((i%19-9)/32+.0007) for i in range(rows*256))
        h.bus.input(job.a,q);h.bus.input(job.b,k);h.bus.input(job.c,v);h.bus.output(job.dst,job.write_bytes)
        capture=ResidentAttentionObservation(owner,source_sha256=sources) if observe else None
        from contextlib import nullcontext
        ticks=0;injected=False;local_holds=0;local_seen=None;local_hold_remaining=0
        with capture if capture else nullcontext():
            need(h.tick(job=job)['job_fire'],'job admission')
            while owner.ports()['response'] is None:
                need(ticks<200000 and time.monotonic()-start<65,'small owner event/deadline cap')
                kw=dict(memory_ready=not stall or ticks%5!=0,matrix_request_ready=not stall or ticks%7!=0,
                  matrix_result_ready=not stall or ticks%11!=0,service_result_ready=not stall or ticks%13!=0,service_done_ready=not stall or ticks%17!=0)
                if cached:kw.update(cache_request_ready=not stall or ticks%3!=0,cache_response_ready=not stall or ticks%4!=0)
                pending=h.bus.pending;local=owner.ports().get('cache_response')
                if cached and stall and scratch.pending is not None:
                    identity_now=(scratch.pending.epoch,scratch.pending.serial)
                    if identity_now!=local_seen:local_seen=identity_now;local_hold_remaining=2
                    if local_hold_remaining:kw['cache_response_ready']=False;local_hold_remaining-=1
                    else:kw['cache_response_ready']=True
                if cached and scratch.held is not None and not kw['cache_response_ready']:local_holds+=1
                if mode is not None and not injected:
                    request=scratch.pending
                    if mode.startswith('memory_') and pending is not None and not pending.write and pending.address==job.b:
                        response=h.bus.response()
                        if mode=='memory_wrongtag':response=replace(response,tag=response.tag+1)
                        elif mode=='memory_error':response=replace(response,error=True)
                        else:response=replace(response,nbytes=32,data=response.data[:32])
                        kw.update(response=response,respond=True);injected=True
                    elif request is not None and ((mode=='fill_abort' and request.write) or (mode!='fill_abort' and not request.write)):
                        if mode in ('fill_abort','hit_abort'):kw.update(local_reset=True,cache_response_ready=False)
                        elif mode=='producer_change':scratch.producer_changed(replace(identity,producer_k=6))
                        elif mode=='region_write':scratch.notify_write(job.b,64)
                        elif local is not None:
                            kw['cache_response_override']=replace(local,epoch=local.epoch-1) if mode=='hit_wrong_epoch' else replace(local,data=bytes(64))
                        else:
                            kw['cache_response_ready']=False
                            h.tick(**kw);ticks+=1;continue
                        injected=True
                h.tick(**kw);ticks+=1
            result=owner.ports()['response'];need(h.bus.pending is None,'memory debt at terminal')
            if cached:need(scratch.pending is None and not owner.local_pending,'local debt at terminal')
            held=result
            for _ in range(3):h.tick();need(owner.ports()['response']==held,'held owner terminal changed')
            need(h.tick(response_ready=True)['response_fire'],'owner terminal consume')
        need(service.owner is None and scalar.client is None and owner.matrix_client is None,'shared service debt')
        need(int(library.matrix_accumulator_address())==initial_accumulator and library.matrix_accumulator_bytes()==81920,'one fixed Matrix accumulator')
        if cached:need(scratch.owner is None and not any(scratch.valid),'cache lease/valid survives terminal')
        output=h.bus.raw(job.dst);readbytes=Counter()
        for address in h.bus.reads:readbytes['q' if job.a<=address<job.a+job.write_bytes else 'k' if job.b<=address<job.b+rows*1024 else 'v']+=64
        item=dict(name=name,rows=rows,cached=cached,mode=mode,terminal=asdict(result),owner=owner.report(),matrix=service.report(),
          scalar_calls=dict(scalar.calls),read_bytes=dict(readbytes),write_ack_bytes=owner.ack_bytes,ticks=ticks,local_hold_edges=local_holds,
          output_sha256=hashlib.sha256(output).hexdigest(),input_sha256={n:hashlib.sha256(struct.pack('<%dI'%len(w),*w)).hexdigest() for n,w in [('q',q),('k',k),('v',v)]},
          output_published=False,injected=injected)
        fields={}
        if capture:
            item['observation']=capture.save(out/(name+'_observation'))
            need(item['observation']['status'].startswith('COMPLETE_'),'incomplete observation '+str(item['observation'].get('observer_error')))
            fields={n:(capture._bytes(n),bytes(f['observed']),capture._bytes(n,'frequency')) for n,f in capture.fields.items()}
        if mode:
            need(injected and result.status==('Memory' if mode=='memory_error' else 'Protocol'),'negative injection/status')
            need(not h.bus.readable.intersection(h.bus.outputs[job.dst]),'fault output published')
        else:
            need(result.status is None and owner.ack_bytes==job.write_bytes,'successful exact output ACK')
            if cached:
                need(readbytes['k']==readbytes['v']==rows*1024,'KV must be read once')
                need(scratch.counts['fill_commits']==rows*32,'complete unique KV fill')
                need(scratch.counts['consume_acks']==scratch.counts['fill_requests']+scratch.counts['read_requests'],'exact local ACK accounting')
        cases.append(item);save(out/'PROGRESS.json',dict(cases=cases))
        return item,output,fields
    comparisons=[]
    for rows in (1,2):
        old,a,fa=one('M%d_OLD'%rows,rows,observe=True)
        new,b,fb=one('M%d_CACHED'%rows,rows,cached=True,observe=True)
        need(a==b and fa==fb,'old/new output or full intermediate bit mismatch')
        need(old['scalar_calls']==new['scalar_calls'],'cache changed scalar graph count')
        need(old['matrix']['normal_fma_calls']==new['matrix']['normal_fma_calls'],'cache changed physical FMA count')
        comparisons.append(dict(case='M%d'%rows,output_bit_diff_count=0,intermediate_bit_diff_count=0,observed_fields=len(fa),
          old_external_read_bytes=sum(old['read_bytes'].values()),cached_external_read_bytes=sum(new['read_bytes'].values()),
          old_kv_read_bytes=old['read_bytes']['k']+old['read_bytes']['v'],cached_kv_read_bytes=new['read_bytes']['k']+new['read_bytes']['v']))
        if rows==2:
            stalled,c,fc=one('M2_CACHED_STALLED',2,cached=True,observe=True,stall=True)
            need(b==c and fb==fc and new['scalar_calls']==stalled['scalar_calls'],'stalled cache output/observation differs')
            need(stalled['local_hold_edges']>0,'local response backpressure not exercised')
    for mode in ('fill_abort','hit_abort','hit_wrong_epoch','hit_wrong_data','producer_change','region_write','memory_wrongtag','memory_error','memory_short'):
        one(mode,cached=True,mode=mode)
    need(all(sha(ROOT/p)==v for p,v in sources.items()),'source drift')
    need(all(sha(p)==v for p,v in runtime_identity.items()),'runtime drift')
    report=dict(status='PASS_SMALL_SYNTHETIC_RESIDENT_EQUIVALENCE',comparisons=comparisons,cases=cases,sources=sources,build=build,runtime_identity=runtime_identity,
      host_cpu_seconds=time.process_time()-cpu,host_wall_seconds=time.monotonic()-start,max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
      full_m128_executed=False,fullblock_executed=False,rtl_executed=False,ci_executed=False,
      source_boundary='ACTUAL_LIVE_PV32_UNMODIFIED_ARITHMETIC_NEW_SOFTWARE_KV_SUPPLY',hardware_cycles=None)
    save(out/'RESULT.json',report)
    safe=dict(status='PASS_SMALL_SYNTHETIC_RESIDENT_EQUIVALENCE',comparisons=comparisons,negative_cases_passed=9,
      arithmetic='UNCHANGED_LIVE_PV32',cache_capacity_bytes=262144,A_capacity_bytes=704512,metadata_bytes=512,
      local_outstanding_limit=1,local_minimum_response_edges=1,rtl='NOT_EXECUTED',m128='NOT_EXECUTED',fullblock='NOT_EXECUTED',ci='NOT_EXECUTED')
    save(out/'SAFE_PUBLIC.json',safe)
    need(sum(p.stat().st_size for p in out.rglob('*') if p.is_file())<32<<20,'output bound')
    print(json.dumps(dict(status=report['status'],comparisons=comparisons,cpu_seconds=report['host_cpu_seconds'])),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');p.add_argument('--out');a=p.parse_args()
    if a.execute:need(a.out is not None,'fresh work output required');run(a.out)
    else:print(json.dumps(dict(status='NOT_EXECUTED')))
