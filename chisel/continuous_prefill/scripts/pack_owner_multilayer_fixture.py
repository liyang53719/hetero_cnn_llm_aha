#!/usr/bin/env python3
"""Build two/three distinct-weight layers as ONE original-opcode Host graph.

No BLOCK opcode, intermediate Host copy or memory reset. All weights are in the
initial read-only region; layer n's X descriptor aliases layer n-1's actual Y.
The existing maxCommands=64 endpoint supports at most three 21-command layers.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from pack_owner_block_fixture import pack,align
from heteronpu.command import Command128,Engine,Opcode,NULL_INDEX
from heteronpu.descriptor_chain import DescriptorRecord,MatrixAux,SfuProgram,TensorDType,validate_descriptor_chain
from heteronpu.gemmini_descriptor_v2 import tensor_base_record,shape4_record,stride3_record,matrix_op_record


def require(ok,message):
    if not ok:raise ValueError(message)


def pack_layers(shape,tokens,layers,out,relocate=0):
    require(type(layers) is int and 1<=layers<=3,'one to three layers within frozen 64-command capacity')
    require(type(tokens) is int and 1<=tokens<=shape['MAX_TOKENS'],'token capacity')
    require(type(relocate) is int and relocate>=0 and relocate%64==0,'aligned nonnegative relocation')
    require(not out.exists(),'new fixture output required')
    out.mkdir(parents=True)
    template=pack(shape,tokens,out/'single_layer_template')
    base=0x100000000+relocate;meta=base+65536;cur=meta
    tensors={};allocations=[];layer_names=[]
    def alloc(name,t):
        nonlocal cur
        cur=align(cur)+64;tensors[name]={**t,'address':cur};allocations.append(name);cur+=4*t['words']
    # All weights are immutable before the one and only Host graph launch.
    for layer in range(layers):
        names={n:f'l{layer}_{n}' for n in template['tensors']};layer_names.append(names)
        for n in template['allocations']:
            t=template['tensors'][n]
            if t['readonly'] and (n!='x' or layer==0):alloc(names[n],t)
    scratch=align(cur)+64;cur=scratch
    for layer,names in enumerate(layer_names):
        for n in template['allocations']:
            t=template['tensors'][n]
            if not t['readonly']:alloc(names[n],t)
        for n,offset in [('cache_k',0),('cache_v',tokens*shape['KVHEADS']*shape['HD']*4)]:
            tensors[names[n]]={**template['tensors'][n],'address':tensors[names['kv']]['address']+offset}
        if layer:
            # Descriptor alias only. The test must not memcpy a result here.
            tensors[names['x']]={**tensors[layer_names[layer-1]['y']],'readonly':False}
    limit=align(cur)+64;require(limit<=1<<56,'outside physical address contract')
    records=[];commands=[];schedule=[]
    old_records=[DescriptorRecord.unpack(int.from_bytes((out/'single_layer_template/host_descriptors.bin').read_bytes()[16*i:16*i+16],'little')) for i in range(template['descriptors'])]
    def chain(name,extra):
        t=tensors[name];dims=tuple(t['dims'])+(1,)*(4-len(t['dims']));root=len(records)
        strides=(dims[1]*dims[2]*dims[3],dims[2]*dims[3],dims[3])
        records.extend([tensor_base_record(t['address'],dtype=7,rank=len(t['dims']),next_index=root+1),shape4_record(dims,next_index=root+2),stride3_record(strides,next_index=root+3 if extra else NULL_INDEX)])
        for j,r in enumerate(extra):records.append(DescriptorRecord(r.record_type,r.subtype,r.flags,root+4+j if j+1<len(extra) else NULL_INDEX,r.payload))
        return root
    for layer,names in enumerate(layer_names):
        for op in template['schedule']:
            pc=len(commands);root=op['roots'][0]
            old_chain=validate_descriptor_chain(root,dict(enumerate(old_records)))
            extra=[r for _,r in old_chain[3:]]
            a=names[op['a']];b=names[op['b']] if op['b'] else None;d=names[op['dst']]
            roots=[chain(a,extra),chain(b,[]) if b else NULL_INDEX,chain(d,[])]
            c=Command128(Opcode[op['opcode']],Engine[op['owner']],event_wait=pc,event_signal=pc+1,src0=roots[0],src1=roots[1],dst=roots[2]);commands.append(c)
            schedule.append({**op,'pc':pc,'layer':layer,'operation':f'l{layer}.'+op['operation'].split('.')[-1],
                'roots':roots,'a':a,'b':b,'dst':d,'outputs':[names[x] for x in op['outputs']]})
    cb=b''.join(c.to_bytes() for c in commands);db=b''.join(r.pack().to_bytes(16,'little') for r in records)
    require(base+4096+align(len(db))<=meta,'descriptor metadata capacity')
    for c in commands:
        require(Command128.from_bytes(c.to_bytes())==c,'command ABI roundtrip')
        for r in (c.src0,c.src1,c.dst):
            if r!=NULL_INDEX:validate_descriptor_chain(r,dict(enumerate(records)))
    manifest={**template,'base':base,'commandBase':base,'commandLimit':base+align(len(cb)),
        'descriptorBase':base+4096,'descriptorLimit':base+4096+align(len(db)),
        'metadataLimit':meta,'scratchBase':scratch,'limit':limit,'layers':layers,'commands':len(commands),
        'descriptors':len(records),'tensors':tensors,'allocations':allocations,'schedule':schedule,
        'layer_names':layer_names,'layer_weight_salts':[17*i for i in range(layers)],
        'attention_fusion':[[21*i+10,21*i+11,21*i+12] for i in range(layers)],
        'scope':{'synthetic_weights':True,'single_host_launch':True,'multilayer':layers>1,
                 'host_layer_copy':False,'gguf_descriptor_image':False,'paged_kv':False,'full_model':False,'dc':False}}
    for name,data in [('host_commands.bin',cb.ljust(align(len(cb)),b'\0')),('host_descriptors.bin',db.ljust(align(len(db)),b'\0'))]:(out/name).write_bytes(data)
    manifest['table_sha256']={n:hashlib.sha256((out/n).read_bytes()).hexdigest() for n in ['host_commands.bin','host_descriptors.bin']}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    h=['// Public-ABI generated test allocation; no RTL edits.','#pragma once','#include <cstdint>',
        '#define OWNER_STACK_FIXTURE 1','struct TensorSpec {const char*name;uint64_t address,words;bool readonly,virtualValue;};',
        f'static constexpr unsigned LAYERS={layers},TOKENS={tokens},COMMANDS={len(commands)},DESCRIPTORS={len(records)};',
        'static unsigned ORACLE_LAYER=0;']
    for n,v in [('BASE',base),('COMMAND_BASE',base),('COMMAND_LIMIT',manifest['commandLimit']),('DESC_BASE',manifest['descriptorBase']),('DESC_LIMIT',manifest['descriptorLimit']),('META_LIMIT',meta),('SCRATCH',scratch),('LIMIT',limit)]:h.append(f'static constexpr uint64_t {n}={v}ULL;')
    names=sorted(template['tensors']);h.append('struct LayerAddresses {'+' '.join('uint64_t '+n+';' for n in names)+'};')
    h.append('static const LayerAddresses LAYER_ADDRS[]={')
    for ln in layer_names:h.append('{'+','.join(str(tensors[ln[n]]['address'])+'ULL' for n in names)+'},')
    h.append('};')
    for n in names:h.append(f'#define A_{n.upper()} (LAYER_ADDRS[ORACLE_LAYER].{n})')
    h.append('static const TensorSpec ALLOCATIONS[]={')
    for n in allocations:
        t=tensors[n];h.append(f'{{"{n}",{t["address"]}ULL,{t["words"]}ULL,{str(t["readonly"]).lower()},{str(t["virtual"]).lower()}}},')
    h.append('};')
    outputs=[]
    for op in schedule:
        for n in op['outputs']:outputs.append(f'{{"{n}",{tensors[n]["address"]}ULL,{tensors[n]["words"]}ULL,{op["pc"]}}}')
    h.append('#define OWNER_OUTPUT_TABLE '+','.join(outputs))
    (out/'owner_fixture.h').write_text('\n'.join(h)+'\n');return manifest


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('shape',type=Path);p.add_argument('output',type=Path);p.add_argument('--tokens',type=int,default=17);p.add_argument('--layers',type=int,default=2);p.add_argument('--relocate',type=int,default=9467985920);a=p.parse_args()
    try:
        text=a.shape.read_text();shape={n:int(re.search(r'\b'+n+r'=(\d+)',text).group(1)) for n in ['H','F','HEADS','KVHEADS','HD','MAX_TOKENS']}
        m=pack_layers(shape,a.tokens,a.layers,a.output,a.relocate);print(json.dumps({k:m[k] for k in ['layers','tokens','commands','descriptors','table_sha256']},indent=2))
    except (ValueError,OSError,KeyError,AttributeError) as e:raise SystemExit('MULTILAYER_FIXTURE_REJECTED: '+str(e))
