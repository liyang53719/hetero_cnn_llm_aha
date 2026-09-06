#!/usr/bin/env python3
"""Non-overlapping q1024 bring-up allocations. Not an inference/compiler result.

Read-only packed weight extents must come from the actual device-format manifest,
not model parameter count or compressed GGUF byte rate. All generated addresses
are checked against the retained 56-bit descriptor transport limit.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

BASELINE = "fdd8f95c9ffe9d49854f796f0daf4ec770d91e27"
PROFILES = {
    "qwen2": dict(name="Qwen2-1.5B", hidden=1536, vocab=151936, layers=28,
                  attention_layers=28, q_heads=12, kv_heads=2, head_dim=128,
                  recurrent_layers=0, value_heads=0, intermediate=8960, experts=0, topk=1, branches=1),
    "qwen35": dict(name="Qwen3.5-35B-A3B", hidden=2048, vocab=248320, layers=40,
                   attention_layers=10, q_heads=16, kv_heads=2, head_dim=256,
                   recurrent_layers=30, value_heads=32, intermediate=512, experts=256, topk=8, branches=1),
    "qwen38": dict(name="Qwen3.8-Flash-Next", hidden=2560, vocab=248320, layers=48,
                   attention_layers=12, q_heads=24, kv_heads=2, head_dim=256,
                   recurrent_layers=36, value_heads=48, intermediate=640, experts=512, topk=10, branches=4),
}

def align(n: int, alignment: int = 4096) -> int:
    if type(n) is not int or n < 0 or alignment <= 0 or alignment & (alignment - 1):
        raise ValueError("invalid alignment input")
    return (n + alignment - 1) & -alignment

def budgets(key: str, tokens: int = 1024) -> dict[str, dict[str, int]]:
    if key not in PROFILES or type(tokens) is not int or tokens != 1024:
        raise ValueError("only locked q1024 profiles are supported")
    p = PROFILES[key]; h = p['hidden']; q = p['q_heads'] * p['head_dim']
    scratch = dict(hidden_ping=tokens*h*4, hidden_pong=tokens*h*4, norm_bf16=tokens*h*2,
                   q_bf16=tokens*q*2, attention_output_fp32=tokens*q*4,
                   oproj_fp32=tokens*h*4, residual_fp32=tokens*h*4,
                   gate=tokens*p['intermediate']*p['topk']*2,
                   up=tokens*p['intermediate']*p['topk']*2,
                   gated_mlp=tokens*p['intermediate']*p['topk']*2,
                   down_fp32=tokens*h*4)
    state = dict(kv_all_layers=p['attention_layers']*2*tokens*p['kv_heads']*p['head_dim']*2)
    if p['recurrent_layers']:
        channels = 2*16*128 + p['value_heads']*128
        state['gdn_all_layers_fp32'] = p['recurrent_layers']*p['value_heads']*128*128*4
        state['causal_conv_history_fp32'] = p['recurrent_layers']*3*channels*4
        scratch['gdn_qkv_bf16'] = tokens*channels*2
        scratch['moe_route_scores_fp32'] = tokens*p['experts']*4
        scratch['moe_route_indices'] = tokens*p['topk']*4
        scratch['moe_route_probabilities_fp32'] = tokens*p['topk']*4
        scratch['moe_dispatch_bf16'] = tokens*p['topk']*h*2
        scratch['shared_expert_fp32'] = tokens*h*4
    if p['branches'] == 4:
        scratch['hyper_ping_fp32'] = tokens*h*4*4
        scratch['hyper_pong_fp32'] = tokens*h*4*4
        state['qsa_index_keys_bf16'] = p['attention_layers']*tokens*128*2
        state['qsa_summaries_fp32'] = p['attention_layers']*((tokens+3)//4)*128*4
        state['ple_convolution_history_fp32'] = 9*h*4
        state['ple_ngram_history'] = 2*4
        scratch['qsa_selected_indices_max'] = tokens*min(tokens,2048)*4
    return dict(scratch=scratch, persistent=state,
                output=dict(last_token_logits_fp32=p['vocab']*4),
                control=dict(descriptor_and_program=2**20, counters_and_status=2**16))

def plan(key: str, weights: list[dict[str, Any]], ddr_limit: int) -> dict[str, Any]:
    if type(ddr_limit) is not int or not 2**32 < ddr_limit <= 2**56:
        raise ValueError("DDR limit is an exclusive logical address, <= 2^56")
    if not weights:
        raise ValueError("actual device-format weight manifest is required")
    cursor = 2**32; allocations=[]; regions=[]
    def add(name: str, size: int, region: str) -> None:
        nonlocal cursor
        if type(size) is not int or size <= 0:
            raise ValueError("invalid extent size")
        cursor=align(cursor)
        begin=cursor; end=begin+align(size)
        if end > ddr_limit:
            raise ValueError(f"DDR capacity exceeded by {name}")
        allocations.append(dict(name=name, region=region, base=begin, payload_bytes=size,
                                limit=end, guard_bytes=4096))
        cursor=end+4096
    seen=set(); ro_start=cursor
    for w in weights:
        if not isinstance(w.get('name'),str) or not w['name'] or w['name'] in seen:
            raise ValueError("invalid or duplicate weight name")
        digest=w.get('sha256')
        if not isinstance(digest,str) or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError("weight file SHA256 required")
        seen.add(w['name']);add('weight/'+w['name'],w['bytes'],'readonly')
    b=budgets(key)
    # Tokens/constants are external inputs, so reserve within the immutable region.
    add('input_token_ids',1024*4,'readonly')
    add('constants_and_descriptors',b['control']['descriptor_and_program'],'readonly')
    regions.append(dict(name='readonly',base=ro_start,limit=cursor,read=True,write=False))
    for region,sections in [('scratch',['scratch']),('persistent',['persistent']),('output',['output'])]:
        cursor=align(cursor,2**21);start=cursor
        for section in sections:
            for name,size in b[section].items():add(name,size,region)
        if region=='output':add('counters_and_status',2**16,region)
        regions.append(dict(name=region,base=start,limit=cursor,read=True,write=True))
    if cursor>ddr_limit:raise ValueError('final guard exceeds DDR capacity')
    return dict(schema=1, baseline=BASELINE, model=PROFILES[key]['name'],tokens=1024,
                status='ALLOCATION_PLAN_ONLY',regions=regions,allocations=allocations,
                required_address_end=cursor,ddr_limit=ddr_limit,
                weight_manifest=weights,local_sram_bytes=1572864,
                local_tile_partition=dict(a=[0,4096],b=[4096,8192],c=[8192,12288]),
                nonclaims=['No full-model execution or throughput result',
                           'Static non-aliasing bring-up allocation; not optimized liveness reuse',
                           'GDN orientation/conv history layouts require canonical source binding',
                           'PLE full table versus paging policy must be decided from actual checkpoint'])

def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument('--model',choices=sorted(PROFILES),required=True)
    parser.add_argument('--weights',type=Path,required=True)
    parser.add_argument('--ddr-limit',type=lambda s:int(s,0),required=True)
    parser.add_argument('--out',type=Path,required=True)
    a=parser.parse_args();raw=a.weights.read_bytes();result=plan(a.model,json.loads(raw),a.ddr_limit)
    result['input_manifest_sha256']=hashlib.sha256(raw).hexdigest()
    with a.out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
if __name__=='__main__':main()
