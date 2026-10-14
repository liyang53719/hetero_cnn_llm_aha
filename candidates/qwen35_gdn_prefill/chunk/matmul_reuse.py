"""Local 4-row matmul candidate: 1KiB explicit scratch, unchanged per-output K order.

This generator needs the existing read/write ACK transport and Vector16 loan.
ChunkOwner selects it only through an explicit opt-in policy.
This is not a hardware throughput result.
"""
from array import array
from .model import require

class Scratch1024:
    A, B, ACC = 0, 64, 192
    def __init__(self):
        self.words=array('I',[0])*256
        require(self.words.itemsize==4,'32-bit scratch storage')
        self.client=None
        self.high_water_words=0
    def acquire(self,client):
        require(self.client is None,'scratch already leased')
        self.client=client
    def release(self,client):
        require(self.client is client,'scratch lease identity')
        self.client=None
    def put(self,client,offset,values):
        require(self.client is client and type(offset) is int and 0<=offset and offset+len(values)<=256,'scratch write range/owner')
        require(all(type(x) is int and 0<=x<1<<32 for x in values),'FP32 words')
        self.words[offset:offset+len(values)]=array('I',values)
        self.high_water_words=max(self.high_water_words,offset+len(values))
    def get(self,client,offset,count):
        require(self.client is client and 0<=offset and 0<=count and offset+count<=256,'scratch read range/owner')
        return self.words[offset:offset+count].tolist()

def matmul4(owner,a,b,destination,*,scratch,factor=None):
    require(a.cols==b.rows and (destination.rows,destination.cols)==(a.rows,b.cols),'matmul dimensions')
    require(a.cols%16==0 and b.cols%16==0,'full FP32 beats')
    scratch.acquire(owner)
    try:
        for first in range(0,a.rows,4):
            rows=min(4,a.rows-first)
            for col in range(0,b.cols,16):
                scratch.put(owner,scratch.ACC,[0]*64)
                for start in range(0,a.cols,16):
                    for r in range(rows):
                        scratch.put(owner,scratch.A+r*16,(yield from owner._read(a.address(first+r,start))))
                    for half in (0,8):
                        for k in range(8):
                            scratch.put(owner,scratch.B+k*16,(yield from owner._read(b.address(start+half+k,col))))
                        for k in range(8):
                            bv=scratch.get(owner,scratch.B+k*16,16)
                            for r in range(rows):
                                owner.position=dict(row=first+r,column=col,reduction_k=start+half+k)
                                av=scratch.get(owner,scratch.A+r*16+half+k,1)[0]
                                total=owner._mul_add([av]*16,bv,scratch.get(owner,scratch.ACC+r*16,16))
                                scratch.put(owner,scratch.ACC+r*16,total)
                for r in range(rows):
                    total=scratch.get(owner,scratch.ACC+r*16,16)
                    if factor is not None:
                        owner.position=dict(row=first+r,column=col,reduction_k=None,node='pair_decay_mul')
                        weights=yield from owner._read(factor.address(first+r,col))
                        total=owner._op('mul',total,weights)
                    yield from owner._write(destination.address(first+r,col),total)
    finally:
        scratch.release(owner)
