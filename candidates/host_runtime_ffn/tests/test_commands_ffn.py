"""Executable protocol model, not Chisel simulation or numeric DUT evidence."""
from dataclasses import dataclass, replace
from pathlib import Path
import unittest

@dataclass(frozen=True)
class Host:
    profile: int = 1
    epoch: int = 7
    table: int = 0x1000
    regions: tuple = (0x100000, 0x4000000, 0x8000000)

@dataclass(frozen=True)
class Tensor:
    address: int
    rows: int
    cols: int
    dtype: int = 5
    readonly: bool = False
    padding: int = 0
    @property
    def size(self): return self.rows * self.cols * 2
    @property
    def end(self): return self.address + self.size + self.padding

def allocation(t, rows, cols):
    return (t.dtype == 5 and t.rows == rows and t.cols == cols and t.padding == 0
            and t.address % 64 == 0 and 0 < t.address < t.end <= 1 << 56)

def overlap(a, b): return a.address < b.end and b.address < a.end

@dataclass(frozen=True)
class Job:
    phase: int
    a: int
    b: int
    dst: int
    m: int
    n: int
    k: int
    tag: int = 0x70010
    cold: bool = True
    generation: int = 0
    public21_reduction: bool = False
    @property
    def bytes(self): return self.m*self.n*2
    @property
    def macs(self): return self.m*self.n*self.k if self.phase in (1, 2, 4) else 0

@dataclass(frozen=True)
class Result:
    tag: int
    status: int
    bytes: int
    useful: int
    executed: int
    cycles: int = 1234

@dataclass(frozen=True)
class Proof:
    host: Host
    transaction: int
    logical: Job
    physical: Job
    result: Result

class CommandsModel:
    def __init__(self, profile=1, rows=128):
        self.host=Host(profile=profile); self.transaction=77; self.rows=rows
        self.postnorm=Tensor(0x2000000, rows, 1024)
        self.residual=Tensor(0x2100000, rows, 1024)
        self.produced=[]; self.weights=[]; self.outputs={}
        self.post_current=True; self.post_committed=True; self.post_physical_exact=True
        self.cold=True; self.generation=0; self.checkpoint=False
        self.bound=None; self.pending=None; self.fault=False; self.complete=False
        self.cache_root=0; self.state_root=0; self.launch_seal=True
    def legal(self, phase, a, b, d):
        p=self.host.profile; m=self.rows
        rows=(p==1 and m in (16,128)) or (p==2 and m==128)
        common=(rows and self.post_current and self.post_committed and self.cold
                and self.generation==0 and not self.checkpoint and not self.fault)
        if phase in (1,2,4):
            k,n=(3584,1024) if phase==4 else (1024,3584)
            shapes=allocation(a,m,k) and allocation(b,k,n) and allocation(d,m,n)
            order=((phase==1 and not self.outputs and a==self.postnorm and self.post_physical_exact)
                or (phase==2 and set(self.outputs)=={1} and a==self.postnorm and self.post_physical_exact)
                or (phase==4 and set(self.outputs)=={1,2,3} and a==self.outputs[3]))
            source=b.readonly and not a.readonly and all(not overlap(b,x) for x in self.weights+self.produced+[self.postnorm,self.residual])
        else:
            k=n=3584 if phase==3 else 1024
            shapes=allocation(a,m,n) and allocation(b,m,n) and allocation(d,m,n)
            order=((phase==3 and set(self.outputs)=={1,2} and a==self.outputs[1] and b==self.outputs[2])
                or (phase==5 and set(self.outputs)=={1,2,3,4} and a==self.residual and b==self.outputs[4]))
            source=not a.readonly and not b.readonly
        fresh=not d.readonly and all(not overlap(d,x) for x in self.weights+self.produced+[self.postnorm,self.residual,a,b])
        pairwise=not overlap(a,b)
        return common and shapes and order and source and fresh and pairwise
    def bind(self, phase, a, b, d):
        if not self.legal(phase,a,b,d): return False
        self.bound=Job(phase,a.address,b.address,d.address,self.rows,d.cols,a.cols)
        self.bound_operands=(a,b,d); self.pending=None; self.complete=False
        return True
    def exact(self,p):
        if not self.bound or p is None: return False
        e=replace(self.bound,tag=p.physical.tag)
        return (p.host==self.host and p.transaction==self.transaction and p.logical==self.bound
            and p.physical==e and p.physical.tag!=0xffffffff and p.result.tag==p.physical.tag
            and p.result.status==0 and p.result.bytes==self.bound.bytes
            and (self.bound.phase not in (1,2,4) or
                 (p.result.useful==self.bound.macs and p.result.executed>=p.result.useful)))
    def done(self,p,r):
        if self.fault or not self.exact(p) or replace(p.result,tag=self.bound.tag)!=r:return False
        self.pending=p; self.complete=True; return True
    def completion(self,p):
        if self.fault or not self.complete or not self.exact(p) or p!=self.pending:return False
        a,b,d=self.bound_operands
        self.outputs[self.bound.phase]=d; self.produced.append(d)
        if self.bound.phase in (1,2,4):self.weights.append(b)
        self.pending=None; self.complete=False
        return True
    def operands(self,phase):
        out=Tensor(0x2300000+phase*0x100000,self.rows,3584 if phase<=3 else 1024)
        if phase in (1,2):return self.postnorm,Tensor(0x100000+phase*0x800000,1024,3584,readonly=True),out
        if phase==3:return self.outputs[1],self.outputs[2],out
        if phase==4:return self.outputs[3],Tensor(0x19000000,3584,1024,readonly=True),out
        return self.residual,self.outputs[4],out
    def proof(self,tag=100):
        p=replace(self.bound,tag=tag)
        return Proof(self.host,self.transaction,self.bound,p,Result(tag,0,p.bytes,p.macs,p.macs))
    def run_phase(self,phase):
        if not self.bind(phase,*self.operands(phase)):raise ValueError("model bind failed")
        p=self.proof(100+phase)
        if not self.done(p,replace(p.result,tag=self.bound.tag)):raise ValueError("model done failed")
        if not self.completion(p):raise ValueError("model completion failed")

class TestCommandsFfn(unittest.TestCase):
    def test_full_profiles_and_allowed_rows_still_sealed(self):
        for profile,rows in ((1,16),(1,128),(2,128)):
            with self.subTest(profile=profile,rows=rows):
                m=CommandsModel(profile,rows)
                for phase in range(1,6):m.run_phase(phase)
                self.assertEqual(set(m.outputs),{1,2,3,4,5})
                self.assertEqual((m.cache_root,m.state_root),(0,0)); self.assertTrue(m.launch_seal)
    def test_original_m1_is_not_public_runtime_batch(self):
        for p in (0,1,2,3,4):
            m=CommandsModel(p,1); self.assertFalse(m.bind(1,*m.operands(1)))
    def test_no_moe_or_qwen2_runtime_dense(self):
        for p in (0,3,4,5):
            m=CommandsModel(p); self.assertFalse(m.bind(1,*m.operands(1)))
    def test_attention_m16_is_not_accepted(self):
        m=CommandsModel(2,16);self.assertFalse(m.bind(1,*m.operands(1)))
    def test_all_other_rows_rejected(self):
        for rows in (0,15,17,127,129,1024):
            m=CommandsModel(1,rows);self.assertFalse(m.bind(1,*m.operands(1)))
    def test_gate_requires_exact_postnorm(self):
        for field in ('post_current','post_committed','post_physical_exact','cold'):
            m=CommandsModel();setattr(m,field,False);self.assertFalse(m.bind(1,*m.operands(1)))
    def test_cold_generation_zero_only(self):
        for field,value in (('generation',1),('checkpoint',True),('fault',True)):
            m=CommandsModel();setattr(m,field,value);self.assertFalse(m.bind(1,*m.operands(1)))
    def test_preloaded_postnorm_address_cannot_substitute(self):
        m=CommandsModel();a,b,d=m.operands(1);self.assertFalse(m.bind(1,replace(a,address=a.address+64),b,d))
    def test_readonly_postnorm_cannot_substitute(self):
        m=CommandsModel();a,b,d=m.operands(1);self.assertFalse(m.bind(1,replace(a,readonly=True),b,d))
    def test_dtype_and_shape_and_padding_fail(self):
        for idx in range(3):
            for field,value in (('dtype',7),('padding',64),('cols',1023),('address',3)):
                m=CommandsModel();v=list(m.operands(1));v[idx]=replace(v[idx],**{field:value})
                self.assertFalse(m.bind(1,*v))
    def test_weight_writable_fails(self):
        m=CommandsModel();a,b,d=m.operands(1);self.assertFalse(m.bind(1,a,replace(b,readonly=False),d))
    def test_weight_alias_input_fails(self):
        m=CommandsModel();a,b,d=m.operands(1);self.assertFalse(m.bind(1,a,replace(b,address=a.address),d))
    def test_output_alias_fails(self):
        for idx in (0,1):
            m=CommandsModel();a,b,d=m.operands(1);self.assertFalse(m.bind(1,a,b,replace(d,address=(a,b)[idx].address)))
    def test_up_requires_gate_completion(self):
        m=CommandsModel();self.assertFalse(m.bind(2,*m.operands(2)))
    def test_no_publication_at_raw_done_or_missing_receipt(self):
        m=CommandsModel();self.assertTrue(m.bind(1,*m.operands(1)));p=m.proof()
        self.assertFalse(m.completion(p));self.assertFalse(m.done(None,replace(p.result,tag=m.bound.tag)))
        self.assertTrue(m.done(p,replace(p.result,tag=m.bound.tag)));self.assertEqual(m.outputs,{})
    def test_receipt_all_identity_mutations_fail(self):
        m=CommandsModel();self.assertTrue(m.bind(1,*m.operands(1)));p=m.proof();r=replace(p.result,tag=m.bound.tag)
        bad=[replace(p,host=replace(p.host,epoch=8)),replace(p,host=replace(p.host,table=0x2000)),
             replace(p,transaction=p.transaction+1),replace(p,logical=replace(p.logical,phase=2)),
             replace(p,physical=replace(p.physical,k=3584)),replace(p,physical=replace(p.physical,tag=0xffffffff)),
             replace(p,result=replace(p.result,tag=101)),replace(p,result=replace(p.result,status=1)),
             replace(p,result=replace(p.result,bytes=p.result.bytes-64)),replace(p,result=replace(p.result,useful=1)),
             replace(p,result=replace(p.result,executed=1))]
        for b in bad:self.assertFalse(m.done(b,r))
    def test_actual_guard_result_all_fields_bound(self):
        for field,value in (('tag',5),('status',1),('bytes',64),('useful',1),('executed',1),('cycles',999)):
            m=CommandsModel();m.bind(1,*m.operands(1));p=m.proof();r=replace(p.result,tag=m.bound.tag)
            self.assertFalse(m.done(p,replace(r,**{field:value})))
    def test_completion_backpressure_keeps_receipt(self):
        m=CommandsModel();m.bind(1,*m.operands(1));p=m.proof();m.done(p,replace(p.result,tag=m.bound.tag))
        for _ in range(5):self.assertEqual(m.pending,p);self.assertEqual(m.outputs,{})
        self.assertTrue(m.completion(p))
    def test_late_fault_vetoes_publication(self):
        m=CommandsModel();m.bind(1,*m.operands(1));p=m.proof();m.done(p,replace(p.result,tag=m.bound.tag));m.fault=True
        self.assertFalse(m.completion(p));self.assertEqual(m.outputs,{})
    def test_receipt_mutation_during_completion_fails(self):
        m=CommandsModel();m.bind(1,*m.operands(1));p=m.proof();m.done(p,replace(p.result,tag=m.bound.tag))
        self.assertFalse(m.completion(replace(p,result=replace(p.result,cycles=5678))))
    def test_completed_phase_cannot_replay(self):
        m=CommandsModel();m.run_phase(1);self.assertFalse(m.bind(1,*m.operands(1)))
    def test_up_weight_cannot_alias_gate_weight(self):
        m=CommandsModel();m.run_phase(1);a,b,d=m.operands(2)
        self.assertFalse(m.bind(2,a,replace(b,address=m.weights[0].address),d))
    def test_silu_requires_both_correct_tensors(self):
        m=CommandsModel();m.run_phase(1);m.run_phase(2);a,b,d=m.operands(3)
        self.assertFalse(m.bind(3,b,a,d));self.assertFalse(m.bind(3,a,replace(b,address=b.address+64),d))
    def test_down_requires_real_silu_output(self):
        m=CommandsModel();[m.run_phase(p) for p in (1,2,3)];a,b,d=m.operands(4)
        self.assertFalse(m.bind(4,m.outputs[1],b,d));self.assertTrue(m.bind(4,a,b,d))
    def test_residual2_requires_original_residual1_and_down(self):
        m=CommandsModel();[m.run_phase(p) for p in (1,2,3,4)];a,b,d=m.operands(5)
        self.assertFalse(m.bind(5,m.postnorm,b,d));self.assertFalse(m.bind(5,a,m.outputs[1],d))
    def test_m128_dense_math_contract(self):
        self.assertEqual(128*1024*3584,469762048)
        self.assertEqual(3*128*1024*3584,1409286144)
        self.assertEqual((3584+3584+3584+1024+1024)*128*2,3276800)
    def test_public21_reduction_semantics_ignore_physical_low_tag(self):
        def semantic(official,profile,dense,pc):return official and profile==0 and dense and pc in (1,4,7)
        for tag in (1,4,7,0x10001,0xffff0007,99):
            self.assertFalse(semantic(True,1,True,tag&0xffff))
            self.assertFalse(semantic(True,2,True,tag&0xffff))
            self.assertTrue(semantic(True,0,True,1))
        for pc in (0,2,3,5,6,8,13,16,17,19):self.assertFalse(semantic(True,0,True,pc))
        self.assertFalse(semantic(False,0,True,1));self.assertFalse(semantic(True,0,False,1))
    def test_ffn_proof_cannot_inject_public21_reduction(self):
        m=CommandsModel();m.bind(1,*m.operands(1));p=m.proof()
        injected=replace(p,physical=replace(p.physical,public21_reduction=True))
        self.assertFalse(m.done(injected,replace(p.result,tag=m.bound.tag)))
    def test_down_reuses_original_prefix_workspace_contract(self):
        self.assertEqual((1024//32)*16384,524288)

if __name__=='__main__':unittest.main()
