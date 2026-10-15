"""Complete independent Q/K candidate; bounded local arithmetic only."""
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
from candidates.qwen2_qk_aten_reduction_candidate import model,official,source_closure
from candidates.qwen2_aten_q_projection_candidate import probe as oldprobe,prefix_probe
from candidates.qwen2_qk_probability_diagnostic import model as qkm
ROOT=model.ROOT;HERE=model.HERE
OUT=ROOT/'work/qwen2_qk_aten_reduction_candidate/local02'
SELECTED_PROBABILITY_ROWS=((0,0),(0,63),*( (h,127) for h in range(12)),(7,91),(9,102))

def run(execute=False):
    if not execute:
        source_closure.snapshot()
        return {'status':'NOT_EXECUTED'}
    start=time.monotonic();cpu=time.process_time()
    resource.setrlimit(resource.RLIMIT_CPU,(120,120));resource.setrlimit(resource.RLIMIT_AS,(4<<30,4<<30))
    resource.setrlimit(resource.RLIMIT_FSIZE,(63<<20,63<<20))
    model.need(not OUT.exists() and 'torch' not in sys.modules,'fresh output/process')
    model.need(os.getenv('ATEN_CPU_CAPABILITY')=='avx2','preimport AVX2')
    model.need(os.getenv('PYTHONPATH')==str(ROOT/'work/runtime_recovery/site-packages'),'fixed runtime path')
    sources={str(p.relative_to(ROOT)):model.sha(p) for p in HERE.iterdir() if p.is_file()}
    tracked_sources=source_closure.snapshot()
    compiler=Path('/usr/bin/g++').resolve();compiler_sha=model.sha(compiler)
    from candidates.qwen2_runtime_relocation import runtime
    pins=runtime._expected('full29');native=runtime.check_native(pins,family='full29')
    framework_sources=source_closure.runtime_python_snapshot(pins)
    input_pins={**oldprobe.INPUTS,**prefix_probe.EXTRA}
    raw={n:(oldprobe.DATA/(n+'.bin')).read_bytes() for n in input_pins}
    model.need(all(hashlib.sha256(b).hexdigest()==input_pins[n] for n,b in raw.items()),'fixed raw identity')
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
    biases={n:np.frombuffer(raw['b'+n],'<f4').copy() for n in ('q','k')}
    rope=np.frombuffer(raw['rope'],'<f4').reshape(2,1024,64).copy()
    OUT.mkdir(parents=True);argv=model.compile_library(OUT/'candidate.so',True);candidate=model.Candidate(OUT/'candidate.so')
    own={};own['n0']=candidate.rms(x,gamma)
    # Measured real pilot, no oracle input. Covers all K and actual suffix jobs.
    pstart=time.process_time();pilot_raw,pstats=candidate.raw(own['n0'][:1].copy(),weights['k'])
    pilot_proj=time.process_time()-pstart
    pstart=time.process_time();pilot_b,pilot_k,pilot_records=model.original_bias_rope(pilot_raw,biases['k'],rope)
    pilot_suffix=time.process_time()-pstart
    estimate=(pilot_proj+pilot_suffix)*128*7
    model.need(estimate<85,'pilot projected candidate cost above budget')
    # Small source-extension check: complete Q first row versus earlier exact
    # eight-column candidate using only candidate-produced n0/raw operands.
    first_q,first_stats=candidate.raw(own['n0'][:1].copy(),weights['q'])
    cols=oldprobe.COLS
    baseline_raw,_=candidate.project(own['n0'][:1].copy(),weights['q'],biases['q'],cols)
    model.need(first_q[:,cols].tobytes()==baseline_raw.tobytes(),'full-width extension differs from earlier graph')
    stats={};owners={};candidate_start=time.process_time()
    for n in ('q','k'):
        own[n+'raw'],stats[n]=candidate.raw(own['n0'],weights[n])
        own[n+'r'],own[n],owners[n]=model.original_bias_rope(own[n+'raw'],biases[n],rope)
    candidate_cpu=time.process_time()-candidate_start
    # References are executed only after every candidate Q/K suffix result.
    ref,ns,execute=official.prefix(raw,pins,torch,np)
    model.need(all(np.isfinite(a).all() for a in own.values()),'candidate finite')
    def metrics(a,b,mask=None):
        if mask is not None:a,b=a[mask],b[mask]
        a=np.ascontiguousarray(a,dtype='<f4');b=np.ascontiguousarray(b,dtype='<f4')
        d=np.abs(a.astype(np.float64)-b.astype(np.float64))
        return dict(max_abs=float(d.max()),mean_abs=float(d.mean()),count=int(d.size),
          different=int(np.count_nonzero(d)),bit_diff_count=int(np.count_nonzero(a.view('<u4')!=b.view('<u4'))))
    from scripts import qwen2_layer0_model_gate as gate
    policy=gate.load_policy(ROOT);model.need(policy['operator']=={'max_abs':0.03125,'mean_abs':0.005},'unchanged original gate')
    prefix_metrics={n:{'metrics':metrics(own[n],ref[n]),'verdict':gate.stage_verdict(n,metrics(own[n],ref[n]),'bf16',policy)}
       for n in ('n0','qr','kr','q','k')}
    causal=np.broadcast_to(np.tril(np.ones((128,128),dtype=bool)),(12,128,128))
    with torch.inference_mode():
        ns['math']=math;execute([15,16,18,19]);refscore=ns['attn_weights'].float().numpy()[0].copy()
    batch_argv=qkm.compile_batch(OUT/'native_batch.so',execute=True);batch=qkm.NativeBatch(OUT/'native_batch.so')
    qk=batch.run(own['q'],own['k'])
    qfn,sfn=qkm.exact_owner_functions()
    from candidates.qwen2_resident_matrix.ffn_public.prefix_arithmetic import ScalarService,bf,word,value
    scalar=ScalarService();client=SimpleNamespace(scalar=scalar,counts=Counter(),peak_probability_words=0)
    model.need(scalar.acquire(client),'exclusive scalar');client._op=lambda op,a,b=0,policy='legacy_scalar':scalar.op(client,op,a,b,policy=policy)
    score_metrics=metrics(qk['scores'],refscore,causal)
    score_delta=np.where(causal,np.abs(qk['scores'].astype(np.float64)-refscore.astype(np.float64)),-1)
    top=[tuple(int(x) for x in np.unravel_index(int(i),score_delta.shape)) for i in np.argsort(score_delta.ravel(),kind='stable')[-16:]]
    for h,t,k in top:
        observed=qfn(client,tuple(int(u) for u in qk['parts'][h,t,k].view('<u4')))
        expected=tuple(int(qk[n][h,t,k].view('<u4')) for n in ('sums','dots','scores'))
        model.need(observed==expected,'batch vs original owner AST words')
    mask_raw=b''.join((0xff7f if k>t else 0).to_bytes(2,'little') for t in range(128) for k in range(128))
    model.need(hashlib.sha256(mask_raw).hexdigest()==pins['mask_contract']['native_sha256'],'exact original finite mask')
    ns['attention_mask']=torch.from_numpy(np.frombuffer(mask_raw,'<u2').copy()).view(torch.bfloat16).reshape(1,1,128,128)
    def official_soft(scores):
        s=scores.copy();s[~causal]=0.0
        with torch.inference_mode():
            ns['attn_weights']=torch.from_numpy(s).to(torch.bfloat16).unsqueeze(0);execute([20,21])
            return ns['attn_weights'].float().numpy()[0].copy()
    refprob=official_soft(refscore);same_score_official=official_soft(qk['scores'])
    propagation=metrics(same_score_official,refprob,causal)
    # Preserve prior actual worst row and every source row with any mismatch;
    # add last row of each head. Coverage stays bounded and explicit.
    rows=set(SELECTED_PROBABILITY_ROWS)
    rows.update((int(h),int(t)) for h,t,k in np.argwhere(causal&(qk['scores']!=refscore)))
    rows.update((h,127) for h in range(12));rows=sorted(rows)
    model.need(len(rows)<=64,'bounded selected softmax rows')
    actual=[];expected=[];same=[];row_details=[]
    for h,t in rows:
        words=tuple(int(v) for v in qk['scores'][h,t,:t+1].view('<u4'))
        result,exps,total,inverse=sfn(client,words,word(float(qk['scores'][h,t,:t+1].max())))
        a=np.asarray([bf(v) for v in result],dtype='<u4').view('<f4')
        actual.extend(a);expected.extend(refprob[h,t,:t+1]);same.extend(same_score_official[h,t,:t+1])
        row_details.append({'position':[h,t],'metrics':metrics(a,refprob[h,t,:t+1]),'scalar_total':float(value(total))})
    scalar.release(client)
    actual,expected,same=(np.array(a,dtype='<f4') for a in (actual,expected,same))
    prob_metrics=metrics(actual,expected);same_metrics=metrics(actual,same)
    results={'scores':{'metrics':score_metrics,'verdict':gate.stage_verdict('scores',score_metrics,'bf16',policy)},
      'prob_bounded':{'metrics':prob_metrics,'verdict':gate.stage_verdict('prob',prob_metrics,'bf16',policy)},
      'same_scores_scalar_vs_official_bounded':same_metrics,'candidate_scores_official_softmax_all_causal':propagation}
    model.need(state()==prefix_probe.EXPECTED and runtime.check_native(pins,family='full29')==native,'runtime/native drift')
    model.need(all(model.sha(ROOT/p)==h for p,h in sources.items()),'new source drift')
    model.need(source_closure.snapshot()==tracked_sources,'tracked dependency drift')
    model.need(source_closure.runtime_python_snapshot(pins)==framework_sources,'framework source drift')
    model.need(model.sha(compiler)==compiler_sha,'compiler drift')
    model.need(all(model.sha(oldprobe.DATA/(n+'.bin'))==h for n,h in input_pins.items()),'raw input drift')
    public={'status':'COMPLETE_QK_CANDIDATE_LOCAL_DIAGNOSTIC','prefix':prefix_metrics,'attention':results,
      'projection_fmas':sum(v['fmas'] for v in stats.values()),'projection_adds':sum(v['adds'] for v in stats.values()),
      'peak_partial_words':4096,'original_qk_native_fmas':qk['fmas'],'selected_probability_rows':len(rows),
      'selected_probability_positions':int(actual.size),'qk_coverage':'ALL_CAUSAL',
      'current_probability_coverage':'BOUNDED_SELECTED_ROWS','candidate_source':'INDEPENDENT_RAW_INPUT_MODEL',
      'bias_rope':'UNCHANGED_OWNER_MEMORY_ACK_EXECUTION','hardware_mapping':'NOT_IMPLEMENTED',
      'rtl':'NOT_EXECUTED','fullblock':'NOT_EXECUTED','ci':'NOT_EXECUTED','gate_policy':'UNCHANGED',
      'platform_identity':'LOCAL_PINNED_PROFILE_NOT_CI_EQUIVALENCE'}
    report={'public':public,'sources':sources,'input_sha256':input_pins,'runtime':state(),'native':native,
      'tracked_source_snapshot':tracked_sources,'framework_source_snapshot':framework_sources,
      'compiler_identity':{'path':str(compiler),'sha256':compiler_sha},'projection_stats':stats,'suffix_owner_receipts':owners,
      'pilot':{'projection_cpu_seconds':pilot_proj,'suffix_cpu_seconds':pilot_suffix,'estimated_cpu_seconds':estimate,
          'stats':pstats,'suffix_owner_receipts':pilot_records,'earlier_extension_columns':cols},
      'candidate_cpu_seconds':candidate_cpu,'schedule':model.SCHEDULE,'compiler_argv':argv,'native_batch_argv':batch_argv,
      'library_sha256':model.sha(OUT/'candidate.so'),'selected_probability_rows':row_details,
      'policy':policy,'host_cpu_seconds':time.process_time()-cpu,'host_wall_seconds':time.monotonic()-start,
      'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
      'limits':{'cpu_seconds':120,'address_space_bytes':4<<30,'total_output_bytes':64<<20,'external_wall_seconds':150},
      'limitations':['Independent projection arithmetic candidate, no production owner integration or Chisel.',
        'Fixed 4096 MAC resource mapping requires separate review; software partial array is not hardware utilization evidence.',
        'Reference tensors never supply candidate operands; only fixed raw inputs and candidate-produced intermediates.',
        'Full Q/K and causal scores covered, current softmax bounded selected rows only.']}
    np.savez_compressed(OUT/'LOCAL_ARRAYS.npz',**own,**{'official_'+n:v for n,v in ref.items()},
       candidate_score=qk['scores'],official_score=refscore,official_probability=refprob,
       candidate_score_official_probability=same_score_official)
    (OUT/'RESULT.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    (OUT/'SAFE_SUMMARY.json').write_text(json.dumps(public,indent=2,sort_keys=True)+'\n')
    model.need(sum(p.stat().st_size for p in OUT.iterdir() if p.is_file())<64<<20,'total output cap')
    print(json.dumps(public,sort_keys=True));return report

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');a=p.parse_args()
    r=run(a.execute)
    if not a.execute:print(json.dumps(r))
