#!/usr/bin/env python3
"""Opt-in M1/M2 real-owner synthetic gate; no public21 or official acceptance."""
import argparse
from collections import Counter
from contextlib import nullcontext
from dataclasses import asdict,replace
import hashlib
import json
import os
from pathlib import Path
import resource
import struct
import sys
import time
import traceback
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from candidates.qwen2_live_attention_model_m128 import gates
from candidates.qwen2_live_attention_model_m128.runner import dependencies,save,require


def run(destination):
    resource.setrlimit(resource.RLIMIT_AS,(2<<30,2<<30))
    require(not sys.flags.optimize,'actual synthetic bus assertions must remain enabled')
    require(all(os.environ.get(k)=='1' for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS')),'one-thread environment')
    cpu=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpu})
    out=Path(destination).absolute();gates.fresh_output(out,ROOT/'work/qwen2_live_qkv_inputs_m128/frozen01');out.mkdir()
    started=time.monotonic();deadline=started+52
    report=dict(schema=1,status='STARTED_PV32_SMALL_OWNER',scope='synthetic real M1/M2 owner and negative protocol gates',
        official_numeric_executed=False,public21_executed=False,full_m128_executed=False,fullblock_pass=False,
        rtl_executed=False,new_matrix_profile=False,hardware_cycles=None,hardware_utilization=None,
        input_roles='locally generated synthetic q/k/v only',threads=1,affinity=[cpu],address_space_bytes=2<<30,outer_budget_seconds=60,cases=[])
    def checkpoint():save(out/'RESULT.json',report)
    checkpoint()
    try:
        r,dense,native,helper,original,fixtures,public,prefix,scalar,owner_module,binding,profiles,execution,suffix,observation=dependencies()
        from candidates.qwen2_resident_matrix.ffn_public.test_prefix_owners import Harness
        from candidates.qwen2_resident_matrix.ffn_public import prefix_owners as p
        from candidates.qwen2_resident_matrix.ffn_attention import matrix_service as m
        from candidates.qwen2_resident_matrix.official_bf16.owners import OfficialAttentionOwner
        from candidates.qwen2_live_attention_model_m128.pv32_owner import OfficialPV32AttentionOwner
        from candidates.qwen2_live_attention_model_m128.pv32_observation import PV32AttentionObservation
        sources=gates.sources()
        sources['candidates/qwen2_resident_matrix/ffn_public/test_prefix_owners.py']=gates.sha(ROOT/'candidates/qwen2_resident_matrix/ffn_public/test_prefix_owners.py')
        report['source_sha256_before']=sources
        library,build=dense.build_library(out/'build');report['compile']=build
        import numpy as np
        tools=dict(python=Path(sys.executable).resolve(),compiler=Path(build['compiler']['path']),library=Path(build['library']),numpy=Path(np._core._multiarray_umath.__file__).resolve())
        report['tools_before']={n:dict(path=str(pth),sha256=gates.sha(pth),bytes=pth.stat().st_size) for n,pth in tools.items()}
        checkpoint()
        initial_address=int(library.matrix_accumulator_address())
        def one(name,rows=1,*,old=False,observe=False,mode=None):
            require(time.monotonic()<deadline,'small-owner budget')
            require(library.td_reset()==0,'fresh synthetic owner reset')
            service=binding.ProfiledMatrixService(library,profiles.QWEN2_QKV_PROFILE);shared=scalar.ScalarService()
            owner=(OfficialAttentionOwner if old else OfficialPV32AttentionOwner)(service,shared);h=Harness(owner)
            job=p.Job('Attention',(11<<16)|12,0x100000,0x200000,0x400000,rows,1536,128,rows*1536*4,c=0x300000)
            q=tuple(scalar.word((i%17-8)/32) for i in range(rows*1536))
            k=tuple(scalar.word((i%13-6)/32) for i in range(rows*256))
            v=[scalar.word(((i%19-9)/32)+.0007) for i in range(rows*256)]
            if mode in ('low_nan','high_nan'):v[3 if mode=='low_nan' else 20]=0x7fc10000
            h.bus.input(job.a,q);h.bus.input(job.b,k);h.bus.input(job.c,v);h.bus.output(job.dst,job.write_bytes)
            capture=PV32AttentionObservation(owner,source_sha256=sources) if observe else None
            tick=0;injected=False;holds=0;borrow_checks=0;borrow_events=[];previous_borrow=False;request_at_borrow=None
            last_stall=5;start=time.monotonic()
            with capture if capture else nullcontext():
                require(h.tick(job=job)['job_fire'],'synthetic owner admission')
                while owner.ports()['response'] is None:
                    require(time.monotonic()<deadline and tick<200000,'small-owner deadline/tick cap')
                    kwargs=dict(memory_ready=tick%5!=0,matrix_request_ready=tick%7!=0,matrix_result_ready=tick%11!=0,
                        service_result_ready=tick%13!=0,service_done_ready=tick%17!=0)
                    pending=h.bus.pending;borrowed=getattr(owner,'pv32_borrowed',False)
                    if pending and pending.write and owner.ack_bytes+64==job.write_bytes and last_stall:
                        kwargs['respond']=False;last_stall-=1
                    if not injected and mode and mode not in ('low_nan','high_nan'):
                        half=64 if mode in ('high_wrongtag','high_error','abort_high_pending') else 0
                        at_write=pending is not None and pending.write and pending.address==job.dst+half
                        at_v_read=(pending is not None and not pending.write and
                            pending.address==job.c+(64 if mode.startswith('v_second_') else 0))
                        if mode.startswith(('v_first_','v_second_')) and at_v_read:
                            if mode.endswith('_abort'):
                                kwargs.update(local_reset=True,respond=False)
                            else:
                                response=h.bus.response()
                                if mode.endswith('_wrongtag'):response=replace(response,tag=response.tag+1)
                                elif mode.endswith('_short'):response=replace(response,nbytes=32,data=response.data[:32])
                                elif mode.endswith('_error'):response=replace(response,error=True)
                                else:raise ValueError('unknown V-read fault mode')
                                kwargs.update(response=response,respond=True)
                            injected=True
                        elif mode in ('low_wrongtag','high_wrongtag','low_error','high_error') and at_write:
                            response=h.bus.response();kwargs['response']=replace(response,tag=response.tag+1) if 'wrongtag' in mode else replace(response,error=True)
                            kwargs['respond']=True;injected=True
                        elif mode in ('abort_low_pending','abort_high_pending') and at_write:
                            kwargs.update(local_reset=True,respond=False);injected=True
                        elif mode=='abort_between_halves' and borrowed and owner.ack_bytes==64 and pending is None:
                            kwargs.update(local_reset=True);injected=True
                        elif mode=='wrong_matrix_done' and owner.matrix_client is not None and owner.matrix_client.state=='wait_done' and owner.matrix_client.request.opcode==0x24 and service.done is not None:
                            kwargs['done_override']=replace(service.done,tag=service.done.tag+1);kwargs['service_done_ready']=True;injected=True
                        elif mode=='error_done_without_result' and owner.matrix_client is not None and owner.matrix_client.state=='issue' and owner.matrix_client.request.opcode==0x24:
                            service.abort(owner);injected=True
                        elif mode=='intermediate_high_nan' and pending is not None and not pending.write and pending.address==job.c+64 and owner.ack_bytes>=1536*4:
                            words=list(struct.unpack('<16I',h.bus.response().data));words[4]=0x7fc10000
                            kwargs['response']=replace(h.bus.response(),data=struct.pack('<16I',*words));kwargs['respond']=True;injected=True
                    edge=h.tick(**kwargs);tick+=1
                    now=getattr(owner,'pv32_borrowed',False)
                    if edge.get('pv32_reply_borrow_fire'):
                        response=owner.matrix_client.ports()['result']
                        borrow_events.append(dict(tick=tick,ticket=response.ticket,epoch=response.epoch,reply_sha256=response.value.sha256,
                            ack_at_borrow=owner.ack_bytes,matrix_request_count=owner.counts['matrix_requests']))
                        request_at_borrow=owner.counts['matrix_requests']
                    if now and not owner.poison and owner.state not in ('drain','finish','locked'):
                        require(owner.counts['matrix_requests']==request_at_borrow,'new Matrix request while reply borrowed')
                        response=owner.matrix_client.ports()['result'];require(response is not None,'borrowed response missing')
                        require(response.value.sha256==owner.pv32_borrow_hash and
                            (response.ticket,response.epoch)==(borrow_events[-1]['ticket'],borrow_events[-1]['epoch']),'borrow identity/hash/ticket/epoch drift')
                        borrow_checks+=1
                        if pending and pending.write and kwargs.get('respond') is False:holds+=1
                    previous_borrow=now
                result=owner.ports()['response']
                require(h.bus.pending is None and shared.client is None,'terminal before memory/Scalar drain')
                require(owner.matrix_client is None or owner.matrix_client.drained,'terminal before Matrix client drain')
                held=result
                for _ in range(3):
                    h.tick();require(owner.ports()['response']==held,'held terminal changed')
                require(h.tick(response_ready=True)['response_fire'],'owner terminal retirement')
            require(h.bus.pending is None and service.owner is None and shared.client is None and owner.matrix_client is None,'accepted debts remained')
            require(library.matrix_state() in (0,256),'unexpected C state after drained terminal')
            require(int(library.matrix_accumulator_address())==initial_address and library.matrix_accumulator_bytes()==81920,'physical resource changed')
            raw=h.bus.raw(job.dst);complete=result.status is None
            require(not h.bus.readable.intersection(h.bus.outputs[job.dst]),'synthetic output unexpectedly published')
            if complete:
                require(len(h.bus.acked)*64==job.write_bytes and not last_stall,'successful complete ACK coverage/hold')
                require(all((w&0xffff)==0 and scalar.finite(w) for w in struct.unpack('<%dI'%(len(raw)//4),raw)),'non-BF16/nonfinite final output')
            item=dict(name=name,rows=rows,old_original_owner=old,observer_enabled=observe,mode=mode,
                status='PASS_SUCCESS' if complete else 'EXPECTED_OWNER_FAULT',terminal=asdict(result),ticks=tick,
                seconds=time.monotonic()-start,owner=owner.report(),matrix=service.report(),scalar_calls=dict(shared.calls),
                memory=dict(read_events=len(h.bus.reads),write_events=len(h.bus.writes),ack_beats=len(h.bus.acked),
                    ack_bytes=len(h.bus.acked)*64,read_addresses=h.bus.reads[:80],output_published=False),
                output_sha256=hashlib.sha256(raw).hexdigest(),publication_rejection_executed=False,borrow_checks=borrow_checks,borrow_events=borrow_events,
                final_ack_hold_ticks=5-last_stall,borrow_memory_hold_checks=holds,injected=injected,
                final_c_state=int(library.matrix_state()),same_accumulator_address=True)
            if capture:
                item['observation']=capture.save(out/(name+'_observation'))
                require(item['observation']['status'].startswith('COMPLETE_'),'new observation incomplete: '+str(item['observation'].get('observer_error')))
                pv=np.frombuffer(capture._bytes('pv_bf16'),dtype='<u4').reshape(12,rows,128)
                require(pv.transpose(1,0,2).copy().tobytes()==raw,'captured BF16 PV != actual ACKed bytes')
            report['cases'].append(item);checkpoint()
            return item,raw
        for rows in (1,2):
            old,a=one('original_m'+str(rows),rows,old=True)
            new,b=one('pv32_m'+str(rows),rows)
            observed,c=one('pv32_observed_m'+str(rows),rows,observe=True)
            require(a==b==c,'original/PV32/observed final BF16 bytes differ')
            require(new['owner']==observed['owner'] and new['matrix']==observed['matrix'] and new['scalar_calls']==observed['scalar_calls'] and
                new['ticks']==observed['ticks'],'observer changed owner/service/scalar counters or state')
            pairs=12*rows*(rows+1)//2
            require(new['terminal']['executed_macs']==pairs*12*512 and new['terminal']['useful_macs']==pairs*256,'new true MAC count')
            require(new['memory']['read_events']==old['memory']['read_events'] and new['memory']['write_events']==old['memory']['write_events'],'DDR transaction bytes changed')
        for mode in ('low_nan','high_nan','intermediate_high_nan','low_wrongtag','high_wrongtag','low_error','high_error',
                     'abort_low_pending','abort_high_pending','abort_between_halves','wrong_matrix_done','error_done_without_result',
                     'v_first_wrongtag','v_second_wrongtag','v_first_short','v_second_short','v_first_error','v_second_error','v_second_abort'):
            item,_=one(mode,2 if mode=='intermediate_high_nan' else 1,mode=mode)
            expected='Numerical' if 'nan' in mode else 'Memory' if mode in ('low_error','high_error','v_first_error','v_second_error') else 'Protocol'
            require(item['terminal']['status']==expected,'wrong fault classification '+mode)
            require(item['injected'] or mode in ('low_nan','high_nan'),'fault injection point not reached '+mode)
            if mode in ('low_nan','high_nan','low_wrongtag','low_error'):require(item['memory']['ack_bytes']==0,'unexpected failed prefix '+mode)
            if mode in ('high_wrongtag','high_error','abort_between_halves'):require(item['memory']['ack_bytes']==64,'wrong legal low-only prefix '+mode)
            if mode.startswith(('v_first_','v_second_')):require(item['memory']['ack_bytes']==0,'unexpected V-read failed prefix '+mode)
            if mode=='intermediate_high_nan':require(item['memory']['ack_bytes']==6144,'intermediate PV rejection prefix')
        original_fault,_=one('original_high_nan',old=True,mode='high_nan')
        require(original_fault['memory']['ack_bytes']==64,'original high-half late fault prefix changed')
        # A final -0 actual Matrix result. Explicit generic stress, not legal softmax-domain.
        require(library.td_reset()==0,'negative-zero direct reset');service=binding.ProfiledMatrixService(library,profiles.QWEN2_QKV_PROFILE)
        who=object();require(service.acquire(who,'normal',3101),'negative-zero service acquire');client=m.LegacyMatrixClient(service,who)
        req=m.LegacyRequest(0x24,(0x8001,)+(0,)*15,(0x0001,)*32+(0,)*224,True,True,1)
        require(client.tick(request=req)['request_fire'],'negative-zero real step')
        for _ in range(20):
            if client.ports()['result'] is not None:break
            client.tick()
        reply=client.ports()['result'];require(reply is not None and all(reply.value[0][i]==0x80000000 for i in range(32)),'final negative-zero actual sample')
        require(client.tick(result_ready=True)['result_fire'],'negative-zero reply retire');service.retire_owner_response(who);service.release(who)
        report['final_negative_zero']=dict(status='PASS',selected_word='0x80000000',columns=32,actual_fma=512,
            domain='direct profile0 negative tiny probability stress, not legal softmax',matrix=service.report())
        report['source_sha256_after']={n:gates.sha(ROOT/n) for n in sources}
        report['tools_after']={n:dict(path=str(pth),sha256=gates.sha(pth),bytes=pth.stat().st_size) for n,pth in tools.items()}
        require(report['source_sha256_after']==sources and report['tools_after']==report['tools_before'],'small-owner source/tool drift')
        for rel,digest in sources.items():
            raw=(ROOT/rel).read_bytes();require(hashlib.sha256(raw).hexdigest()==digest,'freeze drift')
            target=out/'frozen_sources'/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        report.update(status='PASS_PV32_SMALL_OWNER_AND_NEGATIVES_ONLY',host_wall_seconds=time.monotonic()-started,
            peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            changed_fault_prefix_contract='all32 selected finite checks precede final low16 write; old2group high-half fault can leave low64B ACKed',
            observer_four_probability_repeats=True,fullchunk_still_required=True)
        checkpoint();print(json.dumps({k:report[k] for k in ('status','host_wall_seconds','peak_rss_kib')}),flush=True)
    except BaseException as error:
        report.update(status='FAILED_PV32_SMALL_OWNER',error=repr(error),traceback=traceback.format_exc(),host_wall_seconds=time.monotonic()-started)
        checkpoint();raise


def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--actual-small',action='store_true');ap.add_argument('--out');a=ap.parse_args(argv)
    if not a.actual_small:
        require(a.out is None,'out needs --actual-small');print(json.dumps(dict(status='NOT_EXECUTED',small_owner_only=True)));return 0
    require(a.out is not None,'fresh output required');run(a.out);return 0
if __name__=='__main__':raise SystemExit(main())
