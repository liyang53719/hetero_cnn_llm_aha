#!/usr/bin/env python3
"""Fresh same-live-chain M128 pc0..12 held-completion software gate. No archived PASS or RTL claim."""
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
OUTPUT_ROOT = ROOT/'work/qwen2_live_attention_numeric_m128_20261014'
DATA = None
sys.path.insert(0, str(ROOT))
INPUT_ROLES = frozenset(('x','gamma0','wq','wk','wv','bq','bk','bv','rope'))
PRODUCERS = ('n0','qraw','qr','q','kraw','kr','k','vraw','v')
from candidates.qwen2_live_attention_model_m128 import gates, boundary, compare


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
    from candidates.qwen2_resident_matrix.dense_block_reduce import check_public_numeric as r
    previous, new = r.runtime()
    (modules,dense,observer,native)=previous
    helper,original,fixtures,public,prefix,_,scalar,suffix,*_=modules
    owner_module,binding,profiles,execution,observation,_=new
    return r,dense,native,helper,original,fixtures,public,prefix,scalar,owner_module,binding,profiles,execution,suffix,observation


def run(out, data, reference):
    global DATA
    gates.require_final_reference()
    require(gates.pins().get('actual_execution_authorized') is True,'M128 execution awaiting independent review/authorization')
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
    started=time.monotonic(); cpu=time.process_time()
    report=dict(schema=1,status='STARTED',scope='M128 public21 fresh pc0..12; pc12 public completion held',
        old_pass_inherited=False,rtl_executed=False,eda_executed=False,fullblock_pass=False,
        hardware_cycles=None,model_ticks_are_hardware_cycles=False,finalfence=False,
        preloaded_intermediates=[],allowed_input_roles=sorted(INPUT_ROLES))
    def checkpoint(): save(out/'RESULT.json',report)
    checkpoint()
    gate=OracleGate(DATA,out,REFERENCE)
    try:
        r,dense,native,helper,original,fixtures,public,prefix,scalar,owner_module,binding,profiles,execution,suffix,observation=dependencies()
        from candidates.qwen2_live_attention_model_m128.public_binding import PV32PublicExecution,PV32ReductionDriver
        from candidates.qwen2_live_attention_model_m128.pv32_owner import OfficialPV32AttentionOwner
        from candidates.qwen2_live_attention_model_m128.pv32_observation import PV32AttentionObservation
        sources=gates.sources()
        report['source_sha256_before']=sources
        report['source_manifest_sha256']=hashlib.sha256(json.dumps(sources,sort_keys=True).encode()).hexdigest()
        inputs, ready, evidence, preflight = gates.validate_inputs(DATA,REFERENCE)
        report.update(evidence_sha256_before=evidence,input_identity_before=ready['roles'],
            input_validation=preflight,postimage_correspondence=gates.correspondence())
        sys.addaudithook(gate.audit)
        library,built=dense.build_library(out/'build')
        report['compile']=built
        # Compatibility receipt for unchanged small-test verifier; derives only from this fresh build.
        save(out/'build/compile.json',dict(status='PASS_HOST_BUILD_ONLY',returncode=built['returncode'],
            sources_before=built['source_sha256'],sources_after=built['source_sha256'],argv=built['argv'],
            library=built['library'],library_sha256=built['library_sha256'],
            derived_from='official_bf16_compile.json',old_pass_inherited=False))
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
        with r.base.frozen_exec(sources) as observed:
            f=fixtures.make_qwen2_21_fixture(128,7)
            require(all(len(raw)==f.allocations[name].storage_bytes for name,raw in inputs.items()),'typed readonly extent')
            physical=prefix.PhysicalMemory(f,{n:r.base.bytes_provider(v) for n,v in inputs.items()})
            region=f.config.regions[3]
            owner=owner_module.DenseReductionOwner(original.numeric.model.PrefixWorkspace(
                region.base,region.limit-region.base,8,2560),enable_dense_drain=True,enable_k_window=True,
                enable_ffn_window=True,enable_ffn_tiles=True,enable_ffn_drain=True)
            require(library.td_reset()==0,'fresh Matrix reset failed')
            service=binding.ProfiledMatrixService(library,profiles.QWEN2_QKV_PROFILE)
            shared=scalar.ScalarService()
            x=PV32PublicExecution(public.PublicFrontend(physical.metadata_port(),f.config),owner,
                original.numeric.CappedTrace(out/'host_trace_prefix.jsonl'),started+570,fixture=f,
                host=public.group.HostControl(enabled=True,legacy_prefix=True,legacy_attention=True),
                prefix_owner=execution.OfficialPrefixOwner(shared),attention_owner=OfficialPV32AttentionOwner(service,shared),
                matrix_service=service)
            report['source_guards']=dict(matrix=service.identity,scalar=shared.identity)
            report['base_commit']=shared.identity['recipe']['git_head']
            report['public_metadata']=helper.metadata_identity(f)
            report['initial_unprovided_readonly']=sorted(n for n,a in f.allocations.items() if a.readonly and n not in inputs)
            report['same_live_identity_initial']=boundary.identity(x,physical)
            report['producers']=[]
            for pc,name in enumerate(PRODUCERS):
                job=x.advance_to_request()['ordinary_request']
                require(job is not None and job.tag&0xffff==pc and job.dst==f.allocations[name].address,'typed pc/producer binding')
                if job.kind=='Dense':
                    driver=PV32ReductionDriver(x,physical,job)
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
            job=x.advance_to_request()['ordinary_request']
            require(job is not None and job.kind=='Attention' and job.tag&0xffff==12 and
                (job.a,job.b,job.c,job.dst)==tuple(f.specs[n][0] for n in ('q','cache_k','cache_v','att')) and
                (job.m,job.n,job.k,job.write_bytes)==(128,1536,128,786432),'fused Attention original typed binding')
            capture=PV32AttentionObservation(x.attention_owner,source_sha256=sources)
            counters_before=Counter(physical.counts);scalar_before=Counter(shared.calls)
            dense_fma_before=int(library.matrix_dense_fmas());normal_fma_before=int(library.matrix_normal_fmas())
            with capture:
                attention=suffix.execute_attention_owner(x,physical,job)
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
            report['same_live_identity_final']=boundary.identity(x,physical)
            require(report['same_live_identity_initial']==report['same_live_identity_final'],'live objects/banks/service replaced')
            physical.check_coexistence()
            report['unexecuted_outputs']=boundary.pristine_suffix(physical,set(PRODUCERS)|{'kv','att'})
            report['physical_memory']=physical.report();report['execution']=x.report()
            report['scalar_calls']=dict(shared.calls);report['matrix']=service.report()
            report['backend_debts']=boundary.debts(x,physical)
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
            require(a['normal_fma_delta']==a['result']['executed_macs']==608698368 and
                a['result']['useful_macs']==25362432 and a['accepted']['matrix_requests']==a['accepted']['matrix_results']==1188864 and
                a['dense_fma_delta']==0,'Attention actual accepted/FMA schedule counters differ')
            report['schedule_prediction_and_observation']=dict(legacy_qk_steps_prediction=792576,legacy_pv_steps_prediction=792576,
                pv32_qk_steps_prediction=792576,pv32_pv_steps_prediction=396288,pv32_total_step_prediction=1188864,
                actual_matrix_requests=a['accepted']['matrix_requests'],actual_normal_fma=a['normal_fma_delta'],
                actual_useful_fma=a['result']['useful_macs'],
                useful_over_executed=a['result']['useful_macs']/a['result']['executed_macs'],
                full_4096_opportunity_count=a['accepted']['matrix_requests']*4096,hardware_busy_fraction=None,
                software_state_ticks=a['backend']['functional_state_ticks'],
                counter_kind='software functional events and actual C FMA, not hardware cycles/utilization')
            report['observed_totals']=dict(dense_fma_calls=report['matrix']['dense_fma_calls'],
                normal_fma_calls=report['matrix']['normal_fma_calls'],
                useful_macs=totals['useful_macs']+a['result']['useful_macs'],
                executed_macs=totals['executed_macs']+a['result']['executed_macs'])
            report['slice_updates_equivalent']=dict(count=totals['actual_c_fma_calls']//512,
                independently_clocked_slice_handshake=False,derivation='observed C FMA calls / (16*32); model executes all 8 slices per wide step')
            report['executed_repository_imports']=sorted(observed)
            report['status']='ACTUAL_OUTPUTS_SEALED_PC12_HELD';checkpoint()
        # No official tensor has been read at any point above this seal.
        require(not gate.reference_reads,'premature oracle reads')
        gate.opened=True
        ref,reference_bytes=gates.validate_references(DATA,REFERENCE)
        report['numerical_policy']=native.load_policy(ROOT)
        report.update(compare.official(out,report,capture,ref,reference_bytes,native,np))
        report['reference_reads_after_seal']=gate.reference_reads
        report['isolation_scope']='explicit Python model read paths and post-seal gate; not an OS sandbox or interception of arbitrary native syscalls'
        after=gates.sources()
        report['source_sha256_after']=after
        report['input_identity_after']={n:dict(bytes=len(v),sha256=sha(DATA/'inputs'/(n+'.bin'))) for n,v in inputs.items()}
        report['raw_identity_after']=gates.raw_identity(DATA)
        report['reference_identity_after']={n:dict(bytes=len(v),sha256=sha(REFERENCE/(n+'.f32le'))) for n,v in reference_bytes.items()}
        require(report['raw_identity_after']==preflight['raw_tensors'],'raw BF16 source drift')
        require(all(report['reference_identity_after'][n]['sha256']==ref['outputs'][n]['sha256'] for n in reference_bytes),'reference payload drift')
        report['evidence_sha256_after']={p:sha(ROOT/p) for p in evidence}
        report['tools_after']={k:dict(path=str(p),sha256=sha(p),bytes=p.stat().st_size) for k,p in tool_paths.items()}
        require(after==sources and report['evidence_sha256_after']==evidence and report['tools_after']==tools_before,'source/evidence/tool drift')
        require(all(report['input_identity_after'][n]['sha256']==ready['roles'][n]['sha256'] for n in inputs),'input drift')
        report.update(status='PASS_M128_OFFICIAL_OBSERVED_ATTENTION_PC12_HELD' if report['official_observed_node_pass'] else 'FAIL_M128_OFFICIAL_OBSERVED_CONTRACT',
            host_wall_seconds=time.monotonic()-started,host_cpu_seconds=time.process_time()-cpu,
            peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            full_per_producer_official_acceptance=False,missing_official_raw_nodes=['qraw','kraw','vraw'],
            typed_attention_bit_exact_executed=False,hardware_utilization=None)
        checkpoint();return report
    except BaseException as e:
        report.update(status='FAILED',error=repr(e),traceback=traceback.format_exc(),host_wall_seconds=time.monotonic()-started)
        if 'physical' in locals(): report['failed_physical_memory']=physical.report()
        if 'x' in locals(): report['failed_execution']=x.report()
        if 'service' in locals(): report['failed_matrix']=service.report()
        if 'shared' in locals(): report['failed_scalar_calls']=dict(shared.calls)
        if 'capture' in locals() and capture.closed and not capture.active:
            try:report['failed_observation']=capture.save(out/'failed_attention_observation')
            except Exception as error:report['failed_observation_error']=str(error)
        checkpoint();raise


def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--actual',action='store_true',help='explicitly execute fresh M128 software model')
    ap.add_argument('--data',help='existing published input-recipe run directory')
    ap.add_argument('--reference',help='frozen independent Attention reference directory')
    ap.add_argument('--out',help='fresh directory under work/qwen2_live_attention_numeric_m128_20261014')
    a=ap.parse_args(argv)
    if not a.actual:
        require(a.data is None and a.out is None and a.reference is None,'data/out require explicit --actual')
        gates.verify_dependencies()
        print(json.dumps(dict(status='NOT_EXECUTED',rows=128,scope='software pc0..12 held completion',
            input_loading=False,build=False,rtl=False,fullblock=False,
            input_recipe_finalized=gates.pins()['input_recipe_finalized'],
            attention_reference_finalized=gates.pins()['attention_reference_finalized'],
            actual_execution_authorized=gates.pins().get('actual_execution_authorized',False))))
        return 0
    require(a.data is not None and a.out is not None and a.reference is not None,'--actual requires --data, --reference and --out')
    resource.setrlimit(resource.RLIMIT_AS,(2<<30,2<<30))
    result=run(a.out,a.data,a.reference)
    print(json.dumps({k:result[k] for k in ('status','host_wall_seconds','peak_rss_kib')}),flush=True)
    return 0 if result['official_observed_node_pass'] else 1


if __name__=='__main__':raise SystemExit(main())
