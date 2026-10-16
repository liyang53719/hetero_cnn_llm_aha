"""Independent QKV plus explicit candidate raw QK pair reduction."""
import ctypes
import hashlib
from pathlib import Path
from . import kernel
from ..raw_kv_native_qkv import adapter as qkv

PROFILE='qwen2-independent-qkv-and-qk-pair-v1'
SOURCE='candidates/qwen2_resident_matrix/raw_kv_native_qk/adapter.py'
IMPORTED_SHA256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def need(ok):
    if not ok:raise ValueError('independent QK candidate contract')


class Recipe:
    def __init__(self,qkv_directory,qk_directory):
        self.qkv=qkv.Recipe(qkv_directory)
        self.directory=Path(qk_directory)
        self.receipt=kernel.verify(self.directory)
        need(self.receipt['source_sha256'].get(SOURCE)==IMPORTED_SHA256)
        self.library=ctypes.CDLL(str(self.receipt['library_path']))
        self.function=self.library.qk_pair
        pointer=ctypes.POINTER(ctypes.c_float)
        self.function.argtypes=[ctypes.c_int,pointer,pointer,pointer]
        self.function.restype=ctypes.c_int
        self.revalidate()

    def revalidate(self):
        self.qkv.revalidate()
        need(kernel.verify(self.directory)==self.receipt and
             self.receipt['source_sha256'].get(SOURCE)==IMPORTED_SHA256)

    def identity(self):
        self.revalidate()
        return dict(profile=PROFILE,qkv=self.qkv.identity(),
                    qk=dict(library_sha256=self.receipt['library_sha256'],
                            source_sha256=dict(self.receipt['source_sha256']),
                            pins_sha256=self.receipt['pins_sha256']),
                    backend_order_proven=False)

    def linear(self,value,weight,bias,role):
        self.revalidate()
        result=self.qkv.linear(value,weight,bias,role)
        self.revalidate()
        return result

    def qk_dot(self,query,repeated_key):
        """Only independent decoded BF16 operands; returns unrounded FP32 dots."""
        import numpy as np
        self.revalidate()
        need(type(query) is np.ndarray and type(repeated_key) is np.ndarray)
        need(query.ndim==4 and query.shape[0:2]==(1,12) and
             query.shape[2] in (16,128) and query.shape[3]==128 and repeated_key.shape==query.shape)
        for item in (query,repeated_key):
            need(item.dtype==np.dtype('float32') and bool(np.isfinite(item).all()) and
                 bool(((item.view(np.uint32)&0xffff)==0).all()))
        q=np.array(query,dtype=np.float32,order='C',copy=True)
        k=np.array(repeated_key,dtype=np.float32,order='C',copy=True)
        rows=query.shape[2]
        output=np.empty((1,12,rows,rows),dtype=np.float32)
        pointer=ctypes.POINTER(ctypes.c_float)
        code=self.function(rows,*(item.ctypes.data_as(pointer) for item in (q,k,output)))
        need(type(code) is int and code==0 and bool(np.isfinite(output).all()))
        self.revalidate()
        return output


def validate(recipe,*,tokens,carried,threads):
    need(type(recipe) is Recipe and type(tokens) is int and tokens in (16,128) and
         type(carried) is bool and carried is False and type(threads) is int and threads==4)
    recipe.revalidate()
    return recipe.identity()
