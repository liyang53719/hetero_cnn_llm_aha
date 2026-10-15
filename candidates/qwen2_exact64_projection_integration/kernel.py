"""One bounded 16KiB exact64 partial set; actual FMA/Add counters."""
import ctypes as C
import hashlib
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
PINS={
 'candidates/qwen2_qk_aten_reduction_candidate/kernel.cpp':'62214f0372859e57eef4b48a368a1dcc486a94d6c3f348a3a4a707fadfaed42d',
 'candidates/qwen2_aten_q_projection_candidate/kernel.cpp':'e44aa434113f62a7b0d1f37efcffaf38775e8e9e130ee178bd54bb0a41e080ff',
}
def need(ok,message):
    if not ok:raise ValueError(message)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def source_check():
    need(all(sha(ROOT/p)==v for p,v in PINS.items()),'frozen exact64 arithmetic source drift')
    return {**PINS,str((HERE/'kernel.cpp').relative_to(ROOT)):sha(HERE/'kernel.cpp')}
def compile_library(path):
    path=Path(path);need(not path.exists(),'fresh exact64 library output');source_check()
    argv=['/usr/bin/g++','-std=c++17','-O2','-shared','-fPIC','-fno-fast-math','-ffp-contract=off','-fno-tree-vectorize',str(HERE/'kernel.cpp'),'-o',str(path)]
    p=subprocess.run(argv,capture_output=True,text=True,timeout=30);need(p.returncode==0,'exact64 compile failed')
    return dict(argv=argv,returncode=p.returncode,source_sha256=source_check(),library_sha256=sha(path),arithmetic='FROZEN_EXACT64_STREAMED_EQUIVALENT',hardware_mapping='NOT_IMPLEMENTED')
class Exact64Kernel:
    def __init__(self,path):
        source_check();self.lib=C.CDLL(str(Path(path).resolve()))
        f=C.POINTER(C.c_float);u32=C.POINTER(C.c_uint32);u16=C.POINTER(C.c_uint16);u64=C.POINTER(C.c_uint64)
        self.lib.exact64_clear.argtypes=[f];self.lib.exact64_clear.restype=C.c_int
        self.lib.exact64_push.argtypes=[f,C.c_uint,C.c_uint32,u16,u64];self.lib.exact64_push.restype=C.c_int
        self.lib.exact64_finish.argtypes=[f,u32,u64];self.lib.exact64_finish.restype=C.c_int
        self.partial=(C.c_float*4096)();self.fmas=C.c_uint64();self.adds=C.c_uint64()
        self.state='idle';self.next_k=0;self.serial=0;self.tile=None;self.output=None
    def begin(self,tile):
        need(self.state=='idle' and type(tile) is tuple and len(tile)==3 and all(type(v) is int and v>=0 for v in tile),'one canonical tile lease')
        need(self.lib.exact64_clear(self.partial)==0,'exact64 environment/clear')
        self.state='active';self.next_k=0;self.tile=tile;self.serial+=1
    def push(self,k,activation,weights):
        need(self.state=='active' and type(k) is int and k==self.next_k and 0<=k<1536,'ordered accepted K stream')
        need(type(activation) is int and 0<=activation<1<<32 and type(weights) is bytes and len(weights)==128,'exact activation/64 BF16 weights')
        w=(C.c_uint16*64).from_buffer_copy(weights)
        rc=self.lib.exact64_push(self.partial,k,activation,w,C.byref(self.fmas));need(rc==0,'exact64 push error')
        self.next_k+=1
    def finish(self):
        need(self.state=='active' and self.next_k==1536,'full K before tree')
        output=(C.c_uint32*64)();need(self.lib.exact64_finish(self.partial,output,C.byref(self.adds))==0,'exact64 finite tree')
        self.output=bytes(output);self.state='sealed';return self.output
    def retire(self,tile):
        need(self.state=='sealed' and tile==self.tile,'tile release after output ACKs')
        self.state='idle';self.tile=None;self.output=None
    def abort(self):
        self.state='poison';self.output=None
    def report(self):
        return dict(fmas=int(self.fmas.value),adds=int(self.adds.value),partial_words=4096,partial_bytes=C.sizeof(self.partial),
          state=self.state,tiles_started=self.serial,hardware_mapping='NOT_IMPLEMENTED',performance='NO_GO',scope='DIAGNOSTIC_SOFTWARE_OWNER')
