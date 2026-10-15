"""One representative M16 public21 cost diagnostic; unchanged arithmetic owners."""
import argparse
from collections import Counter
from dataclasses import asdict
import hashlib,json,resource,signal,sys,tempfile,time,traceback
from pathlib import Path
from . import common as c,geometry as g,inputs as inp
from .stage_log import StageLog,COUNTER_LIMITS,safe_last

def run(out):
    c.limits(1200,1230);started=time.monotonic();cpu=time.process_time();out=c.fresh_output(out,'model')
    (out/'tmp').mkdir();tempfile.tempdir=str(out/'tmp')
    report=dict(status='STARTED',scope='M16_PUBLIC21_STAGE_COST_DIAGNOSTIC',logical_rows=16,physical_matrix_rows=128,
      diagnostic_software_owner=True,hardware_mapping='NOT_IMPLEMENTED',performance='NO_GO',fullblock_pass=False,
      formal_reference_contract=False,model_completed=False,actual_outputs_sealed=False,hardware_cycles=None,
      old_wrapper_optimizations_loaded=False,reference_executed=False,intermediate_preloads=[])
    log=StageLog(out/'STAGES.jsonl',g.LIMITS_MODEL);x=physical=service=shared=silu=projection=memory=None
    def counts():
        values={key:0 for key in COUNTER_LIMITS}
        if x is not None:values.update(completed=x.host.completed,jobs=x.host.jobs,accepted_results=x.counts['result_fire'],host_ticks=x.counts['host_model_ticks'])
        if physical is not None:values.update(read_bytes=physical.counts['read_bytes'],write_ack_bytes=physical.counts['write_ack_bytes'])
        if service is not None:values.update(dense_steps=service.counts['dense_steps'],normal_steps=service.counts['normal_steps'],
          dense_fma=int(service.lib.matrix_dense_fmas()),normal_fma=int(service.lib.matrix_normal_fmas()))
        if projection is not None:
            k=projection.kernel.report();values.update(exact64_fma=k['fmas'],exact64_add=k['adds'])
        if shared is not None:values['scalar_calls']=sum(shared.calls.values())
        if silu is not None:values['silu_calls']=silu.calls
        return values
    def stage(name):log.transition(name,counters=counts())
    def checkpoint():c.save(out/'RESULT.json',report)
    stage('SETUP');checkpoint()
    try:
        pins,native=c.check_environment();d=c.dependencies();p=d['p'];sources=c.require_freeze();c.snapshot_sources(out,sources)
        import numpy as np
        g.need(Path(np._core._multiarray_umath.__file__).resolve()==Path(native['numpy_multiarray']['path']),'actual pinned NumPy native loaded')
        kernel_path,matrix_receipt,artifact=c.artifacts()
        values,input_records=inp.load_inputs();report.update(sources=sources,native_before=native,artifact_before=artifact,input_records=input_records,framework_sources=c.runtime_python(pins))
        # No reference directory exists yet. Restrict ignored-work payload reads
        # to the declared initial roles, source freeze and verified native files.
        allowed={str((c.ROOT/v['path']).resolve()) for v in inp.ROLES.values()}|{str((c.ROOT/n).resolve()) for n in inp.MANIFESTS}
        allowed|={str(c.FREEZE),str(c.PRIOR/'RESULT.json'),str(kernel_path),str(c.PRIOR/'matrix_build/official_bf16_compile.json'),str(Path(matrix_receipt['library']).resolve())}
        runtime_root=c.ROOT/'work/runtime_recovery/site-packages'
        def audit(event,args):
            if event!='open' or not isinstance(args[0],(str,bytes)):return
            path=Path(args[0].decode() if isinstance(args[0],bytes) else args[0]).absolute()
            if path.is_relative_to(c.ROOT/'work'):
                g.need(str(path) in allowed or path.is_relative_to(out) or path.is_relative_to(runtime_root),'undeclared work payload read/write')
        sys.addaudithook(audit)
        f=p.make_qwen2_21_fixture(16,7)
        g.need(all(len(raw)==f.allocations[n].storage_bytes for n,raw in values.items()),'M16 typed initial extents including full rope')
        physical=p.PhysicalMemory(f,{n:(lambda i,raw=raw:raw[i:i+64]) for n,raw in values.items()})
        memory=d['FullGraphMemory'](physical);region=f.config.regions[3]
        owner=p.LoanDenseOwner(p.numeric.model.PrefixWorkspace(region.base,region.limit-region.base,8,2560),
          enable_dense_drain=True,enable_k_window=True,enable_ffn_window=True,enable_ffn_tiles=True,enable_ffn_drain=True)
        library=p.dense_silu.configure_silu_library(p.dense_silu.configure_library(c.C.CDLL(matrix_receipt['library'])))
        selected=p.dense_silu.selected_library(library)
        g.need(library.td_reset()==0 and selected.sf_reset()==0 and selected.sf_entrypoint=='sf_vector_bf16_v1','fresh original native state')
        silu=d['ObservedSiluLibrary'](selected,16);service=p.ProfiledMatrixService(library,p.QWEN2_QKV_PROFILE);shared=p.ScalarService()
        projection=p.Exact64ProjectionOwner(p.Exact64Kernel(kernel_path),max_rows=16)
        x=p.DiagnosticPublicExecution(p.public.PublicFrontend(physical.metadata_port(),f.config),owner,p.numeric.CappedTrace(out/'HOST.jsonl'),
          started+1230,fixture=f,host=p.public.group.HostControl(enabled=True,legacy_prefix=True,legacy_attention=True),
          prefix_owner=p.OfficialPrefixOwner(shared),attention_owner=p.ResidentPV32AttentionOwner(service,shared,
            scratch=p.banked_scratch(owner.a_banks),identity=p.expected_kv_identity(physical)),matrix_service=service)
        ledger=d['statistics'].StageLedger(x,physical,memory,silu)
        report.update(identity_before=d['statistics'].identity(x,physical,memory),diagnostic_identity_before=d['accounting'].identity(x,projection),
                      producers=[],exact64_projections=[])
        for pc,name in enumerate(g.PRODUCERS):
            stage(g.STAGES[pc]);ledger.transition('pc'+str(pc)+'_'+name)
            job=x.advance_to_request()['ordinary_request'];g.need(job is not None and job.tag&65535==pc and job.dst==f.allocations[name].address,'actual producer binding')
            if pc in (1,4):details=p.Exact64PublicDriver(x,physical,job,projection).run();report['exact64_projections'].append(details)
            elif job.kind=='Dense':details=d['DiagnosticVReductionDriver'](x,physical,job).run()
            else:details=p.execute_prefix_owner(x,physical,job)
            g.need(physical.regions[name]['terminal'] and not physical.regions[name]['published'],'actual owner terminal before publication')
            x.publish_completions((pc,));physical.publish(job,x.host)
            if job.kind=='Dense':x.retire_ordinary_bookkeeping()
            raw=physical.raw(job.dst,job.write_bytes);(out/(name+'.f32le')).write_bytes(raw)
            g.need(np.isfinite(np.frombuffer(raw,'<f4')).all(),'finite producer')
            report['producers'].append(dict(pc=pc,name=name,job=asdict(job),details=details,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),ack_bytes=len(physical.regions[name]['acked'])*64))
            checkpoint()
        stage('PC9_KV_APPEND');ledger.transition('pc9_kv_append')
        job=x.advance_to_request()['ordinary_request'];g.need(job.kind=='KvAppend' and job.tag&65535==9 and job.write_bytes==g.ATTENTION['kv_bytes'],'actual M16 KV job')
        before=Counter(physical.counts);details=p.execute_prefix_owner(x,physical,job);kv=physical.raw(job.dst,job.write_bytes)
        k=physical.raw(f.allocations['k'].address,16*256*4);v=physical.raw(f.allocations['v'].address,16*256*4)
        g.need(kv==k+v and len(physical.regions['kv']['acked'])==512,'same-live KV exact-copy ACK')
        (out/'kv.f32le').write_bytes(kv);report['kv_append']=dict(details=details,physical_counter_delta=dict(Counter(physical.counts)-before),bytes=len(kv))
        x.publish_completions((9,));physical.publish(job,x.host);checkpoint()
        stage('PC10_12_ATTENTION');ledger.transition('pc10_12_attention')
        job=x.advance_to_request()['ordinary_request'];g.need(job.kind=='Attention' and job.tag&65535==12 and (job.m,job.n,job.k,job.write_bytes)==(16,1536,128,98304),'actual M16 fused Attention')
        x.arm_attention(physical,job);capture=d['ResidentAttentionObservation'](x.attention_owner,source_sha256=sources)
        before=Counter(physical.counts);normal_before=int(library.matrix_normal_fmas())
        with capture:attention=d['execute_attention_owner'](x,physical,job)
        report['observation']=capture.save(out/'attention_observation');g.need(report['observation']['status'].startswith('COMPLETE_'),'complete M16 observer')
        report['attention']=dict(attention,physical_counter_delta=dict(Counter(physical.counts)-before),normal_fma_delta=int(library.matrix_normal_fmas())-normal_before)
        a=report['attention'];g.need(a['accepted']['matrix_requests']==a['accepted']['matrix_results']==g.ATTENTION['normal_steps'] and
          a['normal_fma_delta']==a['result']['executed_macs']==g.ATTENTION['normal_fma'] and a['result']['useful_macs']==g.ATTENTION['useful_macs'],'actual M16 Attention work')
        att=physical.raw(job.dst,job.write_bytes);pv=np.frombuffer(capture._bytes('pv_bf16'),'<u4').reshape(12,16,128)
        g.need(pv.transpose(1,0,2).copy().tobytes()==att,'actual PV output layout');(out/'att.f32le').write_bytes(att)
        report['attention']['output']=dict(bytes=len(att),sha256=hashlib.sha256(att).hexdigest())
        x.publish_completions((10,11));g.exact_totals(report['exact64_projections']);g.v_totals(x.reduction_reports);checkpoint()
        def tail_stage(name):stage(g.TAIL_STAGES[name]);ledger.transition(name)
        actual,report['execution']=d['tail'].execute_tail(x,physical,silu,out,memory=memory,attention_job=job,stage=tail_stage)
        stage('FINAL_SEAL');report['whole_block_terminal']=True;report['finalfence']=True
        silu_bytes=silu.seal(actual['act'].tobytes());(out/'actual_silu.f32le').write_bytes(silu_bytes)
        report['sealed_actual_outputs']={n:dict(bytes=len(v)*4,sha256=hashlib.sha256(v.tobytes()).hexdigest()) for n,v in actual.items()}
        report['sealed_actual_outputs']['silu']=dict(bytes=len(silu_bytes),sha256=hashlib.sha256(silu_bytes).hexdigest())
        report['statistics']=ledger.finish();report['matrix']=service.report()
        report['whole_accounting']=g.whole(report['matrix'],x.launch_result,silu,report['statistics'])
        report['backend_debts']=dict(d['statistics'].debts(x,physical,memory),**d['accounting'].debts(x,projection))
        g.need(not any(report['backend_debts'].values()),'no final debt')
        g.need(report['identity_before']==d['statistics'].identity(x,physical,memory) and report['diagnostic_identity_before']==d['accounting'].identity(x,projection),'same actual objects throughout')
        report['local_retention']=d['retention'].seal(out,actual,silu_bytes,capture,report)
        g.need(d['retention'].verify(out,report['local_retention']),'actual payload seal')
        _,native_after=c.check_environment();_,_,artifact_after=c.artifacts();_,inputs_after=inp.load_inputs()
        g.need(native_after==native and artifact_after==artifact and inputs_after==input_records and c.require_freeze()==sources,'source/input/native postcheck')
        report.update(status='M16_MODEL_COMPLETE_COST_DIAGNOSTIC',model_completed=True,actual_outputs_sealed=True,native_after=native_after,
          artifact_after=artifact_after,source_post_verified=True,input_post_verified=True,native_post_verified=True,final_counters=counts(),host_cpu_seconds=time.process_time()-cpu,host_wall_seconds=time.monotonic()-started,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        log.finish(counters=counts());report['safe_last_stage']=safe_last(out/'STAGES.jsonl');checkpoint()
        print(json.dumps(dict(status=report['status'],cpu_seconds=report['host_cpu_seconds'],wall_seconds=report['host_wall_seconds'])))
        return 0
    except BaseException as e:
        original_traceback=traceback.format_exc()
        try:
            if log.active:log.failure(log.active[0],'TIMEOUT' if isinstance(e,TimeoutError) else 'VALIDATION' if isinstance(e,ValueError) else 'INTERNAL',counters=counts())
        except BaseException:pass
        report.update(status='M16_MODEL_FAILED',model_completed=False,actual_outputs_sealed=False,error_type=type(e).__name__,error=str(e),traceback=original_traceback,
          host_cpu_seconds=time.process_time()-cpu,host_wall_seconds=time.monotonic()-started,safe_last_stage=safe_last(out/'STAGES.jsonl'),backend_abort_drain_executed=False)
        try:
            if x is not None:report['failure_counters']=counts();report['failed_debts']=dict(d['statistics'].debts(x,physical,memory),**d['accounting'].debts(x,projection))
        except Exception as audit_error:report['failure_debt_error_type']=type(audit_error).__name__
        try:checkpoint()
        except BaseException:pass
        print(json.dumps(dict(status='M16_MODEL_FAILED')));return 1
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        try:
            if x is not None:x.trace.close()
        except BaseException:pass

def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument('--execute',action='store_true');ap.add_argument('--out');args=ap.parse_args(argv)
    if not args.execute:g.need(args.out is None,'execution args require execute');print(json.dumps(dict(status='NOT_EXECUTED')));return 0
    g.need(args.out is not None,'fixed output required');return run(args.out)
if __name__=='__main__':raise SystemExit(main())
