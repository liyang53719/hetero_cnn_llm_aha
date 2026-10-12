"""Actual original-hidden -> RMS/QKV -> Norm256/RoPE software command chain.

No compiler or official forward is run here. Only authenticated original
hidden, checkpoint weights and captured trig tables are initialized. Native
capture bytes may be read for integrity before launch; their intermediate
values are compared numerically only after actual owner terminals, and are
never supplied to owners.
"""
import argparse
import ctypes as C
from dataclasses import asdict
import json
import os
from pathlib import Path
import struct
import sys
import platform
import time

import numpy as np
from . import run_projection_prefix as prior
from .projection_driver import L3ProjectionCoordinator, L3ProjectionPlan
from .norm_rope.coordinator import L3NormRopeCoordinator, L3NormRopePlan
from .norm_rope.owner import QkNorm256Owner, PartialRope64Owner, SOURCE_SHA256
from .norm_rope.scalar import NormRopeScalar
from .norm_rope import fixture
from .norm_rope.compare import compare_case, ObservationRecorder

ROOT=prior.ROOT
SOURCE_FILES=tuple(dict.fromkeys((*prior.SOURCE_FILES,*SOURCE_SHA256,
    'candidates/qwen35_attention_prefill/run_norm_rope.py',
    'src/heteronpu/qwen35_bf16_reference.py',
    'src/heteronpu/model_geometry.py',
    *(str(p.relative_to(ROOT)) for p in sorted((ROOT/'candidates/qwen35_attention_prefill/norm_rope').glob('*.py'))))))
OUTPUT_WIDTHS={**prior.fixture.WIDTHS,'q_norm':2048,'k_norm':512,'raw_gate':2048,'q_rope':2048,'k_rope':512}
sha,persist,snapshot_bytes=prior.sha,prior.persist,prior.snapshot_bytes


def require(ok,detail):
    if not ok:raise ValueError('actual L3 Norm/RoPE runner: '+detail)


def observation_sink(target,owner,family):
    def observe(stage,token,head,words):
        role=('q_norm' if owner.job.role==0 else 'k_norm') if family=='norm' else ('q_rope' if owner.job.heads==8 else 'k_rope')
        target[role](stage,token,head,words)
    return observe


def freeze_observations(output,case,observations,*,prefix="observations"):
    result={}
    for role,entries in observations.items():
        for stage in sorted({k[0] for k in entries}):
            rows=[(key,entries[key]) for key in sorted(entries) if key[0]==stage]
            raw=b''.join(struct.pack('<'+'I'*len(words),*words) for _,words in rows)
            item=snapshot_bytes(output,prefix+'/'+case+'.'+role+'.'+stage+'.f32le',raw)
            item.update(layout='token,head,element; raw uint32 words',rows=[list(k[1:]) for k,_ in rows],widths=[len(words) for _,words in rows])
            result[role+'.'+stage]=item
    return result


def state(coordinator):
    if coordinator is None:return None
    return dict(role=coordinator.role,ticks=coordinator.ticks,completed_commands=len(coordinator.commands),
                terminal=coordinator.response is not None,active=None if coordinator.active is None else coordinator.active.owner.state)


def run(capture_directory,payload_directory,output,*,budget_seconds=600):
    output=Path(output)
    require(not output.exists() and type(budget_seconds) is int and 0<budget_seconds<=900,'fresh directory and wall budget1..900')
    output.mkdir(parents=True)
    start=time.monotonic();coordinator=memory=None;plans=[];active_outputs={};observed=None;active_name=None
    report=dict(status='RUNNING',scope='ACTUAL_TYPED_L3_RMS_QKV_NORM_ROPE_ONLY',budget_seconds=budget_seconds,
        windows=[],actual_outputs={},observations={},rtl_executed=False,chisel_executed=False,
        public_command128_executed=False,full_block_executed=False,hardware_cycles=None,hardware_mac_utilization=None)
    persist(output/'summary.json',report)
    try:
        source_bytes={p:(ROOT/p).read_bytes() for p in SOURCE_FILES}
        sources={p:sha(b) for p,b in source_bytes.items()}
        for p,b in source_bytes.items():snapshot_bytes(output,'source_snapshot/'+p,b)
        report['source_sha256']=sources
        manifest,weights,inputs,identity,extra=fixture.load_fixture(capture_directory,payload_directory)
        library=prior.d.library_from_environment(ROOT)
        vector=prior.Vector16(os.environ['GDN_VECTOR16_LIBRARY'],exception_policy=prior.IEEE_POLICY)
        lib=prior.configure_library(C.CDLL(str(library)));require(lib.td_reset()==0,'one initial Matrix reset')
        matrix,memory,scalar=prior.d.MatrixService(lib),prior.d.TypedMemory(),NormRopeScalar()
        rms=prior.rms.RmsOwner(scalar);norm=QkNorm256Owner(scalar);rope=PartialRope64Owner(scalar)
        address=0x100000
        def allocate(extent,raw=None):
            nonlocal address
            base=address;address+=extent+64
            memory.add_readonly(base,raw) if raw is not None else memory.allocate_output(base,extent)
            return base
        parameters={}
        for role,raw in weights.items():
            physical=raw if role=='input_norm' else np.frombuffer(raw,'<u2').reshape(prior.fixture.WIDTHS[role],1024).T.copy().tobytes()
            parameters[role]=allocate(len(physical),physical)
        norm_parameters={role:allocate(len(raw),raw) for role,raw in extra['weights'].items()}
        rows=identity['rows']
        for index,(name,hidden) in enumerate(inputs.items()):
            outputs={role:allocate(rows*width*2) for role,width in OUTPUT_WIDTHS.items()}
            p=L3ProjectionPlan(tokens=rows,hidden=allocate(len(hidden),hidden),input_weight=parameters['input_norm'],
                packed_q_gate_weight=parameters['packed_q_gate'],k_weight=parameters['k'],v_weight=parameters['v'],
                tag_base=1+index*8,**{role:outputs[role] for role in prior.fixture.WIDTHS})
            c=extra['cases'][name]
            plan=L3NormRopePlan(projection=p,q_norm_weight=norm_parameters['q_norm'],k_norm_weight=norm_parameters['k_norm'],
                q_norm=outputs['q_norm'],k_norm=outputs['k_norm'],gate=outputs['raw_gate'],q_rope=outputs['q_rope'],k_rope=outputs['k_rope'],
                trig=allocate(len(c['trig']),c['trig']),position_base=c['position_base'],trig_tokens=c['trig_tokens'])
            plans.append((name,plan,outputs))
        workspace=prior.PrefixWorkspace(allocate(16384),16384,1);dense=prior.GdnProjectionOwner(workspace)
        libraries=(library,Path(os.environ['MATRIX_SERVICE_COMPILE_RECEIPT']),vector.library,vector.library.with_suffix('.json'))
        snapshots={}
        for name,raw in inputs.items():snapshots['input:'+name]=snapshot_bytes(output,'raw_inputs/'+name+'.bf16le',raw)
        for role,raw in {**weights,**extra['weights']}.items():snapshots['weight:'+role]=snapshot_bytes(output,'raw_weights/'+role+'.bf16le',raw)
        for name,c in extra['cases'].items():snapshots['trig:'+name]=snapshot_bytes(output,'trig/'+name+'.bf16le',c['trig'])
        for i,p in enumerate(libraries):snapshots['library:'+str(p)]=snapshot_bytes(output,'libraries/'+str(i)+'_'+p.name,p.read_bytes())
        snapshots['manifest']=snapshot_bytes(output,'capture_manifest.json',(Path(capture_directory)/'manifest.json').read_bytes())
        identity.update(software_runtime=dict(python=sys.version,python_executable=sys.executable,
            python_executable_sha256=sha(Path(sys.executable).read_bytes()),numpy=np.__version__,machine=platform.machine(),
            fp32_environment='FE_TONEAREST and gradual underflow/signed-zero tested by shared service constructor'),
            source_sha256=sources,libraries={str(p):sha(p.read_bytes()) for p in libraries},
            local_snapshot_files=snapshots,plans={name:asdict(p) for name,p,_ in plans},matrix_reset_count=1,
            raw_weight_layout='checkpoint[N,K] -> physical[K,N] bytes only',trig_generation_executed=False,native_capture_integrity_prevalidated=True,
            native_intermediates_used_as_execution_inputs=False,native_numeric_comparison_after_terminals=True,
            matrix_vector_scalar_memory_shared=True,scalar_flags='legacy C1/B1 Add0/Mul1 fatal0x1e; input RMS explicit op6 retained')
        report['identity']=identity;persist(output/'identity.json',identity)
        initial=(matrix.resource_address,vector.resource_address,id(memory),id(scalar),id(dense),id(dense.a_banks),id(rms),id(norm),id(rope),matrix.epoch)
        all_observations={};all_terminals={};all_actual={}
        for name,plan,active_outputs in plans:
            active_name=name
            recorders={role:ObservationRecorder(rows,heads,kind) for role,heads,kind in
                (('q_norm',8,'norm'),('k_norm',2,'norm'),('q_rope',8,'rope'),('k_rope',2,'rope'))}
            observed={role:rec.events for role,rec in recorders.items()}
            norm.observer=observation_sink(recorders,norm,'norm');rope.observer=observation_sink(recorders,rope,'rope')
            prefix=L3ProjectionCoordinator(memory=memory,dense=dense,matrix=matrix,vector=vector,rms_owner=rms,plan=plan.projection)
            coordinator=L3NormRopeCoordinator(prefix=prefix,norm_owner=norm,rope_owner=rope,plan=plan)
            window_start=time.monotonic();recorded=0;coordinator.start()
            while coordinator.response is None:
                require(time.monotonic()-start<budget_seconds,'software wall budget exceeded')
                coordinator.tick()
                if coordinator.ticks%8192==0:persist(output/'live_progress.json',dict(window=name,elapsed_seconds=time.monotonic()-start,active=state(coordinator)))
                if len(coordinator.commands)!=recorded:
                    command=coordinator.commands[-1];role=command['role']
                    for target in (('q_norm','raw_gate') if role=='q_norm' else (role,)):
                        region=memory.regions[active_outputs[target]];raw=region.raw()
                        require(command['terminal_status'] is not None or region.published,'successful stage was not published')
                        item=snapshot_bytes(output,name+'.'+target+'.actual.bf16le',raw)
                        item.update(terminal_status=command['terminal_status'],published=region.published)
                        report['actual_outputs'][name+'.'+target]=item
                    recorded=len(coordinator.commands)
                    persist(output/'progress.json',dict(window=name,elapsed_seconds=time.monotonic()-start,actual_outputs=report['actual_outputs'],coordinator=coordinator.report()))
            receipt=coordinator.report();receipt.update(name=name,elapsed_seconds=time.monotonic()-window_start)
            report['windows'].append(receipt);persist(output/(name+'.terminal.json'),receipt)
            require(coordinator.response.status is None,'owner failed: '+str(coordinator.response))
            require(initial==(matrix.resource_address,vector.resource_address,id(memory),id(scalar),id(dense),id(dense.a_banks),id(rms),id(norm),id(rope),matrix.epoch),'shared resource changed')
            report['observations'][name]=freeze_observations(output,name,observed)
            all_observations[name]=observed
            all_actual[name]={role:memory.regions[base].raw() for role,base in active_outputs.items()}
            all_terminals[name]=coordinator
        report.update(status='ACTUAL_COMPLETE_UNCOMPARED',terminal_count=sum(len(w['commands']) for w in report['windows']),elapsed_seconds=time.monotonic()-start)
        persist(output/'actual_terminal.json',report)
        from ..qwen35_gdn_prefill.prefill_bf16_compare import compare_finite_bf16
        thresholds=json.loads((ROOT/prior.fixture.capture.CONTRACT).read_text())['thresholds']['operator']
        report['prefix_gates']={};report['norm_rope_comparisons']={}
        for selection in identity['selections']:
            name=selection['name']
            for role,key in selection['references'].items():
                metrics=compare_finite_bf16(all_actual[name][role],prior.fixture.read_tensor(capture_directory,manifest,key))
                metrics.update(thresholds=thresholds,passed=metrics['max_abs']<=thresholds['max_abs'] and metrics['mean_abs']<=thresholds['mean_abs'])
                report['prefix_gates'][name+'.'+role]=metrics
            # The comparison module checks the complete genuine owner-terminal
            # evidence before its numerical comparison reads native references.
            chain=all_terminals[name]
            terminal_evidence={c['role']:c['owner_report'] for c in chain.commands[4:]}
            actual_tail=all_actual[name]
            report['norm_rope_comparisons'][name]=compare_case(name,all_observations[name],actual_tail,manifest,capture_directory,terminal_evidence=terminal_evidence)
        report['seals']=dict(source=sources=={p:sha((ROOT/p).read_bytes()) for p in sources},
            source_snapshot=all(sha((output/'source_snapshot'/p).read_bytes())==h for p,h in sources.items()),
            libraries=all(sha(Path(p).read_bytes())==h for p,h in identity['libraries'].items()),
            manifest=sha((Path(capture_directory)/'manifest.json').read_bytes())==identity['capture_manifest_sha256'],
            snapshots=all(sha((output/v['file']).read_bytes())==v['sha256'] for v in snapshots.values()),
            actual_outputs=all(sha((output/v['file']).read_bytes())==v['sha256'] for v in report['actual_outputs'].values()),
            observations=all(sha((output/v['file']).read_bytes())==v['sha256'] for entries in report['observations'].values() for v in entries.values()))
        passed=all(report['seals'].values()) and all(x['passed'] for x in report['prefix_gates'].values()) and all(x['complete'] and x['all_computed_stages_pass'] and x['computed_required_producers']==22 for x in report['norm_rope_comparisons'].values())
        report.update(status='PASS_ACTUAL_TYPED_NORM_ROPE_PREFIX_ONLY' if passed else 'FAILED_NATIVE_OR_IDENTITY_GATE',elapsed_seconds=time.monotonic()-start)
        persist(output/'summary.json',report);return report
    except BaseException as error:
        report.update(status='FAILED',elapsed_seconds=time.monotonic()-start,error=dict(type=type(error).__name__,message=str(error)))
        report['evidence_preservation_errors']=[]
        try:report['active_at_failure']=state(coordinator)
        except Exception as extra:report['evidence_preservation_errors'].append(str(extra))
        if coordinator is not None:
            try:
                persist(output/'failure_coordinator.json',coordinator.report())
                if coordinator.active is not None:
                    persist(output/'failure_active_driver.json',coordinator.active.report())
            except Exception as extra:report['evidence_preservation_errors'].append(str(extra))
        if observed is not None:
            try:
                report['failure_observations']=freeze_observations(output,active_name,observed,prefix='failure_observations')
                report['failure_observations_complete']=False
            except Exception as extra:report['evidence_preservation_errors'].append(str(extra))
        for role,base in active_outputs.items():
            try:
                region=memory.regions[base];item=snapshot_bytes(output,'failure_staging/'+role+'.partial.bf16le',region.raw())
                item.update(published=region.published,written_beats=len(region.written),acknowledged_beats=len(region.acknowledged))
                report.setdefault('failure_staging',{})[role]=item
            except Exception as extra:report['evidence_preservation_errors'].append(str(extra))
        persist(output/'summary.json',report);raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('capture','payload','out'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--budget-seconds',type=int,default=600);args=parser.parse_args()
    report=run(args.capture,args.payload,args.out,budget_seconds=args.budget_seconds)
    print(json.dumps({k:report[k] for k in ('status','elapsed_seconds','terminal_count')}))
    raise SystemExit(0 if report['status'].startswith('PASS_') else 1)

if __name__=='__main__':main()
