#!/usr/bin/env python3
"""Opt-in, synthetic profile0 budget calibration; no QKV, official or public21 PASS."""
import argparse
from collections import Counter
from dataclasses import asdict
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import resource
import sys
import time
import traceback
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from candidates.qwen2_live_attention_model_m128 import gates
from candidates.qwen2_live_attention_model_m128.runner import dependencies,save,require


def run(out):
    resource.setrlimit(resource.RLIMIT_AS,(2<<30,2<<30))
    require(not sys.flags.optimize,'synthetic harness assertions require normal CPython')
    require(all(os.environ.get(n)=='1' for n in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS')),'one thread environment required')
    cpu=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpu})
    out=Path(out).absolute();gates.fresh_output(out,ROOT/'work/qwen2_live_qkv_inputs_m128/frozen01');out.mkdir()
    started=time.monotonic();deadline=started+38
    report=dict(status='STARTED_BUDGET_ONLY',scope='synthetic fixed profile0 calibration only',
        official_numeric_executed=False,qkv_executed=False,public21_executed=False,hardware_cycles=None,
        hardware_utilization=None,resource_shape=[5,16,256],accumulator_bytes=81920,threads=1,
        affinity=[cpu],address_space_bytes=2<<30,outer_budget_seconds=45,internal_budget_seconds=38)
    def checkpoint():save(out/'RESULT.json',report)
    checkpoint()
    try:
        r,dense,native,helper,original,fixtures,public,prefix,scalar,owner_module,binding,profiles,execution,suffix,observation=dependencies()
        from candidates.qwen2_resident_matrix.ffn_attention import matrix_service as m
        from candidates.qwen2_resident_matrix.ffn_public import prefix_owners as p
        from candidates.qwen2_resident_matrix.ffn_public.test_prefix_owners import Harness
        from candidates.qwen2_resident_matrix.official_bf16.owners import OfficialAttentionOwner
        sources=gates.sources()
        for name in ('candidates/qwen2_resident_matrix/ffn_public/test_prefix_owners.py',):sources[name]=gates.sha(ROOT/name)
        report['source_sha256_before']=sources
        library,build=dense.build_library(out/'build');report['compile']=build
        import numpy as np
        tool_paths=dict(python=Path(sys.executable).resolve(),compiler=Path(build['compiler']['path']),
            library=Path(build['library']),numpy_multiarray=Path(np._core._multiarray_umath.__file__).resolve())
        report['tools_before']={n:dict(path=str(p),sha256=gates.sha(p),bytes=p.stat().st_size) for n,p in tool_paths.items()}
        report['tool_versions']=dict(python=sys.version,numpy=np.__version__,compiler=build['compiler']['version'])
        checkpoint()
        a_q=(C.c_uint16*16)(*([0x3f00]*16));a_p=(C.c_uint16*16)(0x3e00,*([0]*15))
        b=(C.c_uint16*256)(*([0x3f00]*16+[0]*240));output=(C.c_uint32*4096)()
        require(library.td_reset()==0 and library.matrix_guard_enable()==0,'fresh raw ABI reset/guard')
        require(library.matrix_accumulator_bytes()==81920,'resource denominator changed')
        address=int(library.matrix_accumulator_address());tag=1901
        require(library.matrix_acquire(2,tag)==0,'raw ABI acquisition')
        raw=[];total_step_time=0.0
        for opcode,steps,groups,a in ((0x23,8,256,a_q),(0x24,128,16,a_p)):
            start=time.monotonic();step_time=0;before=int(library.matrix_normal_fmas());counts=Counter()
            for group in range(groups):
                require(time.monotonic()<deadline,'calibration deadline')
                group_tag=1000+len(raw)*1000+group
                require(library.matrix_normal_group(opcode,steps,group_tag,1)==0,'profile0 raw group')
                ticket=library.matrix_ticket();counts['groups']+=1
                for index in range(steps):
                    last=index+1==steps;t=time.perf_counter()
                    rc=library.matrix_normal_step(index,0,index==0,last,last,1,a,b,output)
                    step_time+=time.perf_counter()-t
                    require(rc==1,'raw step result');counts['steps']+=1
                    require(library.matrix_result_retire(ticket,0,last)==0,'raw result retire');counts['results']+=1
                    if last:
                        require(library.matrix_done_ready()==1 and library.matrix_done_retire(ticket,group_tag,0)==0,'raw done retire')
                        counts['done']+=1
                    require(library.matrix_legacy_reply_retire(ticket)==0,'raw legacy reply retire');counts['legacy_replies']+=1
            calls=int(library.matrix_normal_fmas())-before
            require(calls==counts['steps']*512,'profile0 executed FMA is 16x32 per accepted step')
            raw.append(dict(opcode=hex(opcode),steps_per_group=steps,accepted=dict(counts),
                c_fma_calls=calls,elapsed_seconds=time.monotonic()-start,c_step_call_seconds=step_time,
                c_timing_scope='ctypes call plus native matrix_normal_step, includes FMA counter and output zeroing',
                selected_lane_useful_fmas=counts['steps']*16,output_sha256=hashlib.sha256(bytes(output)).hexdigest()))
            total_step_time+=step_time
        require(library.matrix_owner_reply_retire(2,tag)==0 and library.matrix_release(2,tag)==0 and library.matrix_state()==0,'raw ABI debts not drained')
        report['raw_abi']=raw;checkpoint()
        require(library.td_reset()==0,'fresh independent service calibration reset')
        service=binding.ProfiledMatrixService(library,profiles.QWEN2_QKV_PROFILE);owner=object()
        require(service.acquire(owner,'normal',1902),'original service acquire');client=m.LegacyMatrixClient(service,owner)
        service_traces=[]
        for opcode,steps,groups,a in ((0x23,8,256,tuple(a_q)),(0x24,128,16,tuple(a_p))):
            before=int(library.matrix_normal_fmas());start=time.monotonic();counts=Counter()
            for _ in range(groups):
                for index in range(steps):
                    require(time.monotonic()<deadline,'calibration deadline')
                    request=m.LegacyRequest(opcode,a,tuple(b),index==0,index+1==steps,steps)
                    require(client.tick(request=request)['request_fire'],'real legacy request fire');counts['requests']+=1
                    while client.ports()['result'] is None:
                        client.tick();counts['wait_ticks']+=1
                    require(not client.ports()['result'].error,'real legacy result error')
                    require(client.tick(result_ready=True)['result_fire'],'real legacy result fire');counts['results']+=1
            service_traces.append(dict(opcode=hex(opcode),steps_per_group=steps,accepted=dict(counts),
                c_fma_calls=int(library.matrix_normal_fmas())-before,elapsed_seconds=time.monotonic()-start))
        require(client.drained,'legacy client debts');service.retire_owner_response(owner);service.release(owner)
        require(service.owner is None and library.matrix_state()==0,'legacy service debts')
        report['original_service']=dict(traces=service_traces,report=service.report(),
            same_accumulator_address=int(library.matrix_accumulator_address())==address)
        checkpoint()
        # Explicit synthetic launch. No metadata/prefix state or saved producer is used.
        require(library.td_reset()==0,'fresh synthetic owner reset')
        service=binding.ProfiledMatrixService(library,profiles.QWEN2_QKV_PROFILE);shared=scalar.ScalarService()
        backend=OfficialAttentionOwner(service,shared);h=Harness(backend);rows=8
        job=p.Job('Attention',(9<<16)|12,0x100000,0x200000,0x400000,rows,1536,128,rows*1536*4,c=0x300000)
        q=tuple(scalar.word((i%17-8)/32) for i in range(rows*1536))
        k=tuple(scalar.word((i%13-6)/32) for i in range(rows*256))
        v=tuple(scalar.word((i%19-9)/32) for i in range(rows*256))
        h.bus.input(job.a,q);h.bus.input(job.b,k);h.bus.input(job.c,v);h.bus.output(job.dst,job.write_bytes)
        capture=observation.ProfiledAttentionMonitoringObservation(backend,source_sha256=sources)
        start=time.monotonic();ticks=0;final_stall=5
        with capture:
            require(h.tick(job=job)['job_fire'],'synthetic owner request')
            while backend.ports()['response'] is None:
                require(time.monotonic()<deadline,'calibration deadline')
                pending=h.bus.pending;respond=True
                if pending and pending.write and backend.ack_bytes+64==job.write_bytes and final_stall:
                    final_stall-=1;respond=False
                h.tick(memory_ready=ticks%5!=0,respond=respond,matrix_request_ready=ticks%7!=0,
                    matrix_result_ready=ticks%11!=0,service_result_ready=ticks%13!=0,service_done_ready=ticks%17!=0)
                ticks+=1
            result=backend.ports()['response'];require(result.status is None,'synthetic owner failure '+str(result))
            require(h.tick(response_ready=True)['response_fire'],'synthetic terminal retire')
        elapsed=time.monotonic()-start
        require(backend.state=='idle' and backend.matrix_client is None and service.owner is None and shared.client is None and
            h.bus.pending is None and library.matrix_state()==0 and not final_stall,'synthetic obligations not drained')
        observation_report=capture.save(out/'synthetic_m8_observation')
        require(observation_report['status'].startswith('COMPLETE_'),'synthetic observation incomplete')
        require(result.executed_macs==6912*512 and result.useful_macs==6912*16,'synthetic M8 actual counter mismatch')
        report['synthetic_m8']=dict(job=asdict(job),terminal=asdict(result),elapsed_seconds=elapsed,driver_ticks=ticks,
            owner=backend.report(),matrix=service.report(),scalar_calls=dict(shared.calls),observation=observation_report,
            memory=dict(read_request_events=len(h.bus.reads),write_request_events=len(h.bus.writes),
                ack_64b_coverage=len(h.bus.acked),final_ack_stall_ticks=5),
            output_sha256=hashlib.sha256(h.bus.raw(job.dst)).hexdigest(),output_publication=False,
            same_accumulator_address=int(library.matrix_accumulator_address())==address)
        full_requests=1585152
        report['m128_prediction_only']=dict(matrix_requests=full_requests,causal_pairs=99072,
            useful_lane_fmas=25362432,actual_profile0_fma_calls=full_requests*512,
            active_slice_fill=16/512,all_eight_slice_opportunity_fill=16/4096,
            fixed_accumulator_bytes=81920,hardware_busy_fraction=None,
            c_call_seconds_at_measured_rate=total_step_time/4096*full_requests,
            legacy_service_seconds_at_measured_rate=sum(z['elapsed_seconds'] for z in service_traces)/4096*full_requests,
            owner_with_observer_seconds_pair_scaled=elapsed*full_requests/6912,
            qkv_prior_seconds_separate_historical=78.54352224399918,
            limitations=['Synthetic M8 input distribution; scalar cutoff/control differs from official data',
                'Pair scaling overweights per-row work for M128; service/raw rates omit public metadata and memory',
                'Host wall time only; no hardware cycle, occupancy or utilization estimate'])
        report['source_sha256_after']={n:gates.sha(ROOT/n) for n in sources}
        report['tools_after']={n:dict(path=str(p),sha256=gates.sha(p),bytes=p.stat().st_size) for n,p in tool_paths.items()}
        require(report['source_sha256_after']==sources and report['tools_after']==report['tools_before'],'calibration source/tool drift')
        report.update(status='PASS_SYNTHETIC_PROFILE0_BUDGET_CALIBRATION_ONLY',host_wall_seconds=time.monotonic()-started,
            peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        checkpoint();print(json.dumps({k:report[k] for k in ('status','host_wall_seconds','m128_prediction_only')}),flush=True)
    except BaseException as e:
        report.update(status='FAILED_BUDGET_CALIBRATION',error=repr(e),traceback=traceback.format_exc(),
            host_wall_seconds=time.monotonic()-started)
        checkpoint();raise


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--calibrate',action='store_true');ap.add_argument('--out')
    a=ap.parse_args()
    if not a.calibrate:
        require(a.out is None,'out requires --calibrate');print(json.dumps(dict(status='NOT_EXECUTED',synthetic_only=True)));return
    require(a.out,'fresh output required');run(a.out)

if __name__=='__main__':main()
