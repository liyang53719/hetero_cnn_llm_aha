#!/usr/bin/env python3
"""Optional, test-only 1KiB Dense-weight alignment using the public descriptor ABI.

Create a NEW fixture; leave the frozen unaligned comparison untouched. All
opcodes, shapes, order, weights and Y->X aliases remain identical. Only tensor
addresses / region extents change. This is not a GGUF weight packer.
"""
from __future__ import annotations
import argparse, copy, hashlib, json, re, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'src'))
from heteronpu.command import Command128, NULL_INDEX
from heteronpu.descriptor_chain import DescriptorRecord, RecordType, validate_descriptor_chain


def require(ok,message):
    if not ok:raise ValueError(message)


def align(n,a=64):return (n+a-1)&~(a-1)


def transform(source:Path,target:Path,weight_alignment:int=1024)->dict:
    require(type(weight_alignment) is int and weight_alignment in (64,1024),'supported alignment')
    require(not target.exists() and not target.is_symlink(),'target must be new')
    original=json.loads((source/'manifest.json').read_text());m=copy.deepcopy(original)
    require(m.get('layers')==2 and m['tokens']==16 and m['commands']==42 and m['descriptors']==430,'fixed real2 or tiny2 fixture required')
    require(m['layer_weight_salts']==[0,17],'different fixed layer weights required')
    names=m['allocations'];require(len(names)==len(set(names)),'duplicate allocations')
    old=m['tensors'];weights={x['b'] for x in m['schedule'] if x['opcode']=='MATRIX_GEMM'}
    require(len(weights)==14 and all(old[n]['readonly'] for n in weights),'not seven immutable Dense weights per layer')
    readonly=[n for n in names if old[n]['readonly']]
    writable=[n for n in names if not old[n]['readonly']]
    require(names==readonly+writable,'allocator order/permissions changed')
    cursor=m['metadataLimit'];new={}
    for n in readonly:
        cursor=align(align(cursor)+64,weight_alignment if n in weights else 64)
        new[n]={**old[n],'address':cursor};cursor+=old[n]['words']*4
    scratch=align(cursor)+64;cursor=scratch
    for n in writable:
        cursor=align(cursor)+64;new[n]={**old[n],'address':cursor};cursor+=old[n]['words']*4
    limit=align(cursor)+64;require(limit<=1<<56,'address overflow')
    for n,t in old.items():
        if n in new:continue
        parents=[x for x in names if old[x]['address']<=t['address'] and
                 t['address']+4*t['words']<=old[x]['address']+4*old[x]['words']]
        require(len(parents)==1,'ambiguous tensor view '+n)
        parent=parents[0];new[n]={**t,'address':new[parent]['address']+t['address']-old[parent]['address']}
    require(new['l1_x']['address']==new['l0_y']['address'] and 'l1_x' not in names,'lost actual layer boundary alias')
    raw=bytearray((source/'host_descriptors.bin').read_bytes())
    require(len(raw)==m['descriptorLimit']-m['descriptorBase'],'descriptor size')
    touched=set()
    address_mask=((1<<48)-1)|(255<<64)
    for op in m['schedule']:
        for name,root in zip((op['a'],op['b'],op['dst']),op['roots']):
            if name is None:
                require(root==NULL_INDEX,'missing descriptor operand');continue
            require(root not in touched,'unexpected shared descriptor');touched.add(root)
            r=DescriptorRecord.unpack(int.from_bytes(raw[16*root:16*root+16],'little'))
            require(r.record_type==RecordType.TENSOR_BASE,'root is not tensor base')
            a=new[name]['address'];p=(r.payload&~address_mask)|(a&((1<<48)-1))|((a>>48)<<64)
            raw[16*root:16*root+16]=DescriptorRecord(r.record_type,r.subtype,r.flags,r.next_index,p).pack().to_bytes(16,'little')
    records={i:DescriptorRecord.unpack(int.from_bytes(raw[16*i:16*i+16],'little')) for i in range(m['descriptors'])}
    cb=(source/'host_commands.bin').read_bytes()
    for i,op in enumerate(m['schedule']):
        command=Command128.from_bytes(cb[16*i:16*i+16]);require(command.to_bytes()==cb[16*i:16*i+16],'command changed')
        for root in (command.src0,command.src1,command.dst):
            if root!=NULL_INDEX:validate_descriptor_chain(root,records)
    mapping={old[n]['address']:new[n]['address'] for n in old}
    require(all(mapping[old[n]['address']]==new[n]['address'] for n in old),'alias mapping conflict')
    mapping[m['scratchBase']]=scratch;mapping[m['limit']]=limit
    header=(source/'owner_fixture.h').read_text()
    header=re.sub(r'\b(\d+)ULL\b',lambda x:str(mapping.get(int(x[1]),int(x[1])))+'ULL',header)
    m.update(tensors=new,scratchBase=scratch,limit=limit)
    m['alignment_transform']={'weight_alignment_bytes':weight_alignment,
                              'source_manifest_sha256':hashlib.sha256((source/'manifest.json').read_bytes()).hexdigest(),
                              'commands_unchanged':True,'host_layer_copy':False}
    m['table_sha256']={'host_commands.bin':hashlib.sha256(cb).hexdigest(),
                      'host_descriptors.bin':hashlib.sha256(raw).hexdigest()}
    target.mkdir(parents=True)
    (target/'host_commands.bin').write_bytes(cb);(target/'host_descriptors.bin').write_bytes(raw)
    (target/'owner_fixture.h').write_text(header);(target/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')
    return m


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('target',type=Path);p.add_argument('--weight-alignment',type=int,default=1024);a=p.parse_args()
    try:
        m=transform(a.source,a.target,a.weight_alignment)
        print(json.dumps({'status':'ALIGNED_FIXTURE_CREATED_NOT_HARDWARE_PASS','alignment':m['alignment_transform'],'limit':m['limit']},indent=2))
    except (ValueError,OSError,KeyError,TypeError) as e:raise SystemExit('ALIGNMENT_FIXTURE_REJECTED: '+str(e))
