"""Versioned GGML-node capture ABI adapter into the model-agnostic graph IR."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib,json
from typing import Iterable,Mapping
from .graph_partition import Graph,GraphNode
DTYPE={'F32':'fp32','F16':'fp16','BF16':'bf16','I8':'int8','Q8_0':'q8_0','Q6_K':'q6_k','Q3_K':'q3_k','Q4_0':'w4a8'}
GENERIC={'GGML_OP_RMS_NORM':'rmsnorm','GGML_OP_ROPE':'rope','GGML_OP_TOP_K':'topk','GGML_OP_SOFT_MAX':'online_softmax','GGML_OP_SILU':'silu','GGML_OP_MUL':'elementwise_mul','GGML_OP_ADD':'add','GGML_OP_GET_ROWS':'embedding_gather','GGML_OP_MUL_MAT':'matrix_projection'}
SEMANTIC={'projection':'matrix_projection','qk':'matrix_qk','pv':'matrix_pv','gate_up':'matrix_gate_up','down':'matrix_down','silu_mul':'silu_mul','qsa_index':'qsa_index','kv_gather':'kv_gather','output_gate':'output_gate','group_rmsnorm':'group_rmsnorm','low_rank_down':'low_rank_down','low_rank_up':'low_rank_up','branch_mix':'branch_mix','ngram_hash':'ngram_hash','ple_projection':'ple_projection','dilated_dwconv':'dilated_dwconv','router':'router','grouped_expert_gemm':'grouped_expert_gemm','shared_expert':'shared_expert','route_reduce':'route_reduce','gdn_projection':'gdn_projection','causal_conv':'causal_conv','gdn_state_update':'gdn_state_update','gated_norm':'gated_norm','matrix_out':'matrix_out','online_softmax':'online_softmax'}
@dataclass(frozen=True)
class GGMLTensorView:
    tensor_id:str;name:str;dtype:str;shape:tuple[int,...];strides:tuple[int,...];storage:str='host';gguf_name:str|None=None
    def __post_init__(self):
        if not self.tensor_id or not self.name or not self.shape or len(self.shape)!=len(self.strides):raise ValueError('tensor')
    @property
    def normalized_dtype(self):return DTYPE.get(self.dtype.upper(),self.dtype.lower())
@dataclass(frozen=True)
class GGMLNodeView:
    node_id:str;op:str;input_tensors:tuple[str,...];output:GGMLTensorView;semantic:str|None=None;op_params_hex:str='';attrs:tuple[tuple[str,str|int|float|bool],...]=()
    def __post_init__(self):
        if not self.node_id or not self.op:raise ValueError('node')
        if self.op_params_hex:bytes.fromhex(self.op_params_hex)
@dataclass(frozen=True)
class AdapterResult:graph:Graph;tensor_producers:Mapping[str,str];unsupported_nodes:tuple[str,...];sha256:str
class GGMLNodeAdapter:
    def __init__(self,semantic_map=SEMANTIC,generic_map=GENERIC):self.semantic_map=dict(semantic_map);self.generic_map=dict(generic_map)
    def canonical_op(self,n):
        if n.semantic is not None:return self.semantic_map.get(n.semantic,f'unsupported_semantic:{n.semantic}')
        return self.generic_map.get(n.op.upper(),f'unsupported_op:{n.op.lower()}')
    def adapt(self,nodes:Iterable[GGMLNodeView])->AdapterResult:
        producer={};out=[];unsupported=[];node_ids=set()
        for n in nodes:
            if n.node_id in node_ids:raise ValueError('duplicate node')
            node_ids.add(n.node_id);inputs=[]
            for tid in n.input_tensors:
                if tid not in producer:raise ValueError(f'no producer:{tid}')
                inputs.append(producer[tid])
            op=self.canonical_op(n)
            if op.startswith('unsupported_'):unsupported.append(n.node_id)
            attrs=dict(n.attrs);attrs.update({'ggml_op':n.op,'semantic':n.semantic or '','output_tensor':n.output.tensor_id,'output_storage':n.output.storage,'gguf_name':n.output.gguf_name or '','op_params_hex':n.op_params_hex})
            out.append(GraphNode(n.node_id,op,tuple(inputs),n.output.normalized_dtype,n.output.shape,tuple(sorted(attrs.items()))))
            if n.output.tensor_id in producer:raise ValueError('duplicate tensor producer')
            producer[n.output.tensor_id]=n.node_id
        graph=Graph(out);payload=json.dumps([{'id':n.node_id,'op':n.op,'inputs':n.inputs,'dtype':n.dtype,'shape':n.shape,'attrs':n.attrs} for n in graph.nodes],sort_keys=True,separators=(',',':')).encode()
        return AdapterResult(graph,producer,tuple(unsupported),hashlib.sha256(payload).hexdigest())
def _tensor(i,dtype='BF16',shape=(1,128)):
    s=[];v=1
    for d in reversed(shape):s.append(v);v*=d
    return GGMLTensorView(i,i,dtype,shape,tuple(reversed(s)))
def adapter_contract_report():
    nodes=(GGMLNodeView('input','GGML_OP_NONE',(),_tensor('t0'),semantic='projection'),GGMLNodeView('qk','GGML_OP_MUL_MAT',('t0',),_tensor('t1'),semantic='qk'),GGMLNodeView('softmax','GGML_OP_SOFT_MAX',('t1',),_tensor('t2'),semantic='online_softmax',attrs=(('block_tokens',128),)),GGMLNodeView('pv','GGML_OP_MUL_MAT',('t2',),_tensor('t3'),semantic='pv'),GGMLNodeView('vision','GGML_OP_CONV_2D',('t3',),_tensor('t4')))
    a=GGMLNodeAdapter();x=a.adapt(nodes);y=a.adapt(nodes)
    if x.sha256!=y.sha256 or x.unsupported_nodes!=('vision',):raise AssertionError('adapter')
    return {'schema_version':1,'status':'PASS','evidence_class':'GGML_node_adapter_interface_E0_not_linked_llama_cpp_backend','nodes':len(x.graph.nodes),'unsupported_nodes':list(x.unsupported_nodes),'sha256':x.sha256,'contract':{'model_name_conditionals':False,'topological_tensor_producer_validation':True,'semantic_tags_are_versioned_capture_ABI':True,'unknown_ops_remain_explicit_fallback':True,'GGUF_tensor_name_retained':True},'remaining_local_gates':['real_llama_cpp_GGML_node_capture','op_parameter_decoder_parity','GGUF_tensor_binding','GraphPartitioner_real_graph_regression']}
