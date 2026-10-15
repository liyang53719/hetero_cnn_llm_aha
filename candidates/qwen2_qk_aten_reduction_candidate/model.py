"""Explicit bounded independent Q/K projection candidate, original suffix."""
import ctypes
import hashlib
from pathlib import Path
import subprocess
from candidates.qwen2_qk_probability_diagnostic.model import need,sha,OWNER,OWNER_SHA
from candidates.qwen2_aten_q_projection_candidate import model as earlier
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
EARLIER_KERNEL=ROOT/'candidates/qwen2_aten_q_projection_candidate/kernel.cpp'
EARLIER_SHA='e44aa434113f62a7b0d1f37efcffaf38775e8e9e130ee178bd54bb0a41e080ff'
SCHEDULE={'partial_outputs':64,'partial_lanes_per_output':64,'software_partial_words':4096,
  'software_partial_bytes':16384,'fmas_per_output':1536,'register_tree_adds_per_output':56,
  'lane_tree_adds_per_output':7,'zero_tail_adds_per_output':1,'hardware_mapping':'NOT_IMPLEMENTED',
  'hardware_mac_budget':4096,'hardware_utilization':None,'rtl_executed':False}

def compile_library(destination,execute=False):
    if not execute:return None
    need(sha(EARLIER_KERNEL)==EARLIER_SHA,'earlier RMS/kernel source changed')
    need(not Path(destination).exists(),'fresh candidate library')
    argv=['/usr/bin/g++','-std=c++17','-O2','-shared','-fPIC','-fno-fast-math',
      '-ffp-contract=off','-fno-tree-vectorize',str(HERE/'kernel.cpp'),'-o',str(destination)]
    subprocess.run(argv,check=True,capture_output=True,timeout=30);return argv

class Candidate(earlier.Candidate):
    def __init__(self,path):
        super().__init__(path)
        f=ctypes.POINTER(ctypes.c_float);u16=ctypes.POINTER(ctypes.c_uint16);u64=ctypes.POINTER(ctypes.c_uint64)
        self.lib.candidate_project_raw.argtypes=[f,u16,ctypes.c_int,ctypes.c_int,f,u64,u64,ctypes.POINTER(ctypes.c_uint)]
        self.lib.candidate_project_raw.restype=ctypes.c_int
    def raw(self,x,w):
        import numpy as np
        rows,width=x.shape[0],w.shape[1]
        self.array(x,'<f4',(rows,1536));self.array(w,'<u2',(1536,width))
        need(1<=rows<=128 and width in (256,1536),'fixed rows/width')
        y=np.empty((rows,width),dtype='<f4');f=ctypes.POINTER(ctypes.c_float)
        macs=ctypes.c_uint64();adds=ctypes.c_uint64();peak=ctypes.c_uint()
        rc=self.lib.candidate_project_raw(x.ctypes.data_as(f),w.ctypes.data_as(ctypes.POINTER(ctypes.c_uint16)),
             width,rows,y.ctypes.data_as(f),ctypes.byref(macs),ctypes.byref(adds),ctypes.byref(peak))
        need(rc==0,'candidate raw status '+str(rc))
        stats=dict(fmas=macs.value,adds=adds.value,peak_partial_words=peak.value)
        need(stats==dict(fmas=rows*width*1536,adds=rows*width*64,peak_partial_words=4096),'operation counters')
        return y,stats

def original_bias_rope(raw,bias,rope):
    """Run unchanged actual owner through memory responses and write ACKs.

    Only raw candidate output, fixed raw bias and fixed raw RoPE enter the bus.
    This is a local harness for these two suffix jobs, not full-block evidence.
    """
    import numpy as np
    from candidates.qwen2_resident_matrix.ffn_public.prefix_owners import Job
    from candidates.qwen2_resident_matrix.ffn_public.test_prefix_owners import Harness
    from candidates.qwen2_resident_matrix.official_bf16.owners import OfficialPrefixOwner
    from candidates.qwen2_resident_matrix.ffn_public.prefix_arithmetic import ScalarService
    need(sha(OWNER)==OWNER_SHA,'original owner changed')
    rows,width=raw.shape
    need(width in (256,1536) and 1<=rows<=128,'suffix geometry')
    scalar=ScalarService();reports=[]
    def job(kind,a,b,c=None):
        owner=OfficialPrefixOwner(scalar,max_tokens=1024);h=Harness(owner)
        j=Job(kind,0x770001,0x100000,0x200000,0x400000,rows,width,width,rows*width*4,
              c=0x240000 if kind=='Rope' else 0)
        h.bus.input(j.a,[int(v) for v in a.view('<u4').ravel()])
        h.bus.input(j.b,[int(v) for v in b.view('<u4').ravel()])
        if c is not None:h.bus.input(j.c,[int(v) for v in c.view('<u4').ravel()])
        h.bus.output(j.dst,j.write_bytes);result=h.run(j)
        need(result.status is None and owner.ack_bytes==j.write_bytes and owner.state=='idle','actual suffix owner/ACK terminal')
        out=np.frombuffer(h.bus.raw(j.dst),'<f4').reshape(rows,width).copy()
        need(np.isfinite(out).all(),'finite suffix')
        report=owner.report();report.update(output_sha256=hashlib.sha256(out.tobytes()).hexdigest(),
          output_bytes=out.nbytes,terminal=True,ack_bytes=owner.ack_bytes)
        reports.append(report);return out
    biased=job('Bias',raw,bias)
    result=job('Rope',biased,rope[0],rope[1])
    return biased,result,reports
