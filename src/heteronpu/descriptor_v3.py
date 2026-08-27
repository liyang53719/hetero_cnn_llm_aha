"""128-bit descriptor-v3 extension records and capability separation."""
from __future__ import annotations
from dataclasses import dataclass
from enum import IntEnum
NULL_INDEX=0xFFFFFF
class RecordType(IntEnum):
    SHAPE2_32=0x04; ATTENTION_OP=0x13; MOE_POLICY=0x14; DELTA_POLICY=0x15
    QSA_POLICY=0x16; GATED_RESIDUAL_POLICY=0x17; PLE_POLICY=0x18; MTP_POLICY=0x19
    KV_CONTEXT32=0x32; KV_RANGE32=0x33; KV_TABLE=0x34; KV_EPOCH32=0x35
class CompletionStatus(IntEnum): OK=0; UNSUPPORTED_POLICY=4
@dataclass(frozen=True)
class DescriptorRecord:
    record_type:int; subtype:int=0; flags:int=0; next_index:int=NULL_INDEX; payload:int=0
    def pack(self):
        for n,v,w in [('type',self.record_type,8),('subtype',self.subtype,8),('flags',self.flags,16),('next',self.next_index,24),('payload',self.payload,72)]:
            if not 0<=int(v)<1<<w:raise ValueError(n)
        return self.record_type|(self.subtype<<8)|(self.flags<<16)|(self.next_index<<32)|(self.payload<<56)
    def to_bytes(self):return self.pack().to_bytes(16,'little')
    @classmethod
    def unpack(cls,x):
        if isinstance(x,bytes):
            if len(x)!=16:raise ValueError('length')
            x=int.from_bytes(x,'little')
        return cls(x&255,(x>>8)&255,(x>>16)&65535,(x>>32)&0xffffff,(x>>56)&((1<<72)-1))
def _p(fields):
    x=o=0
    for n,v,w in fields:
        if not 0<=int(v)<1<<w:raise ValueError(n)
        x|=int(v)<<o;o+=w
    if o!=72:raise AssertionError(o)
    return x
def _r(t,fields,next_index=NULL_INDEX):return DescriptorRecord(t,next_index=next_index,payload=_p(fields))
def shape2_32(a,b,*,next_index=NULL_INDEX):return _r(RecordType.SHAPE2_32,[('dim0',a,32),('dim1',b,32),('r',0,8)],next_index)
def attention_op(*,q_heads,kv_heads,head_dim,rotary_dim,block_tokens=128,next_index=NULL_INDEX):return _r(RecordType.ATTENTION_OP,[('backend',1,3),('flags',0,5),('block',block_tokens,10),('qh',q_heads,10),('kh',kv_heads,10),('hd',head_dim,10),('rd',rotary_dim,10),('qt',4,4),('kt',5,4),('r',0,6)],next_index)
def moe_policy(*,num_experts,top_k,shared_experts,intermediate_size,next_index=NULL_INDEX):return _r(RecordType.MOE_POLICY,[('e',num_experts,10),('k',top_k,6),('s',shared_experts,4),('i',intermediate_size,16),('wf',2,4),('g',16,8),('f',0,8),('r',0,16)],next_index)
def delta_policy(*,qk_heads,v_heads,key_dim,value_dim,conv_kernel,chunk_size=64,next_index=NULL_INDEX):return _r(RecordType.DELTA_POLICY,[('qh',qk_heads,10),('vh',v_heads,10),('kd',key_dim,10),('vd',value_dim,10),('c',conv_kernel,5),('dt',5,4),('f',0,7),('ch',chunk_size,8),('r',0,8)],next_index)
def qsa_policy(*,index_q_heads,index_kv_heads,index_head_dim,token_budget,compress_ratio,next_index=NULL_INDEX):return _r(RecordType.QSA_POLICY,[('qh',index_q_heads,6),('kh',index_kv_heads,4),('hd',index_head_dim,10),('b',token_budget,16),('cr',compress_ratio,8),('f',0,8),('r',0,20)],next_index)
def gated_residual_policy(*,branch_count,hidden_size,lowrank,norm_group_size,next_index=NULL_INDEX):return _r(RecordType.GATED_RESIDUAL_POLICY,[('b',branch_count,4),('h',hidden_size,16),('l',lowrank,16),('n',norm_group_size,16),('a',0,4),('f',0,8),('r',0,8)],next_index)
def ple_policy(*,ngram_size,heads_per_ngram,embed_dim,conv_kernel,conv_dilation,embedding_table_index=0,next_index=NULL_INDEX):return _r(RecordType.PLE_POLICY,[('n',ngram_size,4),('h',heads_per_ngram,8),('e',embed_dim,16),('k',conv_kernel,8),('d',conv_dilation,8),('t',embedding_table_index,24),('f',0,4)],next_index)
def mtp_policy(*,layers,prediction_steps,hidden_size,vocab_size,next_index=NULL_INDEX):return _r(RecordType.MTP_POLICY,[('l',layers,8),('p',prediction_steps,8),('h',hidden_size,16),('v',vocab_size,24),('f',0,8),('r',0,8)],next_index)
def kv_context32(*,sequence_id,layer_id,kv_head_id,next_index=NULL_INDEX):return _r(RecordType.KV_CONTEXT32,[('s',sequence_id,32),('l',layer_id,12),('h',kv_head_id,12),('f',0,8),('r',0,8)],next_index)
def kv_range32(*,token_start,token_count,next_index=NULL_INDEX):return _r(RecordType.KV_RANGE32,[('s',token_start,32),('c',token_count,32),('f',0,8)],next_index)
def kv_table(*,page_table_tensor_index,physical_page_limit,next_index=NULL_INDEX):return _r(RecordType.KV_TABLE,[('t',page_table_tensor_index,24),('p',physical_page_limit,24),('id',32,6),('lv',2,3),('pt',4,5),('pb',4,4),('f',0,6)],next_index)
def kv_epoch32(*,generation,logical_page_count,next_index=NULL_INDEX):return _r(RecordType.KV_EPOCH32,[('g',generation,32),('c',logical_page_count,32),('f',0,8)],next_index)
_LAYOUT={0x04:[('dim0',32),('dim1',32),('reserved',8)],0x13:[('backend',3),('policy_flags',5),('block_tokens',10),('q_heads',10),('kv_heads',10),('head_dim',10),('rotary_dim',10),('query_tile_log2',4),('key_tile_log2',4),('reserved',6)],0x14:[('num_experts',10),('top_k',6),('shared_experts',4),('intermediate_size',16),('weight_format',4),('expert_group_size',8),('router_flags',8),('reserved',16)],0x15:[('qk_heads',10),('v_heads',10),('key_dim',10),('value_dim',10),('conv_kernel',5),('state_dtype',4),('policy_flags',7),('chunk_size',8),('reserved',8)],0x16:[('index_q_heads',6),('index_kv_heads',4),('index_head_dim',10),('token_budget',16),('compress_ratio',8),('qsa_flags',8),('reserved',20)],0x17:[('branch_count',4),('hidden_size',16),('lowrank',16),('norm_group_size',16),('gate_activation',4),('gr_flags',8),('reserved',8)],0x18:[('ngram_size',4),('heads_per_ngram',8),('embed_dim',16),('conv_kernel',8),('conv_dilation',8),('embedding_table_index',24),('ple_flags',4)],0x19:[('layers',8),('prediction_steps',8),('hidden_size',16),('vocab_size',24),('mtp_flags',8),('reserved',8)],0x32:[('sequence_id',32),('layer_id',12),('kv_head_id',12),('context_flags',8),('reserved',8)],0x33:[('token_start',32),('token_count',32),('range_flags',8)],0x34:[('page_table_tensor_index',24),('physical_page_limit',24),('page_id_bits',6),('levels',3),('page_tokens_log2',5),('pte_bytes_log2',4),('table_flags',6)],0x35:[('generation',32),('logical_page_count',32),('epoch_flags',8)]}
def decode(record):
    if not isinstance(record,DescriptorRecord):record=DescriptorRecord.unpack(record)
    layout=_LAYOUT.get(int(record.record_type));
    if layout is None:raise ValueError('type')
    out={};o=0
    for n,w in layout:out[n]=(record.payload>>o)&((1<<w)-1);o+=w
    out.update(record_type=int(record.record_type),subtype=record.subtype,flags=record.flags,next_index=record.next_index);return out
def rtl_capability(t):
    rec=int(t) in {int(x) for x in RecordType}; exe=int(t) in {0x04,0x32,0x33,0x34,0x35}
    return rec,exe,CompletionStatus.OK if exe else CompletionStatus.UNSUPPORTED_POLICY
