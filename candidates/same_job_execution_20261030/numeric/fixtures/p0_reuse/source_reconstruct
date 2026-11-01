"""Offline, stdlib-only reconstruction from original metadata, never tensor values."""
from pathlib import Path
import hashlib,json,math
HERE=Path(__file__).resolve().parent
PINS={'qwen2_1p5b':('Qwen/Qwen2-1.5B-Instruct','ba1cf1846d7df0a0591d6c00649f57e798519da8','46818a6fde79b4bff4615abc38cca7d8cb9386cdd0298bc07c403cb3d2ceab25'),'qwen3_5_0p8b':('Qwen/Qwen3.5-0.8B','2fc06364715b967f1860aea9cf38778875588b17','b10d1c78df5ef0e5535cb4eb04b45f73ef935e0867a21f3a48dd98e5a89afca5'),'qwen3_5_35b_a3b':('Qwen/Qwen3.5-35B-A3B','62704185bd97ad488cfc404e7caea797396b74dc','ca44aa87cfedd5d302b62c02d77ce64624009998edb78fe0bd025c42beaa4c8e')}
PIN_HASH={0:'80352cc5df45472a8867a4e1d346f60dc888e6f89ee191ec35457b484770d9c4',3:'ab9735a92f3b3377737288621019bccd855a5696bd4d02b2d8257cbf24a5b0ac'}
def need(v,s):
 if not v:raise ValueError(s)
def sha(b):return hashlib.sha256(b).hexdigest()
def same(a,b):return json.dumps(a,sort_keys=True,allow_nan=False)==json.dumps(b,sort_keys=True,allow_nan=False)
def unique(items):
 d={}
 for k,v in items:
  need(k not in d,'duplicate JSON key');d[k]=v
 return d
def load(raw):return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda v:(_ for _ in ()).throw(ValueError('nonfinite JSON')))
def checked_path(root,name):
 p=Path(name);need(not p.is_absolute() and '..' not in p.parts and '\\' not in name,'unsafe relative metadata path');q=(root/p).resolve();need(q.is_relative_to(root.resolve()),'escaped metadata path');return q
def decode(raw,total):
 need(8<len(raw)<=16*1024*1024+8 and int.from_bytes(raw[:8],'little')==len(raw)-8,'header prefix')
 h=load(raw[8:]);meta=h.pop('__metadata__',{});need(isinstance(meta,dict),'header metadata')
 spans=[];width={'BF16':2,'F32':4,'F16':2,'I64':8,'I32':4,'F8_E4M3':1}
 for name,t in h.items():
  need(set(t)=={'shape','dtype','data_offsets'},'tensor header fields')
  shape=t['shape'];off=t['data_offsets'];need(isinstance(shape,list) and all(type(x)is int and x>=0 for x in shape),'shape type')
  need(isinstance(off,list) and len(off)==2 and all(type(x)is int and x>=0 for x in off),'offset type')
  lo,hi=off;need(t['dtype'] in width and hi-lo==math.prod(shape)*width[t['dtype']] and hi<=total-len(raw),'tensor geometry');spans.append((lo,hi))
 cur=0
 for lo,hi in sorted(spans):need(lo==cur,'header gap/overlap');cur=hi
 need(cur==total-len(raw),'header file coverage');return h

def verified_plan(root=HERE):
 root=Path(root);plan=load((root/'ACQUISITION_PLAN.json').read_bytes());old=load((root/'TENSOR_ACQUISITION_PLAN.json').read_bytes());need(set(old)==set(PINS),'model inventory')
 headers={};shards={}
 for key,(model,rev,dig) in PINS.items():
  raw=(root/'pins'/f'{key}_manifest.json').read_bytes();need(sha(raw)==dig,'original bundle SHA');b=load(raw)
  need(b['model_id']==model and b['revision']==rev,'model revision');shards.update({s['url']:s for s in b['shards']})
 for s in plan['headers']:
  need(s['url'] in shards,'header canonical URL');a=shards[s['url']]
  need(s['file_bytes']==a['file_bytes'] and all(s['header'][k]==a['header'][k] for k in ('path','bytes','sha256')),'header identity')
  text=checked_path(root,s['header']['json_text']).read_bytes();raw=len(text).to_bytes(8,'little')+text
  need(len(raw)==s['header']['bytes'] and sha(raw)==s['header']['sha256'],'header text reconstruction SHA')
  need(s['url'] not in headers,'duplicate header URL');headers[s['url']]=(s,decode(raw,s['file_bytes']))
 exact={}
 for i,dig in PIN_HASH.items():
  raw=(root/'pins'/f'layer{i}_payload_pin.json').read_bytes();need(sha(raw)==dig,'exact payload pin hash')
  exact.update({t['name']:t for t in load(raw)['tensors']})
 source=load((root/'HISTORICAL_SOURCE_HASH_SET.json').read_bytes());rebuilt=[]
 for model,v in old.items():
  prefix='model.layers.' if model=='qwen2_1p5b' else 'model.language_model.layers.'
  selected=[]
  for url,(sh,h) in headers.items():
   if '/'+PINS[model][1]+'/' not in url:continue
   for name,t in h.items():
    if not any(name.startswith(prefix+str(layer)+'.') for layer in ([0] if model=='qwen2_1p5b' else [0,3])):continue
    lo,hi=t['data_offsets'];selected.append({'name':name,'dtype':t['dtype'],'shape':t['shape'],'bytes':hi-lo,'start':sh['header']['bytes']+lo,'end':sh['header']['bytes']+hi-1,'url':url,'shard_bytes':sh['file_bytes']})
  need(same(sorted(selected,key=lambda t:t['name']),sorted(v['tensors'],key=lambda t:t['name'])),'independent tensor selection differs')
  for t in selected:
   a={**t,'model':model,'revision':PINS[model][1]}
   if model=='qwen3_5_0p8b':
    p=exact[t['name']];need(all(t[k]==p[k] for k in ('dtype','shape','bytes','start','end')),'exact payload geometry');a.update(verification='EXACT_NAME_SHA256',expected_sha256=p['sha256'])
   elif model=='qwen3_5_35b_a3b':a.update(verification='PUBLISHED_RAW_SOURCE_SET_MEMBERSHIP',allowed_sha256=sorted({s['sha256'] for s in source if s['bytes']==t['bytes']}))
   else:a.update(verification='FRESH_PINNED_REVISION_HTTPS_DIGEST_NO_HISTORICAL_PAYLOAD_HASH')
   rebuilt.append(a)
 need(len(rebuilt)==70 and sum(t['bytes'] for t in rebuilt)==3531306272,'full layer inventory/bytes')
 need(same(sorted(rebuilt,key=lambda t:(t['model'],t['name'])),sorted(plan['specs'],key=lambda t:(t['model'],t['name']))),'acquisition spec mismatch')
 cap=sum(t['bytes'] for t in rebuilt)+sum(s['header']['bytes'] for s,_ in headers.values())
 need(all(type(plan[k]) is int for k in ('body_cap','max_response_bytes','workers')) and plan['body_cap']==cap and plan['max_response_bytes']==8388608 and plan['workers']==2,'acquisition resource contract')
 return plan
if __name__=='__main__':
 p=verified_plan();print(json.dumps({'status':'PASS_OFFLINE_METADATA_RECONSTRUCTION_ONLY','tensors':len(p['specs']),'tensor_bytes':sum(t['bytes'] for t in p['specs']),'body_cap':p['body_cap'],'downloaded':False,'numeric_pass':False}))
