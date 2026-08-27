"""Compact v6 planning/compiler/cycle reference.

This module is deliberately E0: it validates Archspec collateral, expands the
48-layer Qwen3.8 text graph, emits a deterministic mock backend program, audits
the control plane, and models paged-state address translation.  It does not
claim official-weight execution, RTL E1, integrated E3, or physical E4.
"""
from __future__ import annotations
from collections import OrderedDict
from copy import deepcopy
import hashlib,json,math,re
from pathlib import Path
from typing import Any,Mapping
import yaml
from .qwen38_budget import Qwen38Shape,fixed_mac_breakdown,format_bytes,qsa_dynamic_macs,selected_tokens_for_visible_length

REPLACE={('memory','owners')}
def _merge(a:Any,b:Any,p:tuple[str,...]=())->Any:
    if p in REPLACE:return deepcopy(b)
    if isinstance(a,Mapping) and isinstance(b,Mapping):
        o={str(k):deepcopy(v) for k,v in a.items()}
        for k,v in b.items():k=str(k);o[k]=_merge(o[k],v,p+(k,)) if k in o else deepcopy(v)
        return o
    return deepcopy(b)
def _digest(x:Any)->str:return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def load_arch(path:str|Path,root:str|Path)->dict[str,Any]:
    root=Path(root);path=Path(path);path=path if path.is_absolute() else root/path
    raw=yaml.safe_load(path.read_text());base={}
    if raw.get('inherits'):base=load_arch(raw['inherits'],root)
    out=_merge(base,{k:v for k,v in raw.items() if k!='inherits'})
    if raw.get('inherits'):out['resolved_inherits']=[raw['inherits']]
    validate_arch(out);return out
def validate_arch(a:dict[str,Any])->None:
    if a.get('schema_version')!=1:raise ValueError('arch schema')
    m=a.get('memory',{});owners=m.get('owners',{});total=sum(int(v.get('kib',0)) for v in owners.values())
    if total!=int(m.get('total_sram_kib',0)) or total<=0:raise ValueError('SRAM budget')
    if int(a.get('clock',{}).get('target_hz',0))<=0:raise ValueError('clock')
    topo=a.get('aha_sidecar',{}).get('upstream_topology')
    if topo and int(topo['width'])*int(topo['height'])!=int(topo['pe_tiles'])+int(topo['lake_tiles']):raise ValueError('AHA topology')
    ctopo=owners.get('aha_sidecar',{}).get('topology')
    if ctopo and not re.fullmatch(r'\d+x\d+_ratio\d+',str(ctopo)):raise ValueError('candidate topology')
    if 'candidate' in str(a.get('status')) and not a.get('promotion_gates'):raise ValueError('promotion gates')
def arch_collateral(a:dict[str,Any])->dict[str,Any]:
    validate_arch(a);off=0;entries=[]
    for name,v in a['memory']['owners'].items():
        off=(off+4095)&~4095;size=int(v['kib'])*1024;entries.append({'owner':name,'base':off,'bytes':size,'limit':off+size});off+=size
    total=int(a['memory']['total_sram_kib'])*1024
    if off!=total:raise ValueError('map size')
    modes=set(a.get('matrix',{}).get('quantization',{}).get('modes',[]));modes.update(a.get('matrix_candidates',{}).get('required_modes',[]))
    return {'schema_version':1,'arch_id':a['arch_id'],'archspec_sha256':_digest(a),'sram_map':entries,'total_sram_bytes':total,'matrix_modes':sorted(modes),'sfu':sorted(a.get('fixed_sfu',{}).get('operators',[])),'sequence_memory':sorted(a.get('sequence_memory_complex',{})),'promotion_gates':a.get('promotion_gates',[]),'status':a['status']}
def render_arch_sv(c:dict[str,Any])->str:
    lines=['// Generated from Archspec v6.','package heteronpu_arch_pkg;',f"  localparam longint unsigned ARCHSPEC_SHA64 = 64'h{c['archspec_sha256'][:16]};",f"  localparam int unsigned TOTAL_SRAM_BYTES = {c['total_sram_bytes']};"]
    for x in c['sram_map']:
        n=re.sub('[^A-Za-z0-9_]','_',x['owner']).upper();lines+= [f"  localparam int unsigned SRAM_{n}_BASE = {x['base']};",f"  localparam int unsigned SRAM_{n}_BYTES = {x['bytes']};"]
    return '\n'.join(lines+['endpackage',''])

def _shape(p:dict[str,Any])->Qwen38Shape:
    l=tuple(p['layer_pattern']);g=p['gated_deltanet'];a=p['full_attention'];q=p['qsa'];m=p['moe'];r=p['gated_residual'];e=p['ple']
    return Qwen38Shape(hidden_size=p['hidden_size'],layers=len(l),gdn_layers=l.count('linear_attention'),qsa_layers=l.count('qwen_sparse_attention'),vocab_size=p['vocab_size'],residual_branches=r['branches'],residual_lowrank=r['lowrank'],q_heads=a['q_heads'],kv_heads=a['kv_heads'],head_dim=a['head_dim'],index_query_heads=q['index_q_heads'],index_kv_heads=q['index_kv_heads'],index_head_dim=q['index_head_dim'],index_compress_ratio=q['compress_ratio'],index_token_budget=q['token_budget'],gdn_qk_heads=g['qk_heads'],gdn_v_heads=g['v_heads'],gdn_key_dim=g['key_dim'],gdn_value_dim=g['value_dim'],gdn_conv_kernel=g['conv_kernel'],experts=m['num_experts'],active_routed_experts=m['top_k'],shared_experts=m.get('shared_experts',0),expert_intermediate=m['intermediate_size'],ple_layers=len(e['layer_ids']),ple_embed_dim=e['embed_dim'],ple_ngram_heads=e['heads_per_ngram']*2,ple_conv_kernel=e['conv_kernel'])
def build_qwen38_program(profile:dict[str,Any],mode:str='prefill',seq:int=1024,context:int|None=None,weight_bits:int=4)->dict[str,Any]:
    if profile.get('model_id')!='Qwen/Qwen3.8-Flash-Next':raise ValueError('profile')
    if mode not in {'prefill','decode'} or seq<=0 or (mode=='decode' and seq!=1):raise ValueError('mode')
    context=seq if context is None else context;s=_shape(profile);f=fixed_mac_breakdown(s);layers=tuple(profile['layer_pattern']);ple={int(x)-1 for x in profile['ple']['layer_ids']}
    if len(layers)!=48 or layers.count('linear_attention')!=36 or layers.count('qwen_sparse_attention')!=12:raise ValueError('layers')
    d=qsa_dynamic_macs(s,seq) if mode=='prefill' else None
    idx=(d['index_macs']//s.qsa_layers) if d else context//s.index_compress_ratio*s.index_query_heads*s.index_head_dim
    sparse=(d['sparse_qk_pv_macs']//s.qsa_layers) if d else selected_tokens_for_visible_length(context,s.index_compress_ratio,s.index_token_budget)*2*s.q_heads*s.head_dim
    gdn_in=f['gdn_projection_per_layer']-s.gdn_v_width*s.hidden_size;qidx=s.hidden_size*(s.index_query_heads+s.index_kv_heads)*s.index_head_dim;qqkv=s.hidden_size*(2*s.q_width+2*s.kv_width);qout=s.q_width*s.hidden_size;expert=(s.active_routed_experts+s.shared_experts)*f['moe_one_expert_per_layer']
    ops=[]
    def add(layer:int,name:str,engine:str,macs:int=0,weights:int=0,state:str|None=None,policy:str|None=None):
        i=len(ops);ops.append({'op_id':i,'layer':layer,'name':name,'engine':engine,'depends_on':[] if i==0 else [i-1],'macs':int(macs),'compulsory_weight_bytes':format_bytes(int(weights),weight_bits) if weights else 0,'state_domain':state,'policy_record':policy,'rtl_status':'UNIMPLEMENTED_POLICY'});return i
    add(-1,'TOKEN_EMBED','sparse_row_memory',state='token_position')
    for i,t in enumerate(layers):
        if i in ple:add(i,'PLE_NGRAM_HASH_ROW_FETCH','sparse_row_memory',state='ple_history',policy='ple_policy');add(i,'PLE_KEY_VALUE_PROJECTION','matrix',f['ple_projection']*seq,f['ple_projection'],policy='ple_policy');add(i,'PLE_GATE_DILATED_DWCONV','sfu_state',f['ple_gate_and_conv']*seq,state='ple_conv',policy='ple_policy')
        add(i,'GR_ATTN_READ','matrix_sfu',f['gated_residual_per_sublayer']*seq,f['gated_residual_per_sublayer'],state='hyper_stream',policy='gated_residual_policy')
        if t=='linear_attention':
            add(i,'GDN_INPUT_PROJECTIONS','matrix',gdn_in*seq,gdn_in,policy='delta_policy');add(i,'GDN_CAUSAL_CONV_L2NORM_DECAY','sfu_state',f['gdn_causal_conv_per_layer']*seq,state='gdn_conv',policy='delta_policy');add(i,'GDN_RECURRENT_STATE_UPDATE_READOUT','matrix_state',(f['gdn_state_matrix_per_layer']+f['gdn_state_decay_per_layer'])*seq,state='gdn_recurrent',policy='delta_policy');add(i,'GDN_GATED_NORM_OUT_PROJ','matrix_sfu',s.gdn_v_width*s.hidden_size*seq,s.gdn_v_width*s.hidden_size,policy='delta_policy')
        else:
            add(i,'QSA_INDEX_PROJECTION_APPEND_SUMMARY','matrix_state',qidx*seq,qidx,state='qsa_index',policy='qsa_policy');add(i,'QSA_STREAM_SCAN_TOPK_PAGE_PLAN','qsa_selection',idx,state='qsa_index',policy='qsa_policy');add(i,'SPARSE_QKV_PROJECTION','matrix',qqkv*seq,qqkv,state='qsa_kv',policy='attention_op');add(i,'SPARSE_QK_BLOCK128_SOFTMAX_PV','matrix_sfu_kv',sparse,state='qsa_kv',policy='attention_op');add(i,'ATTENTION_OUTPUT_GATE_PROJECTION','matrix_sfu',qout*seq,qout,policy='attention_op')
        add(i,'GR_ATTN_WRITE','sfu',state='hyper_stream',policy='gated_residual_policy');add(i,'GR_MOE_READ','matrix_sfu',f['gated_residual_per_sublayer']*seq,f['gated_residual_per_sublayer'],state='hyper_stream',policy='gated_residual_policy');add(i,'MOE_ROUTER_TOPK_BATCH','sfu_weight_cache',f['moe_router_per_layer']*seq,f['moe_router_per_layer'],state='expert_cache_metadata',policy='moe_policy');add(i,'MOE_GROUPED_ROUTED_SHARED_EXPERTS','matrix_weight_cache',expert*seq,expert,state='expert_cache_metadata',policy='moe_policy');add(i,'GR_MOE_WRITE','sfu',state='hyper_stream',policy='gated_residual_policy')
    add(48,'FINAL_HYPER_MERGE_RMSNORM','matrix_sfu',f['final_hyper_mixer']*seq,f['final_hyper_mixer'],state='hyper_stream',policy='gated_residual_policy');add(48,'MTP_DRAFT_STATE_EPOCH_BEGIN','state_control',state='all_sequence_state',policy='mtp_policy');add(48,'MTP_TARGET_VERIFY','control',policy='mtp_policy');add(48,'MTP_ATOMIC_COMMIT_OR_ROLLBACK','state_control',state='all_sequence_state',policy='mtp_policy')
    expected=f['fixed_macs_per_token']*seq+(d['total_dynamic_macs'] if d else s.qsa_layers*(idx+sparse));actual=sum(x['macs'] for x in ops)
    if actual!=expected or len(ops)!=500:raise ValueError(f'program reconciliation {len(ops)} {actual} {expected}')
    out={'schema_version':1,'evidence_class':'full_shape_compiler_E0','model_id':profile['model_id'],'revision':profile['revision'],'mode':mode,'sequence_length':seq,'context_length':context,'weight_bits':weight_bits,'operations':ops,'operation_count':len(ops),'total_macs':actual,'total_weight_bytes':sum(x['compulsory_weight_bytes'] for x in ops)};out['program_sha256']=_digest(out);return out
CAP_SOURCE={'GDN_INPUT_PROJECTIONS','GDN_GATED_NORM_OUT_PROJ','SPARSE_QKV_PROJECTION','SPARSE_QK_BLOCK128_SOFTMAX_PV','ATTENTION_OUTPUT_GATE_PROJECTION','FINAL_HYPER_MERGE_RMSNORM'}
def compile_mock(program:dict[str,Any],macs_per_cycle:int=4096,read_bytes_per_cycle:int=100)->dict[str,Any]:
    cmds=[];segments=[];last=None
    for op in program['operations']:
        cap='source_ready_wait_e1_e4' if op['name'] in CAP_SOURCE else 'e0_only';cycles=max(1,math.ceil(op['macs']/macs_per_cycle) if op['macs'] else 1,math.ceil(op['compulsory_weight_bytes']/read_bytes_per_cycle) if op['compulsory_weight_bytes'] else 1);cmd={'command_id':op['op_id'],'op_id':op['op_id'],'name':op['name'],'engine':op['engine'],'event_wait':op['depends_on'],'event_signal':op['op_id']+1,'capability':cap,'estimated_cycles':cycles};cmds.append(cmd)
        key=cap
        if last!=key:segments.append({'segment_id':len(segments),'target':'npu_candidate','capability':cap,'command_ids':[]});last=key
        segments[-1]['command_ids'].append(op['op_id'])
    out={'schema_version':1,'evidence_class':'mock_backend_E0','source_program_sha256':program['program_sha256'],'commands':cmds,'segments':segments,'analytical_total_cycles':sum(x['estimated_cycles'] for x in cmds)};out['mock_sha256']=_digest(out);return out

class _LRU:
    def __init__(self,n:int):self.n=n;self.d=OrderedDict()
    def get(self,k):
        if k not in self.d:return None
        self.d.move_to_end(k);return self.d[k]
    def put(self,k,v):
        if k in self.d:self.d.move_to_end(k)
        elif len(self.d)>=self.n:self.d.popitem(last=False)
        self.d[k]=v
class SequenceMemory:
    def __init__(self,page_tokens:int=16,tlb_entries:int=64,leaf_entries:int=4,walk:int=120):self.pt=page_tokens;self.tlb=_LRU(tlb_entries);self.leaf=_LRU(leaf_entries);self.walk=walk;self.gen={};self.map={}
    def create(self,s:int,l:int,h:int,g:int):self.gen[(s,l,h)]=g
    def map_page(self,s:int,l:int,h:int,g:int,lp:int,pp:int):
        if self.gen.get((s,l,h))!=g:raise ValueError('stale generation')
        self.map[(s,l,h,g,lp)]=pp
    def translate(self,s:int,l:int,h:int,g:int,token:int)->dict[str,Any]:
        if self.gen.get((s,l,h))!=g:raise ValueError('stale generation')
        lp,off=divmod(token,self.pt);k=(s,l,h,g,lp);hit=self.tlb.get(k)
        if hit is not None:return {'physical_page':hit,'offset':off,'cycles':1,'path':'tlb_hit'}
        if k not in self.map:raise KeyError('unmapped')
        leaf=(s,l,h,g,lp>>10);path='leaf_cache_hit' if self.leaf.get(leaf) is not None else 'page_walk';cycles=8 if path=='leaf_cache_hit' else self.walk;pp=self.map[k];self.leaf.put(leaf,1);self.tlb.put(k,pp);return {'physical_page':pp,'offset':off,'cycles':cycles,'path':path}
    def cow_cycles(self,page_bytes:int=4096,bytes_per_cycle:int=64)->int:return math.ceil(page_bytes/bytes_per_cycle)

def audit_control(root:str|Path)->dict[str,Any]:
    r=Path(root);c=json.loads((r/'config/control_plane.json').read_text());s=yaml.safe_load((r/c['canonical_stages']).read_text());l=json.loads((r/c['ledger']).read_text());n=json.loads((r/c['next_action']).read_text());w=json.loads((r/c['local_waitlist']).read_text());errors=[];schema=c['schema_version']
    for name,d in [('stages',s),('ledger',l),('next',n),('waitlist',w)]:
        if d.get('schema_version')!=schema:errors.append(f'{name}:schema')
    ids=[x['id'] for x in s['stages']]
    if ids!=c['stage_namespace'] or c['current_stage'] not in ids:errors.append('stage namespace')
    if l.get('current_stage')!=c['current_stage'] or l.get('current_subgate')!=c['current_subgate'] or n.get('stage')!=c['current_stage'] or n.get('subgate')!=c['current_subgate']:errors.append('current state drift')
    e=c['retained_local_evidence']
    if e['block128_e1']!='PASS' or e['block128_wns_ns']<0 and e['block128_e4']!='FAIL_TIMING':errors.append('evidence claim')
    if any('sandbox_status' not in x or 'local_gate' not in x for x in w['items']):errors.append('waitlist split')
    if c['remote_audit'].get('new_local_agent_commit_detected') not in {True,False}:errors.append('remote audit')
    return {'schema_version':1,'status':'PASS' if not errors else 'FAIL','control_schema_version':schema,'errors':errors}
