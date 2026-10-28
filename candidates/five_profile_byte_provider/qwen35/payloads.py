"""Read-only checkpoint byte layouts. No block arithmetic or reference outputs."""
import hashlib, importlib.util, json, math
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
from parent_inputs import path_for_sha
FROZEN_METADATA_SHA256={'profile3_manifest': 'cfb844a82658e41dd7c6b3f81da3708a67da02b708c523ac199f920ac1764e7e', 'profile4_manifest': 'c2a9bdc1df689dcb33e9ddacb15bc9de738e27867ba5e486d76adcdfd9945bed', 'qwen35_source_weights': '783559cf4924129b6e450df1af64647c2233434561b4648489c7e052b230096a', 'qwen35_trig_binding': '788c72cb65c32c872fd19c0ee8a1f6b8dcc50ae52a985ab5fa38e6ed53eeb847', 'qwen35_expected_input': '86ad51be3fac1e462676ab3ab22c5b806fa5bb17b9b126e81ff68263740e30eb'}
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  while b:=f.read(4<<20):h.update(b)
 return h.hexdigest()
class Reader:
 def __init__(self,size,fn,binding): self.size=size;self.fn=fn;self.binding=binding
 def read(self,offset,length):
  if type(offset) is not int or type(length) is not int or offset<0 or length<0 or offset+length>self.size:raise ValueError('outside tensor')
  return self.fn(offset,length)
def direct(data,binding):
 return Reader(len(data),lambda o,n:data[o:o+n],binding)
def zero(size):return Reader(size,lambda o,n:bytes(n),{'kind':'cold_zero','bytes':size})
def array_reader(row,logical_dims,perm=None,slice_axis=None,slice_start=0,slice_count=None,pad_cols=None):
 item=2 if row['dtype']=='BF16' else 4; dtype='<u2' if item==2 else '<u4';shape=list(row['shape'])
 a=np.memmap(row['path'],mode='r',dtype=dtype,shape=tuple(shape)); view=a
 if slice_axis is not None:
  ss=[slice(None)]*len(shape);ss[slice_axis]=slice(slice_start,slice_start+slice_count);view=view[tuple(ss)]
 if perm is not None:view=view.transpose(perm)
 if pad_cols is None and math.prod(view.shape)!=math.prod(logical_dims):raise ValueError('shape mismatch')
 if pad_cols is None and tuple(view.shape)!=tuple(logical_dims):view=view.reshape(logical_dims)
 strides=[s//item for s in view.strides];base=(view.ctypes.data-a.ctypes.data)//item;flat=a.reshape(-1)
 target=tuple(logical_dims)
 def read(o,n):
  if not n:return b''
  first=o//item;last=(o+n+item-1)//item;idx=np.arange(first,last,dtype=np.int64)
  if pad_cols:
   k=idx//pad_cols;col=idx%pad_cols;v=np.zeros(len(idx),dtype=dtype);ok=col==0;v[ok]=flat[k[ok]]
  else:
   # Reshape only collapses contiguous trivial axes; ordinary mappings keep exact rank.
   coords=np.unravel_index(idx,view.shape);src=np.full(len(idx),base,dtype=np.int64)
   for c,s in zip(coords,strides):src+=c*s
   v=flat[src]
  raw=v.astype(dtype,copy=False).tobytes();return raw[o%item:o%item+n]
 binding={'kind':'checkpoint_layout','path':row['path'],'sha256':row['sha256'],'source_shape':shape,'source_dtype':row['dtype'],'logical_dims':logical_dims,'element_bytes':item,'permutation':perm,'slice_axis':slice_axis,'slice_start':slice_start,'slice_count':slice_count,'zero_padded_columns':pad_cols,'source_flat_element_offset':base,'source_element_strides':strides}
 return Reader(math.prod(target)*item,read,binding)
def build_readers(manifest_path):
 manifest_path=Path(manifest_path)
 for rel,digest in FROZEN_METADATA_SHA256.items():
  if sha(path_for_sha(digest))!=digest:raise ValueError('frozen metadata hash mismatch '+rel)
 manifest_digest=sha(manifest_path)
 accepted={FROZEN_METADATA_SHA256[f'profile{i}_manifest'] for i in (3,4)}
 if manifest_digest not in accepted:raise ValueError('unfrozen manifest')
 m=json.loads(manifest_path.read_text());p=m['launch']['profileId'];layer={3:0,4:3}.get(p)
 if layer is None or m['tokens']!=128:raise ValueError('only cold128 profiles3/4')
 records=json.loads(path_for_sha(FROZEN_METADATA_SHA256['qwen35_source_weights']).read_text());rows={r['name'].split(f'layers.{layer}.',1)[1]:r for r in records if f'layers.{layer}.' in r['name']}
 rows={k:dict(r,path=str(path_for_sha(r['sha256'],r['bytes']))) for k,r in rows.items()}
 for r in rows.values():
  if Path(r['path']).stat().st_size!=r['bytes'] or sha(r['path'])!=r['sha256']:raise ValueError('source hash mismatch '+r['name'])
 result={};bind={};t=m['tensors']
 def add(key,name,perm=None,**kw):result[key]=array_reader(rows[name],t[key]['dims'],perm,**kw)
 expected=json.loads(path_for_sha(FROZEN_METADATA_SHA256['qwen35_expected_input']).read_text());g=path_for_sha(expected['generator_sha256'])
 if sha(g)!=expected['generator_sha256']:raise ValueError('input generator pin')
 spec=importlib.util.spec_from_file_location('pinned35input',g);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);data=module.build()
 if len(data)!=expected['bytes'] or hashlib.sha256(data).hexdigest()!=expected['sha256']:raise ValueError('input identity')
 result['input']=direct(data,{'kind':'pinned_experimental_input','generator':str(g),'generator_sha256':sha(g),'sha256':expected['sha256'],'bytes':len(data),'not_upstream_hidden_state':True})
 add('input_gamma','input_layernorm.weight');add('post_gamma','post_attention_layernorm.weight')
 for i,name in [(0,'gate.weight'),(4,'shared_expert.gate_proj.weight'),(5,'shared_expert.up_proj.weight'),(6,'shared_expert.down_proj.weight'),(7,'shared_expert_gate.weight')]:add(f'moe_weight_{i}','mlp.'+name,(1,0))
 add('moe_weight_1','mlp.experts.gate_up_proj',(0,2,1),slice_axis=1,slice_start=0,slice_count=512)
 add('moe_weight_2','mlp.experts.gate_up_proj',(0,2,1),slice_axis=1,slice_start=512,slice_count=512)
 add('moe_weight_3','mlp.experts.down_proj',(0,2,1))
 add('moe_shared_gate_padded','mlp.shared_expert_gate.weight',pad_cols=32)
 if p==3:
  for key,name in [('qkv_weight','in_proj_qkv.weight'),('z_weight','in_proj_z.weight'),('o_weight','out_proj.weight')]:add(key,'linear_attn.'+name,(1,0))
  for key,name in [('conv_weight','conv1d.weight'),('a_log','A_log'),('dt_bias','dt_bias'),('gated_gamma','norm.weight')]:add(key,'linear_attn.'+name)
  ra=array_reader(rows['linear_attn.in_proj_a.weight'],[2048,32],(1,0));rb=array_reader(rows['linear_attn.in_proj_b.weight'],[2048,32],(1,0))
  def read_ab(o,n):
   # [K, aHeads32 then bHeads32], not concatenated full matrices.
   out=bytearray()
   while n:
    row,col=divmod(o,128);take=min(n,64-col if col<64 else 128-col);src=ra if col<64 else rb;out+=src.read(row*64+col%64,take);o+=take;n-=take
   return bytes(out)
  result['ab_weight']=Reader(t['ab_weight']['bytes'],read_ab,{'kind':'row_concat','axis':1,'parts':[ra.binding,rb.binding],'part_row_bytes':64})
  result['history_in']=zero(t['history_in']['bytes']);result['state_in']=zero(t['state_in']['bytes'])
 else:
  for key,name in [('q_weight','q_proj.weight'),('k_weight','k_proj.weight'),('v_weight','v_proj.weight'),('o_weight','o_proj.weight')]:add(key,'self_attn.'+name,(1,0))
  add('q_gamma','self_attn.q_norm.weight');add('k_gamma','self_attn.k_norm.weight')
  coeff=path_for_sha(FROZEN_METADATA_SHA256['qwen35_trig_binding'])
  if not coeff.exists():raise RuntimeError('pinned official RoPE coefficient generation pending')
  c=json.loads(coeff.read_text());raw=path_for_sha(c['sha256']).read_bytes()
  if hashlib.sha256(raw).hexdigest()!=c['sha256'] or len(raw)!=t['trig']['bytes']:raise ValueError('trig pin')
  result['trig']=direct(raw,c)
 required={k for k,v in t.items() if v['readonly']}
 if set(result)!=required:raise ValueError(('RO coverage',required-set(result),set(result)-required))
 for k,r in result.items():
  if r.size!=t[k]['bytes']:raise ValueError('byte size '+k)
 return result,{'status':'BYTE_LAYOUT_ONLY_NOT_DUT_NUMERICAL','profile':p,'manifest':str(manifest_path.resolve()),'manifest_sha256':sha(manifest_path),'sources_current_hash_verified':len(rows),'bindings':{k:r.binding for k,r in result.items()},'reference_output_or_expert_id_injection':False}
