import importlib.util
import json
import struct
from pathlib import Path
import numpy as np
import pytest

spec = importlib.util.spec_from_file_location('stack_pack', Path(__file__).parents[1]/'scripts/pack_qwen2_stack.py')
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)


def checkpoint(tmp_path, dtype='BF16', offsets=None, shape=None, payload=None):
    (tmp_path/'config.json').write_text('{}')
    values=np.array([0x3f80,0xc000,0x0001,0x7f7f],dtype='<u2')
    payload=values.tobytes() if payload is None else payload
    h={'x':{'dtype':dtype,'shape':shape or [2,2],'data_offsets':offsets or [0,len(payload)]}}
    raw=json.dumps(h).encode();(tmp_path/'model.safetensors').write_bytes(struct.pack('<Q',len(raw))+raw+payload)
    return p.SafeCheckpoint(tmp_path)


def test_bf16_bits_are_expanded_without_rounding(tmp_path):
    c=checkpoint(tmp_path)
    np.testing.assert_array_equal(c.fp32('x').view('<u4'),np.array([[0x3f800000,0xc0000000],[0x00010000,0x7f7f0000]],dtype='<u4'))

@pytest.mark.parametrize('dtype,dt',[('F16','<f2'),('F32','<f4')])
def test_float_types_and_selection(tmp_path,dtype,dt):
    values=np.array([[1.5,-2.25],[0,3.125]],dtype=dt)
    c=checkpoint(tmp_path,dtype=dtype,payload=values.tobytes())
    np.testing.assert_array_equal(c.fp32('x',(slice(None),slice(1,2))),values[:,1:2].astype('<f4'))

@pytest.mark.parametrize('offsets,shape',[([0,7],[2,2]),([0,10],[2,2]),([-1,7],[2,2]),([0,8],[3,2])])
def test_malformed_tensor_rejected(tmp_path,offsets,shape):
    with pytest.raises(ValueError):checkpoint(tmp_path,offsets=offsets,shape=shape)


def test_dtype_and_nonfinite_rejected(tmp_path):
    with pytest.raises(ValueError):checkpoint(tmp_path,dtype='F64')
    c=checkpoint(tmp_path,payload=np.array([0x7f80,0,0,0],dtype='<u2').tobytes())
    with pytest.raises(ValueError):c.fp32('x')

@pytest.mark.parametrize('heads,dim',[(1,2),(2,32),(12,128)])
def test_qk_rope_permutation_preserves_dot_and_rotated_values(heads,dim):
    r=np.random.default_rng(53719);q=r.normal(size=(heads,dim));k=r.normal(size=(heads,dim))
    angle=r.normal(size=(heads,dim//2));c=np.cos(angle);s=np.sin(angle)
    def hf(x):return np.concatenate((x[:,:dim//2]*c-x[:,dim//2:]*s,x[:,dim//2:]*c+x[:,:dim//2]*s),axis=1)
    perm=p.adjacent_rope_permutation(heads,dim)
    def device(x):
        t=x.reshape(-1)[perm].reshape(heads,dim//2,2);return np.stack((t[:,:,0]*c-t[:,:,1]*s,t[:,:,1]*c+t[:,:,0]*s),axis=-1).reshape(heads,dim)
    np.testing.assert_allclose(device(q).reshape(-1),hf(q).reshape(-1)[perm],rtol=0,atol=0)
    np.testing.assert_allclose(np.sum(device(q)*device(k),axis=1),np.sum(hf(q)*hf(k),axis=1),atol=1e-12)


def test_rope_weight_bias_permutation_matches_project_then_permute():
    r=np.random.default_rng(17);x=r.normal(size=(3,7));w=r.normal(size=(32,7));b=r.normal(size=32)
    perm=p.adjacent_rope_permutation(2,16)
    np.testing.assert_allclose(x@w[perm].T+b[perm],(x@w.T+b)[:,perm],atol=1e-14)


def test_escape_path_rejected(tmp_path):
    (tmp_path/'config.json').write_text('{}')
    (tmp_path/'model.safetensors.index.json').write_text(json.dumps({'weight_map':{'x':'../outside.safetensors'}}))
    with pytest.raises(ValueError,match='escapes'):p.SafeCheckpoint(tmp_path)


def test_shape_and_missing_tensor_rejected(tmp_path):
    c=checkpoint(tmp_path)
    with pytest.raises(ValueError):c.tensor('x',(4,))
    with pytest.raises(ValueError):c.tensor('missing')


def test_generated_layout_parser(tmp_path):
    fields=['H','F','HEADS','KVHEADS','HD','MAX_TOKENS','STACK_LAYERS','STACK_WEIGHT_BYTES','STACK_ROPE_BYTES','STACK_HIDDEN_BYTES','STACK_SCRATCH_BYTES','OFF_COS','OFF_SIN','OFF_X','OFF_Y','WRITABLE_START']
    header=tmp_path/'layout.h';header.write_text('\n'.join(f'static constexpr uint64_t {key}=64ULL;' for key in fields))
    assert p.read_layout(header)['H']==64
    header.write_text('static constexpr int H=1536;')
    with pytest.raises(ValueError):p.read_layout(header)
