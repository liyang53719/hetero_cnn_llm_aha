import math,random
from pathlib import Path
from heteronpu.hierarchical_attention import *
from heteronpu.descriptor_v3 import *
from heteronpu.gated_deltanet import Geometry,State,step,ConvState,causal_conv_step
from heteronpu.qwen38_ops import *
from heteronpu.mtp import verify
from heteronpu.matrix_contexts import Model,Step,utilization
from heteronpu.performance_budget import Qwen2Budget
from heteronpu.paged_kv_v3 import PagedKV,Key,analyze
from heteronpu.model_support import ModelProfile
from heteronpu.moe_router import route_topk,expert_batches
ROOT=Path(__file__).resolve().parents[1]

def test_block128_counts_and_accuracy():
    assert causal_merge_count(1024,12)==43008
    assert BlockedAttentionGeometry(1024,12,128).live_set_bytes<65536
    rng=random.Random(1)
    for n in (128,384,1024):
        scores=[rng.uniform(-8,8) for _ in range(n)];values=[[rng.uniform(-1,1) for _ in range(4)] for _ in range(n)]
        exact=normalized(summarize(scores,values));rtl=normalized(blockwise(scores,values,128,True))
        assert max(abs(a-b) for a,b in zip(exact,rtl))<0.002

def test_exp2_pwl_bounds():
    assert exp2_pwl_rtl(-17)==0 and exp2_pwl_rtl(0)==1
    worst=max(abs(exp2_pwl_rtl(-16+16*i/10000)-2**(-16+16*i/10000)) for i in range(10001))
    assert worst<0.00025

def test_descriptor_records_roundtrip():
    rs=[shape2_32(123,456),attention_op(q_heads=24,kv_heads=2,head_dim=256,rotary_dim=64),moe_policy(num_experts=512,top_k=10,shared_experts=1,intermediate_size=640),delta_policy(qk_heads=16,v_heads=48,key_dim=128,value_dim=128,conv_kernel=4),qsa_policy(index_q_heads=4,index_kv_heads=1,index_head_dim=128,token_budget=2048,compress_ratio=4),gated_residual_policy(branch_count=4,hidden_size=2560,lowrank=320,norm_group_size=2560),ple_policy(ngram_size=3,heads_per_ngram=8,embed_dim=2560,conv_kernel=4,conv_dilation=3),mtp_policy(layers=1,prediction_steps=1,hidden_size=2560,vocab_size=248320),kv_context32(sequence_id=1,layer_id=2,kv_head_id=3),kv_range32(token_start=1_000_000,token_count=16),kv_table(page_table_tensor_index=1,physical_page_limit=9999),kv_epoch32(generation=0xffffffff,logical_page_count=62500)]
    for r in rs:assert DescriptorRecord.unpack(r.to_bytes())==r and decode(r)['record_type']==r.record_type
    for t in range(0x13,0x1a):assert rtl_capability(t)==(True,False,CompletionStatus.UNSUPPORTED_POLICY)

def test_gdn_recurrent_and_conv():
    g=Geometry(1,1,2,2);out,state=step(geometry=g,query=[[1,0]],key=[[1,0]],value=[[1,2]],a=[0],b=[0],z=[[1,1]],a_log=[0],dt_bias=[0],norm_weight=[1,1],state=State.zeros(g))
    assert len(out)==1 and any(abs(x)>0 for x in out[0]) and g.state_bytes==16
    c=ConvState.zeros(1,3);o,c=causal_conv_step([1],[[1,2,3]],c,activation=None);assert o==(3.0,)

def test_qsa_gr_ple_and_mtp():
    mult=multipliers(248320,3,0);idx=ngram_indices([4,9,12],ngram_size=3,heads_per_ngram=2,sizes=[101,103,107,109],offsets=[0,101,204,311],mults=mult);assert len(idx)==3 and len(idx[0])==4
    sel=qsa_select(queries=[[1,0]],keys=[[1,0],[.9,.1],[0,1],[.1,.9],[.5,.5]],visible=[0,1,2,3,4],token_budget=2,compress_ratio=2);assert sel[:2]==(0,1) and sel[-1]==4
    mix,y=gated_residual([1,2,3,4],[0,0,0,0],[0,0],[1,-1],2,2);assert len(mix)==2 and len(y)==4
    s=DilatedConvState.zeros(1,3,2)
    for v in [1,2,3,4,5]:o,s=dilated_conv_step([v],[[1,2,3]],s)
    assert math.isfinite(o[0])
    r=verify([1,2,3],[1,2,9]);assert r.accepted==2 and r.rejected==(3,)

def test_context_budget_router():
    assert utilization(4,4)==1
    m=Model(4,1,4)
    for t in range(1000):assert m.issue(Step(t%4,(1.0,),t));m.tick()
    while m.q:m.tick()
    assert m.accepted==m.completed==1000
    b=Qwen2Budget();assert b.hard_cycles==3413333333 and .79<b.wall_util<.80
    assert [r.expert_id for r in route_topk([2,2,-1,3],2)]==[3,0]
    assert expert_batches([[1,2,3],[3,2,1]],2,1)

def test_paged_kv_prefix_cow_and_1m():
    kv=PagedKV(max_pages=64);p=Key(1,0,0);c=Key(2,0,0);kv.create(p,7)
    for i in range(20):kv.append(p,7,i)
    kv.fork(p,c,7,20);kv.append(c,7,99)
    assert kv.gather(p,7,16,4)==(16,17,18,19) and kv.gather(c,7,16,5)==(16,17,18,19,99)
    kv.assert_ok();kv.free_stream(c,7);kv.free_stream(p,7);kv.assert_ok()
    assert analyze(1_000_000)['logical_pages']==62500

def test_profiles_and_support():
    q35=ModelProfile.load(ROOT/'config/model_profiles/qwen3_5_35b_a3b.json');q38=ModelProfile.load(ROOT/'config/model_profiles/qwen3_8_flash_next.json')
    assert q35.layer_pattern.count('gated_deltanet')==30 and q35.footprint()['recurrent_state_bytes']==62914560
    assert q38.layer_pattern.count('linear_attention')==36 and q38.support()['qsa_indexer']=='executable_e0_reference'
    assert q38.support()['qwen38_text_tiny_e2e']=='executable_e0_reference'
    assert q38.runtime_schedule() is not None
    assert set(q38.policies())=={'attention_op','delta_policy','moe_policy','qsa_policy','gated_residual_policy','ple_policy','mtp_policy'}
