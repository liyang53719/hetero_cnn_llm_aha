#!/usr/bin/env python3
"""New M128 pc0..8 held-completion software gate. No archived PASS or RTL claim."""
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
OUTPUT_ROOT = ROOT/'work/qwen2_live_qkv_numeric_m128_20261014'
DATA = None
sys.path.insert(0, str(ROOT))
INPUT_ROLES = frozenset(('x','gamma0','wq','wk','wv','bq','bk','bv','rope'))
PRODUCERS = ('n0','qraw','qr','q','kraw','kr','k','vraw','v')
from candidates.qwen2_live_qkv_model_m128 import gates


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
    helper,original,fixtures,public,prefix,_,scalar,*_=modules
    owner_module,binding,profiles,execution,_,_=new
    return r,dense,native,helper,original,fixtures,public,prefix,scalar,owner_module,binding,profiles,execution


def run(out, data):
    global DATA
    gates.require_final_inputs()
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
    report=dict(schema=1,status='STARTED',scope='M128 public21 pc0..8; pc8 public completion held',
        old_pass_inherited=False,rtl_executed=False,eda_executed=False,fullblock_pass=False,
        hardware_cycles=None,model_ticks_are_hardware_cycles=False,finalfence=False,
        preloaded_intermediates=[],allowed_input_roles=sorted(INPUT_ROLES))
    def checkpoint(): save(out/'RESULT.json',report)
    checkpoint()
    gate=OracleGate(DATA,out)
    try:
        r,dense,native,helper,original,fixtures,public,prefix,scalar,owner_module,binding,profiles,execution=dependencies()
        sources=gates.sources()
        report['source_sha256_before']=sources
        report['source_manifest_sha256']=hashlib.sha256(json.dumps(sources,sort_keys=True).encode()).hexdigest()
        inputs, ready, evidence, preflight = gates.validate_inputs(DATA)
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
            x=execution.ReducedPublicExecution(public.PublicFrontend(physical.metadata_port(),f.config),owner,
                original.numeric.CappedTrace(out/'host_trace_prefix.jsonl'),started+570,fixture=f,
                host=public.group.HostControl(enabled=True,legacy_prefix=True,legacy_attention=True),
                prefix_owner=execution.OfficialPrefixOwner(shared),attention_owner=execution.OfficialAttentionOwner(service,shared),
                matrix_service=service)
            report['source_guards']=dict(matrix=service.identity,scalar=shared.identity)
            report['base_commit']=shared.identity['recipe']['git_head']
            report['public_metadata']=helper.metadata_identity(f)
            report['initial_unprovided_readonly']=sorted(n for n,a in f.allocations.items() if a.readonly and n not in inputs)
            report['producers']=[]
            for pc,name in enumerate(PRODUCERS):
                job=x.advance_to_request()['ordinary_request']
                require(job is not None and job.tag&0xffff==pc and job.dst==f.allocations[name].address,'typed pc/producer binding')
                if job.kind=='Dense':
                    driver=execution.ReductionDriver(x,physical,job)
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
            held=x.ports()['completion']
            require(x.host.pc==8 and x.host.completed==8 and held is not None and x.launch_result is None,'pc8 held boundary')
            for _ in range(5):
                x.idle_edge()
                require(x.ports()['completion']==held and x.host.completed==8,'held completion changed')
            physical.check_coexistence()
            for name,region in physical.regions.items():
                if not region['readonly'] and name not in PRODUCERS:
                    require(not region['written'] and not region['acked'] and not region['terminal'], 'unexecuted suffix modified '+name)
            report['physical_memory']=physical.report()
            report['execution']=x.report()
            report['scalar_calls']=dict(shared.calls)
            report['matrix']=service.report()
            report['held_boundary']=dict(pc=x.host.pc,completed=x.host.completed,completion=asdict(held),
                launch_result=x.launch_result,finalfence=False,v_published=physical.regions['v']['published'])
            debts=dict(matrix_owned=service.owner is not None,scalar_owned=shared.client is not None,
                dma_pending=physical.pending is not None,owner_pending=owner.pending is not None,
                owner_fifo=len(owner.fifo),owner_read=owner.read_active is not None,
                owner_a_hold=owner.a_hold is not None,owner_a_rmw=owner.a_rmw_pending is not None,
                accepted_write=owner.accepted_write is not None,tile_lease=owner.tiles.leased,
                tile_busy=not owner.tiles.idle,a_lease=owner.lease is not None,
                reduction_active=x.reduction is not None,reset_required=x.reset_required())
            require(not any(debts.values()),'accepted backend obligations outstanding')
            report['backend_debts']=debts
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
            report['observed_totals']=dict(totals)
            report['slice_updates_equivalent']=dict(count=totals['actual_c_fma_calls']//512,
                independently_clocked_slice_handshake=False,derivation='observed C FMA calls / (16*32); model executes all 8 slices per wide step')
            report['executed_repository_imports']=sorted(observed)
            report['status']='ACTUAL_OUTPUTS_SEALED_PC8_HELD';checkpoint()
        # No official tensor has been read at any point above this seal.
        require(not gate.reference_reads,'premature oracle reads')
        gate.opened=True
        ref, reference_bytes = gates.validate_references(DATA,ready)
        report['numerical_policy']=native.load_policy(ROOT)
        comparisons={}
        for name in PRODUCERS:
            if name not in ref['outputs']:
                comparisons[name]=dict(status='NO_OFFICIAL_RAW_REFERENCE',official_numeric_pass=None,
                    finite=True,all_bytes_acknowledged=True,scope='raw pre-bias FP32 producer')
                continue
            spec=ref['outputs'][name]
            raw=reference_bytes[name]
            require(len(raw)==spec['bytes'] and hashlib.sha256(raw).hexdigest()==spec['sha256'],'reference identity '+name)
            expected=np.frombuffer(raw,dtype='<f4').reshape(spec['shape'])
            if name in ('q','k'): expected=expected.transpose(0,2,1,3).reshape(128,-1)
            else: expected=expected.reshape(128,-1)
            actual=np.frombuffer((out/(name+'.f32le')).read_bytes(),dtype='<f4').reshape(128,-1)
            metrics=native.compare(actual,expected)
            verdict=native.stage_verdict(name,metrics,'bf16',report['numerical_policy'])
            comparisons[name]=dict(metrics=metrics,verdict=verdict,official_numeric_pass=verdict['passed'])
            diff=actual.astype('float64')-expected.astype('float64')
            np.save(out/(name+'.error_f64.npy'),diff,allow_pickle=False)
        report['producer_comparisons']=comparisons
        report['reference_reads_after_seal']=gate.reference_reads
        report['isolation_scope']='explicit Python model read paths and post-seal gate; not an OS sandbox or interception of arbitrary native syscalls'
        report['official_observed_nodes_bit_exact']=all(comparisons[n]['metrics']['bit_exact'] for n in gates.OFFICIAL)
        report['official_observed_node_pass']=gates.official_pass(comparisons)
        after=gates.sources()
        report['source_sha256_after']=after
        report['input_identity_after']={n:dict(bytes=len(v),sha256=sha(DATA/'inputs'/(n+'.bin'))) for n,v in inputs.items()}
        report['raw_identity_after']=gates.raw_identity(DATA)
        report['reference_identity_after']={n:dict(bytes=len(v),sha256=sha(DATA/'reference'/(n+'.f32le'))) for n,v in reference_bytes.items()}
        require(report['raw_identity_after']==preflight['raw_tensors'],'raw BF16 source drift')
        require(all(report['reference_identity_after'][n]['sha256']==ref['outputs'][n]['sha256'] for n in reference_bytes),'reference payload drift')
        report['evidence_sha256_after']={p:sha(ROOT/p) for p in evidence}
        report['tools_after']={k:dict(path=str(p),sha256=sha(p),bytes=p.stat().st_size) for k,p in tool_paths.items()}
        require(after==sources and report['evidence_sha256_after']==evidence and report['tools_after']==tools_before,'source/evidence/tool drift')
        require(all(report['input_identity_after'][n]['sha256']==ready['roles'][n]['sha256'] for n in inputs),'input drift')
        report.update(status='PASS_M128_OFFICIAL_OBSERVED_PRODUCERS_PC8_HELD' if report['official_observed_node_pass'] else 'FAIL_M128_OFFICIAL_PRODUCER_CONTRACT',
            host_wall_seconds=time.monotonic()-started,host_cpu_seconds=time.process_time()-cpu,
            peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            full_per_producer_official_acceptance=False,missing_official_raw_nodes=['qraw','kraw','vraw'])
        checkpoint();return report
    except BaseException as e:
        report.update(status='FAILED',error=repr(e),traceback=traceback.format_exc(),host_wall_seconds=time.monotonic()-started)
        if 'physical' in locals(): report['failed_physical_memory']=physical.report()
        if 'x' in locals(): report['failed_execution']=x.report()
        checkpoint();raise


def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--actual',action='store_true',help='explicitly execute fresh M128 software model')
    ap.add_argument('--data',help='existing published input-recipe run directory')
    ap.add_argument('--out',help='fresh directory under work/qwen2_live_qkv_numeric_m128_20261014')
    a=ap.parse_args(argv)
    if not a.actual:
        require(a.data is None and a.out is None,'data/out require explicit --actual')
        gates.verify_dependencies()
        print(json.dumps(dict(status='NOT_EXECUTED',rows=128,scope='software pc0..8 held completion',
            input_loading=False,build=False,rtl=False,fullblock=False,
            input_recipe_finalized=gates.pins()['input_recipe_finalized'])))
        return 0
    require(a.data is not None and a.out is not None,'--actual requires --data and --out')
    resource.setrlimit(resource.RLIMIT_AS,(2<<30,2<<30))
    result=run(a.out,a.data)
    print(json.dumps({k:result[k] for k in ('status','host_wall_seconds','peak_rss_kib')}),flush=True)
    return 0 if result['official_observed_node_pass'] else 1


if __name__=='__main__':raise SystemExit(main())
