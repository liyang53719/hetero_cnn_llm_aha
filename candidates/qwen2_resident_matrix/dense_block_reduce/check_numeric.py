#!/usr/bin/env python3
"""Bounded actual K-window -> same-bank Add -> DDR/ACK numerical closure.

The archived full-shape reference is opened only after real writes retire.
This is a source-bound host arithmetic/port model, not public21 or RTL.
No partial sum, expected result or intermediate initializes the SRAM.
"""
from dataclasses import asdict, replace
from pathlib import Path
import argparse
import ctypes as C
import hashlib
import json
import os
import struct
import sys
import time

import numpy as np
from .dense_drain import DenseReductionOwner, DenseDrainRequest, Job, drain
from .k_window_model import KWindowRequest
from .test_k_window import ActualMatrixHarness
from .sum_tiles import SumInvocation, TileSumController, shared_loan_edge
from .vector_add_model import VectorLoanModel
from ..ffn_attention.matrix_service import MatrixService, configure_library
from ..ffn_drain.test_model import Harness as DrainHarness
from ..ffn_public.prefix_owners import Job as PublicJob
from .matrix_binding import ProfiledMatrixService
from .profile import QWEN2_QKV_PROFILE

ROOT=Path(__file__).resolve().parents[3]
AUDIT=ROOT/'work/qwen2_official_public21_20261012/qkv_reduction_shape_audit'
MANIFEST_SHA='c1660db521f50b10f87bf0ae943aad304b170628aa0eb8e587d23a8e9deacffd'
ELF=ROOT/'work/qwen2_official_public21_20261012/library_01/official_bf16_matrix_silu.so'
ELF_SHA='bcab4d36ae7990bf6b40c08866066b563d8c6c09fb134a2393d8268505c89c7f'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def require(ok,message):
    if not ok:raise ValueError(message)


def execute_window(service, rows, n, ng, cols, x, weights, blocks, *, deadline, final_ack_delay=7):
    """One original-stride QKV window; only real accepted packets feed FPUs."""
    require(len(blocks)==2 and sum(blocks)==1536 and all(b>0 and b%2==0 for b in blocks),
            'current three-slot mechanism requires two complete even K ranges')
    owner=DenseReductionOwner(drain.PrefixWorkspace(0x10000000,786432,11),
        enable_dense_drain=True,enable_k_window=True,enable_ffn_drain=True,
        enable_ffn_window=True,enable_ffn_tiles=True)
    physical=owner.a_banks
    job=Job(m=rows,k=1536,n=n,tag=13,a=0x100000,b=0x400000,dst=0x4000000,
            activation_bf16=False,weight_bf16=True,write_bytes=rows*n*4)
    original_input_hash=hashlib.sha256(x.tobytes()+weights.tobytes()).hexdigest()
    def source(kind,row,col):
        return int(x[row,col]) if kind=='a' else int(weights[col,row]>>16)
    h=ActualMatrixHarness(instance=owner,service=service,source=source)
    matrix_before=dict(service.report()['counters']);fma_before=service.report()['dense_fma_calls']
    partials=[]
    start=0
    for index,size in enumerate(blocks):
        request=KWindowRequest(job,7,ng,cols,index,bool(index),k_begin=start,
                              k_end=start+size,block_id=index+1,pair_reverse=True)
        h.submit(request)
        while h.completion is None:
            require(time.monotonic()<=deadline,'K-window bounded host wall budget')
            h.cycle()
        require(h.completion.status is None and service.owner is None,'partial failed/Matrix not retired')
        partials.append(asdict(h.completion));start+=size
    require(owner.k_a_fences==1 and owner.tiles.banks is physical,'full A lease reloaded/replaced')
    require(all(owner.tiles.tags[i].sealed and owner.tiles.tags[i].consumed==0 for i in (0,1)),
            'partial was observed/consumed before actual Add')
    matrix_counts=dict(service.report()['counters'])
    sum_controller=TileSumController(owner.tiles)
    loan=VectorLoanModel(lane_latency=2)
    call=SumInvocation(7,ng,rows,cols)
    # The exclusive grant begins only after the actual owner/Matrix retirement.
    require(owner.state=='idle' and service.owner is None,'bank grant before owner retirement')
    require(shared_loan_edge(sum_controller,loan,start=call)['start_fire'],'sum admission')
    for count in range(call.beats*40+100):
        require(time.monotonic()<=deadline,'Add bounded host wall budget')
        edge=shared_loan_edge(sum_controller,loan,bank_ready=count%7!=0)
        require(not sum_controller.poison,'actual shared Add failed')
        if edge['complete']:break
    else:raise ValueError('sum protocol watchdog')
    require(service.report()['counters']==matrix_counts,'Matrix used during shared-vector Add')
    require(owner.a_banks is physical and owner.tiles.banks is physical,'sum replaced SRAM')
    q=DenseDrainRequest(job,7,ng,cols)
    output=DrainHarness(q,owner,seed=False)
    output.submit()
    delay=final_ack_delay
    final_acked=False
    for count in range(rows*cols*20+100):
        require(time.monotonic()<=deadline,'DDR drain bounded host wall budget')
        final=output.ack is not None and len(output.memory)*4==rows*cols*4
        hold=bool(final and delay)
        if hold:
            require(owner.ports()['drain_result'] is None and owner.tiles.tags[2].live,
                    'resident output/public result released before real final ACK')
            delay-=1
        edge=output.cycle(ack=not hold,write_command_ready=count%5!=0,write_data_ready=count%7!=0)
        final_acked |= bool(final and edge['write_ack_fire'])
        if output.completion is not None:break
    else:raise ValueError('drain protocol watchdog')
    result=output.completion
    require(final_acked and delay==0 and result.committed and result.status is None and
            result.ddr_write_bytes==rows*cols*4,'actual ACK/publication boundary')
    require(not owner.tiles.leased and owner.tiles.idle,'resident tile release missing')
    require(owner.a_banks is physical and owner.tiles.banks is physical,'drain replaced SRAM')
    require(hashlib.sha256(x.tobytes()+weights.tobytes()).hexdigest()==original_input_hash,'readonly source changed')
    actual=np.array([output.memory[job.dst+(r*n+ng+c)*4] for r in range(rows)
                     for c in range(cols)],dtype='<u4').reshape(rows,cols)
    expected_addresses={job.dst+(r*n+ng+c)*4 for r in range(rows) for c in range(cols)}
    require(set(output.memory)==expected_addresses,'actual destination coverage/alias')
    after=service.report();counters=after['counters']
    return actual,dict(partials=partials,completion=asdict(result),matrix=after,
        matrix_counters_scope='cumulative across this execution service; per-window delta is separate',
        matrix_counter_delta={k:counters.get(k,0)-matrix_before.get(k,0) for k in counters.keys()|matrix_before.keys()},
        actual_window_fma_calls=after['dense_fma_calls']-fma_before,
        vector_add= dict(sum_controller.counts),physical_tile_counters=dict(owner.tiles.counters),
        ddr_commands=len(output.commands),ddr_acks=len(output.acks),final_ack_held_ticks=final_ack_delay,
        retained_A_fences=owner.k_a_fences,source_reads=len(h.commands),accepted_matrix_steps=len(h.steps),
        resource=dict(A_banks=16,A_depth=1376,B_banks=16,B_depth=160,bank_word_bits=256,
            bank_ports='one synchronous read and one write per bank',extra_sram_bytes=0,
            sum_lhs_register_bits=512,shared_vector_lanes=16),hardware_cycles=None,
        public_Command128_chain_executed=False,rtl_executed=False)


def run(out,cases):
    out=Path(out).resolve();require(not out.exists(),'fresh result directory required')
    require(sha(AUDIT/'MANIFEST.json')==MANIFEST_SHA,'archived numerical audit manifest drift')
    manifest=json.loads((AUDIT/'MANIFEST.json').read_text())
    require(sha(ELF)==ELF_SHA,'actual shared Matrix source ELF drift')
    out.mkdir(parents=True)
    loaded={Path(m.__file__).resolve() for m in tuple(sys.modules.values())
            if getattr(m,'__file__',None) and str(m.__file__).endswith('.py')}
    source={str(p.relative_to(ROOT)):sha(p) for p in sorted(loaded)
            if p.is_relative_to(ROOT) and not p.is_relative_to(ROOT/'work')}
    report=dict(status='STARTED',input_manifest_sha256=MANIFEST_SHA,library_sha256=ELF_SHA,
        source_sha256=source,cases=[],official_whole_block_acceptance=False,rtl_executed=False)
    save=lambda:(out/'summary.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    def verified(relative):
        path=AUDIT/relative;entry=manifest[relative]
        require(path.stat().st_size==entry['bytes'] and sha(path)==entry['sha256'],'frozen audit file drift: '+relative)
        return path
    start=time.monotonic();deadline=start+120
    try:
        lib=configure_library(C.CDLL(str(ELF)));require(lib.td_reset()==0,'Matrix reset')
        service=ProfiledMatrixService(lib,QWEN2_QKV_PROFILE)
        for name,ng,cols in cases:
            nr=json.loads(verified(name+'/NATIVE_RESULT.json').read_text())
            profile=json.loads(verified(name+'/PROFILE.json').read_text())
            rows,n=nr['M'],nr['N']
            x=np.fromfile(verified(name+'/n0.f32le'),dtype='<u4').reshape(rows,1536)
            w=np.fromfile(verified(name+'/weight.f32le'),dtype='<u4').reshape(n,1536)
            require(not np.any(x&65535) and not np.any(w&65535),'source not exact BF16 expanded')
            blocks=profile['block_sizes']
            require(blocks==[k['k_extent'] for k in profile['kernels'] if k['old_fp32_scratch_adds']==0],
                    'K profile does not agree with code-derived independent partial kernels')
            # Different public jobs keep distinct tags/bindings in real launches.
            # This bounded leaf capture creates one fresh service per fixture
            # over the same explicitly reset Matrix ELF and verifies identity.
            if report['cases']:
                require(service.owner is None and lib.td_reset()==0,'fixture coordinated Matrix reset')
                service=ProfiledMatrixService(lib,QWEN2_QKV_PROFILE)
            public=PublicJob('Dense',13,0x100000,0x400000,0x4000000,rows,n,1536,rows*n*4,
                             weight_bf16=True)
            role={'q':'q_raw','k':'k_raw','v':'v_raw'}[nr['projection']]
            service.bind_dense_job(public,role)
            actual,record=execute_window(service,rows,n,ng,cols,x,w,blocks,deadline=deadline)
            # Read independent complete-shape reference only AFTER real DDR ACK.
            gold=np.fromfile(verified(name+'/model_qraw.f32le'),dtype='<u4').reshape(rows,n)[:,ng:ng+cols]
            mismatch=int(np.count_nonzero(actual!=gold))
            require(mismatch==0,'source-profile raw FP32 output differs')
            path=out/(name+'_'+str(ng)+'_actual.f32le');actual.tofile(path)
            record.update(case=name,rows=rows,full_N=n,window_N=cols,ng=ng,raw_values=actual.size,
                raw_fp32_bit_mismatches=mismatch,output_sha256=sha(path),
                reference_full_shape_sha256=manifest[name+'/model_qraw.f32le']['sha256'],
                profile_sha256=manifest[name+'/PROFILE.json']['sha256'])
            report['cases'].append(record);save()
        require(source=={p:sha(ROOT/p) for p in source},'candidate source changed during actual arithmetic capture')
        report['status']='PASS_ACTUAL_TWO_PARTIAL_SUM_DDR_MODEL_ONLY'
    except Exception as exc:
        report.update(status='FAIL',error=str(exc));raise
    finally:
        report['wall_seconds']=time.monotonic()-start;save()
    return report


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args()
    result=run(args.out,[('m16_q',1152,32),('m16_k',224,32),('m16_v',224,32)])
    print(json.dumps(dict(status=result['status'],seconds=result['wall_seconds'],cases=len(result['cases']))))
