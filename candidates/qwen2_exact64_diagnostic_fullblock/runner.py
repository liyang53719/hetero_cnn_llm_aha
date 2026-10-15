#!/usr/bin/env python3
"""Cold, fail-closed exact64 Q/K diagnostic fullblock wiring; no execution authority."""
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
ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUTPUT_ROOT = ROOT/'work/qwen2_exact64_diagnostic_fullblock_numeric'
DATA = None
sys.path.insert(0, str(ROOT))
INPUT_ROLES = frozenset(('x','gamma0','wq','wk','wv','bq','bk','bv','rope','wo','gamma1','wg','wu','wd'))
PRODUCERS = ('n0','qraw','qr','q','kraw','kr','k','vraw','v')
from candidates.qwen2_live_attention_model_m128 import boundary
from candidates.qwen2_exact64_diagnostic_fullblock import native_artifact
from candidates.qwen2_live_fullblock_model_m128 import telemetry
from candidates.qwen2_exact64_diagnostic_fullblock import comparator as compare
from candidates.qwen2_exact64_diagnostic_fullblock import accounting, stage_log as stages
from candidates.qwen2_retention_shape_canonical import retention
from candidates.qwen2_fullblock_ci_dut import statistics
# New admission is deliberately not inherited from the consumed official run.
from candidates.qwen2_exact64_diagnostic_fullblock import gates


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


OracleGate = gates.OracleGate

def dependencies():
    from candidates.qwen2_fullblock_ci_dut import runtime_adapter
    runtime_adapter.initialize()
    from candidates.qwen2_resident_matrix.dense_block_reduce import check_public_numeric as r
    previous, new = r.runtime()
    (modules,dense,observer,native)=previous
    helper,original,fixtures,public,prefix,_,scalar,suffix,*_=modules
    owner_module,binding,profiles,execution,observation,_=new
    return r,dense,native,helper,original,fixtures,public,prefix,scalar,owner_module,binding,profiles,execution,suffix,observation


TAIL_STAGE_NAMES=dict(pc12_release='PC12_RELEASE',pc13_Dense='PC13_O',pc14_Add='PC14_RESIDUAL',
    pc15_Norm='PC15_NORM',pc16_18_resident_ffn='PC16_18_FFN',pc19_down='PC19_DOWN',
    pc20_residual='PC20_RESIDUAL',launch_result_hold_retire='LAUNCH_RESULT')


def stage_counters(context):
    """Read cumulative native/software counters only at existing boundaries."""
    values={key:0 for key in stages.COUNTER_LIMITS}
    x=context.get('x');physical=context.get('physical');service=context.get('service')
    projection=context.get('projection');shared=context.get('shared');silu=context.get('silu')
    if x is not None:values.update(completed=x.host.completed,jobs=x.host.jobs,
        accepted_results=x.counts['result_fire'],host_ticks=x.counts['host_model_ticks'])
    if physical is not None:values.update(read_bytes=physical.counts['read_bytes'],write_ack_bytes=physical.counts['write_ack_bytes'])
    if service is not None:values.update(dense_steps=service.counts['dense_steps'],normal_steps=service.counts['normal_steps'],
        dense_fma=int(service.lib.matrix_dense_fmas()),normal_fma=int(service.lib.matrix_normal_fmas()))
    if projection is not None:
        kernel=projection.kernel.report();values.update(exact64_fma=kernel['fmas'],exact64_add=kernel['adds'])
    if shared is not None:values['scalar_calls']=sum(shared.calls.values())
    if silu is not None:values['silu_calls']=silu.calls
    return values


def stage_failure(log,context,error):
    """Do not let a failed counter read or logger mask the original error."""
    try:
        kind='TIMEOUT' if telemetry.is_budget(error) else 'RESOURCE' if isinstance(error,MemoryError) else 'INTERNAL'
        return log.failure(log.active[0],kind,counters=stage_counters(context)) if log.active is not None else False
    except BaseException:return False


class StageCheckedTelemetry(telemetry.SparseTelemetry):
    def __init__(self,*args,stage_log,**kwargs):
        self.stage_log=stage_log
        super().__init__(*args,**kwargs)
    def emit(self,*args,**kwargs):
        self.stage_log.check()
        return super().emit(*args,**kwargs)


def run(out, data, reference, *, reviewed_source_manifest=None, kernel_library=None):
    gates.require_execution()
    global DATA
    started=time.monotonic(); cpu=time.process_time()
    reviewed_sources=gates.require_review(reviewed_source_manifest)
    limits=gates.require_budget()
    gates.require_final_reference()
    kernel_library,kernel_identity=gates.kernel_artifact(kernel_library)
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
    report=dict(schema=1,status='STARTED',scope='DIAGNOSTIC_SOFTWARE_OWNER', performance='NO_GO', hardware_mapping='NOT_IMPLEMENTED',
        diagnostic_numeric_pass=False, diagnostic_acceptance_sealed=False,
        chisel_full_prefill_pass=False, model_corresponds_to_current_chisel=False,
        old_pass_inherited=False,rtl_executed=False,eda_executed=False,fullblock_pass=False,
        hardware_cycles=None,model_ticks_are_hardware_cycles=False,finalfence=False,
        preloaded_intermediates=[],allowed_input_roles=sorted(INPUT_ROLES),
        actual_outputs_sealed=False,acceptance_sealed=False,
        inner_wall_seconds=limits['inner_wall_seconds'],outer_wall_seconds=limits['outer_wall_seconds'],compile_executed=False,
        whole_block_terminal=False,resource_limits=limits,scalar_sfu_unified_physical_arbiter_proven=False,
        reviewed_source_manifest=reviewed_source_manifest,historical_approval_inherited=False,
        exact64_native_artifact=kernel_identity)
    def checkpoint(): save(out/'RESULT.json',report)
    checkpoint()
    gate=OracleGate(DATA,out,REFERENCE)
    stage_log=stages.StageLog(out/'STAGES.jsonl',dict(cpu_seconds=limits['cpu_seconds'],
        wall_seconds=limits['inner_wall_seconds'],address_space_bytes=limits['rss_bytes'],output_bytes=limits['output_bytes']))
    stage_context={}
    progress=StageCheckedTelemetry(out/'PROGRESS.jsonl',started=started,cpu=cpu,budget=limits['inner_wall_seconds'],stage_log=stage_log)
    try:
        progress.start();stage_log.begin('SETUP',counters=stage_counters(stage_context));progress.mark('dependency_setup')
        r,dense,native,helper,original,fixtures,public,prefix,scalar,owner_module,binding,profiles,execution,suffix,observation=dependencies()
        from candidates.qwen2_exact64_diagnostic_fullblock.public_binding import (
            DiagnosticPublicExecution, DiagnosticVReductionDriver, expected_kv_identity)
        from candidates.qwen2_attention_shared_a_integration.banks import LoanDenseOwner, banked_scratch
        from candidates.qwen2_attention_resident_candidate.owner import ResidentPV32AttentionOwner
        from candidates.qwen2_attention_resident_candidate.observation import ResidentAttentionObservation
        from candidates.qwen2_exact64_projection_integration.kernel import Exact64Kernel
        from candidates.qwen2_exact64_projection_integration.owner import Exact64ProjectionOwner
        from candidates.qwen2_exact64_projection_integration.driver import Exact64PublicDriver
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
        save(out/'native_artifact_reuse.json',reuse)
        progress.mark('tool_hashes_and_fresh_setup')
        import numpy as np
        import yaml
        tool_paths={'python':Path(sys.executable).resolve(),'numpy_multiarray':Path(np._core._multiarray_umath.__file__).resolve(),
                    'compiler':Path(built['compiler']['path']),'matrix_library':Path(built['library']),
                    'exact64_library':Path(kernel_library),
                    'numpy_init':Path(np.__file__).resolve(),'yaml_init':Path(yaml.__file__).resolve()}
        tools_before={k:dict(path=str(p),sha256=sha(p),bytes=p.stat().st_size) for k,p in tool_paths.items()}
        report['tools_before']=tools_before
        report['tool_versions']=dict(python=sys.version,numpy=np.__version__,pyyaml=yaml.__version__,compiler=built['compiler']['version'])
        report['reference_capture_runtime_is_separate']=True
        report['execution_environment']={k:os.environ.get(k) for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS')}
        report['affinity']=sorted(os.sched_getaffinity(0))
        checkpoint()
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
            owner=LoanDenseOwner(original.numeric.model.PrefixWorkspace(
                region.base,region.limit-region.base,8,2560),enable_dense_drain=True,enable_k_window=True,
                enable_ffn_window=True,enable_ffn_tiles=True,enable_ffn_drain=True)
            selected=dense.selected_library(library)
            require(selected.sf_entrypoint=='sf_vector_bf16_v1','original BF16 SiLU selection required')
            require(library.td_reset()==0 and selected.sf_reset()==0,'fresh Matrix/selected SiLU reset failed')
            silu=ObservedSiluLibrary(selected,128)
            service=binding.ProfiledMatrixService(library,profiles.QWEN2_QKV_PROFILE)
            shared=scalar.ScalarService()
            report['scalar_environment_audit']=list(gate.environment_events)
            projection=Exact64ProjectionOwner(Exact64Kernel(kernel_library),max_rows=128)
            x=DiagnosticPublicExecution(public.PublicFrontend(physical.metadata_port(),f.config),owner,
                original.numeric.CappedTrace(out/'host_trace_prefix.jsonl'),started+limits['inner_wall_seconds'],fixture=f,
                host=public.group.HostControl(enabled=True,legacy_prefix=True,legacy_attention=True),
                prefix_owner=execution.OfficialPrefixOwner(shared),attention_owner=ResidentPV32AttentionOwner(service,shared,
                    scratch=banked_scratch(owner.a_banks),identity=expected_kv_identity(physical)),
                matrix_service=service)
            progress.context.update(x=x,physical=physical,service=service,shared=shared,memory=memory)
            stage_context.update(progress.context,projection=projection,silu=silu)
            ledger=statistics.StageLedger(x,physical,memory,silu)
            report['source_guards']=dict(matrix=service.identity,scalar=shared.identity)
            report['base_commit']=shared.identity['recipe']['git_head']
            report['public_metadata']=helper.metadata_identity(f)
            report['initial_unprovided_readonly']=sorted(n for n,a in f.allocations.items() if a.readonly and n not in inputs)
            report['same_live_identity_initial']=statistics.identity(x,physical,memory)
            report['diagnostic_identity_initial']=accounting.identity(x,projection)
            report['producers']=[]
            report['exact64_projections']=[]
            for pc,name in enumerate(PRODUCERS):
                ledger.transition('pc'+str(pc)+'_'+name)
                progress.mark('prefix_pc'+str(pc)+'_'+name)
                stage_log.transition(stages.OWNER_STAGES[pc],counters=stage_counters(stage_context))
                job=x.advance_to_request()['ordinary_request']
                require(job is not None and job.tag&0xffff==pc and job.dst==f.allocations[name].address,'typed pc/producer binding')
                if pc in (1,4):
                    driver=Exact64PublicDriver(x,physical,job,projection)
                    details=driver.run()
                    report['exact64_projections'].append(details)
                elif job.kind=='Dense':
                    driver=DiagnosticVReductionDriver(x,physical,job)
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
            stage_log.transition('PC9_KV_APPEND',counters=stage_counters(stage_context))
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
            stage_log.transition('PC10_12_ATTENTION',counters=stage_counters(stage_context))
            x.arm_attention(physical,job)
            capture=ResidentAttentionObservation(x.attention_owner,source_sha256=sources)
            counters_before=Counter(physical.counts);scalar_before=Counter(shared.calls)
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
            report['observation']=capture.save(out/'attention_observation')
            require(report['observation']['status'].startswith('COMPLETE_'),'Attention observation incomplete')
            att=physical.raw(job.dst,job.write_bytes)
            pv=np.frombuffer(capture._bytes('pv_bf16'),dtype='<u4').reshape(12,128,128)
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
            report['diagnostic_debts_at_pc12']=accounting.debts(x,projection)
            require(not any(report['diagnostic_debts_at_pc12'].values()),'diagnostic pc12 debts remain')
            totals=accounting.v_totals(x.reduction_reports)
            exact=accounting.exact64_totals(report['exact64_projections'])
            report['observed_v_totals']=totals
            report['observed_exact64_qk_totals']=exact
            report['shared_a_route']=x.attention_router.report()
            a=report['attention']
            require(a['normal_fma_delta']==a['result']['executed_macs']==608698368 and
                a['result']['useful_macs']==25362432 and a['accepted']['matrix_requests']==a['accepted']['matrix_results']==1188864 and
                a['dense_fma_delta']==0,'Attention actual accepted/FMA schedule counters differ')
            report['schedule_prediction_and_observation_at_pc12']=dict(legacy_qk_steps_prediction=792576,legacy_pv_steps_prediction=792576,
                pv32_qk_steps_prediction=792576,pv32_pv_steps_prediction=396288,pv32_total_step_prediction=1188864,
                actual_matrix_requests=a['accepted']['matrix_requests'],actual_normal_fma=a['normal_fma_delta'],
                actual_useful_fma=a['result']['useful_macs'],
                useful_over_executed=a['result']['useful_macs']/a['result']['executed_macs'],
                full_4096_opportunity_count=a['accepted']['matrix_requests']*4096,hardware_busy_fraction=None,
                software_state_ticks=a['backend']['functional_state_ticks'],
                counter_kind='software functional events and actual C FMA, not hardware cycles/utilization')
            report['observed_totals_at_pc12']=dict(dense_fma_calls=report['matrix']['dense_fma_calls'],
                normal_fma_calls=report['matrix']['normal_fma_calls'],
                useful_macs=totals['useful_macs']+exact['fmas']+a['result']['useful_macs'],
                executed_macs=totals['executed_macs']+exact['fmas']+a['result']['executed_macs'],
                exact64_software_fma_calls=exact['fmas'],exact64_software_add_calls=exact['adds'])
            report['slice_updates_equivalent_v_only']=dict(count=totals['actual_c_fma_calls']//512,
                independently_clocked_slice_handshake=False,derivation='V-only observed old Matrix C FMA calls / (16*32); exact64 Q/K have no MatrixStream issue')
            def tail_stage(name):
                ledger.transition(name)
                progress.mark(name)
                stage_log.transition(TAIL_STAGE_NAMES[name],counters=stage_counters(stage_context))
            actual,report['execution']=tail.execute_tail(x,physical,silu,out,memory=memory,
                attention_job=job,stage=tail_stage)
            stage_log.transition('FINAL_SEAL',counters=stage_counters(stage_context))
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
            report['diagnostic_backend_debts']=accounting.debts(x,projection)
            require(not any(report['diagnostic_backend_debts'].values()),'diagnostic final debts remain')
            report['diagnostic_identity_final']=accounting.identity(x,projection)
            require(report['diagnostic_identity_initial']==report['diagnostic_identity_final'],'diagnostic storage identity drift')
            require(not any(report['backend_debts'].values()),'fullblock debts remain')
            report['whole_schedule_prediction_and_observation']=accounting.whole(
                report['matrix'],report['statistics'],x.launch_result,silu,ledger.intervals,exact)
            report['local_retention']=retention.seal(out,actual,silu_bytes,capture,report)
            report['local_retention_verified_before_seal']=retention.verify(out,report['local_retention'])
            report['executed_repository_imports']=sorted(observed)
            report['actual_outputs_sealed']=True
            progress.mark('whole_launch_output_seal')
            report['status']='DIAGNOSTIC_ACTUAL_OUTPUTS_SEALED_WHOLE_PUBLIC21';checkpoint()
        # No official tensor has been read at any point above this seal.
        require(not gate.reference_reads,'premature oracle reads')
        progress.mark('post_seal_official_comparison')
        stage_log.transition('POSTSEAL_COMPARISON',counters=stage_counters(stage_context))
        gate.open_after_seal(dict(actual_outputs_sealed=True,public_completions=x.host.completed,
            actual_owner_jobs=x.host.jobs,accepted_launch_results=x.counts['result_fire'],finalfence=True,
            outstanding_debts={**report['backend_debts'],**report['diagnostic_backend_debts']},same_live_identity=report['same_live_identity_initial']==report['same_live_identity_final']))
        ref,reference_bytes=gates.validate_references(DATA,REFERENCE)
        report['numerical_policy']=native.load_policy(ROOT)
        report.update(compare.official(out,report,capture,actual,silu_bytes,ref,reference_bytes,native,np))
        report['reference_reads_after_seal']=gate.reference_reads
        report['isolation_scope']='explicit Python model read paths and post-seal gate; not an OS sandbox or interception of arbitrary native syscalls'
        progress.mark('final_source_input_reference_tool_hashes')
        after=gates.sources()
        report['source_sha256_after']=after
        report['input_identity_after']=gates.input_identity()
        report['raw_identity_after']=gates.raw_identity(DATA)
        report['reference_identity_after']={n:dict(bytes=len(v),sha256=sha(REFERENCE/(n+'.f32le'))) for n,v in reference_bytes.items()}
        require(report['raw_identity_after']==preflight['raw_tensors'],'raw BF16 source drift')
        require(all(report['reference_identity_after'][n]['sha256']==ref['outputs'][n]['sha256'] for n in reference_bytes),'reference payload drift')
        report['evidence_sha256_after']={p:sha(ROOT/p) for p in evidence}
        report['tools_after']={k:dict(path=str(p),sha256=sha(p),bytes=p.stat().st_size) for k,p in tool_paths.items()}
        report['native_artifact_identity_after']=native_artifact.identity()
        report['native_artifact_audit']=list(gate.artifact_reads)
        report['scalar_environment_audit']=list(gate.environment_events)
        require(report['native_artifact_identity_after']==reuse['artifact_identity_before'],'native artifact drift')
        require(after==sources and report['evidence_sha256_after']==evidence and report['tools_after']==tools_before,'source/evidence/tool drift')
        require(all(report['input_identity_after'][n]['sha256']==ready['roles'][n]['sha256'] for n in inputs),'input drift')
        report['local_retention_verified_after_comparison']=retention.verify(out,report['local_retention'])
        report.update(status='PASS_DIAGNOSTIC_SOFTWARE_OWNER' if report['diagnostic_numeric_pass'] else 'FAIL_DIAGNOSTIC_SOFTWARE_OWNER',
            host_wall_seconds=time.monotonic()-started,host_cpu_seconds=time.process_time()-cpu,
            peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            full_per_producer_official_acceptance=False,missing_official_raw_nodes=['qraw','kraw','vraw'],
            typed_attention_bit_exact_executed=False,hardware_utilization=None)
        progress.mark('final_receipt_write')
        report['telemetry']=progress.report()
        report['acceptance_sealed']=False
        report['fullblock_pass']=False
        report['diagnostic_acceptance_sealed']=bool(report['diagnostic_numeric_pass'])
        stage_log.finish(counters=stage_counters(stage_context))
        checkpoint();progress.check();progress.stop();return report
    except BaseException as e:
        stage_failure(stage_log,stage_context,e)
        progress.stop()
        telemetry.attach_failure(report,e,stage=progress.stage,started=started,cpu=cpu,gate=gate,context=progress.context)
        report['scalar_environment_audit']=list(gate.environment_events)
        if 'x' in locals() and 'projection' in locals():
            try:report['failed_diagnostic_debts']=accounting.debts(x,projection)
            except Exception as failure:report['failed_diagnostic_debt_error']=type(failure).__name__
        report['telemetry']=progress.report()
        try:report['source_sha256_after_failure']=gates.sources()
        except Exception as failure:report['failure_source_recheck_error']=repr(failure)
        if 'capture' in locals() and capture.closed and not capture.active:
            try:report['failed_observation']=capture.save(out/'failed_attention_observation')
            except Exception as error:report['failed_observation_error']=str(error)
        checkpoint()
        contextual=telemetry.contextual_error(progress.stage,e)
        if contextual is not e:raise contextual from e
        raise
    finally:
        progress.stop()
        if 'x' in locals():
            x.trace.close()


def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--actual',action='store_true')
    for name in ('data','reference','out','reviewed-source-manifest','kernel-library'):
        ap.add_argument('--'+name)
    a=ap.parse_args(argv)
    if a.actual:
        gates.require_execution()
        require(all(getattr(a,name) is not None for name in ('data','reference','out','reviewed_source_manifest','kernel_library')),
            'actual requires data/reference/output, new reviewed source and exact64 artifact')
        limits=gates.require_budget()
        resource.setrlimit(resource.RLIMIT_CPU,(limits['cpu_seconds'],limits['cpu_seconds']))
        resource.setrlimit(resource.RLIMIT_AS,(limits['rss_bytes'],limits['rss_bytes']))
        resource.setrlimit(resource.RLIMIT_FSIZE,(limits['file_bytes'],limits['file_bytes']))
        result=run(a.out,a.data,a.reference,reviewed_source_manifest=a.reviewed_source_manifest,kernel_library=a.kernel_library)
        print(json.dumps({k:result[k] for k in ('status','host_wall_seconds','peak_rss_kib')}),flush=True)
        return 0 if result['diagnostic_numeric_pass'] else 1
    require(all(getattr(a,name) is None for name in ('data','reference','out','reviewed_source_manifest','kernel_library')),
        'actual arguments require explicit reviewed execution')
    print(json.dumps(dict(status='NOT_EXECUTED',scope='DIAGNOSTIC_SOFTWARE_OWNER',performance='NO_GO',
        hardware_mapping='NOT_IMPLEMENTED',actual_execution_authorized=False,fullblock_pass=False,
        chisel_full_prefill_pass=False,requires_new_source_policy=True,requires_new_reference_pair=True,
        requires_new_budgets=True,requires_reviewed_native_artifact=True)))
    return 0

if __name__=='__main__':raise SystemExit(main())
