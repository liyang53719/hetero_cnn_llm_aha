#!/usr/bin/env python3
"""Pack a real checkpoint into the Chisel functional block's READONLY arena.

No inference, intermediate tensor generation or RTL editing is performed here.
GGUF v2/v3: F32, F16, BF16, Q8_0, Q6_K, Q3_K. Safetensors: F32/F16/BF16.
Other storage types fail explicitly; this is not a native low-bit compute claim.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import mmap
from pathlib import Path
import struct
import sys
import numpy as np
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src'))
from heteronpu.ggml_quant import Q8_0Block, Q6KBlock, Q3KBlock

def require(ok: bool, message: str) -> None:
    if not ok: raise ValueError(message)

def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(8 << 20), b''): h.update(b)
    return h.hexdigest()

def bf16(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype='<f4').copy()
    require(bool(np.isfinite(x).all()), 'nonfinite input tensor')
    u = x.view('<u4')
    u[:] = (u + np.uint32(0x7fff) + ((u >> 16) & 1)) & np.uint32(0xffff0000)
    require(bool(np.isfinite(x).all()), 'BF16 conversion overflow')
    return x

class GGUF:
    TYPES = {0:(1,4), 1:(1,2), 30:(1,2), 8:(32,34), 14:(256,210), 11:(256,110)}
    def __init__(self, path: Path):
        self.path = path; self.file = path.open('rb'); self.data = mmap.mmap(self.file.fileno(), 0, access=mmap.ACCESS_READ); self.pos=0
        require(self.take(4)==b'GGUF', 'not little-endian GGUF')
        require(self.number('I') in (2,3), 'unsupported GGUF version')
        nt, nk = self.number('Q'), self.number('Q')
        require(nt<=100000 and nk<=1000000, 'unbounded GGUF header')
        self.meta={}; self.entries={}; self.used={str(path):None}
        for _ in range(nk):
            key=self.string(); kind=self.number('I'); keep=key in ('general.alignment','general.architecture') or key.startswith('qwen2.')
            value=self.value(kind,keep)
            if keep:self.meta[key]=value
        for _ in range(nt):
            name=self.string();nd=self.number('I');require(0<nd<=4,'GGUF tensor rank')
            dims=tuple(self.number('Q') for _ in range(nd));kind=self.number('I');off=self.number('Q')
            require(name not in self.entries and all(d>0 for d in dims),'duplicate/empty tensor')
            self.entries[name]=(dims,kind,off)
        align=int(self.meta.get('general.alignment',32));require(align>0 and align<=4096 and align&(align-1)==0,'GGUF alignment')
        self.base=(self.pos+align-1)&-align
        require(self.base<=len(self.data),'truncated GGUF')
    def take(self,n:int)->bytes:
        require(0<=n<=len(self.data)-self.pos,'truncated GGUF header');b=self.data[self.pos:self.pos+n];self.pos+=n;return b
    def number(self,fmt:str):return struct.unpack('<'+fmt,self.take(struct.calcsize('<'+fmt)))[0]
    def string(self):
        n=self.number('Q');require(n<=16<<20,'oversized GGUF string');return self.take(n).decode('utf8')
    def value(self,k:int,keep:bool,depth:int=0):
        require(depth<5,'nested metadata overflow')
        formats={0:'B',1:'b',2:'H',3:'h',4:'I',5:'i',6:'f',7:'?',10:'Q',11:'q',12:'d'}
        if k in formats:return self.number(formats[k])
        if k==8:
            n=self.number('Q');require(n<=16<<20,'oversized metadata string');b=self.take(n);return b.decode('utf8') if keep else None
        if k==9:
            t,n=self.number('I'),self.number('Q');require(n<=10000000,'oversized metadata array')
            result=[]
            for _ in range(n):
                v=self.value(t,keep,depth+1)
                if keep:result.append(v)
            return result if keep else None
        raise ValueError('unknown GGUF metadata type '+str(k))
    def tensor(self,name:str,rows:list[int]|None=None)->np.ndarray:
        require(name in self.entries,'missing GGUF tensor '+name)
        dims,kind,off=self.entries[name];require(kind in self.TYPES, f'unsupported GGUF storage type {kind}: {name}; supply a supported GGUF or safetensors')
        block,size=self.TYPES[kind];shape=tuple(reversed(dims));count=math.prod(shape)
        require(count%block==0 and dims[0]%block==0,'misaligned GGUF block rows')
        start=self.base+off;length=count//block*size;require(start>=self.base and start+length<=len(self.data),'truncated tensor '+name)
        if rows is not None:
            require(len(shape)==2 and all(0<=i<shape[0] for i in rows),'embedding row outside vocabulary')
            rowbytes=dims[0]//block*size;parts=[self.decode(self.data[start+i*rowbytes:start+(i+1)*rowbytes],kind) for i in rows]
            return np.stack(parts)
        return self.decode(self.data[start:start+length],kind).reshape(shape)
    @staticmethod
    def decode(raw:bytes,kind:int)->np.ndarray:
        if kind==0:return np.frombuffer(raw,dtype='<f4').copy()
        if kind==1:return np.frombuffer(raw,dtype='<f2').astype('<f4')
        if kind==30:return (np.frombuffer(raw,dtype='<u2').astype('<u4')<<16).view('<f4')
        block,size=GGUF.TYPES[kind];require(len(raw)%size==0,'truncated quant block')
        if kind==8:
            arr=np.frombuffer(raw,dtype=np.uint8).reshape(-1,34);scale=arr[:,:2].copy().view('<f2').astype('<f4')
            return (scale*arr[:,2:].view(np.int8).astype('<f4')).reshape(-1)
        cls={14:Q6KBlock,11:Q3KBlock}[kind]
        out=np.empty(len(raw)//size*block,dtype='<f4')
        for i,j in enumerate(range(0,len(raw),size)):out[i*block:(i+1)*block]=cls.unpack(raw[j:j+size]).dequantize()
        return out

class Safetensors:
    def __init__(self,path:Path):
        self.path=path;self.entries={};self.used={};self.meta={}
        if path.is_dir():
            cfg=path/'config.json'
            if cfg.exists():self.meta=json.loads(cfg.read_text());self.used[str(cfg)]=None
            idx=path/'model.safetensors.index.json'
            files=sorted(set(json.loads(idx.read_text())['weight_map'].values())) if idx.exists() else [p.name for p in path.glob('*.safetensors')]
            require(bool(files),'no safetensors shards found')
            if idx.exists():self.used[str(idx)]=None
            paths=[path/name for name in files]
        else:paths=[path]
        for p in paths:
            with p.open('rb') as f:
                raw=f.read(8);require(len(raw)==8,'short safetensors header');n=struct.unpack('<Q',raw)[0];require(n<=64<<20,'header too large');h=json.loads(f.read(n))
            for name,spec in h.items():
                if name=='__metadata__':continue
                require(name not in self.entries,'duplicate tensor '+name);self.entries[name]=(p,8+n,spec)
    def tensor(self,name:str,rows:list[int]|None=None)->np.ndarray:
        require(name in self.entries,'missing safetensors tensor '+name);p,base,spec=self.entries[name];shape=tuple(spec['shape']);dtype=spec['dtype']
        types={'F32':(4,'<f4'),'F16':(2,'<f2'),'BF16':(2,'<u2')};require(dtype in types,'unsupported dtype '+dtype)
        size,typ=types[dtype];begin,end=spec['data_offsets'];require(end-begin==math.prod(shape)*size and base+end<=p.stat().st_size,'bad tensor extent')
        self.used[str(p)]=None
        with p.open('rb') as f:
            if rows is None:f.seek(base+begin);raw=f.read(end-begin)
            else:
                require(len(shape)==2 and all(0<=i<shape[0] for i in rows),'embedding index outside vocabulary');stride=shape[1]*size;chunks=[]
                for i in rows:f.seek(base+begin+i*stride);chunks.append(f.read(stride))
                raw=b''.join(chunks);shape=(len(rows),shape[1])
        x=np.frombuffer(raw,dtype=typ)
        return ((x.astype('<u4')<<16).view('<f4') if dtype=='BF16' else x.astype('<f4')).reshape(shape)

def pack(layout:dict,reader,layer:int,token_ids:list[int]|None,hidden:Path|None,out:Path,theta:float=1000000.0)->dict:
    require(not out.exists(),'refuse to overwrite arena')
    h,f,hd,kv=layout['hidden'],layout['ffn'],layout['head_dim'],layout['kv_heads']*layout['head_dim']
    require(layer>=0 and math.isfinite(theta) and theta>0,'invalid layer/theta')
    if isinstance(reader,GGUF):
        require(reader.meta.get('general.architecture')=='qwen2','checkpoint architecture is not qwen2')
        fields={'qwen2.embedding_length':h,'qwen2.feed_forward_length':f,'qwen2.attention.head_count':layout['heads'],'qwen2.attention.head_count_kv':layout['kv_heads']}
        for key,expected in fields.items():require(reader.meta.get(key)==expected,'checkpoint geometry mismatch: '+key)
        if 'qwen2.rope.freq_base' in reader.meta:require(float(reader.meta['qwen2.rope.freq_base'])==theta,'RoPE theta mismatch')
        if 'qwen2.attention.layer_norm_rms_epsilon' in reader.meta:require(abs(float(reader.meta['qwen2.attention.layer_norm_rms_epsilon'])-1e-6)<1e-12,'RMS epsilon mismatch')
    elif reader.meta:
        require(reader.meta.get('model_type')=='qwen2','checkpoint architecture is not qwen2')
        for key,expected in {'hidden_size':h,'intermediate_size':f,'num_attention_heads':layout['heads'],'num_key_value_heads':layout['kv_heads']}.items():require(reader.meta.get(key)==expected,'checkpoint geometry mismatch: '+key)
        require(float(reader.meta.get('rope_theta',theta))==theta,'RoPE theta mismatch')
        require(abs(float(reader.meta.get('rms_norm_eps',1e-6))-1e-6)<1e-12,'RMS epsilon mismatch')
    if token_ids is not None:
        require(layer==0,'token embedding only valid for layer0; later layers require actual predecessor output')
        require(bool(token_ids) and all(type(i) is int and i>=0 for i in token_ids),'invalid token IDs')
        name='token_embd.weight' if isinstance(reader,GGUF) else 'model.embed_tokens.weight';x=reader.tensor(name,rows=token_ids)
    else:
        require(hidden is not None,'provide token IDs or actual input hidden');raw=np.fromfile(hidden,dtype='<f4');require(raw.size%h==0,'hidden file size');x=raw.reshape(-1,h)
    t=x.shape[0];require(x.shape==(t,h) and 0<t<=layout['max_tokens'],'wrong input shape');require(bool(np.isfinite(x).all()),'nonfinite input')
    regions={r['name']:r for r in layout['regions']};readonly=min(r['offset'] for r in regions.values() if not r['external'])
    out.parent.mkdir(parents=True,exist_ok=True)
    records=[]
    with out.open('xb') as stream:
        stream.truncate(readonly)
        def put(key:str,values:np.ndarray):
            r=regions[key];require(r['external'],'cannot prepopulate an intermediate');values=np.asarray(values,dtype='<f4');require(values.size<=r['words'],'tensor exceeds region '+key);require(bool(np.isfinite(values).all()),'nonfinite '+key)
            raw=values.tobytes();stream.seek(r['offset']);stream.write(raw);records.append(dict(name=key,offset=r['offset'],elements=values.size,sha256=hashlib.sha256(raw).hexdigest()))
        gg={'wq':'attn_q.weight','wk':'attn_k.weight','wv':'attn_v.weight','wo':'attn_output.weight','wg':'ffn_gate.weight','wu':'ffn_up.weight','wd':'ffn_down.weight','gamma0':'attn_norm.weight','gamma1':'ffn_norm.weight','bq':'attn_q.bias','bk':'attn_k.bias','bv':'attn_v.bias'}
        hf={'wq':'self_attn.q_proj.weight','wk':'self_attn.k_proj.weight','wv':'self_attn.v_proj.weight','wo':'self_attn.o_proj.weight','wg':'mlp.gate_proj.weight','wu':'mlp.up_proj.weight','wd':'mlp.down_proj.weight','gamma0':'input_layernorm.weight','gamma1':'post_attention_layernorm.weight','bq':'self_attn.q_proj.bias','bk':'self_attn.k_proj.bias','bv':'self_attn.v_proj.bias'}
        shapes={'wq':(h,h),'wk':(kv,h),'wv':(kv,h),'wo':(h,h),'wg':(f,h),'wu':(f,h),'wd':(h,f),'gamma0':(h,),'gamma1':(h,),'bq':(h,),'bk':(kv,),'bv':(kv,)}
        for key,shape in shapes.items():
            name=f'blk.{layer}.{gg[key]}' if isinstance(reader,GGUF) else f'model.layers.{layer}.{hf[key]}'
            value=reader.tensor(name);require(value.shape==shape,f'{name}: expected {shape}, got {value.shape}')
            put(key,bf16(value.T) if key.startswith('w') else value)
        positions=np.arange(t,dtype=np.float64)[:,None];inv=theta**(-2*np.arange(hd//2,dtype=np.float64)/hd)
        put('cos',np.cos(positions*inv));put('sin',np.sin(positions*inv));put('x',x)
    sources={p:digest(Path(p)) for p in reader.used}
    if hidden is not None:sources[str(hidden)]=digest(hidden)
    return dict(schema=1,status='PACK_ONLY_NOT_INFERENCE',layer=layer,tokens=t,layout_sha256=hashlib.sha256(json.dumps(layout,sort_keys=True).encode()).hexdigest(),arena_sha256=digest(out),arena_bytes=readonly,source_sha256=sources,token_ids=token_ids,theta=theta,records=records,recipe='bf16_matrix_fp32_reduction_exp_poly7',intermediate_tensor_preloads=0)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--layout',type=Path,required=True);ap.add_argument('--checkpoint',type=Path,required=True);ap.add_argument('--layer',type=int,default=0)
    group=ap.add_mutually_exclusive_group(required=True);group.add_argument('--tokens-json',type=Path);group.add_argument('--input-f32',type=Path)
    ap.add_argument('--out',type=Path,required=True);ap.add_argument('--theta',type=float,default=1000000.0);a=ap.parse_args()
    require(a.layer>=0 and math.isfinite(a.theta) and a.theta>0,'invalid layer/theta')
    reader=GGUF(a.checkpoint) if a.checkpoint.suffix.lower()=='.gguf' else Safetensors(a.checkpoint)
    report=pack(json.loads(a.layout.read_text()),reader,a.layer,json.loads(a.tokens_json.read_text()) if a.tokens_json else None,a.input_f32,a.out,a.theta)
    if a.tokens_json:report['tokens_file_sha256']=digest(a.tokens_json)
    path=Path(str(a.out)+'.json');require(not path.exists(),'refuse to overwrite packing receipt');path.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
