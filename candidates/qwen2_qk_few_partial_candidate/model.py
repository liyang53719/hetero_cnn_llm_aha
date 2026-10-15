import ctypes
import json
from pathlib import Path
import subprocess
from candidates.qwen2_qk_aten_reduction_candidate import model as previous
from candidates.qwen2_qk_aten_reduction_candidate.model import need,sha,original_bias_rope
ROOT=previous.ROOT;HERE=Path(__file__).resolve().parent
CONFIG=json.loads((HERE/'CONFIG.json').read_text())

def splitmix64(state):
    mask=(1<<64)-1;state=(state+0x9e3779b97f4a7c15)&mask;z=state
    z=((z^(z>>30))*0xbf58476d1ce4e5b9)&mask
    z=((z^(z>>27))*0x94d049bb133111eb)&mask
    return state,z^(z>>31)

def transform(x,case):
    import numpy as np
    y=x.copy();state=case['seed']
    if case['transform']=='IDENTITY':return y
    if case['transform']=='CHANNEL_SIGN_XOR':
        signs=[]
        for _ in range(1536):state,z=splitmix64(state);signs.append((z&1)<<31)
        y.view('<u4')[:]^=np.asarray(signs,dtype='<u4')
    elif case['transform']=='CHANNEL_FISHER_YATES':
        permutation=list(range(1536))
        for i in range(1535,0,-1):
            state,z=splitmix64(state);j=z%(i+1);permutation[i],permutation[j]=permutation[j],permutation[i]
        y=x[:,permutation].copy()
    else:raise ValueError('unregistered input transform')
    return y

def compile_library(destination,execute=False):
    if not execute:return None
    need(not Path(destination).exists(),'fresh library')
    argv=['/usr/bin/g++','-std=c++17','-O2','-shared','-fPIC','-fno-fast-math',
       '-ffp-contract=off','-fno-tree-vectorize',str(HERE/'kernel.cpp'),'-o',str(destination)]
    subprocess.run(argv,check=True,capture_output=True,timeout=30);return argv

class Candidate(previous.Candidate):
    def __init__(self,path):
        super().__init__(path);f=ctypes.POINTER(ctypes.c_float);u64=ctypes.POINTER(ctypes.c_uint64)
        self.lib.few_project_raw.argtypes=[f,ctypes.POINTER(ctypes.c_uint16),ctypes.c_int,ctypes.c_int,ctypes.c_int,f,u64,u64,ctypes.POINTER(ctypes.c_uint)]
        self.lib.few_project_raw.restype=ctypes.c_int
    def raw(self,x,w,P):
        import numpy as np
        rows,width=x.shape[0],w.shape[1]
        self.array(x,'<f4',(rows,1536));self.array(w,'<u2',(1536,width))
        need(type(P) is int and P in (2,4),'registered P2/P4')
        need(1<=rows<=128 and width in (256,1536),'bounds')
        out=np.empty((rows,width),dtype='<f4');f=ctypes.POINTER(ctypes.c_float)
        macs=ctypes.c_uint64();adds=ctypes.c_uint64();peak=ctypes.c_uint()
        rc=self.lib.few_project_raw(x.ctypes.data_as(f),w.ctypes.data_as(ctypes.POINTER(ctypes.c_uint16)),
          width,rows,P,out.ctypes.data_as(f),ctypes.byref(macs),ctypes.byref(adds),ctypes.byref(peak))
        need(rc==0,'few-partial status '+str(rc))
        stats=dict(fmas=macs.value,adds=adds.value,active_partial_words=peak.value,partials_per_output=P)
        need(stats==dict(fmas=rows*width*1536,adds=rows*width*P,active_partial_words=128,partials_per_output=P),'operation counts')
        return out,stats

def boundary_tests(candidate):
    import numpy as np
    records=[]
    for P in CONFIG['partials']:
        for name in CONFIG['boundary_tests']:
            x=np.zeros((1,1536),dtype='<f4');w=np.zeros((1536,256),dtype='<u2')
            expected=0.0
            if name=='ZERO_SIGN':x[0,:]=np.float32(-0.0);w[:,0]=0x3f80
            elif name=='CANCELLATION':
                x[0,[0,1,2,3]]=[2**24,1,-2**24,2**-8];w[:4,0]=0x3f80
                expected=1+2**-8
            elif name=='REFILL_BOUNDARIES':
                ix=[127,128,1023,1024,1535];x[0,ix]=[1,0.5,0.25,0.125,0.0625];w[ix,0]=0x3f80;expected=1.9375
            elif name=='BIAS_BF16_MIDPOINT':x[0,:2]=[1,2**-8];w[:2,0]=0x3f80;expected=1+2**-8
            y,stats=candidate.raw(x,w,P)
            need(y[0,0].view('<u4')==np.float32(expected).view('<u4'),'boundary raw '+name)
            if name=='BIAS_BF16_MIDPOINT':
                bias=np.zeros(256,dtype='<f4');bias[0]=2**-8
                rope=np.zeros((2,1024,64),dtype='<f4');rope[0]=1
                biased,rotated,receipt=original_bias_rope(y,bias,rope)
                need(biased[0,0]==np.float32(1+2**-7) and rotated[0,0]==biased[0,0],'bias-before-BF16 boundary')
            records.append({'partials':P,'case':name,'status':'PASS','fmas':stats['fmas']})
    return records
