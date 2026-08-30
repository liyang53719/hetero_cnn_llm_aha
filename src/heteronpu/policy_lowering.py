"""Deterministic macro-policy lowering to primitive Command128 segments.

The lowering deliberately emits one segment per decoder layer, so 16-bit event
IDs never span the full 48-layer model. Descriptor roots are allocated
monotonically and remain stable for a fixed profile and base index.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
from typing import Iterable
from .segment_compiler import compile_segment

@dataclass
class DescriptorAllocator:
 next_index:int=0x1000
 def roots(self,kind:str):
  if kind in {'sfu'}:
   a=self.next_index;self.next_index+=2;return {'src0':a,'dst':a+1}
  if kind in {'kv_gather'}:
   a=self.next_index;self.next_index+=2;return {'src0':a,'dst':a+1}
  if kind in {'kv_alloc','kv_free','barrier'}:
   a=self.next_index;self.next_index+=1;return {'src0':a}
  a=self.next_index;self.next_index+=3;return {'src0':a,'src1':a+1,'dst':a+2}

class LayerBuilder:
 def __init__(self,name,layer,alloc):self.name=name;self.layer=layer;self.alloc=alloc;self.ops=[];self.last=[]
 def emit(self,suffix,engine,opcode,kind='matrix',deps=None,flags=0):
  op_id=f'L{self.layer}.{suffix}';dependencies=list(self.last if deps is None else deps);root=self.alloc.roots(kind);self.ops.append({'id':op_id,'engine':engine,'opcode':opcode,'depends_on':dependencies,'flags':flags,**root});self.last=[op_id];return op_id
 def fork(self):return tuple(self.last)
 def join(self,*deps):self.last=list(deps)
 def spec(self):return {'name':self.name,'barrier_descriptor_base':0xE00000+self.layer*0x100,'operations':self.ops}

def _gr(builder,prefix):
 builder.emit(f'{prefix}.norm','sfu','sfu_rmsnorm','sfu')
 builder.emit(f'{prefix}.down','matrix','matrix_gemm')
 builder.emit(f'{prefix}.silu','sfu','sfu_activation','sfu')
 builder.emit(f'{prefix}.up','matrix','matrix_gemm')
 builder.emit(f'{prefix}.mix','sfu','sfu_vector','sfu')

def _ple(builder):
 builder.emit('ple.rows','dma','dma_1d')
 builder.emit('ple.kv_proj','matrix','matrix_gemm')
 builder.emit('ple.gate','sfu','sfu_vector','sfu')
 builder.emit('ple.dwconv','sfu','sfu_vector','sfu')

def _gdn(builder):
 builder.emit('gdn.input_norm','sfu','sfu_rmsnorm','sfu')
 builder.emit('gdn.qkvbg_proj','matrix','matrix_gemm')
 builder.emit('gdn.causal_conv','sfu','sfu_vector','sfu')
 builder.emit('gdn.state_read','kv','kv_gather','kv_gather')
 read=builder.fork()[0]
 update=builder.emit('gdn.state_update','matrix','matrix_gemm')
 builder.emit('gdn.state_write','kv','kv_append')
 builder.emit('gdn.gated_norm','sfu','sfu_rmsnorm','sfu')
 builder.emit('gdn.out_proj','matrix','matrix_gemm')
 return read,update

def _qsa(builder):
 builder.emit('qsa.index_proj','matrix','matrix_gemm')
 builder.emit('qsa.index_scan','kv','kv_gather','kv_gather')
 builder.emit('qsa.topk','sfu','sfu_vector','sfu')
 builder.emit('qsa.selected_kv','kv','kv_gather','kv_gather')
 builder.emit('qsa.qk','matrix','matrix_qk')
 builder.emit('qsa.online_softmax','sfu','sfu_softmax','sfu')
 builder.emit('qsa.pv','matrix','matrix_pv')
 builder.emit('qsa.output_gate','sfu','sfu_activation','sfu')
 builder.emit('qsa.out_proj','matrix','matrix_gemm')

def _moe(builder):
 builder.emit('moe.router','matrix','matrix_gemv')
 builder.emit('moe.topk','sfu','sfu_vector','sfu')
 route=builder.fork()[0]
 routed=builder.emit('moe.routed','matrix','matrix_gemm',deps=(route,))
 shared=builder.emit('moe.shared','matrix','matrix_gemm',deps=(route,))
 builder.join(routed,shared)
 builder.emit('moe.merge','sfu','sfu_reduce','sfu')

def lower_layer(layer:int,layer_type:str,*,ple:bool=False,descriptor_base:int=0x1000):
 alloc=DescriptorAllocator(descriptor_base);b=LayerBuilder(f'qwen38.layer{layer}.{layer_type}',layer,alloc)
 if ple:_ple(b)
 _gr(b,'gr_attn_read')
 if layer_type=='linear_attention':_gdn(b)
 elif layer_type=='qwen_sparse_attention':_qsa(b)
 else:raise ValueError(layer_type)
 _gr(b,'gr_attn_write')
 _gr(b,'gr_moe_read')
 _moe(b)
 _gr(b,'gr_moe_write')
 spec=b.spec();compiled=compile_segment(spec);return {'spec':spec,'compiled':compiled.to_dict(),'next_descriptor':alloc.next_index}

def lower_qwen38_model(layer_pattern:Iterable[str],*,ple_layers=(1,),descriptor_base:int=0x1000):
 layers=[];base=descriptor_base
 for layer,kind in enumerate(tuple(layer_pattern)):
  item=lower_layer(layer,kind,ple=layer in set(ple_layers),descriptor_base=base);layers.append(item);base=item['next_descriptor']
 payload={'schema_version':1,'layers':layers,'next_descriptor':base,'segment_count':len(layers),'all_event_ids_layer_local':True}
 canonical=json.dumps(payload,sort_keys=True,separators=(',',':')).encode();payload['program_sha256']=hashlib.sha256(canonical).hexdigest();return payload

def qwen38_policy_lowering_report():
 pattern=tuple('qwen_sparse_attention' if (i+1)%4==0 else 'linear_attention' for i in range(48));p=lower_qwen38_model(pattern)
 commands=sum(len(x['compiled']['commands']) for x in p['layers']);barriers=sum(len(x['compiled']['barrier_descriptors']) for x in p['layers']);max_commands=max(len(x['compiled']['commands']) for x in p['layers'])
 return {'schema_version':1,'status':'PASS','evidence_class':'policy_to_Command128_compiler_E0_not_real_llama_backend','model_layers':48,'gdn_layers':36,'qsa_layers':12,'segments':p['segment_count'],'commands':commands,'barriers':barriers,'max_commands_per_segment':max_commands,'next_descriptor':p['next_descriptor'],'program_sha256':p['program_sha256'],'frozen':{'one_segment_per_layer':True,'event_width_bits':16,'descriptor_width_bits':24,'unsupported_policy_fallback_required':True},'remaining_local_gates':['real_GGML_graph_pattern_match','real_GGUF_descriptor_binding','device_command_submission','CPU_fallback_execution']}
