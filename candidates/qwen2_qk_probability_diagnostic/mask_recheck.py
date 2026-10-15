"""Independent bounded supplement for the exact original finite BF16 mask.

Does not rewrite local01, repeat QK, execute a full block, or promote coverage.
The current QK has no future observations. Its future cells are explicitly
filled with diagnostic +0 before the original finite mask is added; only
causal values are measured. Original official scores have full real geometry.
"""
import ast
import hashlib
import json
import os
from pathlib import Path
import resource
import sys
import time
from candidates.qwen2_qk_probability_diagnostic import model
from candidates.qwen2_aten_q_projection_candidate import prefix_probe as prefix

ROOT=model.ROOT
OLD=ROOT/'work/qwen2_qk_probability_diagnostic/local01'
OUT=ROOT/'work/qwen2_qk_probability_diagnostic/mask01'

def run(execute=False):
    if not execute:return {'status':'NOT_EXECUTED'}
    start=time.monotonic();cpu=time.process_time()
    resource.setrlimit(resource.RLIMIT_CPU,(120,120));resource.setrlimit(resource.RLIMIT_AS,(4<<30,4<<30))
    resource.setrlimit(resource.RLIMIT_FSIZE,(63<<20,63<<20))
    model.need(not OUT.exists() and 'torch' not in sys.modules,'fresh process/output')
    model.need(os.environ.get('ATEN_CPU_CAPABILITY')=='avx2','preimport capability')
    model.need(os.environ.get('PYTHONPATH')==str(ROOT/'work/runtime_recovery/site-packages'),'runtime path')
    before={p.name:model.sha(p) for p in OLD.iterdir() if p.is_file()}
    source_sha=model.sha(Path(__file__))
    from candidates.qwen2_runtime_relocation import runtime
    pins=runtime._expected('full29');native=runtime.check_native(pins,family='full29')
    import numpy as np
    import torch
    torch.set_num_threads(4);torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True);torch.backends.mkldnn.enabled=False
    def state():return dict(torch=torch.__version__,commit=torch.version.git_version,
        capability=torch.backends.cpu.get_cpu_capability(),threads=torch.get_num_threads(),
        interop_threads=torch.get_num_interop_threads(),mkldnn_enabled=torch.backends.mkldnn.enabled,
        deterministic=torch.are_deterministic_algorithms_enabled())
    model.need(state()==prefix.EXPECTED,'runtime profile')
    model.need(Path(torch._C.__file__).resolve()==Path(native['torch_C']['path']),'torch path')
    model.need(Path(np._core._multiarray_umath.__file__).resolve()==Path(native['numpy_multiarray']['path']),'numpy path')
    src='config/upstream/weight_headers/qwen2_1p5b/modeling_qwen2.py'
    model.need(model.sha(ROOT/src)==pins['sources'][src]['sha256'],'official source')
    # Same literal cold mask argument as the pinned original capture wrapper.
    mask_raw=b''.join((0xff7f if k>q else 0).to_bytes(2,'little') for q in range(128) for k in range(128))
    model.need(hashlib.sha256(mask_raw).hexdigest()==pins['mask_contract']['native_sha256'],'exact original finite mask identity')
    mask=torch.from_numpy(np.frombuffer(mask_raw,dtype='<u2').copy()).view(torch.bfloat16).reshape(1,1,128,128)
    causal=np.broadcast_to(np.tril(np.ones((128,128),dtype=bool)),(12,128,128))
    ns={'torch':torch,'nn':torch.nn,'bsz':1,'q_len':128,'kv_seq_len':128,
        'query_states':torch.empty(0,dtype=torch.bfloat16),'attention_mask':mask}
    nodes=pins['model_ast_nodes']
    def execute(i):
        n=nodes[i];model.need(hashlib.sha256(n['source'].encode()).hexdigest()==n['source_sha256'],'AST identity')
        exec(compile(ast.parse(n['source']),src,'exec'),ns)
    def compare(a,b):
        x=a[causal];y=b[causal];d=np.abs(x.astype(np.float64)-y.astype(np.float64))
        return {'count':int(d.size),'max_abs':float(d.max()),'mean_abs':float(d.mean()),
                'bit_diff_count':int(np.count_nonzero(x.view('<u4')!=y.view('<u4')))}
    data=np.load(OLD/'LOCAL_ARRAYS.npz');result={};outputs={}
    with torch.inference_mode():
        for label,sname,pname in [('OFFICIAL_SCORES','official_score','official_prob'),
          ('CURRENT_CAUSAL_SCORES','historical_input_current_score','current_score_official_prob')]:
            score=data[sname].copy()
            if label=='CURRENT_CAUSAL_SCORES':score[~causal]=0.0
            ts=torch.from_numpy(score).to(torch.bfloat16).unsqueeze(0)
            ns['attn_weights']=ts;execute(20)
            model.need(torch.isfinite(ns['attn_weights']).all().item(),'finite additive mask')
            execute(21);finite=ns['attn_weights'].float().numpy()[0].copy()
            ns['attn_weights']=ts.masked_fill(~torch.from_numpy(causal.copy()).unsqueeze(0),float('-inf'))
            execute(21);inf=ns['attn_weights'].float().numpy()[0].copy()
            result[label]={'finite_vs_inf':compare(finite,inf),'finite_vs_saved':compare(finite,data[pname])}
            outputs[label]=finite
    propagation=compare(outputs['CURRENT_CAUSAL_SCORES'],outputs['OFFICIAL_SCORES'])
    model.need(all(model.sha(OLD/n)==h for n,h in before.items()),'local01 changed')
    model.need(model.sha(Path(__file__))==source_sha,'supplement source changed')
    model.need(state()==prefix.EXPECTED and runtime.check_native(pins,family='full29')==native,'runtime/native drift')
    public={'status':'EXACT_FINITE_MASK_SUPPLEMENT_COMPLETE','comparisons':result,
      'current_scores_official_softmax_propagation':propagation,
      'mask':'ORIGINAL_FINITE_BF16_MASK_AND_ORIGINAL_AST_NODES',
      'current_future_values':'UNOBSERVED_DIAGNOSTIC_ZERO_FILL_BEFORE_MASK',
      'coverage':'CAUSAL_ONLY','original_result':'UNCHANGED','qk':'NOT_RERUN',
      'fullblock':'NOT_EXECUTED','ci':'NOT_EXECUTED'}
    report={'public':public,'runtime':state(),'native_identity':native,'old_files_sha256':before,
      'source_sha256':source_sha,'official_mask_sha256':hashlib.sha256(mask_raw).hexdigest(),
      'official_ast':[nodes[20],nodes[21]],'host_cpu_seconds':time.process_time()-cpu,
      'host_wall_seconds':time.monotonic()-start,'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
      'limitation':'Current QK has causal observations only; diagnostic future zero fill is not DUT computation.'}
    OUT.mkdir(parents=True);(OUT/'RESULT.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    (OUT/'SAFE_SUMMARY.json').write_text(json.dumps(public,indent=2,sort_keys=True)+'\n')
    print(json.dumps(public,sort_keys=True));return report

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');a=p.parse_args()
    result=run(a.execute)
    if not a.execute:print(json.dumps(result))
