#!/usr/bin/env python3
"""SOURCE-ONLY Fixed93 public21 integration shell; actual entry fails closed without new admission."""
import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import resource
import sys
import tempfile
import time
import traceback

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
CANDIDATE = HERE.parent
ROOT = CANDIDATE / 'source'
DATA = None
if __package__:
    from .interface import load_runtime, validate_observation, validate_wholeblock_seal, validate_comparison_scope, validate_wholeblock_context
    from .artifact_seal import seal_algorithm_artifacts
else:
    from interface import load_runtime, validate_observation, validate_wholeblock_seal, validate_comparison_scope, validate_wholeblock_context
    from artifact_seal import seal_algorithm_artifacts
INPUT_ROLES = frozenset(('x','gamma0','wq','wk','wv','bq','bk','bv','rope','wo','gamma1','wg','wu','wd'))
PRODUCERS = ('n0','qraw','qr','q','kraw','kr','k','vraw','v')


def require(ok, text):
    if not ok:
        raise ValueError(text)


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+'\n')


def dependencies(runtime):
    runtime['initialize_runtime']()
    from candidates.qwen2_resident_matrix.dense_block_reduce import check_public_numeric as r
    previous, new = r.runtime()
    (modules,dense,observer,native)=previous
    helper,original,fixtures,public,prefix,_,scalar,suffix,*_=modules
    owner_module,binding,profiles,execution,observation,_=new
    return r,dense,native,helper,original,fixtures,public,prefix,scalar,owner_module,binding,profiles,execution,suffix,observation


def run(out, data, reference, *, reviewed_source_manifest=None):
    global DATA
    # All absent/new-source/admission checks precede every DUT/runtime import.
    runtime=load_runtime(CANDIDATE, dict(out=str(out), data=str(data), reference=str(reference),
        reviewed_source_manifest=reviewed_source_manifest))
    gates=runtime['gates']; native_artifact=runtime['native_artifact']
    limits=runtime['limits']; wholeblock=None
    sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(CANDIDATE))
    from candidates.qwen2_live_attention_model_m128 import boundary
    from candidates.qwen2_live_fullblock_model_m128 import compare
    from integration import fixed93_telemetry as telemetry
    from candidates.qwen2_fullblock_ci_dut import statistics
    started=time.monotonic(); cpu=time.process_time()
    reviewed_sources=gates.require_review(reviewed_source_manifest)
    require(reviewed_sources==runtime['source_sha256'], 'new admitted source closure differs')
    require(gates.require_budget()==limits, 'new wholeblock budget identity differs')
    resource.setrlimit(resource.RLIMIT_AS,(limits['rss_bytes'],limits['rss_bytes']))
    resource.setrlimit(resource.RLIMIT_FSIZE,(limits['file_bytes'],limits['file_bytes']))
    gates.require_final_reference()
    REFERENCE=gates.reference_path(reference)
    DATA = gates.data_path(data)
    out=Path(out).absolute()
    gates.fresh_output(out, DATA)
    out.mkdir()
    # Existing public metadata packer uses TemporaryDirectory and binary
    # command/descriptor records. Keep those writes in this new run, never
    # broaden the payload gate to arbitrary /tmp or old output directories.
    (out/'tmp').mkdir()
    tempfile.tempdir=str(out/'tmp')
    report=dict(schema=1,status='STARTED',scope='M128 public21 fresh pc0..20 through accepted launch result',
        old_pass_inherited=False,rtl_executed=False,eda_executed=False,fullblock_pass=False,
        hardware_cycles=None,model_ticks_are_hardware_cycles=False,finalfence=False,
        preloaded_intermediates=[],allowed_input_roles=sorted(INPUT_ROLES),
        actual_outputs_sealed=False,acceptance_sealed=False,
        inner_wall_seconds=limits['inner_wall_seconds'],outer_wall_seconds=limits['outer_wall_seconds'],compile_executed=False,
        whole_block_terminal=False,resource_limits=limits,scalar_sfu_unified_physical_arbiter_proven=False,
        reviewed_source_manifest=reviewed_source_manifest,historical_approval_inherited=False)
    def checkpoint(): save(out/'RESULT.json',report)
    checkpoint()
    gate=gates.OracleGate(DATA,out,REFERENCE)
    progress=telemetry.SparseTelemetry(out/'PROGRESS.jsonl',started=started,cpu=cpu,budget=limits['inner_wall_seconds'])
    try:
        progress.start();progress.mark('dependency_setup')
        r,dense,native,helper,original,fixtures,public,prefix,scalar,owner_module,binding,profiles,execution,suffix,observation=dependencies(runtime)
        from candidates.qwen2_fixed93_attention.binding import Fixed93PublicExecution,Fixed93ReductionDriver
        from candidates.qwen2_fixed93_attention.owner import Fixed93AttentionOwner
        from observation.fullblock_attention import Fixed93FullblockAttentionObservation
        progress.mark('source_and_input_hashes')
        sources=gates.sources()
        require(sources==reviewed_sources,'reviewed closure changed during dependency setup')
        report['source_sha256_before']=sources
        report['source_manifest_sha256']=hashlib.sha256(json.dumps(sources,sort_keys=True).encode()).hexdigest()
        inputs, ready, evidence, preflight = gates.validate_inputs(DATA,REFERENCE)
        report.update(evidence_sha256_before=evidence,input_identity_before=ready['roles'],
            input_validation=preflight,postimage_correspondence=gates.correspondence())
        sys.addaudithook(gate.audit)
        progress.mark('native_artifact_validation')
        library,built,reuse=native_artifact.load(dense)
        report['native_artifact_reuse']=reuse
        report['native_artifact_mode']='verified existing profile2 ELF reused; no fresh build or hermetic claim'
        save(out/'native_artifact_reuse.json',reuse)
        progress.mark('tool_hashes_and_fresh_setup')
        import numpy as np
        import yaml
        tool_paths={'python':Path(sys.executable).resolve(),'numpy_multiarray':Path(np._core._multiarray_umath.__file__).resolve(),
                    'compiler':Path(built['compiler']['path']),'matrix_library':Path(built['library']),
                    'numpy_init':Path(np.__file__).resolve(),'yaml_init':Path(yaml.__file__).resolve()}
        tools_before={k:dict(path=str(p),sha256=sha(p),bytes=p.stat().st_size) for k,p in tool_paths.items()}
        report['tools_before']=tools_before
        report['tool_versions']=dict(python=sys.version,numpy=np.__version__,pyyaml=yaml.__version__,compiler=built['compiler']['version'])
        report['reference_capture_runtime_is_separate']=True
        report['execution_environment']={k:os.environ.get(k) for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS')}
        report['affinity']=sorted(os.sched_getaffinity(0))
        checkpoint()
        wholeblock=runtime['wholeblock_observation'](out=out,library=library,
            source_context=dict(source_root=ROOT,source_manifest=runtime['source_manifest'],source_sha256=sources),
            runtime_context=dict(r=r,dense=dense,native=native,helper=helper,original=original,fixtures=fixtures,
                public=public,prefix=prefix,scalar=scalar,owner_module=owner_module,binding=binding,profiles=profiles,
                execution=execution,suffix=suffix,observation=observation,built=built,reuse=reuse))
        validate_wholeblock_context(wholeblock)
        with r.base.frozen_exec(sources) as observed:
            from candidates.qwen2_live_attention_model_m128_bounded import attention_driver
            from candidates.qwen2_fullblock_ci_dut import tail
            f=fixtures.make_qwen2_21_fixture(128,7)
            require(all(len(raw)==f.allocations[name].storage_bytes for name,raw in inputs.items()),'typed readonly extent')
            physical=prefix.PhysicalMemory(f,{n:r.base.bytes_provider(v) for n,v in inputs.items()})
            from candidates.qwen2_resident_matrix.ffn_public.fullgraph_memory import FullGraphMemory
            from candidates.qwen2_resident_matrix.official_bf16.execution import ObservedSiluLibrary
            memory=FullGraphMemory(physical)
            region=f.config.regions[3]
            owner=owner_module.DenseReductionOwner(original.numeric.model.PrefixWorkspace(
                region.base,region.limit-region.base,8,2560),enable_dense_drain=True,enable_k_window=True,
                enable_ffn_window=True,enable_ffn_tiles=True,enable_ffn_drain=True)
            selected=dense.selected_library(library)
            require(selected.sf_entrypoint=='sf_vector_bf16_v1','original BF16 SiLU selection required')
            require(library.td_reset()==0 and selected.sf_reset()==0,'fresh Matrix/selected SiLU reset failed')
            silu=ObservedSiluLibrary(selected,128)
            service=binding.ProfiledMatrixService(library,profiles.QWEN2_QKV_PROFILE)
            shared=scalar.ScalarService()
            report['scalar_environment_audit']=list(gate.environment_events)
            x=Fixed93PublicExecution(public.PublicFrontend(physical.metadata_port(),f.config),owner,
                wholeblock.public_trace,started+limits['inner_wall_seconds'],fixture=f,
                host=public.group.HostControl(enabled=True,legacy_prefix=True,legacy_attention=True),
                prefix_owner=execution.OfficialPrefixOwner(shared),attention_owner=Fixed93AttentionOwner(service,shared),
                matrix_service=service)
            wholeblock.bind(x=x,physical=physical,memory=memory,silu=silu,library=library)
            with wholeblock:
                progress.context.update(x=x,physical=physical,service=service,shared=shared,memory=memory)
                ledger=statistics.StageLedger(x,physical,memory,silu)
                report['source_guards']=dict(matrix=service.identity,scalar=shared.identity)
                report['base_commit']=shared.identity['recipe']['git_head']
                report['public_metadata']=helper.metadata_identity(f)
                report['initial_unprovided_readonly']=sorted(n for n,a in f.allocations.items() if a.readonly and n not in inputs)
                report['same_live_identity_initial']=statistics.identity(x,physical,memory)
                report['producers']=[]
                for pc,name in enumerate(PRODUCERS):
                    ledger.transition('pc'+str(pc)+'_'+name)
                    progress.mark('prefix_pc'+str(pc)+'_'+name)
                    job=x.advance_to_request()['ordinary_request']
                    require(job is not None and job.tag&0xffff==pc and job.dst==f.allocations[name].address,'typed pc/producer binding')
                    if job.kind=='Dense':
                        driver=Fixed93ReductionDriver(x,physical,job)
                        details=driver.run()
                    else:
                        details=prefix.execute_prefix_owner(x,physical,job)
                    require(physical.regions[name]['terminal'] and not physical.regions[name]['published'],'owner terminal/held public completion')
                    if pc<8:
                        x.publish_completions((pc,));physical.publish(job,x.host)
                        if job.kind=='Dense': x.retire_ordinary_bookkeeping()
                    actual=physical.raw(job.dst,job.write_bytes)
                    (out/(name+'.f32le')).write_bytes(actual)
                    require(np.isfinite(np.frombuffer(actual,dtype='<f4')).all(),'nonfinite actual producer '+name)
                    record=dict(pc=pc,name=name,job=asdict(job),details=details,bytes=len(actual),
                        sha256=hashlib.sha256(actual).hexdigest(),finite=True,
                        public_completion_retired=pc<8,owner_terminal=True,ack_bytes=len(physical.regions[name]['acked'])*64)
                    report['producers'].append(record)
                    report.update(status='EXECUTING',last_producer=name,host_wall_seconds=time.monotonic()-started)
                    checkpoint();print(json.dumps({'producer':name,'pc':pc,'seconds':report['host_wall_seconds']}),flush=True)
                ledger.transition('pc8_retire_pc9_kv_append')
                progress.mark('pc8_hold_and_kv_append')
                report['pc8_held_before_continuation']=boundary.stable_hold(x,physical,pc=8,completed=8,jobs=9,output='v')
                require(job.kind=='Bias' and job.tag&0xffff==8,'original pc8 Bias job required')
                x.publish_completions((8,));physical.publish(job,x.host)
                report['producers'][-1]['public_completion_retired']=True
                require(x.host.pc==x.host.completed==9 and x.host.jobs==9,'pc8 did not genuinely retire')
                job=x.advance_to_request()['ordinary_request']
                require(job is not None and job.kind=='KvAppend' and job.tag&0xffff==9 and
                    job.a==f.allocations['k'].address and job.b==f.allocations['v'].address and
                    job.dst==f.allocations['kv'].address and job.write_bytes==262144,'typed KvAppend binding')
                counters_before=Counter(physical.counts)
                details=prefix.execute_prefix_owner(x,physical,job)
                kv=physical.raw(job.dst,job.write_bytes)
                k=physical.raw(f.allocations['k'].address,131072);v=physical.raw(f.allocations['v'].address,131072)
                require(kv==k+v,'KvAppend differs from this live run K/V exact-copy')
                delta=dict(Counter(physical.counts)-counters_before)
                require(delta.get('write_ack_bytes')==262144 and len(physical.regions['kv']['acked'])==4096,
                    'KvAppend ACK coverage differs')
                (out/'kv.f32le').write_bytes(kv)
                report['kv_append']=dict(job=asdict(job),details=details,physical_counter_delta=delta,
                    bytes=262144,sha256=hashlib.sha256(kv).hexdigest(),exact_copy=True,
                    k_sha256=hashlib.sha256(k).hexdigest(),v_sha256=hashlib.sha256(v).hexdigest(),
                    coverage_64b_beats=len(physical.regions['kv']['acked']),
                    write_ack_events=delta.get('write_acks',0),write_command_events=delta.get('write_commands',0),
                    held_before_retire=boundary.held_checkpoint(x,physical,pc=9,completed=9,jobs=10,output='kv'))
                x.publish_completions((9,));physical.publish(job,x.host)
                report.update(status='EXECUTING_ATTENTION',last_producer='kv',host_wall_seconds=time.monotonic()-started)
                checkpoint();print(json.dumps({'producer':'kv','pc':9,'seconds':report['host_wall_seconds']}),flush=True)
                ledger.transition('pc10_12_attention_including_held_pc12')
                job=x.advance_to_request()['ordinary_request']
                require(job is not None and job.kind=='Attention' and job.tag&0xffff==12 and
                    (job.a,job.b,job.c,job.dst)==tuple(f.specs[n][0] for n in ('q','cache_k','cache_v','att')) and
                    (job.m,job.n,job.k,job.write_bytes)==(128,1536,128,786432),'fused Attention original typed binding')
                progress.mark('attention_observer_setup')
                capture=Fixed93FullblockAttentionObservation(x.attention_owner, ROOT,
                    runtime['source_manifest'], out/'attention_observation', trace_limits=runtime['attention_trace_limits'], trace_dispatcher=wholeblock.trace_dispatcher)
                counters_before=Counter(physical.counts);scalar_before=Counter(shared.calls)
                matrix_before=Counter(service.counts)
                dense_fma_before=int(library.matrix_dense_fmas());normal_fma_before=int(library.matrix_normal_fmas())
                progress.mark('attention')
                with capture:
                    attention=attention_driver.execute_attention_owner(x,physical,job,progress=progress)
                progress.mark('attention_writeback_and_pc12_hold')
                report['attention']=attention
                report['attention']['physical_counter_delta']=dict(Counter(physical.counts)-counters_before)
                report['attention']['scalar_counter_delta']=dict(Counter(shared.calls)-scalar_before)
                report['attention']['dense_fma_delta']=int(library.matrix_dense_fmas())-dense_fma_before
                report['attention']['normal_fma_delta']=int(library.matrix_normal_fmas())-normal_fma_before
                report['attention']['service_counter_delta']=dict(Counter(service.counts)-matrix_before)
                report['observation']=capture.save(out/'attention_observation')
                validate_observation(capture, report['observation'])
                att=physical.raw(job.dst,job.write_bytes)
                pv=np.frombuffer(capture.field_words('pv_bf16'),dtype='<u4').reshape(12,128,128)
                require(pv.transpose(1,0,2).copy().tobytes()==att,'observed PV layout differs from physical ACKed context')
                (out/'att.f32le').write_bytes(att)
                report['attention']['output']=dict(bytes=len(att),sha256=hashlib.sha256(att).hexdigest(),
                    pv_to_token_exact=True,owner_terminal=True,ack_bytes=len(physical.regions['att']['acked'])*64)
                x.publish_completions((10,11))
                report['held_boundary']=boundary.stable_hold(x,physical,pc=12,completed=12,jobs=11,output='att')
                report['same_live_identity_at_pc12']=statistics.identity(x,physical,memory)
                require(report['same_live_identity_initial']==report['same_live_identity_at_pc12'],'live objects/banks/service replaced')
                physical.check_coexistence()
                report['unexecuted_outputs_at_pc12']=boundary.pristine_suffix(physical,set(PRODUCERS)|{'kv','att'})
                report['physical_memory_at_pc12']=physical.report();report['execution_at_pc12']=x.report()
                report['scalar_calls']=dict(shared.calls);report['matrix']=service.report()
                report['backend_debts_at_pc12']=boundary.debts(x,physical)
                reduced=x.reduction_reports
                totals=Counter()
                for rr in reduced:
                    totals['partials']+=len(rr['partials']); totals['drains']+=len(rr['drains'])
                    totals['wide_matrix_steps']+=rr['accepted']['backend_step_fire']
                    totals['useful_macs']+=rr['terminal']['useful_macs']
                    totals['executed_macs']+=rr['terminal']['executed_macs']
                    totals['actual_c_fma_calls']+=rr['actual_dense_fma_calls_delta']
                    totals['vector_add_requests']+=rr['shared_vector']['add_requests']
                    totals['raw_qkv_ack_bytes']+=rr['terminal']['write_bytes']
                expected=dict(partials=28,drains=14,wide_matrix_steps=98304,useful_macs=402653184,
                    executed_macs=402653184,actual_c_fma_calls=402653184,vector_add_requests=16384,raw_qkv_ack_bytes=1048576)
                require(dict(totals)==expected,'executed schedule counters differ: '+str(totals))
                report['observed_qkv_totals']=dict(totals)
                a=report['attention']
                # Driver requests include one PackedQkStart per group; packed FIFO
                # borrows are not legacy result handshakes. Keep event domains separate.
                require(a['normal_fma_delta']==a['result']['executed_macs']==632291328 and
                    a['result']['useful_macs']==25362432 and a['accepted']['matrix_requests']==854784 and
                    a['accepted']['matrix_results']==792576 and a['dense_fma_delta']==0,
                    'Attention actual owner-request/FMA counters differ')
                require(tuple(a['service_counter_delta'].get(k,0) for k in
                    ('normal_steps','normal_results','normal_groups','normal_done')) == (847872,799488,19200,19200),
                    'Attention actual accepted service step/result/group counters differ')
                report['schedule_prediction_and_observation_at_pc12']=dict(qk_groups_prediction=6912,
                    fixed93_qk_steps_prediction=55296,fixed93_pv16_steps_prediction=792576,
                    fixed93_total_step_prediction=847872,owner_requests_prediction=854784,
                    legacy_result_fires_prediction=792576,service_result_retirements_prediction=799488,
                    actual_service_counters=a['service_counter_delta'],
                    actual_matrix_requests=a['accepted']['matrix_requests'],actual_normal_fma=a['normal_fma_delta'],
                    actual_useful_fma=a['result']['useful_macs'],
                    useful_over_executed=a['result']['useful_macs']/a['result']['executed_macs'],
                    full_4096_opportunity_count=a['service_counter_delta']['normal_steps']*4096,hardware_busy_fraction=None,
                    software_state_ticks=None,
                    functional_state_ticks_diagnostic=telemetry.state_ticks_diagnostic(),
                    counter_kind='software functional events and actual C FMA, not hardware cycles/utilization')
                report['observed_totals_at_pc12']=dict(dense_fma_calls=report['matrix']['dense_fma_calls'],
                    normal_fma_calls=report['matrix']['normal_fma_calls'],
                    useful_macs=totals['useful_macs']+a['result']['useful_macs'],
                    executed_macs=totals['executed_macs']+a['result']['executed_macs'])
                report['slice_updates_equivalent_qkv']=dict(count=totals['actual_c_fma_calls']//512,
                    independently_clocked_slice_handshake=False,derivation='observed C FMA calls / (16*32); model executes all 8 slices per wide step')
                def tail_stage(name):
                    ledger.transition(name)
                    progress.mark(name)
                actual,report['execution']=tail.execute_tail(x,physical,silu,out,memory=memory,
                    attention_job=job,stage=tail_stage)
                report['whole_block_terminal']=True
                report['finalfence']=True
                report['finalfence_scope']='public21 last completion + accepted launch result + drained obligations; no RTL fence opcode'
                report['same_live_identity_final']=statistics.identity(x,physical,memory)
                require(report['same_live_identity_initial']==report['same_live_identity_final'],'fullblock live identity drift')
                silu_bytes=silu.seal(actual['act'].tobytes())
                (out/'actual_silu.f32le').write_bytes(silu_bytes)
                report['sealed_actual_outputs']={n:dict(bytes=len(v)*4,sha256=hashlib.sha256(v.tobytes()).hexdigest()) for n,v in actual.items()}
                report['sealed_actual_outputs']['silu']=dict(bytes=len(silu_bytes),sha256=hashlib.sha256(silu_bytes).hexdigest())
                report['statistics']=ledger.finish()
                x.trace.close()
                report['matrix']=service.report();report['physical_memory']=physical.report()
                report['scalar_calls']=dict(shared.calls)
                report['backend_debts']=statistics.debts(x,physical,memory)
                require(not any(report['backend_debts'].values()),'fullblock debts remain')
                counters=report['matrix']['counters']
                expected_whole=dict(dense_steps=1462272,normal_steps=847872,dense_fma=5989466112,
                    normal_fma=632291328,whole_useful_macs=6014828544,whole_executed_macs=6621757440,
                    opportunities=9462349824,silu_calls=71680,tail_dense_steps=1363968,
                    tail_dense_fma=5586812928,tail_dense_groups=162,tail_dense_results=800,tail_matrix_leases=114)
                require(counters['dense_steps']==expected_whole['dense_steps'] and
                    counters['normal_steps']==expected_whole['normal_steps'] and
                    report['matrix']['dense_fma_calls']==expected_whole['dense_fma'] and
                    report['matrix']['normal_fma_calls']==expected_whole['normal_fma'] and
                    x.launch_result['useful_macs']==expected_whole['whole_useful_macs'] and
                    x.launch_result['executed_macs']==expected_whole['whole_executed_macs'] and
                    report['statistics']['full_fixed_array_issued_cell_opportunities']==expected_whole['opportunities'] and
                    silu.calls==int(silu.sf_calls())==expected_whole['silu_calls'] and int(silu.sf_failures())==0,
                    'actual wholeblock accepted work differs from original shape schedule')
                tail_intervals=[r for r in ledger.intervals if r['name'] in ('pc13_Dense','pc16_18_resident_ffn','pc19_down')]
                tail_counts=Counter()
                for interval in tail_intervals:
                    tail_counts.update(interval['accepted_counter_delta']['matrix'])
                require(tuple(tail_counts[n] for n in ('dense_steps','dense_groups','dense_results','owner_acquires','owner_releases','dense_seed_acks')) ==
                        (1363968,162,800,114,114,144),'actual tail issue/lease/result/seed schedule differs')
                report['whole_schedule_prediction_and_observation']=dict(predicted=expected_whole,observed_tail=dict(tail_counts),
                    actual_useful_macs=x.launch_result['useful_macs'],actual_executed_macs=x.launch_result['executed_macs'])
                report['executed_repository_imports']=sorted(observed)
                report['algorithm_artifact_seal']=seal_algorithm_artifacts(out,report,capture)
                report['wholeblock_observation']=wholeblock.seal(report=report)
                validate_wholeblock_seal(report['wholeblock_observation'],report['algorithm_artifact_seal'])
                report['evidence_contract']='original-algorithm-arrays-plus-true-events-and-pv-reuse-attention-v1'
                report['unobserved_native_silu_internal_exp_nodes']=17
                report['unobserved_native_silu_pre_bf16_product']=True
                report['every_dense_physical_bank_recorded']=False
                report['all_active_fmas_exactly_recomputed']=False
                report['actual_outputs_sealed']=True
                progress.mark('whole_launch_output_seal')
                report['status']='ACTUAL_OUTPUTS_SEALED_WHOLE_PUBLIC21';checkpoint()
        # No official tensor has been read at any point above this seal.
        require(not gate.reference_reads,'premature oracle reads')
        progress.mark('post_seal_official_comparison')
        gate.open_after_seal(dict(actual_outputs_sealed=True,public_completions=x.host.completed,
            actual_owner_jobs=x.host.jobs,accepted_launch_results=x.counts['result_fire'],finalfence=True,
            outstanding_debts=report['backend_debts'],same_live_identity=report['same_live_identity_initial']==report['same_live_identity_final']))
        ref,reference_bytes=gates.validate_references(DATA,REFERENCE)
        report['numerical_policy']=native.load_policy(ROOT)
        legacy_capture=capture.legacy_adapter()
        report.update(compare.official(out,report,legacy_capture,actual,silu_bytes,ref,reference_bytes,native,np))
        validate_comparison_scope(report)
        report['reference_reads_after_seal']=gate.reference_reads
        report['isolation_scope']='explicit Python model read paths and post-seal gate; not an OS sandbox or interception of arbitrary native syscalls'
        progress.mark('final_source_input_reference_tool_hashes')
        after=gates.sources()
        report['source_sha256_after']=after
        report['input_identity_after']=gates.input_identity()
        report['raw_identity_after']=gates.raw_identity(DATA)
        report['reference_identity_after']={n:gates.reference_identity(n) for n in reference_bytes}
        require(report['raw_identity_after']==preflight['raw_tensors'],'raw BF16 source drift')
        require(all(report['reference_identity_after'][n]['sha256']==ref['outputs'][n]['sha256'] for n in reference_bytes),'reference payload drift')
        report['evidence_sha256_after']=gates.evidence_identity(evidence)
        report['tools_after']={k:dict(path=str(p),sha256=sha(p),bytes=p.stat().st_size) for k,p in tool_paths.items()}
        report['native_artifact_identity_after']=native_artifact.identity()
        report['native_artifact_audit']=list(gate.artifact_reads)
        report['scalar_environment_audit']=list(gate.environment_events)
        require(report['native_artifact_identity_after']==reuse['artifact_identity_before'],'native artifact drift')
        require(after==sources and report['evidence_sha256_after']==evidence and report['tools_after']==tools_before,'source/evidence/tool drift')
        require(all(report['input_identity_after'][n]['sha256']==ready['roles'][n]['sha256'] for n in inputs),'input drift')
        report.update(status='PASS_FIXED93_M128_OFFICIAL_OBSERVED_FULLBLOCK_PUBLIC21' if report['official_observed_node_pass'] else 'FAIL_M128_OFFICIAL_OBSERVED_CONTRACT',
            host_wall_seconds=time.monotonic()-started,host_cpu_seconds=time.process_time()-cpu,
            peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            full_per_producer_official_acceptance=False,missing_official_raw_nodes=['qraw','kraw','vraw'],
            typed_attention_bit_exact_executed=False,hardware_utilization=None)
        progress.mark('final_receipt_write')
        report['telemetry']=progress.report()
        report['acceptance_sealed']=bool(report['official_observed_node_pass'])
        checkpoint();progress.check();progress.stop();return report
    except BaseException as e:
        progress.stop()
        telemetry.attach_failure(report,e,stage=progress.stage,started=started,cpu=cpu,gate=gate,context=progress.context)
        report['scalar_environment_audit']=list(gate.environment_events)
        report['telemetry']=progress.report()
        try:report['source_sha256_after_failure']=gates.sources()
        except Exception as failure:report['failure_source_recheck_error']=repr(failure)
        if 'capture' in locals() and capture.closed and not capture.active:
            try:report['failed_observation']=capture.report()
            except Exception as error:report['failed_observation_error']=str(error)
        checkpoint()
        contextual=telemetry.contextual_error(progress.stage,e)
        if contextual is not e:raise contextual from e
        raise
    finally:
        progress.stop()
        if 'x' in locals():
            x.trace.close()
        if wholeblock is not None:
            wholeblock.close()


def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--actual',action='store_true',help='explicitly execute fresh M128 software model')
    ap.add_argument('--data',help='existing published input-recipe run directory')
    ap.add_argument('--reference',help='exact fresh frozen29 independent reference directory')
    ap.add_argument('--out',help='fresh destination admitted by NEW fullblock gate')
    ap.add_argument('--reviewed-source-manifest',help='exact new closure independently approved by parent')
    a=ap.parse_args(argv)
    if not a.actual:
        require(a.data is None and a.out is None and a.reference is None and a.reviewed_source_manifest is None,'actual arguments require explicit --actual')
        print(json.dumps(dict(status='NOT_EXECUTED',rows=128,scope='fresh software pc0..20 public21',
            input_loading=False,build=False,rtl=False,fullblock=False,actual_execution_authorized=False,
            reviewed_source_manifest_required=True,whole_scope_budget_review_required=True,
            source_only_shell=True,source_runtime_imported=False,
            prerequisites=['new source/runtime/native identity gate','new wholeblock budget and supervisor',
                'exact ProfiledMatrixService observation','wholeblock accepted schedule/cache observation',
                'one-use actual authorization'])))
        return 0
    require(a.data is not None and a.out is not None and a.reference is not None,'--actual requires --data, --reference and --out')
    # New output-side resource control only. The unchanged model's binary
    # artifacts/LEC1 and every input/reference read retain their original IO.
    # Source admission still occurs inside run before any DUT/native import.
    from integration.aux_output import AuxiliaryOutputBudget
    with AuxiliaryOutputBudget(Path(a.out), 67108864) as auxiliary:
        result=run(a.out,a.data,a.reference,reviewed_source_manifest=a.reviewed_source_manifest)
    summary={k:result[k] for k in ('status','host_wall_seconds','peak_rss_kib')}
    summary['auxiliary_output_budget']=auxiliary.report()
    print(json.dumps(summary),flush=True)
    return 0 if result['official_observed_node_pass'] else 1


if __name__=='__main__':raise SystemExit(main())
