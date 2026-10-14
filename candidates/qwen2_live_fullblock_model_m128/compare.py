"""Post-whole-terminal original-policy comparison, never an operand provider."""
import hashlib
from candidates.qwen2_live_attention_model_m128 import compare as prefix_compare

TAIL = ('o','r','n1','gate','up','silu','act','down','y')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def official(out, report, capture, actual, silu, reference, payloads, native, np):
    require(report['actual_outputs_sealed'] and report['whole_block_terminal'] and
            report['execution']['host']['launch_result']['completed'] == 21,
            'comparison requires sealed whole public21 terminal')
    result = prefix_compare.official(out,report,capture,reference,payloads,native,np)
    comparisons = {}
    for name in TAIL:
        raw = silu if name == 'silu' else actual[name].tobytes()
        require(hashlib.sha256(raw).hexdigest() == report['sealed_actual_outputs'][name]['sha256'],
                'sealed tail output drift: '+name)
        spec = reference['outputs'][name]
        a = np.frombuffer(raw,dtype='<f4').reshape(spec['shape'])
        b = np.frombuffer(payloads[name],dtype='<f4').reshape(spec['shape'])
        require(np.isfinite(a).all() and np.isfinite(b).all(), 'nonfinite tail output: '+name)
        metrics = native.compare(a,b)
        verdict = native.stage_verdict(name,metrics,'bf16',report['numerical_policy'])
        require(type(verdict['passed']) is bool, 'tail node lacks original BF16 policy: '+name)
        comparisons[name] = dict(metrics=metrics,verdict=verdict,official_numeric_pass=verdict['passed'],
            coverage='complete',observed_elements=int(a.size),
            origin='accepted resident tile reads' if name in ('gate','up') else
                   'original BF16 SiLU phase4 return' if name == 'silu' else 'ACKed physical output')
    # Cache aliases are physical views of this launch's exact-copy KV append.
    cache = {}
    for name, producer in (('cache_k','k'),('cache_v','v')):
        spec = reference['outputs'][name]
        reference_token = np.frombuffer(payloads[name],'<f4').reshape(spec['shape']).transpose(0,2,1,3).copy().tobytes()
        raw = actual[producer].tobytes()
        metrics = native.compare(np.frombuffer(raw,'<f4'),np.frombuffer(reference_token,'<f4'))
        cache[name] = dict(metrics=metrics,exact_cold_alias=raw==reference_token,
            dynamic_cache_executed=False,origin='same-live KV append K/V physical subspan')
    passed = result['official_observed_node_pass'] and all(c['official_numeric_pass'] for c in comparisons.values()) and all(
        c['exact_cold_alias'] for c in cache.values())
    result['official_observed_nodes_bit_exact']=result['official_observed_nodes_bit_exact'] and all(
        c['metrics']['bit_exact'] for c in comparisons.values()) and all(c['exact_cold_alias'] for c in cache.values())
    result.update(tail_comparisons=comparisons,cold_cache_comparisons=cache,
        official_observed_node_pass=passed,whole_block_terminal=True,fullblock_pass=passed,
        fullblock_pass_scope='fresh public21 software-model observed nodes under existing BF16 operator/block gates',
        full_29_node_acceptance=False,full_official_forward_executed=False,
        reference_only_nodes=['x','cos','sin','repeat_k','repeat_v','mask'],
        missing_official_raw_nodes=['qraw','kraw','vraw'],softmax_fp32_tolerance=None)
    return result
