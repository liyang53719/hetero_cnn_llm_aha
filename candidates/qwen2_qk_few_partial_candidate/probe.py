"""Preregistered six-case P2/P4 screen under one 120-second CPU budget."""
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import sys
import time
from collections import Counter
from types import SimpleNamespace
from candidates.qwen2_qk_few_partial_candidate import model
from candidates.qwen2_qk_aten_reduction_candidate import official,source_closure,public_summary
from candidates.qwen2_aten_q_projection_candidate import probe as inputs,prefix_probe
from candidates.qwen2_qk_probability_diagnostic import model as qkm
ROOT=model.ROOT;HERE=model.HERE;OUT=ROOT/'work/qwen2_qk_few_partial_candidate/local01'

class BudgetStop(RuntimeError):pass

def dependencies():
    result=source_closure.snapshot()
    expected=json.loads((HERE/'DEPENDENCIES.json').read_text())['tracked_sources']
    import subprocess
    tracked=set(subprocess.run(['git','ls-files','--',*expected],cwd=ROOT,check=True,capture_output=True,text=True).stdout.splitlines())
    model.need(tracked==set(expected),'reviewed shared candidate dependencies must be published')
    for name,h in expected.items():
        model.need(model.sha(ROOT/name)==h,'reviewed dependency changed')
        result[name]=h
    return result

def run(execute=False):
    if not execute:
        dependencies();return {'status':'NOT_EXECUTED'}
    start=time.monotonic();start_cpu=time.process_time();cfg=model.CONFIG
    limits=cfg['limits'];resource.setrlimit(resource.RLIMIT_CPU,(120,120))
    resource.setrlimit(resource.RLIMIT_AS,(4<<30,4<<30));resource.setrlimit(resource.RLIMIT_FSIZE,(63<<20,63<<20))
    model.need(not OUT.exists() and 'torch' not in sys.modules,'fresh run required')
    model.need(os.getenv('ATEN_CPU_CAPABILITY')=='avx2','preimport AVX2')
    model.need(os.getenv('PYTHONPATH')==str(ROOT/'work/runtime_recovery/site-packages'),'fixed runtime path')
    sources={str(p.relative_to(ROOT)):model.sha(p) for p in HERE.iterdir() if p.is_file()}
    tracked_sources=dependencies();compiler=Path('/usr/bin/g++').resolve();compiler_sha=model.sha(compiler)
    from candidates.qwen2_runtime_relocation import runtime
    pins=runtime._expected('full29');native=runtime.check_native(pins,family='full29')
    framework_sources=source_closure.runtime_python_snapshot(pins)
    input_pins={**inputs.INPUTS,**prefix_probe.EXTRA}
    raw={n:(inputs.DATA/(n+'.bin')).read_bytes() for n in input_pins}
    model.need(all(hashlib.sha256(b).hexdigest()==input_pins[n] for n,b in raw.items()),'fixed raw input identity')
    import numpy as np
    import torch
    torch.set_num_threads(4);torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True);torch.backends.mkldnn.enabled=False
    def state():return dict(torch=torch.__version__,commit=torch.version.git_version,
        capability=torch.backends.cpu.get_cpu_capability(),threads=torch.get_num_threads(),
        interop_threads=torch.get_num_interop_threads(),mkldnn_enabled=torch.backends.mkldnn.enabled,
        deterministic=torch.are_deterministic_algorithms_enabled())
    model.need(state()==prefix_probe.EXPECTED,'runtime profile')
    model.need(Path(torch._C.__file__).resolve()==Path(native['torch_C']['path']),'torch import')
    model.need(Path(np._core._multiarray_umath.__file__).resolve()==Path(native['numpy_multiarray']['path']),'numpy import')
    x=np.frombuffer(raw['x'],'<f4').reshape(128,1536).copy();gamma=np.frombuffer(raw['gamma0'],'<f4').copy()
    weights={n:np.frombuffer(raw['w'+n],'<u2').reshape(1536,w).copy() for n,w in [('q',1536),('k',256)]}
    biases={n:np.frombuffer(raw['b'+n],'<f4').copy() for n in ('q','k')};rope=np.frombuffer(raw['rope'],'<f4').reshape(2,1024,64).copy()
    OUT.mkdir(parents=True)
    # Preregistration/source identity is persisted before compilation or pilot.
    (OUT/'PREREGISTRATION.json').write_text(json.dumps({'config':cfg,'sources':sources,'tracked_sources':tracked_sources},indent=2,sort_keys=True)+'\n')
    argv=model.compile_library(OUT/'candidate.so',True);candidate=model.Candidate(OUT/'candidate.so')
    batch_argv=qkm.compile_batch(OUT/'native_batch.so',execute=True);batch=qkm.NativeBatch(OUT/'native_batch.so')
    boundaries=model.boundary_tests(candidate)
    qfn,sfn=qkm.exact_owner_functions()
    from candidates.qwen2_resident_matrix.ffn_public.prefix_arithmetic import ScalarService,bf,word
    scalar=ScalarService();client=SimpleNamespace(scalar=scalar,counts=Counter(),peak_probability_words=0)
    model.need(scalar.acquire(client),'scalar acquisition')
    client._op=lambda op,a,b=0,policy='legacy_scalar':scalar.op(client,op,a,b,policy=policy)
    def cpu_used():
        child=resource.getrusage(resource.RUSAGE_CHILDREN)
        return time.process_time()-start_cpu+child.ru_utime+child.ru_stime
    def budget():
        if cpu_used()>110:raise BudgetStop('TOTAL_CPU_SOFT_STOP')
    def metric(a,b,mask=None):
        if mask is not None:a,b=a[mask],b[mask]
        a=np.ascontiguousarray(a,dtype='<f4');b=np.ascontiguousarray(b,dtype='<f4')
        diff=np.abs(a.astype(np.float64)-b.astype(np.float64))
        m={'max_abs':float(diff.max()),'mean_abs':float(diff.mean()),'count':int(diff.size),
           'different':int(np.count_nonzero(diff)), 'bit_diff_count':int(np.count_nonzero(a.view('<u4')!=b.view('<u4')))}
        return public_summary.aggregate_metrics(m)
    from scripts import qwen2_layer0_model_gate as gate
    policy=gate.load_policy(ROOT);model.need(policy['operator']=={'max_abs':0.03125,'mean_abs':0.005},'original numerical policy')
    def stage(a,b,name,mask=None):
        m=metric(a,b,mask);v=gate.stage_verdict(name,m,'bf16',policy)
        return {'metrics':m,'verdict':'PASS' if v['passed'] else 'FAIL'}
    # Real P2/P4 full-depth 16-row pilot, unchanged actual suffix for each.
    n0pilot=candidate.rms(x[:16].copy(),gamma);pilot_times={};pilot_own={}
    for P in cfg['partials']:
        pstart=time.process_time();own={}
        for n in ('q','k'):
            r,_=candidate.raw(n0pilot,weights[n],P)
            _,own[n],_=model.original_bias_rope(r,biases[n],rope)
        pilot_times[str(P)]=time.process_time()-pstart;pilot_own=own
    qp=np.zeros((128,1536),'<f4');kp=np.zeros((128,256),'<f4');qp[:16]=pilot_own['q'];kp[:16]=pilot_own['k']
    pstart=time.process_time();pilot_qk=batch.run(qp,kp,rows=16);qk_seconds=time.process_time()-pstart
    pstart=time.process_time()
    for _ in range(16):sfn(client,(0,)*128,0)
    scalar_seconds=time.process_time()-pstart
    # Uniform scores exercise the full exp polynomial, a conservative bound.
    projected=(sum(pilot_times.values())*8*3+qk_seconds*(99072/(12*16*17/2))*6+
               scalar_seconds*(594432/(16*128))+8.0+cpu_used())
    pilot={'projection_suffix_seconds':pilot_times,'qk_seconds':qk_seconds,'scalar_2048_positions_seconds':scalar_seconds,
           'predicted_total_cpu_seconds':projected,'admission_limit_seconds':95,'actual_cpu_so_far':cpu_used(),
           'status':'ADMITTED' if projected<=95 else 'BUDGET_REJECTED'}
    (OUT/'PILOT.json').write_text(json.dumps(pilot,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'status':'PILOT_COMPLETE','prediction_seconds':projected,'admission':pilot['status']}),flush=True)
    del pilot_qk,pilot_own,qp,kp
    case_results=[{'case':c['id'],'partials':P,'status':'NOT_EXECUTED'} for c in cfg['cases'] for P in cfg['partials']]
    details={};causal=np.broadcast_to(np.tril(np.ones((128,128),dtype=bool)),(12,128,128))
    maskraw=b''.join((0xff7f if k>t else 0).to_bytes(2,'little') for t in range(128) for k in range(128))
    model.need(hashlib.sha256(maskraw).hexdigest()==pins['mask_contract']['native_sha256'],'original finite mask')
    def checkpoint():
        (OUT/'PROGRESS.json').write_text(json.dumps({'cases':case_results,'cpu_seconds':cpu_used()},indent=2,sort_keys=True)+'\n')
    checkpoint();stop=None
    if pilot['status']=='ADMITTED':
      try:
        for case in cfg['cases']:
            budget();case_x=model.transform(x,case);n0=candidate.rms(case_x,gamma);candidates={};case_details={}
            # Both candidates finish their prefix before this case's oracle.
            for P in cfg['partials']:
                budget();own={'n0':n0};receipts={};stats={}
                for n in ('q','k'):
                    own[n+'raw'],stats[n]=candidate.raw(n0,weights[n],P)
                    own[n+'r'],own[n],receipts[n]=model.original_bias_rope(own[n+'raw'],biases[n],rope)
                candidates[P]=own;case_details[P]={'suffix_receipts':receipts,'projection_stats':stats}
            case_raw={**raw,'x':case_x.tobytes()};ref,ns,execute=official.prefix(case_raw,pins,torch,np)
            ns['math']=math
            with torch.inference_mode():
                execute([15,16,18,19]);refscore=ns['attn_weights'].float().numpy()[0].copy()
                ns['attention_mask']=torch.from_numpy(np.frombuffer(maskraw,'<u2').copy()).view(torch.bfloat16).reshape(1,1,128,128)
                execute([20,21]);refprob=ns['attn_weights'].float().numpy()[0].copy()
            for P in cfg['partials']:
                budget();own=candidates[P];index=next(i for i,r in enumerate(case_results) if r['case']==case['id'] and r['partials']==P)
                r=case_results[index];r['prefix']={n:stage(own[n],ref[n],n) for n in ('n0','qr','kr','q','k')}
                qk=batch.run(own['q'],own['k']);r['scores']=stage(qk['scores'],refscore,'scores',causal)
                for h,t,k in ((0,0,0),(7,91,91),(9,102,100),(11,127,127)):
                    got=qfn(client,tuple(int(v) for v in qk['parts'][h,t,k].view('<u4')))
                    expected=tuple(int(qk[n][h,t,k].view('<u4')) for n in ('sums','dots','scores'))
                    model.need(got==expected,'batch current owner AST exact word check')
                r['status']='PROBABILITY_RUNNING';r['probability_positions']=0;checkpoint()
                actual=np.full((12,128,128),np.nan,dtype='<f4')
                for h in range(12):
                    for t in range(128):
                        budget();row=qk['scores'][h,t,:t+1];words=tuple(int(v) for v in row.view('<u4'))
                        result,exps,total,inverse=sfn(client,words,word(float(row.max())))
                        actual[h,t,:t+1]=np.asarray([bf(v) for v in result],dtype='<u4').view('<f4')
                        r['probability_positions']+=t+1
                    checkpoint()
                model.need(r['probability_positions']==99072,'complete causal probability coverage')
                r['probability']=stage(actual,refprob,'prob',causal)
                r['projection_fmas']=sum(s['fmas'] for s in case_details[P]['projection_stats'].values())
                r['projection_adds']=sum(s['adds'] for s in case_details[P]['projection_stats'].values())
                r['qk_native_fmas']=qk['fmas']
                failed=[n for n,item in r['prefix'].items() if item['verdict']=='FAIL']
                failed.extend(n for n in ('scores','probability') if r[n]['verdict']=='FAIL')
                r['status']='COMPLETE_NUMERIC_FAIL' if failed else 'COMPLETE_NUMERIC_PASS';r['failed_stages']=failed
                np.savez_compressed(OUT/(case['id']+'_P'+str(P)+'.npz'),q=own['q'],k=own['k'],scores=qk['scores'],probability=actual)
                details[case['id']+'_P'+str(P)]={**case_details[P],
                   'input_sha256':hashlib.sha256(case_x.tobytes()).hexdigest()}
                checkpoint();print(json.dumps({'status':'CASE_COMPLETE','case':case['id'],'partials':P,'result':r['status'],
                   'score_max':r['scores']['metrics']['max_abs'],'prob_max':r['probability']['metrics']['max_abs']}),flush=True)
                del qk,actual
      except BudgetStop as error:
        stop=str(error)
        for r in case_results:
            if r['status']=='PROBABILITY_RUNNING':r['status']='INCOMPLETE_PROBABILITY_BUDGET'
            elif r['status']=='NOT_EXECUTED':r['status']='NOT_EXECUTED_BUDGET'
        checkpoint()
    else:
        stop='PILOT_BUDGET_REJECTED'
        for r in case_results:r['status']='NOT_EXECUTED_PILOT_BUDGET'
    scalar.release(client)
    model.need(state()==prefix_probe.EXPECTED and runtime.check_native(pins,family='full29')==native,'runtime/native drift')
    model.need(dependencies()==tracked_sources,'tracked dependency drift')
    model.need(source_closure.runtime_python_snapshot(pins)==framework_sources,'framework source drift')
    model.need(all(model.sha(ROOT/p)==h for p,h in sources.items()),'candidate source drift')
    model.need(model.sha(compiler)==compiler_sha,'compiler drift')
    model.need(all(model.sha(inputs.DATA/(n+'.bin'))==h for n,h in input_pins.items()),'raw input drift')
    completed=sum(r['status'].startswith('COMPLETE_NUMERIC_') for r in case_results)
    public={'status':'SIX_CASE_SCREEN_COMPLETE' if completed==6 else 'BOUNDED_SCREEN_INCOMPLETE','cases':case_results,
      'completed_cases':completed,'registered_cases':6,'boundaries':boundaries,'pilot':pilot,
      'gate_policy':'UNCHANGED','selection':'NO_POSTHOC_GRAPH_OR_SEED_SELECTION','rtl':'NOT_EXECUTED',
      'fullblock':'NOT_EXECUTED','ci':'NOT_EXECUTED','hardware_mapping':'CONDITIONAL_NOT_IMPLEMENTED'}
    report={'public':public,'config':cfg,'sources':sources,'tracked_sources':tracked_sources,'native':native,
      'framework_sources':framework_sources,'compiler':{'path':str(compiler),'sha256':compiler_sha},
      'input_pins':input_pins,'details':details,'stop':stop,'runtime':state(),'policy':policy,
      'compiler_argv':argv,'native_batch_argv':batch_argv,'host_cpu_seconds':cpu_used(),
      'host_wall_seconds':time.monotonic()-start,'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
      'limits':limits,'full_owner_protocol':'ONLY_UNCHANGED_BIAS_ROPE_JOBS','probability_execution':'ORIGINAL_SCALAR_OWNER_STATEMENTS'}
    (OUT/'RESULT.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    (OUT/'AGGREGATE.json').write_text(json.dumps(public,indent=2,sort_keys=True)+'\n')
    model.need(sum(p.stat().st_size for p in OUT.iterdir() if p.is_file())<64<<20,'total output bound')
    print(json.dumps({'status':public['status'],'completed_cases':completed,'cpu_seconds':report['host_cpu_seconds']}),flush=True)
    return report

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');a=p.parse_args()
    result=run(a.execute)
    if not a.execute:print(json.dumps(result))
