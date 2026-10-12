#!/usr/bin/env python3
"""Bounded public21 execution with explicit QKV partial-order policy.

Only the existing Q/K/V Dense dispatch changes. Inputs come from the original
public map, all intermediate values come from actual acknowledged writes, and
both independent and native comparison payloads remain closed until terminal.
This is a software port/transaction model; ticks are not hardware cycles.
"""
import argparse
import ctypes as C
import importlib
import json
from pathlib import Path
import resource
import sys
import time

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from ..official_bf16 import check_numeric as prior
from ..official_bf16 import execution as policy
base=prior.base
require,sha,encoded,file_sha=prior.require,prior.sha,prior.encoded,prior.file_sha
PREFIX='candidates/qwen2_resident_matrix/dense_block_reduce/'
EXECUTION_FILES=('k_window_model.py','vector_add_model.py','sum_tiles.py','dense_drain.py',
    'profile.py','matrix_binding.py','public_coordinator.py','public_execution.py',
    'observation.py','check_public_numeric.py','k_window.patch','vector_add.patch',
    'dense_drain.patch','DenseTileSumBridge.scala','DenseBlockReductionCoordinator.scala')
POLICY_ID='qwen2-public21-official-bf16-v2-qkv-explicit-block-pair-v1'


def source_hashes():
    result=prior.source_hashes()
    result.update({PREFIX+p:file_sha(ROOT/PREFIX/p) for p in EXECUTION_FILES})
    # Reference packaging is an independent verifier, never an actual producer.
    for path in sorted((ROOT/PREFIX/'reference').rglob('*')):
        if path.is_file() and path.suffix in ('.py','.inc','.json') and '__pycache__' not in path.parts:
            result[str(path.relative_to(ROOT))]=file_sha(path)
    return result


def runtime():
    old=prior.runtime()
    sources=source_hashes()
    with base.frozen_exec(sources):
        modules=tuple(importlib.import_module('candidates.qwen2_resident_matrix.dense_block_reduce.'+p)
            for p in ('dense_drain','matrix_binding','profile','public_execution','observation','reference.completed'))
    require(source_hashes()==sources,'new reduction source changed during import')
    return old,modules


def validate_rows(rows):
    require(type(rows) is int and rows in (16,128),'cold public21 rows must be exactly 16 or 128')
    return rows


def prepare(out,compile_receipt,reference,reference_sha256,rows=16):
    out=Path(out).resolve()
    validate_rows(rows)
    require(not out.exists(),'fresh integration snapshot required')
    out.mkdir(parents=True)
    # Revalidate original source, public metadata, payload, table and native
    # archives; this performs no arithmetic or actual-chain execution.
    original_path,s=prior.prepare(out/'original_policy',compile_receipt,rows)
    _,modules=runtime();completed=modules[-1]
    independent=completed.reference_spec(reference,reference_sha256)
    require(independent['rows']==rows and independent['readonly_input']['input_x_sha256']==
            s['reference']['inputs']['input_x_sha256'],'independent reference raw input differs')
    sources=source_hashes()
    s=dict(s,status='PREPARED_REDUCED_PUBLIC21_NOT_EXECUTED',reduction_policy=POLICY_ID,
        source_sha256=sources,source_manifest_sha256=sha(encoded(sources)),
        original_snapshot=str(original_path),original_snapshot_sha256=file_sha(original_path),
        independent_reference=independent,old_pass_inherited=False)
    for relative,digest in sources.items():
        raw=(ROOT/relative).read_bytes();require(sha(raw)==digest,'snapshot source drift')
        target=out/'frozen_sources'/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    require(source_hashes()==sources,'source drift while sealing snapshot')
    path=out/'SNAPSHOT.json';path.write_bytes(encoded(s));return path,s


def verify_snapshot(path,digest):
    path=Path(path).resolve();require(file_sha(path)==digest,'new snapshot hash differs')
    s=json.loads(path.read_text());original=prior.verify_snapshot(s['original_snapshot'],s['original_snapshot_sha256'])
    _,modules=runtime()
    require(s['status']=='PREPARED_REDUCED_PUBLIC21_NOT_EXECUTED' and s['reduction_policy']==POLICY_ID
        and validate_rows(s['rows'])==s['rows'] and s['source_sha256']==source_hashes()
        and s['source_manifest_sha256']==sha(encoded(s['source_sha256'])),'new source/policy/domain drift')
    for key in ('rows','epoch','input_spec','loaded_inputs','binaries','metadata','host_tools','reference'):
        require(s[key]==original[key],'original input/tool/public identity changed: '+key)
    for relative,expected in s['source_sha256'].items():
        require(file_sha(path.parent/'frozen_sources'/relative)==expected,'frozen source drift: '+relative)
    ref=s['independent_reference']
    require(modules[-1].reference_spec(ref['directory'],ref['result_sha256'])==ref,'independent reference drift')
    return s


def independent_bytes(ref,name):
    relative='raw_stages/'+name
    found=[e for e in ref['artifacts'] if e['path']==relative]
    require(len(found)==1,'independent output missing/duplicate: '+name)
    raw=(Path(ref['directory'])/relative).read_bytes();record=found[0]
    require(len(raw)==record['bytes'] and sha(raw)==record['sha256'],'independent output drift: '+name)
    return raw


def compare(s,actual,inputs,capture,silu,native):
    import numpy as np
    result=prior.compare(s,actual,inputs,capture,silu,native)
    result['old_sequential_producer_diagnostic']={k:result[k] for k in
        ('whole_outputs','actual_observed_nodes','fixed_arithmetic_pass')}
    ref,rows=s['independent_reference'],s['rows'];fixed={}
    for index,(name,width) in enumerate(prior.old.STAGE_WIDTHS.items()):
        raw=independent_bytes(ref,'phase_%d_%s_recipe.f32le'%(index,name))
        require(len(raw)==len(actual[name])*4,'independent output geometry')
        fixed[name]=native.compare(np.frombuffer(actual[name].tobytes(),dtype='<f4'),np.frombuffer(raw,dtype='<f4'))
    observed={}
    mapping={'scores':'scores_bf16','logits':'scores_bf16','softmax_fp32':'softmax_fp32',
             'prob':'prob_bf16','pv':'pv_bf16'}
    for name,field in mapping.items():
        f=capture.fields[field];a=np.frombuffer(capture._bytes(field),dtype='<f4').reshape(f['shape'])
        if name=='pv':
            raw=independent_bytes(ref,'phase_6_att_recipe.f32le')
            expected=np.frombuffer(raw,dtype='<f4').reshape(rows,12,128).transpose(1,0,2)
        else:expected=np.frombuffer(independent_bytes(ref,name+'.f32le'),dtype='<f4').reshape(a.shape)
        mask=np.frombuffer(bytes(f['observed']),dtype=np.uint8).reshape(a.shape).astype(bool)
        observed[name]=native.compare(a[mask],expected[mask])
    observed['silu']=native.compare(np.frombuffer(silu,dtype='<f4'),
                                  np.frombuffer(independent_bytes(ref,'silu.f32le'),dtype='<f4'))
    result.update(whole_outputs=fixed,actual_observed_nodes=observed,
        fixed_arithmetic_pass=all(v['bit_exact'] for v in (*fixed.values(),*observed.values())),
        independent_reference=ref,official_target='official_self_cache',
        independent_self_cache_is_auxiliary=True,old_sequential_producer_is_auxiliary=True,
        acceptance_requires_all_assigned_official_observed_node_gates=True,
        full_29_node_acceptance=False,reference_reuse='same frozen raw input; original official archive; new independently executed block/pair arithmetic')
    return result


def run(out,path,digest,*,wall_budget=900):
    out,path=Path(out).resolve(),Path(path).resolve()
    require(not out.exists() and 0<wall_budget<=1800,'fresh bounded reduced public21 run required')
    s=verify_snapshot(path,digest)
    (modules,dense,_,native),new=runtime()
    helper,original,fixtures,public,prefix,_,scalar,suffix,physical_adapter,matrix,_,_=modules
    owner_module,binding,profiles,execution,observation,_=new
    require(helper.host_tool_identity()==s['host_tools'],'execution host tool drift')
    out.mkdir(parents=True);started,cpu=time.monotonic(),time.process_time();deadline=started+wall_budget
    report=dict(status='PINNED_NOT_EXECUTED',policy=POLICY_ID,rows=s['rows'],source_sha256=s['source_sha256'],
        input_spec=s['input_spec'],binaries=s['binaries'],snapshot=str(path),snapshot_sha256=digest,
        rtl_executed=False,scala_executed=False,hardware_cycles=None,prelaunch_intermediate_payloads=[],
        old_pass_inherited=False,native_acceptance='PENDING_OBSERVED_NODE_GATES')
    def save():(out/'summary.json').write_bytes(encoded(report))
    try:
        with base.frozen_exec(s['source_sha256']) as observed,policy.reference_gate(s['input_spec']) as gate:
            f=fixtures.make_qwen2_21_fixture(s['rows'],s['epoch'])
            require(helper.metadata_identity(f)==s['metadata'],'public metadata changed')
            inputs=prior.load_inputs(s['input_spec'],s['rows'],s['reference'])
            require(base.identities(inputs)==s['loaded_inputs'],'raw input identity changed')
            physical=prefix.PhysicalMemory(f,{n:base.bytes_provider(v) for n,v in inputs.items()})
            memory=physical_adapter.FullGraphMemory(physical);n,region=original.numeric,f.config.regions[3]
            owner=owner_module.DenseReductionOwner(n.model.PrefixWorkspace(region.base,region.limit-region.base,s['epoch']+1,2560),
                enable_dense_drain=True,enable_k_window=True,enable_ffn_window=True,enable_ffn_tiles=True,enable_ffn_drain=True)
            library=matrix.configure_library(C.CDLL(s['binaries']['library']));selected=dense.selected_library(library)
            require(library.td_reset()==selected.sf_reset()==0,'initial arithmetic reset failed')
            service=binding.ProfiledMatrixService(library,profiles.QWEN2_QKV_PROFILE);shared_scalar=scalar.ScalarService()
            x=execution.ReducedPublicExecution(public.PublicFrontend(physical.metadata_port(),f.config),owner,n.CappedTrace(),deadline,
                fixture=f,host=public.group.HostControl(enabled=True,legacy_prefix=True,legacy_attention=True),
                prefix_owner=policy.OfficialPrefixOwner(shared_scalar),
                attention_owner=policy.OfficialAttentionOwner(service,shared_scalar),matrix_service=service)
            silu=policy.ObservedSiluLibrary(selected,s['rows']);guarded=gate.library(silu)
            capture=observation.ProfiledAttentionMonitoringObservation(x.attention_owner,source_sha256=s['source_sha256'])
            report.update(loaded_inputs=base.identities(inputs),metadata=s['metadata']);save()
            report['prefix_execution']=execution.execute_public_prefix(x,physical,guarded,out)
            report.update(status='ACTUAL_PREFIX_COMPLETE',prefix_host_wall_seconds=time.monotonic()-started);save()
            with capture:actual,report['execution']=suffix.execute_public_suffix(x,physical,guarded,out,memory=memory)
            report['whole_terminal_host_wall_seconds']=time.monotonic()-started
            # The unchanged suffix driver carries a historical policy label;
            # execution itself never evaluates a native numerical contract.
            report['execution']['inherited_native_acceptance_label']=report['execution']['native_acceptance']
            report['execution']['native_acceptance']='NOT_EVALUATED_BY_EXECUTION_SEE_COMPARISON'
            require(x.launch_result and x.launch_result['completed']==21 and x.counts['result_fire']==1 and not x.reset_required(),
                    'whole public terminal missing')
            report['observation']=capture.save(out/'attention_observation')
            require(report['observation']['status'].startswith('COMPLETE_'),'actual Attention observation incomplete')
            import numpy as np
            pv=np.frombuffer(capture._bytes('pv_bf16'),dtype='<u4').reshape(12,s['rows'],128)
            require(pv.transpose(1,0,2).copy().tobytes()==actual['att'].tobytes(),'observed PV differs from ACKed attention output')
            silu_bytes=silu.seal(actual['act'].tobytes());(out/'actual_silu.f32le').write_bytes(silu_bytes)
            report['sealed_actual_outputs']={name:dict(bytes=len(v)*4,sha256=sha(v.tobytes())) for name,v in actual.items()}
            report['sealed_silu_sha256']=sha(silu_bytes)
            report['status']='WHOLE_TERMINAL_ACTUAL_OUTPUTS_SEALED';save()
            gate.opened=True
            report['comparison']=compare(s,actual,inputs,capture,silu_bytes,native)
            require(report['comparison']['fixed_arithmetic_pass'],'actual chain differs from independent block/pair recipe')
            require(source_hashes()==s['source_sha256'] and base.identities(inputs)==s['loaded_inputs'],'post-run source/input drift')
            official=report['comparison']['methods']['official_self_cache']
            report.update(status=('PASS_REDUCED_BF16_OBSERVED_OFFICIAL_GATES' if official['numerical_status']=='PASS_OBSERVED_ONLY' else 'FAIL_OFFICIAL_OBSERVED_NODE_GATES'),source_sha256_after=source_hashes(),
                executed_imports_observed=sorted(observed),native_acceptance=official['numerical_status'],
                full_29_node_acceptance=False,actual_dataflow_pass=True,host_wall_seconds=time.monotonic()-started,
                host_cpu_seconds=time.process_time()-cpu,host_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            save();return report
    except Exception as error:
        report.update(status='FAILED',error=str(error),host_wall_seconds=time.monotonic()-started)
        if 'x' in locals():report['failed_host']=x.report()
        if 'physical' in locals():report['failed_memory']=physical.report()
        try:report['failure_capture']=prior.retain_failed_run(out,locals().get('physical'),locals().get('capture'))
        except Exception as preservation_error:report['failure_capture_error']=str(preservation_error)
        save();raise


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--prepare-only',action='store_true');p.add_argument('--compile-receipt',type=Path)
    p.add_argument('--reference',type=Path);p.add_argument('--reference-sha256');p.add_argument('--rows',type=int,choices=(16,128),default=16)
    p.add_argument('--snapshot',type=Path);p.add_argument('--snapshot-sha256');p.add_argument('--wall-budget',type=int,default=900)
    a=p.parse_args()
    if a.prepare_only:
        path,s=prepare(a.out,a.compile_receipt,a.reference,a.reference_sha256,rows=a.rows)
        print(json.dumps(dict(path=str(path),sha256=file_sha(path),status=s['status'])),flush=True)
    else:
        r=run(a.out,a.snapshot,a.snapshot_sha256,wall_budget=a.wall_budget)
        print(json.dumps({k:r[k] for k in ('status','rows','native_acceptance','host_wall_seconds')}),flush=True)
        if r['native_acceptance']!='PASS_OBSERVED_ONLY':raise SystemExit(1)

if __name__=='__main__':main()
