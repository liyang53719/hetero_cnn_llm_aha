#!/usr/bin/env python3
"""Small opt-in profile0 PV32 equivalence/lifecycle trace, never an Attention owner."""
import argparse
from collections import Counter
import ctypes as C
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import struct
import sys
import time
import traceback
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from candidates.qwen2_live_attention_model_m128 import gates
from candidates.qwen2_live_attention_model_m128.runner import dependencies,save,require


def validate_width(width):
    require(type(width) is int and width in (16,32),'short trace width must be exactly16 or32')
    return width


def validate_tail(count,length):
    require(type(count) is int and type(length) is int and 0<count<=length<=128,'bounded nonempty causal prefix required')
    return count


def run(destination):
    resource.setrlimit(resource.RLIMIT_AS,(2<<30,2<<30))
    require(not sys.flags.optimize,'actual source test bus uses active assertions')
    require(all(os.environ.get(k)=='1' for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS')),'single-thread environment required')
    cpu=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpu})
    out=Path(destination).absolute();gates.fresh_output(out,ROOT/'work/qwen2_live_qkv_inputs_m128/frozen01');out.mkdir()
    started=time.monotonic();deadline=started+50
    report=dict(schema=1,status='STARTED_PV32_SHORT_TRACE_ONLY',scope='original profile0 two16 vs one32 synthetic packet equivalence',
        full_attention_executed=False,public21_executed=False,official_numeric_executed=False,new_profile=False,new_owner=False,
        new_matrix_or_scalar_or_vector_instance=False,hardware_cycles=None,hardware_utilization=None,
        outer_budget_seconds=60,address_space_bytes=2<<30,threads=1,affinity=[cpu],cases=[])
    def checkpoint():save(out/'RESULT.json',report)
    checkpoint()
    try:
        r,dense,native,helper,original,fixtures,public,prefix,scalar,owner_module,binding,profiles,execution,suffix,observation=dependencies()
        from candidates.qwen2_resident_matrix.ffn_attention import matrix_service as m
        from candidates.qwen2_resident_matrix.ffn_public import prefix_owners as p
        from candidates.qwen2_resident_matrix.ffn_public.test_prefix_owners import Bus,exact,rn
        sources=gates.sources()
        for name in ('candidates/qwen2_resident_matrix/ffn_public/test_prefix_owners.py',):sources[name]=gates.sha(ROOT/name)
        report['source_sha256_before']=sources
        library,build=dense.build_library(out/'build');report['compile']=build
        require(library.td_reset()==0,'fresh Matrix reset');service=binding.ProfiledMatrixService(library,profiles.QWEN2_QKV_PROFILE)
        shared=scalar.ScalarService();owner=object();require(service.acquire(owner,'normal',2901),'shared service acquisition')
        client=m.LegacyMatrixClient(service,owner)
        address=int(library.matrix_accumulator_address())
        require(library.matrix_accumulator_bytes()==81920,'fixed accumulator extent')
        report['resource']=dict(shape=[5,16,256],bytes=81920,address=address,selected_slices=1,
            test_result_hold='original LegacyMatrixClient held full immutable reply; only one16word selected write hold',
            new_32word_output_accumulator=False,resident_tile_slots_used=0,vector_loan_instantiated=False)
        # fenv observer is a separate tiny probe, never an arithmetic producer.
        probe=out/'fenv_probe.cpp';probe.write_text('#include <cfenv>\nextern "C" void clear_flags(){std::feclearexcept(FE_ALL_EXCEPT);}\nextern "C" int read_flags(){return std::fetestexcept(FE_ALL_EXCEPT);}\nextern "C" int flag_mask(int n){switch(n){case 0:return FE_INVALID;case 1:return FE_DIVBYZERO;case 2:return FE_OVERFLOW;case 3:return FE_UNDERFLOW;case 4:return FE_INEXACT;default:return FE_ALL_EXCEPT;}}\n')
        compiler=build['compiler']['path'];probe_library=out/'fenv_probe.so'
        cmd=[compiler,'-shared','-fPIC','-O2',str(probe),'-o',str(probe_library)]
        built=subprocess.run(cmd,capture_output=True,text=True,timeout=15)
        require(built.returncode==0,'fenv probe build failed '+built.stderr)
        fenv=C.CDLL(str(probe_library));fenv.clear_flags.argtypes=[];fenv.clear_flags.restype=None
        fenv.read_flags.argtypes=[];fenv.read_flags.restype=C.c_int;fenv.flag_mask.argtypes=[C.c_int];fenv.flag_mask.restype=C.c_int
        report['fenv_probe']=dict(argv=cmd,source_sha256=gates.sha(probe),library_sha256=gates.sha(probe_library),
            meaning='host aggregate exceptions across selected physical512cells only; not per-lane RTL flags or owner rejection',
            masks={n:fenv.flag_mask(i) for i,n in enumerate(('invalid','divide_by_zero','overflow','underflow','inexact'))})
        import numpy as np
        tool_paths=dict(python=Path(sys.executable).resolve(),compiler=Path(compiler),library=Path(build['library']),
            numpy=Path(np._core._multiarray_umath.__file__).resolve(),fenv_probe=probe_library)
        report['tools_before']={n:dict(path=str(v),sha256=gates.sha(v),bytes=v.stat().st_size) for n,v in tool_paths.items()}
        checkpoint()
        def group(probabilities,values,width,offset=0,*,unselected_nan=False,inactive_nan=False,write_held=False):
            validate_width(width);steps=len(probabilities);count=Counter();outputs=[];flags=0;holds=[];before=int(library.matrix_normal_fmas())
            bus=Bus();base=0x600000;bus.output(base,width*4)
            scalar_before=Counter(shared.calls)
            for key,(prob,v) in enumerate(zip(probabilities,values)):
                require(time.monotonic()<deadline,'bounded trace deadline')
                a=(prob,)+(0x7fc1 if unselected_nan else 0,)+(0,)*14
                b=tuple(v[offset:offset+width])+(0,)*(256-width)
                if inactive_nan:b=b[:200]+(0x7fc1,)+b[201:]
                req=m.LegacyRequest(0x24,a,b,key==0,key+1==steps,steps)
                fenv.clear_flags()
                edge=client.tick(request=req);require(edge['request_fire'],'accepted original profile0 request')
                count['request_fire']+=1
                while client.ports()['result'] is None:
                    e=client.tick();count['wait_ticks']+=1
                result=client.ports()['result'];flags|=fenv.read_flags()
                require(not result.error and result.value is not None,'original service protocol error')
                # Audit copies are comparisons only; never operands of a later group.
                selected=tuple(result.value[0][i] for i in range(width))
                outputs.append(selected)
                finite=all(scalar.finite(w) for w in selected)
                if write_held and key+1==steps and finite:
                    held=result;signature=result.value.sha256
                    # Reuse the original complete reply; one16word output hold at a time.
                    for half in range(width//16):
                        words=tuple(result.value[0][half*16+i] for i in range(16))
                        request=p.MemoryRequest(base+half*64,half,True,struct.pack('<16I',*words),p.FULL_MASK)
                        bus.accept(request)
                        for _ in range(3):
                            client.tick(result_ready=False);count['held_reply_ticks']+=1
                            require(client.ports()['result'] is held and held.value.sha256==signature,'held result bytes changed')
                        response=bus.response();bus.retire(response)
                        require(base+half*64 in bus.acked,'selected write ACK missing')
                        holds.append(dict(half=half,ack=True,reply_still_held=client.ports()['result'] is held))
                        del words
                    require(not bus.pending and len(bus.acked)*64==width*4,'selected output debt')
                require(client.tick(result_ready=True)['result_fire'],'original legacy reply retirement')
                count['result_fire']+=1
            require(client.drained,'group Matrix result/done/legacy debt')
            delta=int(library.matrix_normal_fmas())-before
            require(delta==count['request_fire']*512,'actual profile0 C FMA count')
            return dict(accepted=dict(count),actual_c_fma_calls=delta,outputs=outputs,host_fenv_flags=flags,
                final_selected_finite=all(scalar.finite(w) for w in outputs[-1]),
                selected_write_ack_events=len(bus.acked),selected_output_bytes=len(bus.acked)*64,
                held_reply_write_evidence=holds,scalar_counter_delta=dict(Counter(shared.calls)-scalar_before))
        def words(value):return scalar.word(value)>>16
        finite_prob=[words(v) for v in (.5,.25,.125,.0625,.03125,.015625,.0078125)]
        finite_v=[[words(((k*7+c)%17-8)/16) for c in range(32)] for k in range(7)]
        cases=[('finite_causal1',finite_prob[:1],finite_v[:1],True,{}),
            ('finite_causal3',finite_prob[:3],finite_v[:3],True,{}),
            ('finite_causal7',finite_prob,finite_v,True,{}),
            ('signed_zero',[0,0x8000,0x3f00],[[0 if c%2 else 0x8000 for c in range(32)]]*3,True,{}),
            ('exact_subnormal',[0x0080,0x0001],[[0x3e80]*32,[0x3f00]*32],True,{}),
            ('inexact_underflow',[0x0001],[[0x0001]*32],True,{}),
            ('selected_overflow',[0x7f00],[[0x4000]*32],False,{}),
            ('padded_row_nonfinite',[0x3f00],[[0x3f00]*32],False,{'unselected_nan':True}),
            ('inactive_slice_nonfinite',[0x3f00],[[0x3f00]*32],False,{'inactive_nan':True}),
            ('high_half_selected_nan',[0x3f00],[[0x3f00]*20+[0x7fc1]+[0x3f00]*11],False,{})]
        for name,probs,values,rational,options in cases:
            k=validate_tail(len(probs),7 if len(probs)<=7 else len(probs))
            low=group(probs,values,16,0,**options)
            high=group(probs,values,16,16,**options)
            wide=group(probs,values,32,0,write_held=True,**options)
            same=all(tuple(low['outputs'][i])+tuple(high['outputs'][i])==tuple(wide['outputs'][i]) for i in range(k))
            require(same,'two16 vs one32 stepwise bit mismatch '+name)
            independent=True
            if rational:
                expected=[0]*32
                for i in range(k):
                    expected=[rn(exact(probs[i]<<16)*exact(values[i][c]<<16)+exact(expected[c])) for c in range(32)]
                    require(tuple(expected)==tuple(wide['outputs'][i]),'independent rational FMA mismatch '+name)
            else:independent=None
            for z in (low,high,wide):
                z['selected_trace_sha256']=hashlib.sha256(json.dumps(z.pop('outputs')).encode()).hexdigest()
            record=dict(name=name,causal_keys=k,accepted_key_indices=list(range(k)),future_key_requests=0,
                two16_low=low,two16_high=high,one32=wide,stepwise_raw_fp32_bit_exact=same,
                independent_rational_fma_bit_exact=independent,
                input_packet_accepted_domain='generic profile0 stress packet; not legal original PV padding' if options.get('unselected_nan') else 'synthetic PV-like packet',
                selected_finite_rule='row0 all32 only; no padded-row finite rejection')
            report['cases'].append(record);checkpoint()
        # Actual shared ScalarService calls demonstrate repeated normalization;
        # outputs only compare against each other and are not Matrix operands.
        require(shared.acquire(owner),'normalization scalar acquire')
        norm=[]
        for probability,inverse in ((scalar.word(.375),scalar.word(.7)),(0x80000000,0x3f800000),(0x00010000,0x3f000001)):
            pair=[]
            for repeats in (8,4):
                before=Counter(shared.calls);results=[];errors=[]
                for _ in range(repeats):
                    try:results.append(shared.op(owner,'bf',shared.op(owner,'mul',probability,inverse,policy='legacy_scalar')))
                    except scalar.ArithmeticFault as error:errors.append(str(error))
                pair.append(dict(repeats=repeats,results=results,errors=errors,counter_delta=dict(Counter(shared.calls)-before)))
            require(set(pair[0]['results'])==set(pair[1]['results']) and set(pair[0]['errors'])==set(pair[1]['errors']),'normalization repeat equivalence')
            norm.append(dict(probability=probability,inverse=inverse,legacy8=pair[0],candidate4=pair[1]))
        shared.release(owner);report['normalization']=norm
        service.retire_owner_response(owner);service.release(owner)
        require(service.owner is None and shared.client is None and library.matrix_state()==0 and
            int(library.matrix_accumulator_address())==address and library.matrix_accumulator_bytes()==81920,'resource identity/terminal debt')
        report['matrix']=service.report();report['backend_debts']=dict(matrix_owner=False,scalar_owner=False,c_state=0,client_drained=client.drained)
        report['prediction_only']=dict(qk_unchanged_steps=792576,pv_old_steps=792576,pv32_steps=396288,
            total_steps=1188864,total_actual_fma=608698368,useful_fma=25362432,
            useful_over_executed=25362432/608698368,whole_8slice_opportunity_ratio=25362432/(1188864*4096),
            ddr_read_write_bytes_reduction=0)
        report['source_sha256_after']={n:gates.sha(ROOT/n) for n in sources}
        report['tools_after']={n:dict(path=str(v),sha256=gates.sha(v),bytes=v.stat().st_size) for n,v in tool_paths.items()}
        require(report['source_sha256_after']==sources and report['tools_after']==report['tools_before'],'source/runtime drift')
        for rel,digest in sources.items():
            raw=(ROOT/rel).read_bytes();require(hashlib.sha256(raw).hexdigest()==digest,'snapshot drift')
            target=out/'frozen_sources'/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        report.update(status='PASS_PROFILE0_PV32_SYNTHETIC_SHORT_TRACE_ONLY',host_wall_seconds=time.monotonic()-started,
            peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            limitations=['No Attention owner/host wiring implemented or tested',
                'No fullchunk, causal scheduler, official node acceptance or hardware utilization claim',
                'Finite/error detection prefix and partial-store timing can differ when two packets are fused',
                'Synthetic held-reply bus trace holds the same reply through both ACKs; production sequencing needs explicit arbiter/abort review',
                'Host fenv is aggregate512cell diagnostic; Matrix endpoint does not expose selected-lane flag acceptance'])
        checkpoint();print(json.dumps({k:report[k] for k in ('status','host_wall_seconds','prediction_only')}),flush=True)
    except BaseException as e:
        report.update(status='FAILED_PV32_SHORT_TRACE',error=repr(e),traceback=traceback.format_exc(),host_wall_seconds=time.monotonic()-started)
        if 'service' in locals():report['failed_matrix']=service.report()
        if 'shared' in locals():report['failed_scalar_calls']=dict(shared.calls)
        checkpoint();raise


def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--trace',action='store_true');ap.add_argument('--out');a=ap.parse_args(argv)
    if not a.trace:
        require(a.out is None,'out requires explicit --trace');print(json.dumps(dict(status='NOT_EXECUTED',short_trace_only=True)));return 0
    require(a.out is not None,'--trace requires fresh --out');run(a.out);return 0

if __name__=='__main__':raise SystemExit(main())
