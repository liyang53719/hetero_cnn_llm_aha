"""One explicitly launched cold M16/M128 producer, then archived comparison.

Does not execute native PyTorch, actual owners/Matrix, Chisel or RTL. Official
arrays are opened only after every producer output has been sealed.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import time
from . import builder as b
from . import workload as w

STAGES=w.STAGES
LAYOUT_SHA='70b6a3678d5cf2fa14ab7aae61f1f97fffdbf5dac1f17fb0fa6aa4a822fe7170'

def verified_preparation(directory,expected_sha):
    directory=Path(directory).resolve();p=b.frozen_json(directory/'PREPARED.json',expected_sha)
    rows=w.cold_rows(p['rows'],p['past_tokens'])
    b.require(p['status']=='PREPARED_SOURCE_ONLY_NOT_EXECUTED' and p['version']==b.VERSION,'only prepared cold M16/M128 launch is admitted here')
    for relative,digest in p['source_sha256'].items():b.require(b.file_sha(b.ROOT/relative)==digest,'prepared generator source drift')
    archive,top,cold=b.archive_context(rows,archive_directory=p['old_archive']['directory'])
    original,_=b.regenerate_original();profile=Path(p['profile_path']).read_bytes();candidate=(directory/'candidate.cpp').read_bytes()
    b.require(b.sha(candidate)==p['transform']['candidate_cpp_sha256'] and b.file_sha(directory/'block_layout.h')==p['header_sha256']==b.HEADER_SHA,'prepared source/header drift')
    b.verify_transform(original,candidate,profile)
    arena=Path(p['readonly_input']['path']);b.require(b.file_sha(arena)==p['readonly_input']['sha256']==cold['inputs']['readonly_sha256'],'readonly input drift')
    b.verify_input_binding(p,top,cold)
    b.require((directory/'empty_cache.bin').read_bytes()==b'','cold cache must be empty')
    expected_compile=[p['compile_command'][0],*b.FLAGS,str(directory/'candidate.cpp'),'-o',str(directory/'candidate')]
    b.require(p['compile_command']==expected_compile,'compile flags/paths differ')
    expected_run=[str(directory/'candidate'),str(arena),str(rows),str(directory/'raw_stages'),'0',str(directory/'empty_cache.bin'),str(directory/'empty_cache.bin')]
    b.require(p['proposed_execution_command']==expected_run,'execution command differs')
    return p,archive,top,cold

def run(directory,prepared_sha):
    directory=Path(directory).resolve();prepared,archive,top,cold=verified_preparation(directory,prepared_sha)
    rows=w.cold_rows(prepared['rows'],prepared['past_tokens'])
    b.require(not (directory/'candidate').exists() and not (directory/'raw_stages').exists() and not (directory/'RESULT.json').exists(),'one fresh compile/run only')
    source_files=[b.HERE/'builder.py',b.HERE/'dot16.inc',Path(__file__),b.HERE/'test_builder.py',b.HERE/'workload.py',b.HERE/'test_workload.py']
    source_pins={str(f.relative_to(b.ROOT)):b.file_sha(f) for f in source_files}
    compiler=Path(prepared['compile_command'][0]).resolve()
    frozen=dict(version=b.VERSION,rows=rows,past_tokens=0,prepared_sha256=prepared_sha,source_sha256=source_pins,
        profile_sha256=prepared['profile_sha256'],original_cpp_sha256=b.ORIGINAL_CPP_SHA,
        candidate_cpp_sha256=prepared['transform']['candidate_cpp_sha256'],header_sha256=b.HEADER_SHA,
        readonly_input=prepared['readonly_input'],actual_input_source=prepared['actual_input_source'],compiler_path=str(compiler),compiler_sha256=b.file_sha(compiler),
        compile_command=prepared['compile_command'],run_command=prepared['proposed_execution_command'],
        compile_wall_budget_seconds=w.COMPILE_WALL_SECONDS,run_wall_budget_seconds=w.RUN_WALL_SECONDS[rows],processes=1,threads=1,
        process_scope='One producer invocation and one active compile command; compiler/linker may create child processes',
        env=dict(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1'),
        original_gate=prepared['thresholds'],original_FAIL=prepared['old_archive']['preserved_failures'])
    (directory/'FROZEN.json').write_text(json.dumps(frozen,indent=2)+'\n')
    report=dict(status='STARTED_INDEPENDENT_REFERENCE',version=b.VERSION,rows=rows,
        frozen_sha256=b.file_sha(directory/'FROZEN.json'),prepared_sha256=prepared_sha,
        producer_role='Independent auxiliary reference only; old sequential producer is not an additional acceptance gate',
        actual_chain_executed=False,new_official_forward_executed=False,rtl_executed=False,
        thresholds_changed=False,old_FAIL_preserved=prepared['old_archive']['preserved_failures'],
        implementation_acceptance=False,native_acceptance=False)
    def save():(directory/'RESULT.json').write_text(json.dumps(report,indent=2)+'\n')
    def execute(command,kind,timeout):
        def guard():
            resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3));resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_CPU,(timeout,timeout));os.nice(5)
        started=time.monotonic();env=os.environ.copy();env.update(frozen['env'])
        with (directory/(kind+'.stdout.log')).open('w') as stdout,(directory/(kind+'.stderr.log')).open('w') as stderr:
            done=subprocess.run(command,cwd=directory,stdout=stdout,stderr=stderr,timeout=timeout,preexec_fn=guard,env=env)
        receipt=dict(returncode=done.returncode,wall_seconds=time.monotonic()-started,command=command,stdout_sha256=b.file_sha(directory/(kind+'.stdout.log')),stderr_sha256=b.file_sha(directory/(kind+'.stderr.log')))
        report[kind]=receipt;save();b.require(done.returncode==0,kind+' failed; logs retained');return receipt
    try:
        execute(prepared['compile_command'],'compile',w.COMPILE_WALL_SECONDS);report['binary_sha256']=b.file_sha(directory/'candidate')
        verified_preparation(directory,prepared_sha)
        (directory/'raw_stages').mkdir();execute(prepared['proposed_execution_command'],'execution',w.RUN_WALL_SECONDS[rows])
        for relative,digest in source_pins.items():b.require(b.file_sha(b.ROOT/relative)==digest,'reference source changed during run')
        verified_preparation(directory,prepared_sha)
        sealed={}
        expected=w.output_inventory(rows)
        b.require({f.name for f in (directory/'raw_stages').iterdir()}==set(expected),'producer output inventory differs')
        for name,size in expected.items():
            path=directory/'raw_stages'/name;b.require(path.is_file() and not path.is_symlink() and path.stat().st_size==size,'producer output size/source differs');sealed[name]=dict(bytes=size,sha256=b.file_sha(path))
        report.update(status='SEALED_INDEPENDENT_REFERENCE_BEFORE_OFFICIAL_READ',sealed_outputs=sealed);save()
        report['comparison']=compare_archived(directory,prepared,archive,top,cold,sealed)
        report.update(status='COMPLETE_INDEPENDENT_REFERENCE_WITH_ARCHIVED_DIAGNOSTIC',full_reference_executed=True)
        save();print(json.dumps(dict(status=report['status'],execution_seconds=report['execution']['wall_seconds'],official_failed_stages=report['comparison']['official_failed_stages'],causal_failed_stages=report['comparison']['causal_failed_stages'],actual_chain_executed=False)),flush=True)
    except Exception as exc:
        report.update(status='FAILED_INDEPENDENT_REFERENCE',error=str(exc));save();raise
    return report

def compare_archived(directory,prepared,archive,top,cold,sealed):
    import numpy as np
    rows=w.cold_rows(prepared['rows'],prepared['past_tokens'])
    source=b.ROOT/'scripts/qwen2_layer0_model_gate.py';b.require(b.file_sha(source)==b.GENERATOR_PINS['scripts/qwen2_layer0_model_gate.py'],'comparison helper drift before import')
    layout=b.ROOT/'candidates/qwen2_resident_matrix/official_bf16/reference_layout.py';b.require(b.file_sha(layout)==LAYOUT_SHA,'Q/K layout decoder drift before import')
    def load(path,name):
        spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
    metrics=load(source,'qkv_reference_compare_only');decode=load(layout,'qkv_reference_layout_only')
    b.require(metrics.load_policy(b.ROOT)==prepared['thresholds'],'original official target limits changed')
    def output(name,shape):
        path=directory/'raw_stages'/name;b.require(b.file_sha(path)==sealed[name]['sha256'],'sealed output changed before comparison');return np.fromfile(path,dtype='<f4').reshape(shape)
    fields={name:output(f'phase_{i}_{name}_recipe.f32le',(1,rows,width)) for i,(name,width) in enumerate(STAGES)}
    for name,heads in [('q',12),('k',2)]:fields[name]=fields[name].reshape(1,rows,heads,128).transpose(0,2,1,3)
    for name in ('cache_k','cache_v'):fields[name]=output(name+'.f32le',(1,rows,2,128)).transpose(0,2,1,3)
    for name in ('scores','logits','softmax_fp32','prob'):fields[name]=output(name+'.f32le',(1,12,rows,rows))
    fields['silu']=output('silu.f32le',(1,rows,8960));fields['pv']=fields['att'].reshape(1,rows,12,128).transpose(0,2,1,3)
    fields['repeat_k']=np.repeat(fields['cache_k'],6,axis=1);fields['repeat_v']=np.repeat(fields['cache_v'],6,axis=1)
    regions={r['name']:r for r in top['build']['layout']['regions']}
    with Path(prepared['readonly_input']['path']).open('rb') as f:
        f.seek(regions['x']['offset']);fields['x']=np.frombuffer(f.read(rows*1536*4),'<f4').reshape(1,rows,1536)
        for name in ('cos','sin'):
            f.seek(regions[name]['offset']);half=metrics.bf16(np.frombuffer(f.read(rows*64*4),'<f4').reshape(rows,64));fields[name]=np.concatenate((half,half),axis=1)
    inventory={a['path']:a for a in cold['artifacts']};comparisons={};causal={};reference_hashes={}
    for name,value in fields.items():
        rel=f'references/official_self_cache/{name}.f32le';entry=inventory[rel];path=archive/'cold'/rel;raw=path.read_bytes();b.require(len(raw)==entry['bytes'] and b.sha(raw)==entry['sha256'],'official archived comparison bytes differ: '+name);reference_hashes[rel]=entry['sha256']
        expected=decode.read_native_reference(raw,rows=rows,method='official_self_cache',name=name,shape=value.shape)
        m=metrics.compare(value,expected);comparisons[name]=dict(metrics=m,verdict=metrics.stage_verdict(name,m,'bf16',prepared['thresholds']),coverage='complete independent software producer')
        if name in ('scores','logits','softmax_fp32','prob'):
            mask=np.broadcast_to(np.tri(rows,dtype=bool),value.shape);cm=metrics.compare(value[mask],expected[mask]);causal[name]=dict(metrics=cm,verdict=metrics.stage_verdict(name,cm,'bf16',prepared['thresholds']),coverage='causal positions only for comparability with actual owner observation')
    return dict(stages=comparisons,causal_attention=causal,official_failed_stages=[n for n,r in comparisons.items() if r['verdict']['passed'] is False],causal_failed_stages=[n for n,r in causal.items() if r['verdict']['passed'] is False],comparison_source_sha256=b.file_sha(source),layout_source_sha256=b.file_sha(layout),official_artifact_sha256=reference_hashes,producer_outputs_sealed_before_official_read=True,compared_field_count=len(fields),missing_explicit_mask=True,full_29_node_acceptance=False,old_FAIL_preserved=prepared['old_archive']['preserved_failures'],actual_chain_executed=False,independent_reference_is_auxiliary=True,old_sequential_producer_not_dual_AND_gate=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--directory',type=Path,required=True);ap.add_argument('--prepared-sha',required=True);args=ap.parse_args();run(args.directory,args.prepared_sha)
