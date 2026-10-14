"""Bounded local replay of frozen actual chunk operands; no full-chain execution.

Reads accepted final SSA scratch bytes as immutable test operands. Reference
output is compared only after both old and candidate kernels finish. This does
not import saved data as a new production producer or prove integration drain.
"""
import argparse,hashlib,json,struct,time
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from .model import ChunkOwner,ChunkJob,ScratchPlan,Matrix,finite,require
from .matmul_reuse import Scratch1024,matmul4
from .vector import Vector16,IEEE_POLICY
from ..prep.layout import GROUPED_35B

def sha(raw):return hashlib.sha256(raw).hexdigest()
def record(p):return dict(path=str(p.resolve()),bytes=p.stat().st_size,sha256=sha(p.read_bytes()))

class LocalOwner:
    _matmul=ChunkOwner._matmul
    def __init__(self,vector):self.vector=vector;self.position={};self.calls=Counter()
    def _read(self,address):
        data=yield(address,None);require(type(data) is bytes and len(data)==64,'read beat')
        words=list(struct.unpack('<16I',data));require(all(finite(x) for x in words),'finite operand')
        return words
    def _write(self,address,words):yield(address,struct.pack('<16I',*words))
    def _mul_add(self,a,b,total):
        self.calls['mul_add']+=1;return self.vector.mul_add(self,a,b,total)
    def _op(self,op,a,b):self.calls[op]+=1;return self.vector.op(self,op,a,b)

def execute(vector,a,b,dst,inputs,*,factor=None,reuse=False):
    owner=LocalOwner(vector);scratch=Scratch1024();counts=Counter();written={}
    program=matmul4(owner,a,b,dst,scratch=scratch,factor=factor) if reuse else owner._matmul(a,b,dst,factor=factor)
    vector.acquire(owner);reply=None
    try:
        while True:
            try:address,data=program.send(reply)
            except StopIteration:break
            if data is None:
                matches=[(name,base,raw) for name,(base,raw) in inputs.items() if base<=address and address+64<=base+len(raw)]
                require(len(matches)==1 and address%64==0,'exact immutable read span')
                name,base,raw=matches[0];reply=raw[address-base:address-base+64];counts[name+'_read_bytes']+=64
            else:
                require(dst.base<=address and address+64<=dst.base+dst.rows*dst.cols*4 and address%64==0,'destination write span')
                require(address not in written and len(data)==64,'fresh complete write beat')
                written[address]=data;counts['write_bytes']+=64
                # One accepted write followed by its ACK before generator advance.
                counts['write_ack_bytes']+=64;reply=None
        require(len(written)*64==dst.rows*dst.cols*4,'complete local output')
        return b''.join(written[dst.base+i] for i in range(0,dst.rows*dst.cols*4,64)),dict(counts),dict(owner.calls),scratch.high_water_words*4
    finally:
        program.close();vector.release(owner)
        require(scratch.client is None,'scratch lifetime released')

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--producer',type=Path,required=True)
    ap.add_argument('--summary-sha256',required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    require(not a.out.exists(),'fresh ignored report directory');a.out.mkdir()
    sp=a.producer/'summary.json';raw=sp.read_bytes();require(sha(raw)==a.summary_sha256,'producer summary pin');s=json.loads(raw)
    require(s['tokens'] in (16,128) and s['sources_unchanged'] and s['native_artifacts_unchanged'],'frozen producer')
    obs=next(x for x in s['observations'] if x['stage']=='chunk_scratch_staging');rp=Path(obs['output']['path']);data=rp.read_bytes()
    require(sha(data)==obs['output']['sha256'] and len(data)==obs['output']['bytes'],'actual SSA scratch bytes')
    lib=Path(s['vector_library']['path']);require(sha(lib.read_bytes())==s['vector_library']['sha256'],'actual Vector binary pin')
    vector=Vector16(lib,exception_policy=IEEE_POLICY)
    job=ChunkJob(1,0,1<<30,2<<30,3<<30,obs['owner']['base'],s['tokens'],heads=32,layout=GROUPED_35B)
    plan=ScratchPlan(job)
    files=[Path(__file__),Path(__file__).with_name('model.py'),Path(__file__).with_name('matmul_reuse.py'),Path(__file__).with_name('vector.py')]
    before={str(p):sha(p.read_bytes()) for p in files};cases=[]
    selected=[(0,0),(31,job.chunks-1)]
    for head,chunk in selected:
        m=plan.chunks[head][chunk];previous=plan.initial[head] if chunk==0 else plan.chunks[head][chunk-1]['next_state']
        for name,an,bn,dn,fn in [('ut','kb','kt','ut','pair'),('predict','solvek',None,'pred',None),('state_update','ket','vnew','state_update',None)]:
            aa=m[an];bb=previous if bn is None else m[bn];dd=m[dn];ff=m[fn] if fn else None
            def extract(mat):
                off=mat.base-job.scratch;return data[off:off+mat.rows*mat.cols*4]
            inputs={'a':(aa.base,extract(aa)),'b':(bb.base,extract(bb))}
            if ff:inputs['factor']=(ff.base,extract(ff))
            expected=extract(dd);results=[]
            for reuse in (False,True):
                start=time.monotonic();out,counts,calls,capacity=execute(vector,aa,bb,dd,inputs,factor=ff,reuse=reuse)
                require(out==expected,'local kernel differs from actual SSA destination')
                path=a.out/f'h{head}_c{chunk}_{name}_{int(reuse)}.fp32le';path.write_bytes(out)
                results.append(dict(reuse=reuse,output=record(path),counts=counts,vector_calls=calls,scratch_high_water_bytes=capacity,host_seconds=time.monotonic()-start))
            require(results[0]['vector_calls']==results[1]['vector_calls'],'same arithmetic work')
            require(results[0]['counts']['b_read_bytes']==4*results[1]['counts']['b_read_bytes'],'four-row B reuse')
            cases.append(dict(head=head,chunk=chunk,phase=name,geometry=[aa.rows,aa.cols,bb.cols],input_sha256={k:sha(v[1]) for k,v in inputs.items()},actual_reference_sha256=sha(expected),results=results))
    after={str(p):sha(p.read_bytes()) for p in files};require(before==after,'source drift')
    report=dict(scope='FROZEN_ACTUAL_SSA_LOCAL_MATMUL_REPLAY_ONLY',status='PASS_LOCAL_BITEXACT_AND_MEASURED_READ_COUNTS',producer=record(sp),scratch=record(rp),vector_binary=record(lib),source_before=before,source_after=after,cases=cases,full_chain_rerun=False,chunk_policy_integrated=False,production_chisel_binding=False,hardware_cycles=None,hardware_mac_utilization=None,new_array=False,scratch_candidate_bytes=1024,transpose_scratch_lifetime_mapping_proven=False,transport_fault_drain_integrated=False)
    (a.out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(status=report['status'],cases=len(cases))),flush=True)
if __name__=='__main__':main()
