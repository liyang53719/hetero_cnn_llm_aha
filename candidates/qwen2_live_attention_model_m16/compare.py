"""Post-seal official comparisons only; never produces a model operand."""
import hashlib
from pathlib import Path


def require(ok,message):
    if not ok:raise ValueError(message)


def official(out,report,capture,reference,payloads,native,np):
    from . import gates
    out=Path(out);policy=report['numerical_policy'];comparisons={}
    def expected(name):
        spec=reference['outputs'][name]
        return np.frombuffer(payloads[name],dtype='<f4').reshape(spec['shape'])
    def check(name,a,b,*,coverage='complete'):
        require(a.shape==b.shape and np.isfinite(a).all() and np.isfinite(b).all(),'nonfinite or incompatible shapes '+name)
        metrics=native.compare(a,b);verdict=native.stage_verdict(name,metrics,'bf16',policy)
        return dict(metrics=metrics,verdict=verdict,official_numeric_pass=verdict['passed'],coverage=coverage,
            observed_elements=int(a.size))
    for record in report['producers']:
        name=record['name'];raw=(out/(name+'.f32le')).read_bytes()
        require(hashlib.sha256(raw).hexdigest()==record['sha256'],'sealed producer drift '+name)
        a=np.frombuffer(raw,dtype='<f4').reshape(16,-1)
        if name in gates.RAW:
            comparisons[name]=dict(official_numeric_pass=None,status='NO_OFFICIAL_RAW_REFERENCE');continue
        b=expected(name)
        if name in ('q','k'):b=b.transpose(0,2,1,3)
        comparisons[name]=check(name,a,b.reshape(16,-1))
    kv=(out/'kv.f32le').read_bytes()
    b=expected('k').transpose(0,2,1,3).copy().tobytes()+payloads['v']
    require(len(kv)==len(b)==32768,'official KV extent')
    kv_compare=check('kv',np.frombuffer(kv,'<f4'),np.frombuffer(b,'<f4'))
    kv_compare['official_kv_exact_copy']=kv==b
    mask=expected('mask');words=mask.view('<u4')
    require(mask.shape==(1,1,16,16),'explicit mask shape')
    future=np.broadcast_to(np.triu(np.ones((16,16),dtype=bool),1),mask.shape)
    require((words[future]==0xff7f0000).all() and (words[~future]==0).all(),'explicit BF16 mask contract')
    mapping={'scores':'scores_bf16','logits':'scores_bf16','softmax_fp32':'softmax_fp32','prob':'prob_bf16','pv':'pv_bf16'}
    attention={};arrays={}
    for name,field in mapping.items():
        spec=capture.fields[field]
        a=np.frombuffer(capture._bytes(field),dtype='<f4').reshape((1,*spec['shape']))
        presence=np.frombuffer(bytes(spec['observed']),dtype='u1').reshape(a.shape).astype(bool)
        wanted=np.ones(a.shape,dtype=bool) if name=='pv' else np.broadcast_to(np.tri(16,dtype=bool),a.shape)
        require(np.array_equal(presence,wanted),'actual causal coverage differs '+name)
        count=24576 if name=='pv' else 1632
        require(int(presence.sum())==count,'observed coverage cardinality '+name)
        b=expected(name);require(a.shape==b.shape,'reference logical layout '+name)
        attention[name]=check(name,a[presence],b[presence],coverage='complete' if name=='pv' else 'actual_causal_positions_only')
        attention[name].update(logical_elements=int(a.size),unobserved_elements=int(a.size-count),future_observed=False)
        arrays[name]=(a,presence)
    att=(out/'att.f32le').read_bytes()
    require(hashlib.sha256(att).hexdigest()==report['attention']['output']['sha256'],'sealed att drift')
    attention['att']=check('att',np.frombuffer(att,'<f4').reshape(1,16,1536),expected('att'))
    soft,presence=arrays['softmax_fp32']
    sums=np.where(presence,soft,np.float32(0)).sum(axis=-1,dtype=np.float64)
    errors=np.abs(sums-1.0)
    probability_sum=dict(contract='spec/numerical_contract.md:Softmax',limit=2e-5,
        reduction='float64 audit sum of actual FP32 probabilities; absent future positions excluded',
        max_abs=float(errors.max()),passed=bool((errors<=2e-5).all()),rows=int(errors.size))
    require('Probability sum absolute error <= `2e-5`' in (gates.ROOT/'spec/numerical_contract.md').read_text(),'softmax contract drift')
    passed=gates.official_pass(comparisons) and kv_compare['official_kv_exact_copy'] and probability_sum['passed'] and all(
        attention[n]['official_numeric_pass'] is True for n in gates.ATTENTION-{'softmax_fp32'})
    require(attention['softmax_fp32']['official_numeric_pass'] is None,'invented FP32 official tolerance')
    return dict(producer_comparisons=comparisons,attention_comparisons=attention,official_kv_comparison=kv_compare,
        softmax_probability_sum=probability_sum,official_observed_node_pass=passed,
        official_observed_nodes_bit_exact=all(v['metrics']['bit_exact'] for n,v in comparisons.items() if n in gates.OFFICIAL)
            and all(v['metrics']['bit_exact'] for v in attention.values()),
        causal_semantics=dict(reference_mask_exact=True,mask_future_word='0xff7f0000',mask_allowed_word='0x00000000',
            reference_mask_is_explicit_wrapper_parameter=True,dut_explicit_mask_tensor_observed=False,
            dut_future_positions_observed=False,actual_causal_positions_per_field=1632,
            full_matrix_positions_per_field=3072,actual_pv_context_elements=24576,
            implicit_mask='unchanged owner loops key in range(token+1); future descriptor/physical work skipped'),
        full_29_node_acceptance=False,whole_block_terminal=False,
        reference_only_nodes=['x','cos','sin','repeat_k','repeat_v','mask'],typed_attention_bit_exact_executed=False)
