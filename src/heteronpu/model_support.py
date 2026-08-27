"""Model inventory, descriptor lowering and explicit support levels."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path
from .descriptor_v3 import *
class Level(str,Enum): RTL_PRIMITIVE='rtl_primitive_not_integrated'; RTL_SOURCE='rtl_source_wait_local_sim_dc'; EXECUTABLE_E0='executable_e0_reference'; FUNCTIONAL='functional_model'; ANALYSIS='compiler_analysis_only'; UNSUPPORTED='unsupported'
CAP={'dense_bf16_gemm':Level.RTL_PRIMITIVE,'rms_norm':Level.RTL_PRIMITIVE,'rope_partial':Level.RTL_PRIMITIVE,'gqa':Level.RTL_PRIMITIVE,'hierarchical_block128_attention':Level.RTL_SOURCE,'gated_deltanet_recurrent':Level.EXECUTABLE_E0,'gated_deltanet_prefill':Level.EXECUTABLE_E0,'causal_conv1d':Level.EXECUTABLE_E0,'moe_topk_router':Level.EXECUTABLE_E0,'moe_expert_batching':Level.EXECUTABLE_E0,'moe_expert_execution':Level.EXECUTABLE_E0,'moe_dispatch_cache':Level.ANALYSIS,'qsa_indexer':Level.EXECUTABLE_E0,'qsa_sparse_attention':Level.EXECUTABLE_E0,'attention_output_gate':Level.EXECUTABLE_E0,'gated_residual':Level.EXECUTABLE_E0,'ple_hash_lookup_conv':Level.EXECUTABLE_E0,'mtp_verify_rollback':Level.EXECUTABLE_E0,'qwen38_text_tiny_e2e':Level.EXECUTABLE_E0,'vision_encoder':Level.UNSUPPORTED}
@dataclass(frozen=True)
class ModelProfile:
    raw:dict
    @classmethod
    def load(cls,p):return cls(json.loads(Path(p).read_text()))
    @property
    def name(self):return self.raw.get('requested_name',self.raw.get('model_id','unknown'))
    @property
    def layer_pattern(self):return tuple(self.raw.get('layer_pattern',()))
    def required(self):
        ops={'dense_bf16_gemm','rms_norm'};layers=set(self.layer_pattern)
        if {'full_attention','qwen_sparse_attention'}&layers:ops|={'rope_partial','gqa','hierarchical_block128_attention'}
        if {'gated_deltanet','linear_attention'}&layers:ops|={'gated_deltanet_recurrent','gated_deltanet_prefill','causal_conv1d'}
        if self.raw.get('moe'):ops|={'moe_topk_router','moe_expert_batching','moe_expert_execution','moe_dispatch_cache'}
        if self.raw.get('qsa'):ops|={'qsa_indexer','qsa_sparse_attention','attention_output_gate'}
        if self.raw.get('gated_residual'):ops.add('gated_residual')
        if self.raw.get('ple'):ops.add('ple_hash_lookup_conv')
        if self.raw.get('mtp'):ops.add('mtp_verify_rollback')
        if self.raw.get('model_id')=='Qwen/Qwen3.8-Flash-Next':ops.add('qwen38_text_tiny_e2e')
        if (self.raw.get('vision_encoder') or {}).get('present'):ops.add('vision_encoder')
        return tuple(sorted(ops))
    def support(self):return {x:CAP[x].value for x in self.required()}
    def policies(self):
        out={};r=self.raw
        if r.get('full_attention'):
            a=r['full_attention'];out['attention_op']=attention_op(q_heads=a['q_heads'],kv_heads=a['kv_heads'],head_dim=a['head_dim'],rotary_dim=a['rotary_dim']).pack()
        if r.get('gated_deltanet'):
            d=r['gated_deltanet'];out['delta_policy']=delta_policy(qk_heads=d['qk_heads'],v_heads=d['v_heads'],key_dim=d['key_dim'],value_dim=d['value_dim'],conv_kernel=d['conv_kernel']).pack()
        if r.get('moe'):
            m=r['moe'];out['moe_policy']=moe_policy(num_experts=m['num_experts'],top_k=m['top_k'],shared_experts=m.get('shared_experts',0),intermediate_size=m['intermediate_size']).pack()
        if r.get('qsa'):
            q=r['qsa'];out['qsa_policy']=qsa_policy(index_q_heads=q['index_q_heads'],index_kv_heads=q['index_kv_heads'],index_head_dim=q['index_head_dim'],token_budget=q['token_budget'],compress_ratio=q['compress_ratio']).pack()
        if r.get('gated_residual'):
            g=r['gated_residual'];out['gated_residual_policy']=gated_residual_policy(branch_count=g['branches'],hidden_size=r['hidden_size'],lowrank=g['lowrank'],norm_group_size=r['hidden_size']).pack()
        if r.get('ple'):
            p=r['ple'];out['ple_policy']=ple_policy(ngram_size=p['ngram_size'],heads_per_ngram=p['heads_per_ngram'],embed_dim=p['embed_dim'],conv_kernel=p['conv_kernel'],conv_dilation=p['conv_dilation']).pack()
        if r.get('mtp'):
            m=r['mtp'];out['mtp_policy']=mtp_policy(layers=m['layers'],prediction_steps=m.get('prediction_steps',m['layers']),hidden_size=r['hidden_size'],vocab_size=r['vocab_size']).pack()
        return out

    def runtime_schedule(self):
        """Return a hardware-oriented Qwen3.8 text schedule when applicable."""
        if self.raw.get('model_id')!='Qwen/Qwen3.8-Flash-Next':
            return None
        from .qwen38_schedule import build_qwen38_schedule
        ple_ids=tuple(int(x)-1 for x in (self.raw.get('ple') or {}).get('layer_ids',()))
        return build_qwen38_schedule(self.layer_pattern,ple_ids,include_mtp=bool(self.raw.get('mtp')))

    def footprint(self):
        d=self.raw.get('gated_deltanet') or {};layers=self.layer_pattern.count('gated_deltanet')+self.layer_pattern.count('linear_attention');qh=d.get('qk_heads',0);vh=d.get('v_heads',0);kd=d.get('key_dim',0);vd=d.get('value_dim',0);kernel=d.get('conv_kernel',1)
        recurrent=layers*vh*kd*vd*4;conv=layers*(kernel-1)*(2*qh*kd+vh*vd)*4
        return {'recurrent_state_bytes':recurrent,'conv_state_bytes':conv,'total_state_bytes':recurrent+conv}
def load_profiles(root):return tuple(ModelProfile.load(p) for p in sorted(Path(root).glob('*.json')))
