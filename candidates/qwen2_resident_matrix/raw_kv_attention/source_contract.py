"""Source-bound PV16 address traces only; never execute/substitute arithmetic."""
import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
SCALA='chisel/continuous_prefill/src/main/scala/heteronpu/continuous/'
OFFICIAL='candidates/qwen2_resident_matrix/official_bf16/owners.py'
POLICY='candidates/qwen2_resident_matrix/official_bf16/chisel_policy.patch'

def need(ok,message):
    if not ok:raise ValueError(message)
def sha(data):return hashlib.sha256(data).hexdigest()
def blob(data):return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
def attention_method():
    tree=ast.parse((ROOT/OFFICIAL).read_text())
    classes=[n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='OfficialAttentionOwner']
    need(len(classes)==1,'exact PV16 owner class')
    methods=[n for n in classes[0].body if isinstance(n,ast.FunctionDef) and n.name=='_attention']
    need(len(methods)==1,'original attention method')
    return methods[0]

def check(verify=True):
    pins=json.loads((HERE/'source_pins.json').read_text()) if verify else None
    if verify:
        for p,h in pins['inputs'].items():need(blob((ROOT/p).read_bytes())==h,'source drift: '+p)
    method=attention_method();body=ast.unparse(method)
    for token in ('for token in range(j.m):','for head in range(12):','kv_head = head // 6',
        'for depth in range(0, 128, 16):','for key in range(token + 1):',
        'for col in range(0, 128, 16):','for key, probability in enumerate(probabilities):',
        'self._read(j.b + (key * 256 + kv_head * 128 + depth) * 4)',
        'self._read(j.c + (key * 256 + kv_head * 128 + col) * 4)',
        "dot = self._op('bf', total)","self._op('bf', self._op('mul', dot, 1035273459))"):
        need(token in body,'PV16 source contract changed: '+token)
    core=(ROOT/(SCALA+'Qwen2Block.scala')).read_text()
    for token in ('when(state===st("attLocal")){read(ptr("k",key.pad(32)*s.kv.U+kvHead*s.headDim.U+depth),"attDot")}',
                  'when(state===st("attProbScale")){probability:=scalarValue;read(ptr("v",key.pad(32)*s.kv.U+kvHead*s.headDim.U+col),"attPVCompute")}',
                  'matrixRequest.bits.opcode:=Mux(dot,0x23.U,Mux(pv,0x24.U,0x20.U))'):
        need(token in core,'original Chisel consumer drift')
    # Apply only the TWO original Attention numeric-policy hunks. No core or
    # kernel implementation is generated/replaced by this model-only checker.
    target=SCALA+'Qwen2Block.scala';head='--- a/'+target+'\n'
    text=(ROOT/POLICY).read_text().split(head)[1].split('\ndiff --git ')[0]
    hunks=[h for h in re.split(r'(?=^@@ )',text,flags=re.M)[1:]
           if '\n-  when(state===st("attReduceDone"))' in h or '\n-  when(state===st("attPVWrite"))' in h]
    need(len(hunks)==2,'two exact Attention materialization hunks')
    with tempfile.TemporaryDirectory(prefix='attention-contract-') as d:
        dest=Path(d)/target;dest.parent.mkdir(parents=True);dest.write_text(core)
        patch=head+'+++ b/'+target+'\n'+''.join(hunks)
        subprocess.run(['patch','--batch','--fuzz=0','-p1'],input=patch,text=True,cwd=d,check=True,capture_output=True,timeout=10)
        final=dest.read_text();region=final.split('  // Causal GQA.')[1].split('  // Numerically stable SiLU')[0]
    result=dict(pv16_method_ast_sha256=sha(body.encode()),attention_region_sha256=sha(region.encode()))
    if verify:need(result==pins['contracts'],'source method/region drift')
    return result

def kv_reads(tokens,k_base,v_base):
    """Project only the pinned source's address-loop order, not its arithmetic.

    M1/M2 are short consumer traces; all4096 line coverage is a separate capacity
    transport test and is never described as actual M128 inference execution.
    """
    if type(tokens) is not int or not 1<=tokens<=128:raise ValueError('M1..128')
    for token in range(tokens):
        for head in range(12):
            kv_head=head//6
            for key in range(token+1):
                for depth in range(0,128,16):
                    yield ('k',k_base+4*(key*256+kv_head*128+depth))
            for col in range(0,128,16):
                for key in range(token+1):
                    yield ('v',v_base+4*(key*256+kv_head*128+col))

if __name__=='__main__':
    check();print('PASS original PV16 source/address contract; arithmetic and RTL NOT RUN')
