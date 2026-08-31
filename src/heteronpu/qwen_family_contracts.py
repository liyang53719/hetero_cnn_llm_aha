"""Authoritative architecture separation for Qwen3.5-35B-A3B and Qwen3.8-Flash-Next.

Qwen3.5-35B-A3B is qwen3_5_moe: Gated-DeltaNet/full-attention MoE with a
single residual stream. Qwen3.8-Flash-Next is qwen4_exp: QSA, four gated
residual streams, PLE n-gram embeddings and a larger MoE. This module freezes
operator/state inventories, hardware owners and shape-only schedules. It is
compiler/architecture E0, not official-weight or RTL evidence.
"""
from __future__ import annotations
from collections import Counter
from dataclasses import dataclass
import hashlib,json
from pathlib import Path

@dataclass(frozen=True)
class OperatorContract:
    name:str;owner:str;stateful:bool;support:str

COMMON={
"token_embedding":OperatorContract("token_embedding","memory",False,"analysis"),
"rmsnorm":OperatorContract("rmsnorm","sfu",False,"rtl_primitive"),
"partial_rope":OperatorContract("partial_rope","sfu",False,"rtl_primitive"),
"gdn_projection":OperatorContract("gdn_projection","matrix",False,"e0_reference"),
"gdn_causal_conv":OperatorContract("gdn_causal_conv","state",True,"e0_reference"),
"gdn_recurrent_update":OperatorContract("gdn_recurrent_update","matrix_state",True,"e0_reference"),
"gdn_gated_norm_output":OperatorContract("gdn_gated_norm_output","sfu_matrix",False,"e0_reference"),
"attention_output_gate":OperatorContract("attention_output_gate","sfu",False,"e0_reference"),
"moe_router_topk":OperatorContract("moe_router_topk","sfu",False,"e0_reference"),
"moe_routed_experts":OperatorContract("moe_routed_experts","matrix_weight",False,"e0_reference"),
"moe_shared_expert":OperatorContract("moe_shared_expert","matrix_weight",False,"e0_reference"),
"moe_route_reduce":OperatorContract("moe_route_reduce","sfu",False,"e0_reference"),
"mtp_state_transaction":OperatorContract("mtp_state_transaction","control_state",True,"e0_reference"),
"vision_encoder":OperatorContract("vision_encoder","vision",False,"unsupported_project_scope")}
Q35={
"standard_residual_add":OperatorContract("standard_residual_add","sfu",False,"analysis"),
"dense_full_attention_qkv":OperatorContract("dense_full_attention_qkv","matrix",False,"source_ready"),
"dense_full_attention_mlo":OperatorContract("dense_full_attention_mlo","matrix_sfu_kv",True,"source_ready")}
Q38={
"gated_residual_read":OperatorContract("gated_residual_read","matrix_sfu",True,"e0_reference"),
"gated_residual_write":OperatorContract("gated_residual_write","sfu",True,"e0_reference"),
"group_rmsnorm":OperatorContract("group_rmsnorm","sfu",False,"e0_reference"),
"ple_ngram_hash":OperatorContract("ple_ngram_hash","control_memory",True,"e0_reference"),
"ple_sparse_row_fetch":OperatorContract("ple_sparse_row_fetch","memory",True,"analysis"),
"ple_projection_dwconv":OperatorContract("ple_projection_dwconv","matrix_state",True,"e0_reference"),
"qsa_index_projection":OperatorContract("qsa_index_projection","matrix",False,"e0_reference"),
"qsa_block_summary":OperatorContract("qsa_block_summary","state",True,"e0_reference"),
"qsa_streaming_topk":OperatorContract("qsa_streaming_topk","selection",True,"e0_reference"),
"qsa_sparse_kv_gather":OperatorContract("qsa_sparse_kv_gather","kv_memory",True,"e0_reference"),
"qsa_sparse_attention":OperatorContract("qsa_sparse_attention","matrix_sfu_kv",True,"e0_reference")}
ALL=COMMON|Q35|Q38

def load_profile(path):return json.loads(Path(path).read_text())
def _pattern(p,layers,special):
    assert len(p["layer_pattern"])==layers
    assert tuple(i for i,x in enumerate(p["layer_pattern"]) if x==special)==tuple(range(3,layers,4))
def validate(q35,q38):
    assert q35["model_id"]=="Qwen/Qwen3.5-35B-A3B" and q35["hf_model_type"]=="qwen3_5_moe" and q35["text_model_type"]=="qwen3_5_moe_text"
    assert q38["model_id"]=="Qwen/Qwen3.8-Flash-Next" and q38["hf_model_type"]=="qwen4_exp" and q38["text_model_type"]=="qwen4_exp_text"
    assert q35["architecture_family"]!=q38["architecture_family"] and not q38.get("is_qwen3_dense_architecture",True)
    _pattern(q35,40,"full_attention");_pattern(q38,48,"qwen_sparse_attention")
    assert not any(q35.get(x) for x in ("qsa","gated_residual","ple"))
    assert all(q38.get(x) for x in ("qsa","gated_residual","ple"))
def inventory(p):
    family=p["architecture_family"];ops=COMMON|(Q35 if family=="qwen3_5_hybrid_gdn_full_attention_moe" else Q38 if family=="qwen4_exp_flash_next" else {})
    return tuple(ops[n] for n in sorted(ops))
def states(p):
    base={"gdn_recurrent_matrix","gdn_causal_conv_history","moe_weight_cache_metadata","mtp_speculative_generation","runtime_sampler_state","attention_output_gate_state"}
    if p["architecture_family"]=="qwen3_5_hybrid_gdn_full_attention_moe":base.add("dense_kv_cache")
    else:base|={"qsa_kv_cache","qsa_raw_or_block_index_keys","qsa_selected_token_list","four_branch_hyper_residual","ple_token_history","ple_dilated_conv_history","ple_row_cache_metadata"}
    return tuple(sorted(base))
def layer_ops(p,i):
    family=p["architecture_family"];kind=p["layer_pattern"][i];out=[]
    if family=="qwen4_exp_flash_next" and i+1 in p["ple"]["layer_ids"]:out += ["ple_ngram_hash","ple_sparse_row_fetch","ple_projection_dwconv"]
    out += ["gated_residual_read","group_rmsnorm"] if family=="qwen4_exp_flash_next" else ["rmsnorm"]
    if kind in ("gated_deltanet","linear_attention"):out += ["gdn_projection","gdn_causal_conv","gdn_recurrent_update","gdn_gated_norm_output"]
    elif kind=="full_attention":out += ["dense_full_attention_qkv","partial_rope","dense_full_attention_mlo","attention_output_gate"]
    elif kind=="qwen_sparse_attention":out += ["qsa_index_projection","partial_rope","qsa_block_summary","qsa_streaming_topk","qsa_sparse_kv_gather","qsa_sparse_attention","attention_output_gate"]
    else:raise ValueError(kind)
    out += ["gated_residual_write","gated_residual_read","group_rmsnorm"] if family=="qwen4_exp_flash_next" else ["standard_residual_add","rmsnorm"]
    out += ["moe_router_topk","moe_routed_experts","moe_shared_expert","moe_route_reduce",("gated_residual_write" if family=="qwen4_exp_flash_next" else "standard_residual_add")]
    return tuple(out)
def schedule(p):
    out=[]
    for layer in range(p["num_hidden_layers"]):
        for op in layer_ops(p,layer):out.append({"op_id":len(out),"layer":layer,"layer_type":p["layer_pattern"][layer],"operator":op,"owner":ALL[op].owner})
    if p.get("mtp"):out.append({"op_id":len(out),"layer":p["num_hidden_layers"],"layer_type":"mtp","operator":"mtp_state_transaction","owner":"control_state"})
    return tuple(out)
def summary(p):
    ops=inventory(p);s=schedule(p)
    return {"model_id":p["model_id"],"architecture_family":p["architecture_family"],"hf_model_type":p["hf_model_type"],"text_model_type":p["text_model_type"],"layers":p["num_hidden_layers"],"layer_type_counts":dict(Counter(p["layer_pattern"])),"operator_count":len(ops),"schedule_ops":len(s),"schedule_operator_counts":dict(sorted(Counter(x["operator"] for x in s).items())),"state_domains":states(p),"hardware_owner_counts":dict(sorted(Counter(x["owner"] for x in s).items())),"sandbox_ready":tuple(sorted(x.name for x in ops if x.support in {"rtl_primitive","source_ready","e0_reference"})),"local_only":tuple(sorted(x.name for x in ops if x.support in {"analysis","unsupported_project_scope"}))}
def family_contract_report(q35_path,q38_path):
    a=load_profile(q35_path);b=load_profile(q38_path);validate(a,b);sa=summary(a);sb=summary(b);oa={x.name for x in inventory(a)};ob={x.name for x in inventory(b)}
    payload={"qwen3_5_35b_a3b":sa,"qwen3_8_flash_next":sb,"common_operators":tuple(sorted(oa&ob)),"qwen3_5_only":tuple(sorted(oa-ob)),"qwen3_8_flash_next_only":tuple(sorted(ob-oa)),"architecture_decision":{"shareable_engines":["matrix_projection_and_grouped_expert_array","fixed_norm_rope_gate_sfu","gdn_recurrent_state_engine","mtp_transaction_manager"],"qwen3_5_specific":["dense_full_attention_path","standard_single_residual_stream"],"qwen3_8_flash_next_specific":["qsa_selection_and_sparse_gather_engine","four_branch_gated_residual_datapath","ple_sparse_row_fetch_and_conv_state","larger_512_expert_top10_weight_scheduler"],"forbidden_conflation":["Do not classify Qwen3.8-Flash-Next as Qwen3 dense or Qwen3-8B.","Do not add QSA, PLE or four-branch gated residual to Qwen3.5.","Do not use dense full-attention service curves for QSA index scan and sparse gather."]},"sandbox_next":{"qwen3_5":["tiny executable 3xGDN+1xfull-attention+MoE group E0","GDN recurrent/chunk parity at official head geometry","dense full-attention output-gate vectors","40-layer shape/liveness/descriptor schedule","MoE top8 batching/cache DSE"],"qwen3_8_flash_next":["QSA block-summary/top512 vectors","PLE row-fetch/cache model","four-branch residual liveness","48-layer state transaction trace","512-expert top10 batching/cache DSE"],"shared":["policy lowering without model-name conditionals","official trace schema/replayer","quantized grouped expert scheduling","state commit/rollback vectors"]}}
    return {"schema_version":1,"status":"PASS","evidence_class":"official_config_architecture_contract_E0_not_official_weight_or_RTL_execution",**payload,"sha256":hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":")).encode()).hexdigest()}
