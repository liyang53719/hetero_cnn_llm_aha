#!/usr/bin/env python3
"""Independent read-only public-ABI and completion audit of a completed owner run.

This consumes stored evidence. It neither builds a fixture nor provides DUT
memory, and cannot establish trusted execution solely from user-authored logs.
"""
from __future__ import annotations
import argparse, hashlib, json, re, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'src'))
from heteronpu.command import Command128, Engine, Opcode, NULL_INDEX
from heteronpu.descriptor_chain import DescriptorRecord, RecordType, MatrixAux, SfuProgram, TensorDType, validate_descriptor_chain
from verify_host_block_gate import verify, tagged, require


def audit(out:Path) -> dict:
    numeric=verify(out,False)
    fixture=json.loads((out/'fixture/manifest.json').read_text())
    L=fixture.get('layers',1);C=21*L;NREC=215*L
    T=fixture['tokens'];H,F,G,J,D=(fixture['shape'][x] for x in ('H','F','HEADS','KVHEADS','HD'));K=J*D
    raw=(out/'tensors/host_commands.bin').read_bytes();db=(out/'tensors/host_descriptors.bin').read_bytes()
    require(fixture['descriptors']==NREC and fixture['commands']==C,'fixed scoped table counts')
    require(not any(raw[C*16:]) and not any(db[NREC*16:]),'nonzero table padding')
    records={i:DescriptorRecord.unpack(int.from_bytes(db[i*16:i*16+16],'little')) for i in range(NREC)}
    dims={1:(T,H,H),4:(T,K,H),7:(T,K,H),10:(T,T,D),12:(T,D,T),13:(T,H,H),16:(T,F,H),17:(T,F,H),19:(T,H,F)}
    seen=set();commands=[]
    for pc,op in enumerate(fixture['schedule']):
        local=pc%21;chunk=raw[pc*16:pc*16+16];c=Command128.from_bytes(chunk)
        engine=Engine.MATRIX if local in dims else (Engine.KV if local==9 else Engine.SFU_CGRA)
        require(c.to_bytes()==chunk and c.engine==engine and c.flags==0,'owner/flags/roundtrip')
        chains=[]
        for index,name in zip((c.src0,c.src1,c.dst),(op['a'],op['b'],op['dst'])):
            if index==NULL_INDEX:require(local==11 and name is None,'null operand');chains.append([]);continue
            chain=validate_descriptor_chain(index,records);chains.append(chain)
            types=[RecordType.TENSOR_BASE,RecordType.SHAPE4,RecordType.STRIDE3]
            if index==c.src0 and local!=9:types+=([RecordType.MATRIX_OP,RecordType.MATRIX_AUX] if local in dims else [RecordType.SFU_PROGRAM])
            require([r.record_type for _,r in chain]==types,'typed record sequence')
            for i,r in chain:
                require(i not in seen and r.flags==0 and r.subtype==0,'shared/reserved descriptor')
                require(r.pack().to_bytes(16,'little')==db[16*i:16*i+16],'record roundtrip')
                seen.add(i)
            t=fixture['tensors'][name];a=t['address'];rank=len(t['dims']);shape=tuple(t['dims'])+(1,)*(4-rank)
            base=(a&((1<<48)-1))|(t.get('storage_dtype',7)<<52)|(rank<<60)|((a>>48)<<64)
            require(chain[0][1].payload==base,'tensor address/rank/space/layout/dtype')
            require(chain[1][1].payload==sum(v<<(18*i) for i,v in enumerate(shape)),'shape encoding')
            strides=(shape[1]*shape[2]*shape[3],shape[2]*shape[3],shape[3])
            require(chain[2][1].payload==sum(v<<(24*i) for i,v in enumerate(strides)),'element stride encoding')
        if local in dims:
            m,n,k=dims[local];payload=m|(n<<16)|(k<<32)|(int(local==10)<<59)
            require(chains[0][3][1].payload==payload,'matrix geometry/dataflow/transpose/quant policy')
            require(MatrixAux.from_record(chains[0][4][1])==MatrixAux(full_c=True),'matrix auxiliary policy')
        elif local!=9:
            expected=SfuProgram(int(c.opcode),1 if local==11 else 2,input_dtype=TensorDType.FP32,output_dtype=TensorDType.FP32)
            require(SfuProgram.from_record(chains[0][3][1])==expected,'SFU semantic policy')
        commands.append({'pc':pc,'opcode':c.opcode.name,'engine':int(engine),'wait':c.event_wait,'signal':c.event_signal})
    require(seen==set(range(NREC)),'unused or missing descriptor record')
    log=(out/'run.log').read_text();completions=tagged(log,'OWNER_COMPLETION');tensors=tagged(log,'OWNER_TENSOR')
    prior=-1
    for pc,c in enumerate(completions):
        require(int(c['owner'])==commands[pc]['engine'],'completion owner mismatch')
        cyc=int(c['cycle']);require(cyc>prior,'nonmonotonic completion cycle');prior=cyc
        expected=sum(fixture['tensors'][n]['words']*4 for n in fixture['schedule'][pc]['outputs'])
        require(int(c['write_ack_bytes'])==expected,'completion write-ACK byte mismatch')
        require(all(int(t['cycle'])==cyc for t in tensors if int(t['pc'])==pc),'tensor not checked at corresponding completion')
    result={'status':'PASS_OWNER_PUBLIC_ABI_AND_NUMERICAL_RECHECK','commands':commands,'descriptor_records':NREC,
            'checked_fp32':numeric['checked_fp32'],'tokens':T,'hidden':H,'ffn':F,
            'all_tensor_bytes_rechecked':True,'all_command_policy_fields_rechecked':True,
            'layers':L,'attention_fusion':[[21*i+10,21*i+11,21*i+12] for i in range(L)],'official_weights':False,'full_model_q1024':False,
            'tables_sha256':{'commands':hashlib.sha256(raw).hexdigest(),'descriptors':hashlib.sha256(db).hexdigest()}}
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('evidence',type=Path);p.add_argument('--output',type=Path);a=p.parse_args()
    try:
        result=audit(a.evidence)
        text=json.dumps(result,indent=2)+'\n'
        if a.output:
            with a.output.open('x') as f:f.write(text)
        print(text,end='')
    except (ValueError,OSError,KeyError,TypeError) as e:raise SystemExit('OWNER_ABI_REJECTED: '+str(e))
