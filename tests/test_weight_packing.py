"""Raw synthetic matrices, finite IEEE bit boundaries and full package readback."""
from dataclasses import replace
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import numpy as np
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from heteronpu.weight_packing import PackContract, PackingError, round_bf16, pack_file, verify_package


def source(root,rows,cols,dtype='f32le'):
    x=(np.arange(rows*cols,dtype=np.float32).reshape(rows,cols)*0.03125-3).astype('<f4')
    raw=x.tobytes() if dtype=='f32le' else round_bf16(x.view('<u4')).tobytes()
    p=root/'source.bin';p.write_bytes(raw);return p,x


@pytest.mark.parametrize('shape',[(1,1),(17,33),(33,17),(65,257),(128,512),(256,640),(1536,32)])
@pytest.mark.parametrize('transpose',[False,True])
@pytest.mark.parametrize('dtype',['f32le','bf16le'])
def test_transpose_tiles_padding_and_all_bytes(tmp_path,shape,transpose,dtype):
    p,x=source(tmp_path,*shape,dtype)
    c=PackContract(*shape,transpose,input_dtype=dtype,chunk_rows=7,tile_columns=13)
    out=tmp_path/'packed';m=pack_file(p,out,c);r=verify_package(p,out,c)
    assert r['elements']==x.size and not r['official_weights_verified'] and not r['rtl_execution']
    k,n=c.layout()['logical_kn'];pn=c.layout()['storage_kn'][1]
    words=np.frombuffer((out/'weights.bf16le').read_bytes(),dtype='<u2').reshape(k,pn)
    target=x.T if transpose else x
    # These fixture values are exactly BF16-representable or scalar-RNE rounded.
    expected=np.array([scalar(int(u)) for u in target.copy().view('<u4').flat],dtype='<u2').reshape(k,n)
    assert np.array_equal(words[:,:n],expected) and not np.any(words[:,n:])
    assert m['chunks'][0]['offset']==0 and m['chunks'][-1]['offset']+m['chunks'][-1]['bytes']==r['payload_bytes']


def scalar(word):
    # Test oracle: quotient/remainder and nearest-even, no encoder add-bias.
    q,r=divmod(word,65536)
    return (q+int(r>32768 or (r==32768 and q%2==1))) & 0xffff


def test_all_finite_bf16_patterns_and_tie_sides():
    finite=np.array([v for v in range(65536) if v & 0x7f80 != 0x7f80],dtype=np.uint32)
    bits=finite<<16
    assert np.array_equal(round_bf16(bits),finite)
    # Every finite BF16 exponent/sign/mantissa with values around the tie.
    for low in (0x7fff,0x8000,0x8001):
        words=bits|low
        expected=np.array([scalar(int(v)) for v in words],dtype=np.uint16)
        legal=(expected&0x7f80)!=0x7f80
        assert np.array_equal(round_bf16(words[legal]),expected[legal])


@pytest.mark.parametrize('bits',[0,0x80000000,1,0x00008000,0x00018000,0x007fffff,0x00800000,0x3f808000,0x3f818000,0xbf818000])
def test_scalar_special_finite(bits):
    assert int(round_bf16(np.array([bits],dtype=np.uint32))[0])==scalar(bits)


@pytest.mark.parametrize('bits',[0x7f800000,0xff800000,0x7fc00000,0x7f800001,0x7f7fffff,0xff7fffff])
def test_nonfinite_and_overflow_rejected_before_output(tmp_path,bits):
    p=tmp_path/'s';p.write_bytes(struct.pack('<I',bits));out=tmp_path/'o'
    with pytest.raises(PackingError): pack_file(p,out,PackContract(1,1,False))
    assert not out.exists()


def test_original_native_bf16_recipe_parity():
    root=Path(__file__).resolve().parents[1]
    spec=importlib.util.spec_from_file_location('old_bf16',root/'chisel/continuous_prefill/scripts/pack_owner_bf16_weights.py')
    old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    rng=np.random.default_rng(321);f=rng.normal(size=8193).astype('<f4')
    assert old.pack_words(f.tobytes())==round_bf16(f.view('<u4')).tobytes()


@pytest.mark.parametrize('field,value',[('source_rows',0),('source_rows',True),('transpose',1),('input_dtype','f32be'),('column_multiple',16),('column_multiple',33),('chunk_rows',0),('device_base',3),('device_base',-64),('device_base',(1<<56)-64)])
def test_contract_reject(field,value):
    with pytest.raises(PackingError): replace(PackContract(17,33,False),**{field:value}).layout()


@pytest.mark.parametrize('kind',['truncated_source','oversized_source','existing_output','symlink_output'])
def test_io_reject_without_overwriting(tmp_path,kind):
    p,_=source(tmp_path,17,33);out=tmp_path/'out';c=PackContract(17,33,False)
    if kind=='truncated_source': p.write_bytes(p.read_bytes()[:-4])
    elif kind=='oversized_source': p.write_bytes(p.read_bytes()+b'xxxx')
    elif kind=='existing_output': out.mkdir();(out/'guard').write_text('preserve')
    else: out.symlink_to(tmp_path/'missing',target_is_directory=True)
    with pytest.raises(PackingError): pack_file(p,out,c)
    if kind=='existing_output': assert (out/'guard').read_text()=='preserve'


@pytest.mark.parametrize('kind',['truncate','hash','padding','data','missing_chunk','duplicate_chunk','chunk_order','contract','shape','source','bool','unknown'])
def test_corrupt_package(tmp_path,kind):
    p,_=source(tmp_path,17,33);out=tmp_path/'out';c=PackContract(17,33,False,chunk_rows=7)
    m=pack_file(p,out,c);payload=out/'weights.bf16le';b=bytearray(payload.read_bytes())
    if kind=='truncate': payload.write_bytes(b[:-2])
    elif kind=='hash': m['payload_sha256']='0'*64
    elif kind in ('data','padding'):
        index=0 if kind=='data' else 33*2;b[index]^=1;payload.write_bytes(b)
        # Recompute both hashes: readback must still reject actual wrong values.
        from heteronpu.weight_packing import _chunks
        m['payload_sha256']=hashlib.sha256(b).hexdigest();m['chunks']=_chunks(payload,c.layout(),c)
    elif kind=='missing_chunk': m['chunks'].pop()
    elif kind=='duplicate_chunk': m['chunks'].append(m['chunks'][0])
    elif kind=='chunk_order': m['chunks'].reverse()
    elif kind=='contract': m['contract']['transpose']=True
    elif kind=='shape': m['logical_kn']=[33,17]
    elif kind=='source': p.write_bytes(p.read_bytes()[:-4]+struct.pack('<f',99.))
    elif kind=='bool': m['schema']=True
    elif kind=='unknown': m['skip_check']=True
    (out/'manifest.json').write_text(json.dumps(m))
    with pytest.raises(PackingError): verify_package(p,out,c)


def test_no_tile_order_change(tmp_path):
    p,_=source(tmp_path,33,65)
    a=PackContract(33,65,True,chunk_rows=1,tile_columns=1)
    b=replace(a,chunk_rows=64,tile_columns=256)
    x=pack_file(p,tmp_path/'a',a);y=pack_file(p,tmp_path/'b',b)
    assert x['payload_sha256']==y['payload_sha256']
