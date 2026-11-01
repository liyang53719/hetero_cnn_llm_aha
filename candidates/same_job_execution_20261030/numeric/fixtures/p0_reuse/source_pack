#!/usr/bin/env python3
"""Public ABI fixture for the existing 21-op Qwen2 schedule (synthetic weights).

No alternative Host opcode is introduced. This is *not* the original GGUF
binary descriptor image. It binds FP32-container/BF16-compute tensors under a
scoped Qwen2 recipe; QK+SOFTMAX+PV logical intermediates are fused and forbidden
as standalone DDR inputs. Only readonly fixture bytes are initialized by Host.
"""
from __future__ import annotations
import argparse, hashlib, json, re, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'src'))
from heteronpu.command import Command128,Engine,Opcode,NULL_INDEX
from heteronpu.descriptor_chain import DescriptorRecord,RecordType,MatrixAux,SfuProgram,TensorDType,validate_descriptor_chain
from heteronpu.gemmini_descriptor_v2 import tensor_base_record,shape4_record,stride3_record,matrix_op_record
from heteronpu.l9_transport_contract import EXPECTED_LAYER0

def align(n:int)->int:return (n+63)&~63

def pack(shape:dict[str,int],tokens:int,out:Path,relocate:int=0)->dict:
    if not 1<=tokens<=shape['MAX_TOKENS']:raise ValueError('invalid token count')
    if out.exists():raise ValueError('new fixture directory required')
    H,F,G,J,D=(shape[x] for x in ('H','F','HEADS','KVHEADS','HD'));K=J*D
    B=0x100000000+align(relocate);meta=B+65536;cur=meta
    tensors={};locations=[]
    def alloc(name, dims, readonly=True, virtual=False):
        nonlocal cur
        dims=tuple(dims);words=1
        for n in dims:words*=n
        cur=align(cur)+64 # a poisoned guard beat separates *every* allocation
        tensors[name]={'address':cur,'dims':dims,'words':words,'readonly':readonly,'virtual':virtual}
        locations.append(name);cur+=words*4
    for name,k,n in [('wq',H,H),('wk',H,K),('wv',H,K),('wo',H,H),('wg',H,F),('wu',H,F),('wd',F,H)]:alloc(name,(k,n))
    for name,n in [('gamma0',H),('gamma1',H),('bq',H),('bk',K),('bv',K)]:alloc(name,(1,n))
    alloc('rope',(2,shape['MAX_TOKENS'],D//2));alloc('x',(tokens,H))
    scratch=align(cur)+64;cur=scratch
    for name,n in [('n0',H),('qraw',H),('qr',H),('q',H),('kraw',K),('kr',K),('k',K),('vraw',K),('v',K)]:alloc(name,(tokens,n),False)
    alloc('kv',(2,tokens,K),False)
    tensors['cache_k']={'address':tensors['kv']['address'],'dims':(tokens,K),'words':tokens*K,'readonly':False,'virtual':False}
    tensors['cache_v']={**tensors['cache_k'],'address':tensors['kv']['address']+tokens*K*4}
    alloc('scores',(G,tokens,tokens),False,True);alloc('probabilities',(G,tokens,tokens),False,True)
    for name,n in [('att',H),('o',H),('r',H),('n1',H),('gate',F),('up',F),('act',F),('down',H),('y',H)]:alloc(name,(tokens,n),False)
    limit=align(cur)+64
    records=[]
    def chain(name,extra=()):
        t=tensors[name];dims=t['dims']+(1,)*(4-len(t['dims']));root=len(records)
        strides=(dims[1]*dims[2]*dims[3],dims[2]*dims[3],dims[3])
        rr=[tensor_base_record(t['address'],dtype=7,rank=len(t['dims']),next_index=root+1),
            shape4_record(dims,next_index=root+2),stride3_record(strides,next_index=root+3 if extra else NULL_INDEX)]
        for j,r in enumerate(extra):rr.append(DescriptorRecord(r.record_type,r.subtype,r.flags,root+4+j if j+1<len(extra) else NULL_INDEX,r.payload))
        records.extend(rr);return root
    cmds=[];schedule=[]
    def emit(op,a,b,d,extra=(),outputs=None):
        opcode=Opcode[op];engine=Engine.MATRIX if op.startswith('MATRIX') else (Engine.KV if op.startswith('KV_') else Engine.SFU_CGRA)
        pc=len(cmds);roots=[chain(a,extra),chain(b) if b else NULL_INDEX,chain(d)]
        c=Command128(opcode,engine,event_wait=pc,event_signal=pc+1,src0=roots[0],src1=roots[1],dst=roots[2]);cmds.append(c)
        schedule.append({'pc':pc,'operation':EXPECTED_LAYER0[pc].operation,'opcode':op,'owner':engine.name,'roots':roots,'a':a,'b':b,'dst':d,'outputs':outputs or ([d] if not tensors[d]['virtual'] else [])})
    def sfu(op,a,b,d):emit(op,a,b,d,(SfuProgram(int(Opcode[op]),2 if b else 1,input_dtype=TensorDType.FP32,output_dtype=TensorDType.FP32).to_record(),))
    def mat(op,a,b,d,m,n,k,tb=False):emit(op,a,b,d,(matrix_op_record(m=m,n=n,k=k,dataflow=0,transpose_b=tb),MatrixAux(full_c=True).to_record()))
    sfu('SFU_RMSNORM','x','gamma0','n0')
    mat('MATRIX_GEMM','n0','wq','qraw',tokens,H,H);sfu('SFU_VECTOR','qraw','bq','qr');sfu('SFU_ROPE','qr','rope','q')
    mat('MATRIX_GEMM','n0','wk','kraw',tokens,K,H);sfu('SFU_VECTOR','kraw','bk','kr');sfu('SFU_ROPE','kr','rope','k')
    mat('MATRIX_GEMM','n0','wv','vraw',tokens,K,H);sfu('SFU_VECTOR','vraw','bv','v')
    emit('KV_APPEND','k','v','kv',outputs=['cache_k','cache_v'])
    mat('MATRIX_QK','q','cache_k','scores',tokens,tokens,D,True)
    sfu('SFU_SOFTMAX','scores',None,'probabilities')
    mat('MATRIX_PV','probabilities','cache_v','att',tokens,D,tokens)
    mat('MATRIX_GEMM','att','wo','o',tokens,H,H);sfu('SFU_VECTOR','x','o','r');sfu('SFU_RMSNORM','r','gamma1','n1')
    mat('MATRIX_GEMM','n1','wg','gate',tokens,F,H);mat('MATRIX_GEMM','n1','wu','up',tokens,F,H)
    sfu('SFU_ACTIVATION','gate','up','act');mat('MATRIX_GEMM','act','wd','down',tokens,H,F);sfu('SFU_VECTOR','r','down','y')
    if [x['opcode'].lower() for x in schedule]!=[x.opcode for x in EXPECTED_LAYER0]:raise RuntimeError('original operator schedule drift')
    for c in cmds:
        if Command128.from_bytes(c.to_bytes())!=c:raise RuntimeError('command ABI parity')
        for ix in [c.src0,c.src1,c.dst]:
            if ix!=NULL_INDEX:validate_descriptor_chain(ix,dict(enumerate(records)))
    cb=b''.join(c.to_bytes() for c in cmds); db=b''.join(r.pack().to_bytes(16,'little') for r in records)
    manifest={'schema':1,'shape':shape,'tokens':tokens,'base':B,'commandBase':B,'commandLimit':B+align(len(cb)),
        'descriptorBase':B+4096,'descriptorLimit':B+4096+align(len(db)),'metadataLimit':meta,'scratchBase':scratch,'limit':limit,
        'commands':len(cmds),'descriptors':len(records),'tensors':tensors,'allocations':locations,'schedule':schedule,
        'recipe':'qwen2-ordered-bf16-fp32-owner-v1','attention_fusion':[10,11,12],
        'scope':{'synthetic_weights':True,'gguf_descriptor_image':False,'paged_kv':False,'full_model':False,'dc':False}}
    if manifest['descriptorLimit']>meta:raise RuntimeError('metadata overflow')
    out.mkdir(parents=True)
    for name,data in [('host_commands.bin',cb.ljust(align(len(cb)),b'\0')),('host_descriptors.bin',db.ljust(align(len(db)),b'\0'))]:(out/name).write_bytes(data)
    manifest['table_sha256']={n:hashlib.sha256((out/n).read_bytes()).hexdigest() for n in ['host_commands.bin','host_descriptors.bin']}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    h=['// Generated test fixture with the retained public ISA encoder. No RTL edits.','#pragma once','#include <cstdint>','struct TensorSpec { const char* name; uint64_t address; uint64_t words; bool readonly; bool virtualValue; };']
    for name,v in [('BASE',B),('COMMAND_BASE',B),('COMMAND_LIMIT',manifest['commandLimit']),('DESC_BASE',manifest['descriptorBase']),('DESC_LIMIT',manifest['descriptorLimit']),('META_LIMIT',meta),('SCRATCH',scratch),('LIMIT',limit)]:h.append(f'static constexpr uint64_t {name}={v}ULL;')
    h.append(f'static constexpr unsigned TOKENS={tokens},DESCRIPTORS={len(records)},COMMANDS=21;')
    for name,t in tensors.items():h.append(f'static constexpr uint64_t A_{name.upper()}={t["address"]}ULL;')
    h.append('static const TensorSpec ALLOCATIONS[]={')
    for name in locations:
        t=tensors[name];h.append(f'{{"{name}",{t["address"]}ULL,{t["words"]}ULL,{str(t["readonly"]).lower()},{str(t["virtual"]).lower()}}},')
    h.append('};')
    (out/'owner_fixture.h').write_text('\n'.join(h)+'\n')
    return manifest

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('shape',type=Path);ap.add_argument('output',type=Path);ap.add_argument('--tokens',type=int,default=16);ap.add_argument('--relocate',type=int,default=0);a=ap.parse_args()
    text=a.shape.read_text();shape={name:int(re.search(r'\b'+name+r'=(\d+)',text).group(1)) for name in ('H','F','HEADS','KVHEADS','HD','MAX_TOKENS')}
    result=pack(shape,a.tokens,a.output,a.relocate);print(json.dumps({k:result[k] for k in ['commands','descriptors','tokens','table_sha256']},indent=2))
