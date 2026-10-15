"""Cold-by-default binding for an independent software arithmetic candidate."""
from pathlib import Path
import ctypes
import subprocess

HERE=Path(__file__).resolve().parent
SCHEDULE={'k':1536,'groups':24,'persistent_fp32_accumulators_per_output':64,
          'fma_per_output':1536,'register_tree_adds':56,'lane_tree_adds':7,
          'zero_tail_adds':1,'bias_adds':1,'bf16_materializations':1,
          'hardware_cycles':None,'rtl_executed':False}

def compile_library(destination, *, execute=False):
    if not execute: return None
    destination=Path(destination)
    if destination.exists(): raise ValueError('fresh library destination required')
    command=['/usr/bin/g++','-std=c++17','-O2','-shared','-fPIC',
             '-fno-fast-math','-ffp-contract=off','-fno-tree-vectorize',
             str(HERE/'kernel.cpp'),'-o',str(destination)]
    subprocess.run(command,check=True,capture_output=True,timeout=30)
    return command

class Candidate:
    def __init__(self, library):
        self.lib=ctypes.CDLL(str(library))
        f=ctypes.POINTER(ctypes.c_float)
        self.lib.candidate_rms.argtypes=[f,f,f,ctypes.c_int]
        self.lib.candidate_q.argtypes=[f,ctypes.POINTER(ctypes.c_uint16),f,
            ctypes.POINTER(ctypes.c_int),ctypes.c_int,ctypes.c_int,f,f]
        self.lib.candidate_rms.restype=self.lib.candidate_q.restype=ctypes.c_int

    @staticmethod
    def array(x,dtype,shape):
        import numpy as np
        if x.dtype!=np.dtype(dtype) or x.shape!=shape or not x.flags.c_contiguous:
            raise ValueError('exact dtype/shape/contiguity required')
        return x

    def rms(self,x,gamma):
        import numpy as np
        rows=x.shape[0]
        self.array(x,'<f4',(rows,1536));self.array(gamma,'<f4',(1536,))
        if not 1<=rows<=128: raise ValueError('rows')
        y=np.empty_like(x);f=ctypes.POINTER(ctypes.c_float)
        if self.lib.candidate_rms(*(a.ctypes.data_as(f) for a in (x,gamma,y)),rows):
            raise ValueError('RMS domain/environment rejected')
        return y

    def project(self,x,w,bias,columns):
        import numpy as np
        rows=x.shape[0]
        self.array(x,'<f4',(rows,1536));self.array(w,'<u2',(1536,1536));self.array(bias,'<f4',(1536,))
        if not 1<=rows<=128 or not 1<=len(columns)<=1536 or any(type(c) is not int or not 0<=c<1536 for c in columns):
            raise ValueError('bounded rows/columns')
        cols=np.asarray(columns,dtype=np.int32);raw=np.empty((rows,len(cols)),dtype='<f4');out=np.empty_like(raw)
        f=ctypes.POINTER(ctypes.c_float)
        rc=self.lib.candidate_q(x.ctypes.data_as(f),w.ctypes.data_as(ctypes.POINTER(ctypes.c_uint16)),
            bias.ctypes.data_as(f),cols.ctypes.data_as(ctypes.POINTER(ctypes.c_int)),len(cols),rows,
            raw.ctypes.data_as(f),out.ctypes.data_as(f))
        if rc: raise ValueError('Q domain/environment rejected')
        return raw,out
