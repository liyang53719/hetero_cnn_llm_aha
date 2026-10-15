"""Explicit bounded local real-input QK/probability arithmetic diagnostic.

No CI, network, full-block execution, acceptance promotion, or gate change.
Detailed private data is written only below the fixed ignored work directory.
"""
import ast
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import sys
import time
from types import SimpleNamespace
from candidates.qwen2_aten_q_projection_candidate import probe as base
from candidates.qwen2_aten_q_projection_candidate import prefix_probe as prefix
from candidates.qwen2_qk_probability_diagnostic import model

ROOT=base.ROOT
HERE=Path(__file__).resolve().parent
OUT=ROOT/'work/qwen2_qk_probability_diagnostic/local01'

def cold():
    qk,soft,normalize=model.owner_nodes()
    return dict(status='NOT_EXECUTED',qk_statement_count=len(qk),
        softmax_statement_count=len(soft),normalization_statement_count=1)

def run(*,execute=False):
    if not execute:return cold()
    start=time.monotonic();cpu_start=time.process_time()
    resource.setrlimit(resource.RLIMIT_CPU,(120,120))
    resource.setrlimit(resource.RLIMIT_AS,(4<<30,4<<30))
    resource.setrlimit(resource.RLIMIT_FSIZE,(63<<20,63<<20))
    model.need(not OUT.exists() and 'torch' not in sys.modules,'fresh process/output')
    model.need(os.environ.get('ATEN_CPU_CAPABILITY')=='avx2','ATen AVX2 before import')
    model.need(os.environ.get('PYTHONPATH')==str(ROOT/'work/runtime_recovery/site-packages'),'fixed runtime')
    from candidates.qwen2_runtime_relocation import runtime
    pins=runtime._expected('full29');native=runtime.check_native(pins,family='full29')
    sources={str(p.relative_to(ROOT)):model.sha(p) for p in HERE.iterdir() if p.is_file() and p.suffix in ('.py','.cpp')}
    inputs={**base.INPUTS,**prefix.EXTRA}
    raw={n:(base.DATA/(n+'.bin')).read_bytes() for n in inputs}
    model.need(all(hashlib.sha256(b).hexdigest()==inputs[n] for n,b in raw.items()),'raw input identity')
    old=json.loads((base.OLD/'RESULT.json').read_text());old_sha=model.sha(base.OLD/'RESULT.json')
    model.need(all(old['input_identity_before'][n]['sha256']==h for n,h in inputs.items()),'historical same raw inputs')
    old_payload={n:(base.OLD/(n+'.f32le')).read_bytes() for n in ('n0','q','k')}
    records={n:prefix.completed_record(old['producers'],n,b) for n,b in old_payload.items()}
    current_old_sources={p:model.sha(ROOT/p) for p in old['source_sha256_before']}
    drift={p for p,h in current_old_sources.items() if h!=old['source_sha256_before'][p]}
    model.need(drift==prefix.KNOWN_DRIFT,'unexpected old source drift')
    native_receipt_path=base.OLD/'native_artifact_reuse.json'
    receipt=json.loads(native_receipt_path.read_text())
    model.need(receipt['fresh_compile_receipt']['library_sha256']==model.NATIVE_SHA,'native historical binding')
    model.need(model.sha(model.NATIVE)==model.NATIVE_SHA,'current native library identity')
    for p,h in receipt['fresh_compile_receipt']['source_sha256'].items():
        model.need(model.sha(ROOT/p)==h,'native arithmetic source changed')
    import torch
    import numpy as np
    torch.set_num_threads(4);torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True);torch.backends.mkldnn.enabled=False
    def state():return dict(torch=torch.__version__,commit=torch.version.git_version,
        capability=torch.backends.cpu.get_cpu_capability(),threads=torch.get_num_threads(),
        interop_threads=torch.get_num_interop_threads(),mkldnn_enabled=torch.backends.mkldnn.enabled,
        deterministic=torch.are_deterministic_algorithms_enabled())
    model.need(state()==prefix.EXPECTED,'runtime profile')
    model.need(Path(torch._C.__file__).resolve()==Path(native['torch_C']['path']),'torch native import')
    model.need(Path(np._core._multiarray_umath.__file__).resolve()==Path(native['numpy_multiarray']['path']),'numpy native import')
    src='config/upstream/weight_headers/qwen2_1p5b/modeling_qwen2.py'
    model.need(model.sha(ROOT/src)==pins['sources'][src]['sha256'],'official source identity')
    ns={'torch':torch,'nn':torch.nn,'math':math};nodes=pins['model_ast_nodes']
    def execute_nodes(indices):
        for i in indices:
            node=nodes[i];text=node['source']
            model.need(hashlib.sha256(text.encode()).hexdigest()==node['source_sha256'],'official AST identity')
            exec(compile(ast.parse(text),src,'exec'),ns)
    def expanded(name,shape):return torch.from_numpy(np.frombuffer(raw[name],'<f4').copy()).reshape(shape).to(torch.bfloat16)
    def array(t):return t.detach().float().cpu().numpy().copy()
    execute_nodes(range(4))
    norm=ns['Qwen2RMSNorm'](1536,eps=1e-6).to(torch.bfloat16).eval()
    norm.weight=torch.nn.Parameter(expanded('gamma0',(1536,)),requires_grad=False)
    attention=torch.nn.Module();attention.hidden_size=1536;attention.num_heads=12
    attention.num_key_value_heads=2;attention.num_key_value_groups=6;attention.head_dim=128
    ns['self']=attention;execute_nodes(range(4,7))
    for letter,width in (('q',1536),('k',256),('v',256)):
        weight=np.frombuffer(raw['w'+letter],'<u2').reshape(1536,width).T.copy()
        layer=getattr(attention,letter+'_proj')
        layer.weight=torch.nn.Parameter(torch.from_numpy(weight).view(torch.bfloat16),requires_grad=False)
        layer.bias=torch.nn.Parameter(expanded('b'+letter,(width,)),requires_grad=False)
    attention.rotary_emb=ns['Qwen2RotaryEmbedding'](128,max_position_embeddings=256,base=1e6).to(torch.bfloat16)
    attention.to(torch.bfloat16).eval()
    with torch.inference_mode():
        n0=norm(expanded('x',(1,128,1536)))
        model.need(array(n0).tobytes()==old_payload['n0'],'same upstream n0')
        ns.update(hidden_states=n0,self=attention,bsz=1,q_len=128,kv_seq_len=128,
            position_ids=torch.arange(128,dtype=torch.long).unsqueeze(0))
        execute_nodes(range(7,15))
        official_q=array(ns['query_states'].transpose(1,2).contiguous()).reshape(128,1536)
        official_k=array(ns['key_states'].transpose(1,2).contiguous()).reshape(128,256)
        rope=np.frombuffer(raw['rope'],'<f4').reshape(2,1024,64)[:,:128,:].copy()
        u=rope.view('<u4');rounded=((u+0x7fff+((u>>16)&1))&0xffff0000).view('<f4')
        model.need(all(array(ns[n]).tobytes()==np.concatenate((rounded[i],rounded[i]),axis=-1).tobytes()
                       for i,n in enumerate(('cos','sin'))),'rope same input binding')
        execute_nodes([15])
    historical_q=np.frombuffer(old_payload['q'],'<f4').reshape(128,1536).copy()
    historical_k=np.frombuffer(old_payload['k'],'<f4').reshape(128,256).copy()
    causal=np.broadcast_to(np.tril(np.ones((128,128),dtype=bool)),(12,128,128))
    model.need(int(causal.sum())==99072,'causal count')
    def official_qk(q,k):
        # Original torch.matmul BF16 expression and original scalar division.
        with torch.inference_mode():
            qt=torch.from_numpy(q).reshape(1,128,12,128).transpose(1,2).to(torch.bfloat16)
            kt=torch.from_numpy(k).reshape(1,128,2,128).transpose(1,2).to(torch.bfloat16)
            ns.update(query_states=qt,key_states=kt)
            execute_nodes([16])
            dot=torch.matmul(qt,ns['key_states'].transpose(2,3))
            execute_nodes([18,19])
            score=ns['attn_weights']
            model.need(dot.dtype==score.dtype==torch.bfloat16,'official matmul/scale BF16 landing')
            model.need(torch.equal(score,dot/math.sqrt(128)),'original AST staged score')
            return array(dot)[0],array(score)[0]
    dot_a,score_a=official_qk(official_q,official_k)
    dot_c,score_c=official_qk(historical_q,historical_k)
    OUT.mkdir(parents=True)
    argv=model.compile_batch(OUT/'native_batch.so',execute=True)
    batch=model.NativeBatch(OUT/'native_batch.so')
    # Low-cost real-input pilot measures the actual unchanged native ABI.
    pilot_start=time.process_time();pilot=batch.run(official_q,official_k,rows=4)
    pilot_cpu=time.process_time()-pilot_start
    estimate=pilot_cpu*(128*129)/(4*5)*2
    model.need(estimate<75,'native pilot estimate exceeds bounded execution budget')
    qfn,sfn=model.exact_owner_functions()
    from candidates.qwen2_resident_matrix.ffn_public.prefix_arithmetic import ScalarService,bf,word,value
    scalar=ScalarService()
    owner=SimpleNamespace(scalar=scalar,counts=Counter(),peak_probability_words=0)
    model.need(scalar.acquire(owner),'exclusive scalar')
    owner._op=lambda operation,a,b=0,policy='legacy_scalar':scalar.op(owner,operation,a,b,policy=policy)
    def verify_cells(result,coords):
        for h,t,k in coords:
            actual=qfn(owner,tuple(int(u) for u in result['parts'][h,t,k].view('<u4')))
            expected=tuple(int(result[n][h,t,k].view('<u4')) for n in ('sums','dots','scores'))
            model.need(actual==expected,'batch fold versus unmodified owner AST mismatch')
    verify_cells(pilot,[(h,t,k) for h in range(12) for t in range(4) for k in range(t+1)])
    del pilot
    batch_start=time.process_time();b=batch.run(official_q,official_k);d=batch.run(historical_q,historical_k)
    batch_cpu=time.process_time()-batch_start
    def metrics(a,b,mask=causal):
        x=a[mask].astype(np.float64);y=b[mask].astype(np.float64);delta=np.abs(x-y)
        model.need(bool(np.isfinite(delta).all()),'nonfinite comparison')
        return dict(max_abs=float(delta.max()),mean_abs=float(delta.mean()),
                    count=int(delta.size),different=int(np.count_nonzero(delta)))
    def locate(a,b,limit=32):
        delta=np.where(causal,np.abs(a.astype(np.float64)-b.astype(np.float64)),-1)
        ix=np.argsort(delta.ravel(),kind='stable')[-limit:][::-1]
        rows=[]
        for i in ix:
            h,t,k=np.unravel_index(int(i),delta.shape)
            ua=int(a[h,t,k].view('<u4'));ub=int(b[h,t,k].view('<u4'))
            rows.append(dict(position=[int(h),int(t),int(k)],a=float(a[h,t,k]),b=float(b[h,t,k]),
                abs_error=float(delta[h,t,k]),a_bits=ua,b_bits=ub,
                same_sign=bool((ua^ub)&0x80000000==0),bf16_steps=abs((ua>>16)-(ub>>16)),
                a_binade_ulp=float(2.0**(((ua>>23)&255)-127-7))))
        return rows
    comparisons={
      'OFFICIAL_INPUT_OFFICIAL_QK':metrics(score_a,score_a),
      'OFFICIAL_INPUT_CURRENT_QK':metrics(b['scores'],score_a),
      'HISTORICAL_INPUT_OFFICIAL_QK':metrics(score_c,score_a),
      'HISTORICAL_INPUT_CURRENT_QK':metrics(d['scores'],score_a),
      'HISTORICAL_INPUT_ARITHMETIC_ONLY':metrics(d['scores'],score_c),
      'CURRENT_QK_INPUT_PROPAGATION':metrics(d['scores'],b['scores'])}
    dot_comparisons={'OFFICIAL_INPUT_CURRENT_DOT':metrics(b['dots'],dot_a),
                     'HISTORICAL_INPUT_CURRENT_DOT':metrics(d['dots'],dot_c)}
    top=locate(d['scores'],score_a,64)
    same_top=locate(b['scores'],score_a,64)
    validation_coords=sorted({tuple(x['position']) for x in top+same_top}|{(h,127,127) for h in range(12)})
    verify_cells(b,validation_coords);verify_cells(d,validation_coords)
    def rounded(x):return torch.from_numpy(np.array(x,dtype='<f4',copy=True)).to(torch.bfloat16).float().numpy()
    f32scale=np.asarray(0x3db504f3,dtype='<u4').view('<f4')
    boundary={
      'OFFICIAL_DOT_F32_MULTIPLY_BF16':metrics(rounded(np.multiply(dot_a,f32scale,dtype=np.float32)),score_a),
      'OFFICIAL_DOT_F32_DIVIDE_BF16':metrics(rounded(np.divide(dot_a,np.float32(math.sqrt(128)),dtype=np.float32)),score_a),
      'CURRENT_SKIP_DOT_BF16':metrics(rounded(np.multiply(b['sums'],f32scale,dtype=np.float32)),score_a)}
    def official_soft(scores,raw_float=False):
        with torch.inference_mode():
            ts=torch.from_numpy(scores.copy()).to(torch.bfloat16).unsqueeze(0)
            ns['attn_weights']=ts.masked_fill(~torch.from_numpy(causal.copy()).unsqueeze(0),float('-inf'))
            if raw_float:return array(torch.nn.functional.softmax(ns['attn_weights'],dim=-1,dtype=torch.float32))[0]
            execute_nodes([21]);return array(ns['attn_weights'])[0]
    prob_a=official_soft(score_a);prob_b=official_soft(b['scores']);prob_c=official_soft(score_c);prob_d=official_soft(d['scores'])
    propagation={'OFFICIAL_INPUT_CURRENT_QK_OFFICIAL_SOFTMAX':metrics(prob_b,prob_a),
       'HISTORICAL_INPUT_OFFICIAL_QK_OFFICIAL_SOFTMAX':metrics(prob_c,prob_a),
       'HISTORICAL_INPUT_CURRENT_QK_OFFICIAL_SOFTMAX':metrics(prob_d,prob_a)}
    prob_top=locate(prob_d,prob_a,32)
    selected_rows=sorted({tuple(x['position'][:2]) for x in top[:8]+same_top[:8]+prob_top[:16]}
       |{(h,127) for h in range(12)}|{(0,0),(0,63)})
    model.need(len(selected_rows)<=64,'bounded softmax row count')
    soft_details={};soft_aggregate={};soft_values={}
    for label,scores,official_prob in [('OFFICIAL_SCORES',score_a,prob_a),('CURRENT_SCORES',d['scores'],prob_d)]:
        gathered_actual=[];gathered_official=[];gathered_full=[];gathered_base=[];gathered_exp=[];gathered_true_exp=[]
        details=[];official_fp32=official_soft(scores,True)
        for h,t in selected_rows:
            row=scores[h,t,:t+1].copy();words=tuple(int(u) for u in row.view('<u4'))
            maximum=word(float(row.max()))
            result,exps,total,inverse=sfn(owner,words,maximum)
            actual=np.asarray([bf(v) for v in result],dtype='<u4').view('<f4')
            full=np.asarray(result,dtype='<u4').view('<f4')
            exp_array=np.asarray(exps,dtype='<u4').view('<f4')
            gather=lambda dest,x:dest.extend(np.asarray(x).tolist())
            gather(gathered_actual,actual);gather(gathered_official,official_prob[h,t,:t+1])
            gather(gathered_full,full);gather(gathered_base,official_fp32[h,t,:t+1])
            gather(gathered_exp,exp_array);gather(gathered_true_exp,np.exp((row-row.max()).astype(np.float64)))
            details.append(dict(position=[h,t],max_abs=float(np.max(np.abs(actual-official_prob[h,t,:t+1]))),
                 sum_fp32=float(np.sum(full,dtype=np.float64)),scalar_total=float(value(total)),scalar_inverse=float(value(inverse))))
            soft_values[(label,h,t)]=actual
        allmask=np.ones(len(gathered_actual),dtype=bool)
        soft_aggregate[label]=dict(bf16=metrics(np.array(gathered_actual),np.array(gathered_official),allmask),
            fp32=metrics(np.array(gathered_full),np.array(gathered_base),allmask),
            exponential=metrics(np.array(gathered_exp),np.array(gathered_true_exp),allmask),rows=len(selected_rows))
        soft_details[label]=details
    # Observed worst propagated probability row: exact current Scalar softmax,
    # compared to the independent original-AST official baseline on that row.
    worst_prob_row=tuple(prob_top[0]['position'][:2]);h,t=worst_prob_row
    pactual=soft_values[('CURRENT_SCORES',h,t)]
    selected_pipeline=[];selected_baseline=[]
    for h,t in selected_rows:
        selected_pipeline.extend(soft_values[('CURRENT_SCORES',h,t)]);selected_baseline.extend(prob_a[h,t,:t+1])
    bounded_pipeline=metrics(np.array(selected_pipeline),np.array(selected_baseline),np.ones(len(selected_pipeline),dtype=bool))
    scalar.release(owner)
    # Local precision details for top actual causal errors; not public payload.
    for entry in top:
        h,t,k=entry['position'];entry.update(current_unrounded_dot=float(d['sums'][h,t,k]),
            current_bf16_dot=float(d['dots'][h,t,k]),official_bf16_dot=float(dot_a[h,t,k]),
            historical_input_official_dot=float(dot_c[h,t,k]),
            official_input_current_dot=float(b['dots'][h,t,k]))
    maxerr=comparisons['HISTORICAL_INPUT_CURRENT_QK']['max_abs']
    maxmask=causal&(np.abs(d['scores'].astype(np.float64)-score_a.astype(np.float64))==maxerr)
    steps=np.abs((d['scores'].view('<u4')[maxmask]>>16).astype(np.int64)-(score_a.view('<u4')[maxmask]>>16).astype(np.int64))
    max_summary=dict(max_error_count=int(maxmask.sum()),one_bf16_step_count=int((steps==1).sum()),
        other_bf16_step_count=int((steps!=1).sum()))
    from scripts import qwen2_layer0_model_gate as gate
    policy=gate.load_policy(ROOT);model.need(policy['operator']=={'max_abs':0.03125,'mean_abs':0.005},'original policy')
    model.need(state()==prefix.EXPECTED and runtime.check_native(pins,family='full29')==native,'runtime/native drift')
    model.need(all(model.sha(ROOT/p)==h for p,h in sources.items()),'new source drift')
    model.need(all(model.sha(ROOT/p)==h for p,h in current_old_sources.items()),'source drift during run')
    model.need(all(model.sha(base.DATA/(n+'.bin'))==h for n,h in inputs.items()),'raw drift')
    model.need(model.sha(base.OLD/'RESULT.json')==old_sha,'historical receipt drift')
    model.need(all(model.sha(base.OLD/(n+'.f32le'))==r['sha256'] for n,r in records.items()),'historical payload drift')
    public=dict(status='COMPLETED_LOCAL_QK_PROB_DIAGNOSTIC',scope='LOCAL_ARITHMETIC_ONLY',
      identity='LOCAL_PROFILE_MATCH_NO_CI_PLATFORM_EQUIVALENCE',history='HISTORICAL_COMPLETED_PREFIX_NOT_CI_OUTPUT',
      comparisons=comparisons,dot_comparisons=dot_comparisons,boundary=boundary,
      probability_propagation_official_softmax=propagation,selected_current_scalar_same_scores=soft_aggregate,
      selected_current_pipeline=bounded_pipeline,max_score_error=max_summary,
      qk_coverage='ALL_CAUSAL_POSITIONS',probability_current_coverage='BOUNDED_SELECTED_ROWS',
      selected_rows=len(selected_rows),selected_positions=len(selected_pipeline),
      fullblock='NOT_EXECUTED',ci='NOT_EXECUTED',gate_policy='UNCHANGED',
      original_native_fma_calls=b['fmas']+d['fmas'],owner_ast_qk_checks=120+len(validation_coords)*2)
    report=dict(schema=1,public=public,runtime=state(),local_native_identity=native,
      ci_runtime_equivalence_claimed=False,old_dut_fresh_executed=False,sources=sources,
      input_sha256=inputs,old_receipt_sha256=old_sha,old_status=old['status'],old_completed_records=records,
      source_drift=sorted(drift),native_library_sha256=model.NATIVE_SHA,native_source_receipt=receipt,
      compiler_argv=argv,batch_library_sha256=model.sha(OUT/'native_batch.so'),
      official_qk_ast=nodes[18],official_softmax_ast=nodes[21],policy=policy,
      prefix_q_metrics=metrics(historical_q,official_q,np.ones_like(official_q,dtype=bool)),
      prefix_k_metrics=metrics(historical_k,official_k,np.ones_like(official_k,dtype=bool)),
      worst_scores=top,worst_scores_same_input=same_top,worst_probability_propagation=prob_top,
      selected_rows=selected_rows,softmax_rows=soft_details,worst_probability_row=list(worst_prob_row),
      pilot_cpu_seconds=pilot_cpu,pilot_estimated_two_full_native_cpu_seconds=estimate,
      native_batch_cpu_seconds=batch_cpu,host_cpu_seconds=time.process_time()-cpu_start,
      host_wall_seconds=time.monotonic()-start,max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
      limits=dict(cpu_seconds=120,address_space_bytes=4<<30,output_bytes=64<<20,external_wall_seconds=150),
      limitations=['Historical prefix artifacts, not outputs from the completed CI run.',
        'Original native Matrix operations plus source-equivalent scalar fold; full owner protocol not executed.',
        'Exact current Scalar softmax only on bounded selected real rows; no full softmax coverage claim.',
        'Original official AST with fixed local native/runtime pins; no CI platform identity claim.'])
    np.savez_compressed(OUT/'LOCAL_ARRAYS.npz',official_q=official_q,official_k=official_k,
       historical_q=historical_q,historical_k=historical_k,official_dot=dot_a,official_score=score_a,
       official_input_current_sum=b['sums'],official_input_current_dot=b['dots'],official_input_current_score=b['scores'],
       historical_input_official_dot=dot_c,historical_input_official_score=score_c,
       historical_input_current_sum=d['sums'],historical_input_current_dot=d['dots'],historical_input_current_score=d['scores'],
       official_prob=prob_a,current_score_official_prob=prob_d)
    (OUT/'RESULT.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    (OUT/'SAFE_SUMMARY.json').write_text(json.dumps(public,indent=2,sort_keys=True)+'\n')
    model.need(sum(p.stat().st_size for p in OUT.rglob('*') if p.is_file())<64<<20,'total output cap')
    print(json.dumps(public,sort_keys=True));return report

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');a=p.parse_args()
    result=run(execute=a.execute)
    if not a.execute:print(json.dumps(result,sort_keys=True))
