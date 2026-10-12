"""Decode frozen reference Q/K by proven producer layout, never by error size.

Native export_value writes Q/K token-major. The historical M16 archive copied
those exports; M128 archived converted logical head-major bytes. Every original
native file hash, logical hash and cold K/cache equality was independently read.
This changes comparison layout only; all payload bytes and old FAILs remain.
"""
import hashlib
import numpy as np

PRODUCER_SHA256 = '917d56f038c646606e9dc67d1d36752f70097adec9748db55b2a915af8147c85'
NATIVE_RESULT_SHA256 = {
    16: 'b6206444a95453770ce3131998000aece244e182e45bebeef841038dd8b2d6a6',
    128: '10ad341ee67fc12f1c619c60716647f29110fa49cd8f17163136059f78cb5315',
}
# (tokens, method, node): (archive SHA, logical head-major SHA).
QK_PINS = {
 (16,'official_self_cache','q'): ('861dfe5deb8ccddd7d27e2c5e7c75323f9fd608fd1ebfef5072cc9650bd4848e','32ae28bab050ccbed9f29e1b8ed0af88435e46a6d37363b0864dcb8ee8065790'),
 (16,'official_self_cache','k'): ('e71f02e124302e9c4725f8af6438eb9894f8c1d37e8a5a3462203c8ad8f12bf0','d8013ced92babfe6a099fdad23a817e8d9de5d0a78e6d411c566bd0a0710ce77'),
 (16,'independent_self_cache','q'): ('5feb7cdb21ced852b3f4fc5ee751a41235a69b5517270f48cead9e06a180bc0e','0cc68c27ba55f62936e277924fd0bbec8f51b4b55d060b507d1c1b59466bde63'),
 (16,'independent_self_cache','k'): ('832339573be592c410b42a814112c3f6796cb643bf5d621d56f0b4f130eb6af6','b143610d8bea612125f9f45ec6002d3b7ffcd2ae0095fac889f171ca7bcc502a'),
 (128,'official_self_cache','q'): ('81b052044f875631b6e6217eb5f51c107da003f3211f07e43fb033b9c27ec910',)*2,
 (128,'official_self_cache','k'): ('702c438d1a083c4f51837d656f9a7a2bce9737e6b4c58b5ad9071be3fd4d078c',)*2,
 (128,'independent_self_cache','q'): ('b40ba46e5d33e8a6899004c6ef3343f1ca90dd4e191848e8a1b6d808710c6800',)*2,
 (128,'independent_self_cache','k'): ('5c80472e3481872129f8a849f16b6c0446975beaa0ffd044171770cd15926751',)*2,
}


def sha(raw):return hashlib.sha256(raw).hexdigest()


def decode_qk(raw, shape, layout):
    if (len(shape)!=4 or any(type(x) is not int or x<=0 for x in shape) or
            len(raw)!=4*np.prod(shape) or layout not in ('token_major','head_major')):
        raise ValueError('invalid Q/K storage shape/layout/length')
    b,h,m,d=shape
    data=np.frombuffer(raw,dtype='<f4')
    if layout=='token_major':return data.reshape(b,m,h,d).transpose(0,2,1,3).copy()
    return data.reshape(shape)


def read_native_reference(raw, *, rows, method, name, shape):
    if name not in ('q','k'):return np.frombuffer(raw,dtype='<f4').reshape(shape)
    pin=QK_PINS.get((rows,method,name))
    if pin is None or sha(raw)!=pin[0] or tuple(shape)!=(1,12 if name=='q' else 2,rows,128):
        raise ValueError('reference Q/K archive identity or logical shape differs')
    value=decode_qk(raw,shape,'token_major' if rows==16 else 'head_major')
    if sha(value.tobytes())!=pin[1]:raise ValueError('reference logical Q/K hash differs')
    return value
