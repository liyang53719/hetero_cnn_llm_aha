"""New bounded official prefix versus historical completed DUT producers.

No reference payload is loaded as an operand. No fresh DUT, attention, FFN,
fullblock, RTL, download or CI execution. Existing numerical gates unchanged.
"""
import ast
import hashlib
import json
import os
from pathlib import Path
import resource
import sys
import time
from candidates.qwen2_aten_q_projection_candidate import probe as base

EXTRA={
 'wk':'313f8c46dec3be020734db5647f124467f86b0f637c1e80a5c85814971413344',
 'bk':'c77424743b1f69c60e2de1b4780666973af58831169c3ee02d7443701bc6d03d',
 'wv':'a00fd3873f1d0ab098694b6003fd27f464e769c3395e227c729bb856246de84a',
 'bv':'e0ba90f0d591f0266f0140802b6e4ccc24a9961ef26e96ee00f5b1567f8b2f70',
 'rope':'f6c6e15e3f480afe2e9ebfb05719ff8d20a77a5a5551aa8a44bf2a49870d77af'}
NAMES=('n0','qr','kr','v','q','k')
KNOWN_DRIFT={'candidates/qwen2_fullblock_recovery/audit_probe.py',
             'candidates/qwen2_fullblock_recovery/gates.py'}
EXPECTED=dict(torch='2.10.0+cpu',commit='449b1768410104d3ed79d3bcfe4ba1d65c7f22c0',
    capability='AVX2',threads=4,interop_threads=1,mkldnn_enabled=False,deterministic=True)

def completed_record(records,name,raw):
    matches=[r for r in records if r['name']==name]
    base.need(len(matches)==1,'unique historical producer')
    r=matches[0]
    base.need(r['owner_terminal'] is True and r['finite'] is True and
              r['ack_bytes']==r['bytes']==len(raw),'historical producer not complete')
    base.need(hashlib.sha256(raw).hexdigest()==r['sha256'],'historical producer bytes changed')
    return r

def run(*,execute=False):
    if not execute:return {'status':'NOT_EXECUTED'}
    start=time.monotonic();root=base.ROOT;out=root/'work/qwen2_aten_q_projection_candidate/local02'
    resource.setrlimit(resource.RLIMIT_CPU,(90,90));resource.setrlimit(resource.RLIMIT_AS,(4<<30,4<<30))
    base.need(not out.exists() and 'torch' not in sys.modules,'fresh output/process')
    base.need(os.environ.get('ATEN_CPU_CAPABILITY')=='avx2','preimport ATen AVX2')
    base.need(os.environ.get('PYTHONPATH')==str(root/'work/runtime_recovery/site-packages'),'fixed runtime path')
    from candidates.qwen2_runtime_relocation import runtime
    pins=runtime._expected('full29');native=runtime.check_native(pins,family='full29')
    sources={str(p.relative_to(root)):base.sha(p) for p in base.HERE.iterdir() if p.is_file() and p.suffix in ('.py','.cpp')}
    inputs={**base.INPUTS,**EXTRA};raw={k:(base.DATA/(k+'.bin')).read_bytes() for k in inputs}
    base.need(all(hashlib.sha256(v).hexdigest()==inputs[k] for k,v in raw.items()),'fixed inputs changed')
    old=json.loads((base.OLD/'RESULT.json').read_text());old_sha=base.sha(base.OLD/'RESULT.json')
    base.need(all(old['input_identity_before'][k]['sha256']==h for k,h in inputs.items()),'historical input binding')
    payloads={n:(base.OLD/(n+'.f32le')).read_bytes() for n in NAMES}
    records={n:completed_record(old['producers'],n,b) for n,b in payloads.items()}
    current_old_sources={p:base.sha(root/p) for p in old['source_sha256_before']}
    drift=[p for p,h in current_old_sources.items() if h!=old['source_sha256_before'][p]]
    base.need(set(drift)==KNOWN_DRIFT,'unapproved arithmetic/input-source drift')
    import torch
    import numpy as np
    torch.set_num_threads(4);torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True);torch.backends.mkldnn.enabled=False
    def state():return dict(torch=torch.__version__,commit=torch.version.git_version,
        capability=torch.backends.cpu.get_cpu_capability(),threads=torch.get_num_threads(),
        interop_threads=torch.get_num_interop_threads(),mkldnn_enabled=torch.backends.mkldnn.enabled,
        deterministic=torch.are_deterministic_algorithms_enabled())
    base.need(state()==EXPECTED,'runtime mismatch')
    base.need(Path(torch._C.__file__).resolve()==Path(native['torch_C']['path']), 'loaded Torch C path')
    base.need(Path(np._core._multiarray_umath.__file__).resolve()==Path(native['numpy_multiarray']['path']),'loaded numpy path')
    src='config/upstream/weight_headers/qwen2_1p5b/modeling_qwen2.py'
    base.need(base.sha(root/src)==pins['sources'][src]['sha256'],'official source identity')
    ns={'torch':torch,'nn':torch.nn}
    nodes=pins['model_ast_nodes']
    def execute(selected):
        for node in selected:
            text=node['source']
            base.need(hashlib.sha256(text.encode()).hexdigest()==node['source_sha256'],'pinned AST text')
            exec(compile(ast.parse(text),src,'exec'),ns)
    execute(nodes[:4])
    def expanded(name,shape):return torch.from_numpy(np.frombuffer(raw[name],'<f4').copy()).reshape(shape).to(torch.bfloat16)
    norm=ns['Qwen2RMSNorm'](1536,eps=1e-6).to(torch.bfloat16).eval()
    norm.weight=torch.nn.Parameter(expanded('gamma0',(1536,)),requires_grad=False)
    attention=torch.nn.Module()
    attention.hidden_size,attention.num_heads=1536,12
    attention.num_key_value_heads,attention.head_dim=2,128
    ns['self']=attention;execute(nodes[4:7])
    for letter,width in (('q',1536),('k',256),('v',256)):
        weight=np.frombuffer(raw['w'+letter],'<u2').reshape(1536,width).T.copy()
        layer=getattr(attention,letter+'_proj')
        layer.weight=torch.nn.Parameter(torch.from_numpy(weight).view(torch.bfloat16),requires_grad=False)
        layer.bias=torch.nn.Parameter(expanded('b'+letter,(width,)),requires_grad=False)
    attention.rotary_emb=ns['Qwen2RotaryEmbedding'](128,max_position_embeddings=256,base=1e6).to(torch.bfloat16)
    attention.to(torch.bfloat16).eval()
    def array(t):return t.detach().float().cpu().numpy().copy()
    with torch.inference_mode():
        x=expanded('x',(1,128,1536));n0=norm(x)
        base.need(n0.is_contiguous() and tuple(n0.shape)==(1,128,1536),'M128 input geometry')
        ns.update(hidden_states=n0,self=attention,bsz=1,q_len=128,kv_seq_len=128,
            position_ids=torch.arange(128,dtype=torch.long).unsqueeze(0))
        execute(nodes[7:10])
        outputs={'n0':array(n0),'qr':array(ns['query_states']),
                 'kr':array(ns['key_states']),'v':array(ns['value_states'])}
        execute(nodes[10:15])
        for name,key in (('q','query_states'),('k','key_states')):
            outputs[name]=array(ns[key].transpose(1,2).contiguous())
        tables=[array(ns['cos']),array(ns['sin'])]
    # Prove current original RoPE uses the same stored table after BF16 RNE.
    rope=np.frombuffer(raw['rope'],'<f4').reshape(2,1024,64)[:,:128,:].copy()
    u=rope.view('<u4');rounded=((u+0x7fff+((u>>16)&1))&0xffff0000).view('<f4')
    base.need(all(t.tobytes()==np.concatenate((rounded[i],rounded[i]),axis=-1).tobytes()
                  for i,t in enumerate(tables)),'rotary table binding differs')
    base.need(outputs['n0'].reshape(128,1536).tobytes()==payloads['n0'],'n0 changed')
    from scripts import qwen2_layer0_model_gate as gate
    policy=gate.load_policy(root)
    base.need(policy['operator']=={'max_abs':0.03125,'mean_abs':0.005},'original gate changed')
    comparisons={}
    for n in NAMES:
        actual=np.frombuffer(payloads[n],'<f4').reshape(128,-1)
        reference=outputs[n].reshape(128,-1)
        metrics=gate.compare(actual,reference)
        comparisons[n]={'metrics':metrics,'verdict':gate.stage_verdict(n,metrics,'bf16',policy)}
    base.need(state()==EXPECTED and runtime.check_native(pins,family='full29')==native,'runtime/native drift')
    base.need(all(base.sha(root/p)==h for p,h in sources.items()),'new source drift')
    base.need(all(base.sha(root/p)==h for p,h in current_old_sources.items()),'old current source drift during probe')
    base.need(all(base.sha(base.DATA/(k+'.bin'))==h for k,h in inputs.items()),'input drift')
    base.need(base.sha(base.OLD/'RESULT.json')==old_sha,'historical receipt drift')
    base.need(all(base.sha(base.OLD/(n+'.f32le'))==r['sha256'] for n,r in records.items()),'historical payload drift')
    report=dict(schema=1,status='COMPLETED_LOCAL_PREFIX_DIAGNOSTIC',runtime=EXPECTED,
        local_native_identity=native,ci_runtime_equivalence_claimed=False,
        sources=sources,input_sha256=inputs,old_receipt_sha256=old_sha,old_result_status=old['status'],
        old_completed_records=records,old_admission_audit_source_drift=drift,
        all_other_old_source_identities_match=True,old_source_closure_unchanged=False,
        old_n0_equals_new_official=True,rotary_tables_equal_after_bf16=True,
        official_shapes={'input':[1,128,1536],'q_output':[1,128,1536],'kv_output':[1,128,256]},
        comparisons=comparisons,policy=policy,
        raw_qkv={'status':'NO_OFFICIAL_PREBIAS_REFERENCE','verdict':None},
        old_dut_fresh_executed=False,attention_executed=False,ffn_executed=False,fullblock_executed=False,
        rtl_executed=False,host_wall_seconds=time.monotonic()-start,
        max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        limits=dict(cpu_seconds=90,address_space_bytes=4<<30,external_wall_seconds=150),
        limitation='Historical completed prefix artifacts versus new local original-AST prefix only; no fullblock acceptance.')
    out.mkdir(parents=True);(out/'RESULT.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'status':report['status'],'comparisons':comparisons,'seconds':report['host_wall_seconds']}))
    return report

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');args=p.parse_args()
    run(execute=args.execute)
