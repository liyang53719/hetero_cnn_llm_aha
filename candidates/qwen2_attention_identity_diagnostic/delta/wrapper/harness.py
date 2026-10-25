"""One supervised Attention component, real services, no full-block admission."""
import ast
from collections import Counter
from contextlib import ExitStack
from runtime_observer import ServiceTrace,bindings,load_observer,compare_arms
from reference_capture import capture_reference
from stage_clock import Stages
from selective_binding import load_candidate, make_capture, mask_snapshot
from artifacts import persist_words, persist_fields
from fractions import Fraction
from functools import lru_cache
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import sys
import time


def need(value, detail):
    if not value: raise ValueError(detail)


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        while block:=f.read(1<<20): h.update(block)
    return h.hexdigest()


def load_exact(path):
    """Only existing primitive ASTs; no reference execution before DUT terminal."""
    names={'exact','rn','ref_add','ref_mul','ref_bf'}
    tree=ast.parse(Path(path).read_text());nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
    need({n.name for n in nodes}==names,'exact helper definitions')
    ns={'Fraction':Fraction,'struct':struct,'lru_cache':lru_cache}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),ns)
    return ns


def lanes(work, exact):
    finite=lambda a:a&0x7f800000!=0x7f800000
    def op(kind,a,b):
        if not finite(a) or not finite(b):return work.LaneResult(0,16)
        mathematical=exact['exact'](a)+exact['exact'](b) if kind=='add' else exact['exact'](a)*exact['exact'](b)
        word=exact['ref_'+kind](a,b);flags=0
        if not finite(word):flags=5
        elif exact['exact'](word)!=mathematical:
            flags=1
            if not word&0x7f800000:flags|=2
        return work.LaneResult(word,flags)
    return work.StrictLaneOps(add=lambda a,b:op('add',a,b),mul=lambda a,b:op('mul',a,b),bf=exact['ref_bf'],finite=finite)


def score_frame(owner, scores):
    g=owner.program
    while g is not None and hasattr(g,'gi_frame'):
        frame=g.gi_frame
        if frame is not None and frame.f_code.co_name=='run' and 'scores' in frame.f_locals and 'head' in frame.f_locals:
            f=frame.f_locals;scores[(f['token'],f['head'])]=tuple(f['scores'])
        g=getattr(g,'gi_yieldfrom',None)


def run_owner(lib, inputs, m, enabled, exact, config, *, variant='off'):
    need(enabled is True and variant in ('off','original','selective_identity_r1') and m == 2,'same ordered M2 arithmetic')
    observe=variant != 'off'
    stages=Stages()
    from candidates.qwen2_resident_matrix.ffn_attention.matrix_service import MatrixService,configure_library
    from candidates.qwen2_resident_matrix.ffn_public.prefix_arithmetic import ScalarService
    from candidates.qwen2_resident_matrix.ffn_public.prefix_owners import Job,MemoryResponse
    from candidates.qwen2_resident_matrix.official_bf16.owners import OfficialAttentionOwner
    from candidates.qwen2_resident_matrix.production_qk16_model import entry,ordered_work
    stages.mark('module_imports')
    configure_library(lib);need(lib.td_reset()==0,'initial coordinated reset')
    service=MatrixService(lib)
    scalar=ScalarService(committed_source_witness=config['committed_source_witness'], committed_source_manifest=config['committed_source_manifest'])
    owner=OfficialAttentionOwner(service,scalar,max_tokens=128)
    stages.mark('original_reset_and_constructors_including_source_and_five_fp32_probes')
    lane=lanes(ordered_work,exact) if enabled else None
    entry.install(owner,ordered_fold=enabled,ordered_lanes=lane)
    job=Job('Attention',0x12340001,0x10000,0x20000,0x40000,m,1536,128,m*1536*4,c=0x30000)
    sources=((job.a,inputs[0]),(job.b,inputs[1]),(job.c,inputs[2]))
    output=[None]*(m*1536);pending=None;scores={};counts=Counter();held_checks=0;writes=[]
    monitor,base=load_observer(config)
    tracer=ServiceTrace(service,config,monitor.bind)
    candidate=None;candidate_receipt=None;mask_receipts=[]
    if variant=='selective_identity_r1':
        candidate,candidate_receipt=load_candidate(config)
        capture=make_capture(candidate,owner,m,base.PackedFields,bindings(owner,config))
    else:
        capture=monitor.Observation(owner,m,base.PackedFields,bindings(owner,config)) if observe else None
    stages.mark('binding_and_monitor_setup')
    def drive():
        nonlocal pending,held_checks
        if candidate is not None:
            try:mask_receipts.append(mask_snapshot(capture,installed=True))
            except KeyboardInterrupt:raise
            except BaseException as error:
                message='installed mask validation: '+type(error).__name__+': '+str(error)
                mask_receipts.append(dict(phase='installed_check_failed',error=message))
                state['capture_error']=message if state['capture_error'] is None else state['capture_error']+'; '+message
        stages.mark('monitor_enter')
        need(owner.tick(job=job)['job_fire'],'actual owner job acceptance')
        for edge in range(20000):
            p=owner.tick(memory_ready=True,memory_response=pending,response_ready=False)
            score_frame(owner,scores)
            if p['memory_response_fire']:pending=None;counts['memory_response']+=1
            if p['memory_fire']:
                need(pending is None,'one physical memory debt');q=p['memory'];counts['write' if q.write else 'read']+=1
                if q.write:
                    off=(q.address-job.dst)//4
                    need(q.address%64==0 and 0<=off<=len(output)-16,'output address')
                    words=struct.unpack('<16I',q.data) if isinstance(q.data,bytes) else tuple(q.data)
                    need(len(words)==16 and all(v is None for v in output[off:off+16]),'single exact output packet')
                    output[off:off+16]=words;writes.append((q.address,q.tag,words));pending=MemoryResponse(q.tag,None)
                else:
                    found=None
                    for base,data in sources:
                        if base<=q.address<base+len(data)*4:
                            off=(q.address-base)//4;need(q.address%64==0 and off+16<=len(data),'input bounds');found=data[off:off+16]
                    need(found is not None,'unmapped input');pending=MemoryResponse(q.tag,found)
            if owner.state=='ordered_fold':
                need(owner.ordered_work.result.service_result is service.result,'live result identity');held_checks+=1
            if owner.state=='finish':break
        else:raise ValueError('bounded owner edge budget exhausted')
        need(owner.status is None and pending is None,'successful terminal and no memory debt')
        need(all(v is not None for v in output),'complete output')
        need(service.result is None and service.done is None and not service.reset_required,'original client terminal debts drained')
        need(service.owner is owner and scalar.client is None,'Matrix retained and Scalar released at original finish')
        need(owner.tick(response_ready=True)['response_fire'],'terminal ACK accepted')
        need(service.owner is None and scalar.client is None,'resources released after terminal ACK')
        return edge
    if candidate is None:
        with ExitStack() as stack:
            stack.enter_context(tracer)
            if capture is not None:stack.enter_context(capture)
            edge=drive()
    else:
        state={'service_error':None,'capture_error':None}
        edge=candidate['bridge'].observe_driver(tracer,capture,drive,state)
    stages.mark('actual_owner_job_through_terminal_ack_and_monitor_exit')
    if candidate is not None:
        need(state['service_error'] is None and state['capture_error'] is None,'candidate monitor lifetime failure: '+str(state))
        mask_receipts.append(mask_snapshot(capture,installed=False,previous=mask_receipts[0]))
    stages.mark('post_timing_monitor_lifecycle_validation')
    fmas=int(lib.matrix_normal_fmas());need(fmas>0,'actual native FMA witness required')
    flat=tuple(v for key in sorted(scores) for v in scores[key]);need(len(flat)==12*m*(m+1)//2,'complete causal score trace')
    capture_report=None;capture_error=None
    if capture is not None:
        try:capture_report=capture.seal()
        except Exception as error:capture_error=type(error).__name__+': '+str(error)
    service_events=None;service_trace_error=None
    try:service_events=tracer.seal()
    except Exception as error:service_trace_error=type(error).__name__+': '+str(error)
    stages.mark('original_result_and_capture_seals')
    result=dict(output=output,scores=flat,writes=tuple(writes),counts=dict(counts),service_counts=dict(service.counts),scalar_calls=dict(scalar.calls),native_fmas=fmas,edges=edge+1,owner_clock=owner.clock,held_checks=held_checks,work_events=dict(owner.ordered_adapter.events),lane_calls=dict(owner.ordered_adapter.lanes.calls),owner_counts=dict(owner.counts),service_events=service_events,service_trace_error=service_trace_error,observer_enabled=observe,terminal_acked=True,resources_released=True,capture_report=capture_report,capture_error=capture_error,capture_fields=capture.data.fields if capture is not None else None)
    result.update(observer_variant=variant, stages=stages.rows, scalar_identity=scalar.identity, selective_binding=candidate_receipt, selective_masks=mask_receipts)
    return result



def compare_original(config,m,inputs,arms,*,reference_out=None):
    """Called only after both real DUT owners have ACKed and released services."""
    need(len(arms)==3 and all(a['terminal_acked'] and a['resources_released'] for a in arms),'all three real terminals required before recipe import')
    path=Path(config['oracle_harness']);saved=list(sys.argv)
    sys.argv=[str(path),'--source-root',config['raw_root']]
    spec=importlib.util.spec_from_file_location('_terminal_only_original_recipe',path)
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module
    try:spec.loader.exec_module(module)
    finally:sys.argv[:]=saved
    compare_arms(arms[:2])
    compare_arms([arms[0],arms[2]])
    _,base=load_observer(config)
    reference=capture_reference(module,m,inputs,base.PackedFields,config['reference_sources'],terminal_gate=all(arm['terminal_acked'] and arm['resources_released'] for arm in arms))
    expected=reference['output'];scores=reference['scores']
    compare_fields(arms[1]['capture_fields'],reference['fields'])
    compare_fields(arms[2]['capture_fields'],reference['fields'])
    for arm in arms:
        need(tuple(arm['output'])==tuple(expected),'independent original recipe output mismatch')
        need(tuple(arm['scores'])==tuple(scores),'independent original recipe score mismatch')
    need(reference_out is not None and all(a['terminal_acked'] and a['resources_released'] for a in arms),'terminal reference evidence destination')
    persist_words(reference_out,'REFERENCE_OUTPUT',expected)
    persist_words(reference_out,'REFERENCE_SCORES',scores)
    persist_fields(reference_out,'REFERENCE',reference['fields'])
    return dict(output_words=len(expected),score_words=len(scores),output_sha256=hashlib.sha256(struct.pack('<%dI'%len(expected),*expected)).hexdigest(),scores_sha256=hashlib.sha256(struct.pack('<%dI'%len(scores),*scores)).hexdigest(),reference='unchanged original independent control/recipe, terminal-only ten-field collector; shared exact RNE primitives disclosed',intermediate_fields=10,reference_capture=reference['report'])


def compare_fields(actual,reference):
    names={'dot_parts','unrounded_dot_sum','dot_bf16','scores_bf16','softmax_exp','softmax_fp32','prob_bf16','normalizer','pv_raw','pv_bf16'}
    need(set(actual)==set(reference)==names,'exact ten captured fields required')
    for name in sorted(names):
        a,b=actual[name],reference[name]
        need(a['shape']==b['shape'],'field shape mismatch '+name)
        need(bytes(a['observed'])==bytes(b['observed']),'field presence mismatch '+name)
        need(tuple(a['words'])==tuple(b['words']),'bit-exact intermediate mismatch '+name)
    # Each collector validates its own actual event frequency contract. Reference
    # normalizer may be observed per PV key/column; never copy those frequencies.
    return True
