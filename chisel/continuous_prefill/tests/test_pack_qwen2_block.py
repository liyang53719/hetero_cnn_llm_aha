# SPDX-License-Identifier: Apache-2.0
import importlib.util
import json
from pathlib import Path
import struct
import sys
import numpy as np
import pytest
P=Path(__file__).resolve().parents[1]/'scripts/pack_qwen2_block.py'
spec=importlib.util.spec_from_file_location('block_pack',P);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def tensors():
    h,f,kv=64,128,32
    result={}
    shapes={'self_attn.q_proj.weight':(h,h),'self_attn.k_proj.weight':(kv,h),'self_attn.v_proj.weight':(kv,h),'self_attn.o_proj.weight':(h,h),'mlp.gate_proj.weight':(f,h),'mlp.up_proj.weight':(f,h),'mlp.down_proj.weight':(h,f),'input_layernorm.weight':(h,),'post_attention_layernorm.weight':(h,),'self_attn.q_proj.bias':(h,),'self_attn.k_proj.bias':(kv,),'self_attn.v_proj.bias':(kv,)}
    for i,(name,shape) in enumerate(shapes.items()):
        x=((np.arange(np.prod(shape))*(i+3))%31-15).astype('<f4').reshape(shape)/128
        if 'layernorm' in name:x=x+1
        result['model.layers.0.'+name]=x
    result['model.embed_tokens.weight']=((np.arange(11*h)%41)-20).astype('<f4').reshape(11,h)/32
    return result

def safe_file(path,items,dtype='F32'):
    header={};payload=b''
    for name,x in items.items():
        raw=x.astype('<f4').tobytes() if dtype=='F32' else (m.bf16(x).view('<u4')>>16).astype('<u2').tobytes()
        header[name]={'dtype':dtype,'shape':list(x.shape),'data_offsets':[len(payload),len(payload)+len(raw)]};payload+=raw
    raw=json.dumps(header).encode();path.write_bytes(struct.pack('<Q',len(raw))+raw+payload)

def layout(items):
    h,f,kv,mt=64,128,32,1024;cursor=0;regions=[]
    for name,words in [('wq',h*h),('wk',h*kv),('wv',h*kv),('wo',h*h),('wg',h*f),('wu',h*f),('wd',h*f),('gamma0',h),('gamma1',h),('bq',h),('bk',kv),('bv',kv),('cos',mt*16),('sin',mt*16),('x',mt*h),('n0',mt*h)]:
        cursor=(cursor+63)&-64;regions.append(dict(name=name,words=words,offset=cursor,external=name!='n0'));cursor+=words*4
    return dict(hidden=h,ffn=f,heads=2,kv_heads=1,head_dim=32,max_tokens=mt,regions=regions)

@pytest.mark.parametrize('dtype',['F32','BF16'])
def test_safetensors_pack_no_intermediates(tmp_path,dtype):
    items=tensors();p=tmp_path/'model.safetensors';safe_file(p,items,dtype);reader=m.Safetensors(p);lo=layout(items);out=tmp_path/'arena.bin'
    report=m.pack(lo,reader,0,[2,7],None,out)
    assert report['tokens']==2 and report['intermediate_tensor_preloads']==0
    assert out.stat().st_size==lo['regions'][-1]['offset']
    regions={r['name']:r for r in lo['regions']};raw=np.fromfile(out,dtype='<f4')
    r=regions['wq'];actual=raw[r['offset']//4:r['offset']//4+r['words']].reshape(64,64)
    assert np.array_equal(actual,m.bf16(items['model.layers.0.self_attn.q_proj.weight'].T))
    with pytest.raises(ValueError,match='overwrite'):m.pack(lo,reader,0,[2,7],None,out)

def test_missing_tensor_and_bad_rows(tmp_path):
    items=tensors();p=tmp_path/'model.safetensors';safe_file(p,items);r=m.Safetensors(p)
    with pytest.raises(ValueError,match='missing'):r.tensor('missing')
    with pytest.raises(ValueError,match='vocabulary'):r.tensor('model.embed_tokens.weight',rows=[11])
    with pytest.raises(ValueError,match='layer0'):m.pack(layout(items),r,1,[1],None,tmp_path/'a')

def test_gguf_f32_and_q8_reader(tmp_path):
    def text(s):b=s.encode();return struct.pack('<Q',len(b))+b
    x=np.arange(32,dtype='<f4').reshape(2,16)/16
    q=struct.pack('<e',0.125)+np.arange(-16,16,dtype=np.int8).tobytes()
    prefix=b'GGUF'+struct.pack('<IQQ',3,2,0)
    prefix+=text('x')+struct.pack('<IQQIQ',2,16,2,0,0)
    prefix+=text('q')+struct.pack('<IQQIQ',2,32,1,8,128)
    prefix+=bytes((-len(prefix))%32);p=tmp_path/'test.gguf';p.write_bytes(prefix+x.tobytes()+q)
    r=m.GGUF(p)
    assert np.array_equal(r.tensor('x'),x)
    assert np.array_equal(r.tensor('x',[1]),x[1:2])
    assert np.array_equal(r.tensor('q'),np.arange(-16,16,dtype='<f4').reshape(1,32)*.125)

def test_quant_decoders_same_retained_blocks():
    from heteronpu.ggml_quant import random_q6_k,random_q3_k
    for kind,fn in [(14,random_q6_k),(11,random_q3_k)]:
        for seed in [1,2,17]:
            block=fn(seed);assert np.array_equal(m.GGUF.decode(block.pack(),kind),np.array(block.dequantize(),dtype='<f4'))

def test_corrupt_sources_fail(tmp_path):
    p=tmp_path/'bad.gguf';p.write_bytes(b'GGUF'+struct.pack('<IQQ',3,1,0))
    with pytest.raises(ValueError,match='truncated'):m.GGUF(p)
    p=tmp_path/'bad.safetensors';p.write_bytes(struct.pack('<Q',1<<30))
    with pytest.raises(ValueError,match='large'):m.Safetensors(p)
    with pytest.raises(ValueError,match='nonfinite'):m.bf16(np.array([np.nan],dtype='<f4'))
