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
                    # STARTUP-ONLY STOP: no original advance or producer body exists below.
                    from integration.startup_boundary import verify_boundary
                    report['startup_boundary']=verify_boundary(
                        x=x,physical=physical,memory=memory,silu=silu,service=service,
                        shared=shared,gate=gate,wholeblock=wholeblock,report=report,
                        out=out,pc=pc,name=name)
                    from integration.attention_route_probe import observe_empty_lifecycle
                    report['attention_observer_routes']=observe_empty_lifecycle(
                        Capture=Fixed93FullblockAttentionObservation,owner=x.attention_owner,
                        source_root=ROOT,source_manifest=runtime['source_manifest'],out=out,
                        trace_limits=runtime['attention_trace_limits'],
                        dispatcher=wholeblock.trace_dispatcher,gate=gate)
                    report['startup_boundary_after_observer']=verify_boundary(
                        x=x,physical=physical,memory=memory,silu=silu,service=service,
                        shared=shared,gate=gate,wholeblock=wholeblock,report=report,
                        out=out,pc=pc,name=name)
                    break
                wholeblock.check()
        require(not gate.reference_reads and not gate.opened,'startup must not open reference oracle')
        report.update(status='PASS_STARTUP_BOUNDARY_ONLY',scope='real M128 initializer, before first advance',
            startup_boundary_reached=True,fullblock_pass=False,M128_execution=False,
            official_observed_node_pass=False,numerical_acceptance=False,
            whole_block_terminal=False,finalfence=False,actual_outputs_sealed=False,
            acceptance_sealed=False,host_wall_seconds=time.monotonic()-started,
            host_cpu_seconds=time.process_time()-cpu,
            peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            reference_reads_after_startup=list(gate.reference_reads),
            cleanup_directory_reads=list(gate.cleanup_directory_reads),
            source_cache_bypasses=list(gate.source_cache_bypasses))
        checkpoint();progress.stop()
        return report
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
    ap=argparse.ArgumentParser(description='Independent startup-only initializer probe; never a fullblock run')
    ap.add_argument('--actual',action='store_true')
    ap.add_argument('--data');ap.add_argument('--reference');ap.add_argument('--out')
    ap.add_argument('--reviewed-source-manifest')
    a=ap.parse_args(argv)
    if not a.actual:
        require(all(v is None for v in (a.data,a.reference,a.out,a.reviewed_source_manifest)),
                'actual parameters require explicit actual startup admission')
        print(json.dumps(dict(status='NOT_EXECUTED',startup_only=True,actual_authorized=False)))
        return 0
    require(all(v is not None for v in (a.data,a.reference,a.out,a.reviewed_source_manifest)),
            'all exact startup paths and reviewed manifest required')
    from integration.aux_output import AuxiliaryOutputBudget
    with AuxiliaryOutputBudget(Path(a.out), 4194304) as auxiliary:
        result=run(a.out,a.data,a.reference,reviewed_source_manifest=a.reviewed_source_manifest)
        require(result.get('status')=='PASS_STARTUP_BOUNDARY_ONLY' and result.get('startup_boundary_reached') is True,
                'startup boundary not established')
        require(result.get('attention_observer_routes',{}).get('status') ==
                'PASS_ACTUAL_EMPTY_OBSERVER_LIFECYCLE_ROUTES_ONLY' and
                result.get('startup_boundary_after_observer',{}).get('zero_model_tasks') is True,
                'actual empty observer routes and repeated zero-task boundary required')
        require(sys.gettrace() is None, 'startup observer trace remains active after cleanup')
        result['startup_cleanup_returned_normally']=True
        result['startup_trace_disabled_after_cleanup']=True
        save(Path(a.out)/'RESULT.json',result)
    print(json.dumps(dict(status=result['status'],startup_only=True,fullblock_pass=False,
        auxiliary_output_budget=auxiliary.report())),flush=True)
    return 0

if __name__=='__main__':raise SystemExit(main())
