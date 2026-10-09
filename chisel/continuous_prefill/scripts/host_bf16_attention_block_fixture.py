#!/usr/bin/env python3
"""Isolated M1 full-block fixture; reference files are audit-only, never DDR.

Two public 22-command launches share one physical cache. Every output owns its
complete M1 allocation plus guard space; this does not imply M128 execution.
Only two authenticated raw hidden rows, eleven weights and shared trig preload.
This source-only packer cannot issue numerical, native or production acceptance.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
FRONTEND = ROOT/'chisel/continuous_prefill/scripts'
for p in (ROOT/'src', ROOT/'chisel/continuous_prefill/scripts'):
    sys.path.insert(0, str(p))
from host_bf16_qkv_descriptor import HostQkvBinding
from host_bf16_qk_rope_descriptor import HostQkNormBinding, HostPartialRopeBinding
from host_bf16_attention_core_descriptor import HostAttentionCoreBinding, AttentionTensor
sys.path.insert(0,str(FRONTEND))
from host_bf16_attention_block_descriptor import (HostAttentionBlockBinding,
    build_host_attention_block_commands, validate_carried_attention_block_commands,
    CHAIN_COMMANDS, CHAIN_RECORDS, OWNER_JOBS)
from host_bf16_attention_core_fixture import require, sha, file_sha, inside, safe_file, checked

SCHEMA = 'HOST_ATTENTION_BLOCK_PAIR_V1'
PHASES, SOURCE_PHASES = ('cold0', 'carried1'), ('cold0', 'cold1')
NAMES = ('input_norm','q','k','v','norm_q','gate','norm_k','rope_q','rope_k',
         'cache_k','cache_v','context','sigmoid_mul','o','residual1','post_norm',
         'ffn_gate','ffn_up','silu_mul','down','residual2')
WIDTHS = (1024,4096,512,512,2048,2048,512,2048,512,512,512,2048,2048,
          1024,1024,1024,3584,3584,3584,1024,1024)
PCS = (0,1,2,3,4,4,5,6,7,8,8,11,12,13,14,15,16,17,18,19,20)
RECORDS = (12,21,21,21,15,12,12,12,11,13,9,13,12,13,12,12,13,13,12,13,12,12)
ENGINES = (3,2,2,2,3,3,3,3,4,2,3,2,3,2,3,3,2,2,3,2,3,3)
COMMAND_NAMES = ('input_norm','q','k','v','norm_q','norm_k','rope_q','rope_k',
                 'append','qk','softmax','pv','sigmoid_mul','o','residual1',
                 'post_norm','ffn_gate','ffn_up','silu_mul','down','residual2','fence')
DENSE_SHAPES = {'q':(1024,4096),'k':(1024,512),'v':(1024,512),'o':(2048,1024),
                'ffn_gate':(1024,3584),'ffn_up':(1024,3584),'down':(3584,1024)}
INPUTS = {**{f'weight_{n}.bf16le':k*v*2 for n,(k,v) in DENSE_SHAPES.items()},
          'weight_input_norm.bf16le':2048,'weight_post_norm.bf16le':2048,
          'weight_q_gamma.bf16le':512,'weight_k_gamma.bf16le':512,
          'cold0_hidden.bf16le':2048,'cold1_hidden.bf16le':2048,'trig.bf16le':32768}
HEADER = 'base limit meta scratch cache capacity'.split()
LAUNCH = 'cb cl db dl rows first count position old_length old_generation epoch'.split()
COMMAND = 'name engine records signal input input_bytes constant constant_bytes'.split()
SPAN = 'name pc allocation allocation_bytes begin bytes'.split()
COMMAND_BYTES = (CHAIN_COMMANDS*16+63)//64*64
DESCRIPTOR_BYTES = (CHAIN_RECORDS*16+63)//64*64
ACK_BYTES = sum(WIDTHS)*2
DENSE_MACS = sum(k*n for k,n in DENSE_SHAPES.values())


def source_identity():
    paths=set((ROOT/'chisel/continuous_prefill/src/main/scala').rglob('*.scala'))
    paths.update((ROOT/'src/heteronpu').glob('*.py'))
    paths.update((ROOT/'chisel/continuous_prefill/scripts').glob('*.py'))
    paths.update(HERE.glob('*.py'));paths.add(ROOT/'chisel/continuous_prefill/tests/host_bf16_attention_block.cpp')
    paths.update(FRONTEND.glob('host_bf16_attention_block_descriptor.py'))
    paths.add(ROOT/'chisel/continuous_prefill/tests/host_physical_axi.h')
    require(all(p.is_file() and not p.is_symlink() for p in paths),'source closure')
    return {str(p.relative_to(ROOT)):file_sha(p) for p in sorted(paths)}


def build_layout():
    h=dict(base=0x120000000,capacity=256)
    # 296 descriptor records occupy 4736 bytes: the old 8192-byte table stride
    # would overlap the next command table. Use separately guarded 16 KiB slots.
    tables=[(h['base']+i*16384,h['base']+i*16384+4096) for i in range(2)]
    h['meta']=h['base']+32768;cursor=h['meta']+4096
    def allocate(size):
        nonlocal cursor
        address=cursor;cursor+=(size+63)//64*64+4096
        return address
    addresses={name:allocate(size) for name,size in INPUTS.items()}
    h['scratch']=cursor;h['cache']=allocate(256*2048)
    launches=[];pairs=[];preloads=[]
    def tensor(a,n):return AttentionTensor(a,(1,n))
    for run,(cb,db) in enumerate(tables):
        hidden=addresses[SOURCE_PHASES[run]+'_hidden.bf16le']
        outputs={n:allocate(w*2) for n,w in zip(NAMES,WIDTHS) if not n.startswith('cache_')}
        scores,probabilities=allocate(64),allocate(64)
        ps=[HostQkvBinding(i,1,0,1,outputs['input_norm'],addresses[f'weight_{r}.bf16le'],outputs[r]) for i,r in enumerate('qkv')]
        ns=[HostQkNormBinding(i,1,0,1,outputs[r],addresses[f'weight_{r}_gamma.bf16le'],outputs['norm_'+r],outputs['gate'] if i==0 else 0) for i,r in enumerate('qk')]
        rs=[HostPartialRopeBinding(i,1,0,1,outputs['norm_'+r],addresses['trig.bf16le'],outputs['rope_'+r],256,run) for i,r in enumerate('qk')]
        core=HostAttentionCoreBinding(1,0,1,256,run,run,run,run==0,outputs['rope_q'],outputs['rope_k'],outputs['v'],h['cache'],scores,probabilities,outputs['context'])
        def block(op,role,a,b,d):return HostAttentionBlockBinding(op,role,core.context,a,b,d)
        def t(n):return tensor(outputs[n],dict(zip(NAMES,WIDTHS))[n])
        def weight(n):
            shape=DENSE_SHAPES.get(n,(1,1024))
            return AttentionTensor(addresses[f'weight_{n}.bf16le'],shape)
        raw=tensor(hidden,1024)
        block_bindings=[block(5,0,raw,weight('input_norm'),t('input_norm')),
            block(7,0,t('gate'),t('context'),t('sigmoid_mul')),
            block(6,0,t('sigmoid_mul'),weight('o'),t('o')),
            block(7,1,raw,t('o'),t('residual1')),
            block(5,1,t('residual1'),weight('post_norm'),t('post_norm')),
            block(6,1,t('post_norm'),weight('ffn_gate'),t('ffn_gate')),
            block(6,2,t('post_norm'),weight('ffn_up'),t('ffn_up')),
            block(7,2,t('ffn_gate'),t('ffn_up'),t('silu_mul')),
            block(6,3,t('silu_mul'),weight('down'),t('down')),
            block(7,3,t('residual1'),t('down'),t('residual2')),
            block(4,0,core.tensors[3],raw,t('residual2'))]
        commands,records=build_host_attention_block_commands(ps,ns,rs,core,block_bindings)
        require(len(commands)==22 and len(records)==sum(RECORDS)==296,'formal descriptor inventory')
        pairs.append((commands,records));specs=[]
        surrounds=dict(zip((0,12,13,14,15,16,17,18,19,20,21),block_bindings))
        for pc in range(22):
            src=nb=constant=nc=0
            if pc in surrounds and pc!=21:
                b=surrounds[pc];src,nb=b.a.address,b.a.payload_bytes;constant,nc=b.b.address,b.b.payload_bytes
            elif 1<=pc<=3:
                b=ps[pc-1];src,nb=outputs['input_norm'],2048;constant,nc=b.weight_ddr,1024*b.n*2
            elif 4<=pc<=5:
                b=ns[pc-4];src,nb=b.job['input'],b.input_columns*2;constant,nc=b.weight_ddr,512
            elif 6<=pc<=7:
                b=rs[pc-6];src,nb=b.job['input'],b.n*2;constant,nc=addresses['trig.bf16le']+run*128,128
            elif pc==8:src,nb,constant,nc=outputs['rope_k'],1024,outputs['v'],1024
            elif pc==11:src,nb,constant,nc=outputs['rope_q'],4096,h['cache'],256*2048
            specs.append(dict(zip(COMMAND,(COMMAND_NAMES[pc],ENGINES[pc],RECORDS[pc],pc+1,src,nb,constant,nc))))
        spans=[]
        for name,pc,width in zip(NAMES,PCS,WIDTHS):
            if name.startswith('cache_'):
                addr=h['cache'];allocation=256*2048;begin=addr+(256*1024 if name=='cache_v' else 0)+run*1024
            else:addr=begin=outputs[name];allocation=width*2
            spans.append(dict(zip(SPAN,(name,pc,addr,allocation,begin,width*2))))
        launches.append(dict(cb=cb,cl=cb+COMMAND_BYTES,db=db,dl=db+DESCRIPTOR_BYTES,rows=1,first=0,count=1,
            position=run,old_length=run,old_generation=run,epoch=9+run,source_phase='cold',source_token=run,
            commands=specs,spans=spans,internal=[dict(name='scores',address=scores,bytes=64),dict(name='probabilities',address=probabilities,bytes=64)]))
        preloads += [dict(file=PHASES[run]+'_commands.bin',address=cb,bytes=COMMAND_BYTES),dict(file=PHASES[run]+'_descriptors.bin',address=db,bytes=DESCRIPTOR_BYTES)]
    validate_carried_attention_block_commands(*pairs[0],*pairs[1])
    preloads += [dict(file='input/'+name,address=addresses[name],bytes=size) for name,size in INPUTS.items()]
    h['limit']=cursor
    require(cursor-h['base']<=64*1024*1024,'exact physical allocation exceeds existing DDR cap')
    layout=dict(header=h,preloads=preloads,launches=launches)
    validate_physical_layout(layout)
    return layout,pairs


def validate_physical_layout(layout):
    """No metadata, readonly input or writable allocation may alias.

    The only repeated allocation is the deliberately shared combined KV cache.
    Every active output span remains disjoint, including across both launches.
    """
    h=layout['header'];regions=[];active=[]
    for p in layout['preloads']:
        a,n=p['address'],p['bytes']
        require(a%64==n%64==0 and inside(a,n,h['base'],h['scratch']-h['base']),'preload allocation')
        is_table=p['file'].endswith(('_commands.bin','_descriptors.bin'))
        require(inside(a,n,h['base'] if is_table else h['meta'],(h['meta']-h['base']) if is_table else (h['scratch']-h['meta'])),'metadata/source region')
        regions.append((a,n))
    regions.append((h['cache'],h['capacity']*2048))
    for launch in layout['launches']:
        for s in launch['spans']:
            a,n=s['allocation'],s['allocation_bytes']
            require(inside(a,n,h['scratch'],h['limit']-h['scratch']) and inside(s['begin'],s['bytes'],a,n),'output allocation')
            if s['name'].startswith('cache_'):require((a,n)==(h['cache'],h['capacity']*2048),'shared cache allocation')
            else:regions.append((a,n))
            active.append((s['begin'],s['bytes']))
        regions.extend((s['address'],s['bytes']) for s in launch['internal'])
    for rows in (regions,active):
        for i,(a,n) in enumerate(rows):
            require(a%64==n%64==0 and inside(a,n,h['base'],h['limit']-h['base']),'full physical range')
            require(all(a+n<=b or b+k<=a for b,k in rows[i+1:]),'physical allocation overlap')
    return True


def layout_text(layout):
    h=layout['header'];lines=[SCHEMA,' '.join(str(h[k]) for k in HEADER),str(len(layout['preloads']))]
    lines += [f"{p['file']} {p['address']} {p['bytes']}" for p in layout['preloads']]
    for launch in layout['launches']:
        lines.append(' '.join(str(launch[k]) for k in LAUNCH))
        lines.extend(' '.join(str(c[k]) for k in COMMAND) for c in launch['commands'])
        lines.extend(' '.join(str(s[k]) for k in SPAN) for s in launch['spans'])
    return ('\n'.join(lines)+'\n').encode()


def reference_inventory(receipt):
    require(receipt.get('status')=='PREPARED_FULL_BLOCK_EXPECTED_ONLY_NOT_NATIVE_PASS','full block reference status')
    for key,wanted in dict(expected_only=True,intermediate_preload_allowed=False,dut_input_injection=False,
                           actual_cache_execution=False,numerical_rtl_executed=False,native_full_block_pass=False,
                           full128_reference_generated=False).items():require(receipt.get(key) is wanted,'reference provenance: '+key)
    require(receipt.get('launch_counts')==[1,1] and set(receipt.get('cases',{}))==set(SOURCE_PHASES),'M1 source cases')
    require(set(receipt.get('inputs',{}))==set(INPUTS),'only raw hidden, eleven weights and shared trig are inputs')
    require(set(receipt.get('expected',{}))==set(SOURCE_PHASES),'expected cases')
    require(receipt.get('source_sha256_before')==receipt.get('source_sha256_after') and receipt.get('source_sha256_before'),'reference source immutability')
    digest=receipt.get('official_manifest_sha256','')
    require(isinstance(digest,str) and len(digest)==64 and all(c in '0123456789abcdef' for c in digest),'official manifest identity')
    official=json.loads((ROOT/'config/upstream/qwen3_5_0p8b/layer3_bf16_contract.json').read_text())
    require(receipt.get('schema',{}).get('producers')==official['producer_sequence'],'all official producer nodes and dtypes required')
    require(receipt['schema'].get('command_order')==list(COMMAND_NAMES),'reference command mapping')
    for index,label in enumerate(SOURCE_PHASES):
        case=receipt['cases'][label]
        require(tuple(case.get(k) for k in ('command_count','source_phase','source_token','token_count','absolute_position','expected_length','expected_generation','cold'))==
                (22,'cold',index,1,index,index,index,index==0),'official cold-row / actual Host carried mapping')
        require(case.get('native_accuracy_accepted') is False and case.get('independent_proofs'),'independent full graph proof')
        require(case.get('producer_predecessors')==receipt['schema'].get('producer_predecessors') and
                set(case.get('producer_predecessors',{}))=={f'producer_{i:02d}' for i in range(57)},'canonical producer dependencies')
        require(all(row.get('native_intermediate_consumed') is False and row.get('origin')=='same_raw_hidden_canonical_graph'
                    for row in case['producer_predecessors'].values()),'native intermediate substitution')
        proofs=case['independent_proofs'];gqa=proofs.get('gqa',{})
        require(gqa.get('status')=='PASS_INTEGER_C_EVERY_QK_PV_FMA' and gqa.get('fmas')==4096*(index+1) and
                gqa.get('bit_mismatches')==gqa.get('flag_mismatches')==0,'every GQA FMA independent witness')
        for role,(k,n) in DENSE_SHAPES.items():
            tiles=proofs.get(role,[])
            require(len(tiles)==n//256,'all Dense tiles independently checked')
            for start,tile in enumerate(tiles):
                require(tile.get('token')==0 and tile.get('column_start')==start*256 and
                        tile.get('k')==k and tile.get('columns')==256 and tile.get('matrix_accumulator_steps')==k*256 and
                        tile.get('pass') is True and tile.get('uninterrupted_fp32_accumulation') is True and
                        tile.get('terminal_bf16_roundings')==1 and tile.get('bit_mismatches')==tile.get('flag_mismatches')==0,
                        'Dense uninterrupted integer/C witness')
        require(proofs.get('norm_rope'),'independent Norm/RoPE proof')
        names=set(NAMES)|{'sigmoid','silu'}
        inventory={n+'.bf16le' for n in names}|{f'producer_{i:02d}.f32le' for i in range(57)}
        require(set(receipt['expected'][label])==inventory,'57-node and terminal inventory')
    for key in ('original_capture_evidence','original_native_report','original_prefix_report','original_native_thresholds',
                'original_projection_gate_pass','original_norm_rope_gate_pass','original_native_full_block_failures'):
        require(key in receipt,'original acceptance limitation absent: '+key)
    return {**{'input/'+n:r for n,r in receipt['inputs'].items()},
            **{'reference/'+phase+'/'+n:r for phase,files in receipt['expected'].items() for n,r in files.items()}}


def validate_reference_receipt(bundle,receipt):
    records=reference_inventory(receipt)
    for name,digest in receipt['source_sha256_before'].items():require(file_sha(safe_file(ROOT,name))==digest,'reference source drift: '+name)
    raw={name:checked(bundle,name,record) for name,record in records.items()}
    for name,size in INPUTS.items():require(len(raw['input/'+name])==size,'input byte geometry: '+name)
    for run,label in enumerate(SOURCE_PHASES):
        case=receipt['cases'][label];trig=raw['input/trig.bf16le']
        require(case.get('raw_hidden_sha256')==sha(raw['input/'+label+'_hidden.bf16le']),'raw hidden identity')
        require(case.get('selected_trig')==dict(backing_file='trig.bf16le',byte_offset=run*128,bytes=128,
            sha256=sha(trig[run*128:(run+1)*128]),backing_sha256=sha(trig)),'shared authenticated trig selection')
        require(case.get('cache_prefix_origin')==('cold_empty' if run==0 else 'previous_launch_canonical_append_outputs'),'actual canonical cache prefix provenance')
        prefix=(raw['reference/cold0/cache_k.bf16le']+raw['reference/cold0/cache_v.bf16le']) if run else b''
        prefix_fp32=b''.join(b'\0\0'+prefix[i:i+2] for i in range(0,len(prefix),2))
        require(case.get('canonical_cache_prefix_sha256')==sha(prefix_fp32),'canonical prior cache hash')
        for name,width in zip(NAMES,WIDTHS):
            size=width*2*((run+1) if name.startswith('cache_') else 1)
            require(len(raw[f'reference/{label}/{name}.bf16le'])==size,'terminal geometry: '+name)
        for name,width in (('sigmoid',2048),('silu',3584)):
            require(len(raw[f'reference/{label}/{name}.bf16le'])==width*2,'internal terminal geometry')
        for i in range(57):
            value=raw[f'reference/{label}/producer_{i:02d}.f32le'];require(value and len(value)%4==0,'producer FP32 container geometry')
        for cache,producer in (('cache_k','rope_k'),('cache_v','v')):
            value=raw[f'reference/{label}/{cache}.bf16le']
            require(value[run*1024:]==raw[f'reference/{label}/{producer}.bf16le'],'cache append must use canonical predecessor')
            if run:require(value[:1024]==raw[f'reference/cold0/{cache}.bf16le'],'carried cache old prefix changed')
    return raw


def write_reference_bundle(inputs,expected,receipt,output):
    """Save the live factory result verbatim; receipt itself is not authority."""
    output=Path(output);require(not output.exists(),'fresh reference bundle required')
    records=reference_inventory(receipt)
    raw={**{'input/'+n:v for n,v in inputs.items()},**{'reference/'+p+'/'+n:v for p,files in expected.items() for n,v in files.items()}}
    require(set(raw)==set(records),'live return inventory')
    for name,value in raw.items():require(type(value) is bytes and records[name]==dict(bytes=len(value),sha256=sha(value)),'live return byte/hash mismatch')
    output.mkdir(parents=True)
    for name,value in raw.items():
        p=output/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(value)
    (output/'reference_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    validate_reference_receipt(output,receipt)
    return output


def derived_payload(raw,receipt):
    layout,pairs=build_layout();payload=dict(raw)
    payload['launch.txt']=layout_text(layout)
    for run,(phase,label,(commands,records)) in enumerate(zip(PHASES,SOURCE_PHASES,pairs)):
        for name in NAMES:
            value=raw[f'reference/{label}/{name}.bf16le']
            payload[f'expected/{phase}/{name}.bf16le']=value[run*1024:] if name.startswith('cache_') else value
        command_bytes=b''.join(c.pack().to_bytes(16,'little') for c in commands)
        payload[phase+'_commands.bin']=command_bytes.ljust(COMMAND_BYTES,b'\0')
        payload[phase+'_descriptors.bin']=b''.join(records[i].pack().to_bytes(16,'little') for i in range(CHAIN_RECORDS))
    return layout,payload


def pack(bundle,output):
    bundle,output=Path(bundle),Path(output);require(not output.exists(),'fresh fixture output required')
    receipt_raw=safe_file(bundle,'reference_receipt.json').read_bytes();receipt=json.loads(receipt_raw)
    raw=validate_reference_receipt(bundle,receipt);layout,payload=derived_payload(raw,receipt)
    payload['reference_receipt.json']=receipt_raw
    manifest=dict(schema=SCHEMA,status='FIXTURE_PREPARED_NOT_EXECUTED',numerical_acceptance_eligible=False,
        layout=layout,source_sha256=source_identity(),reference_receipt_sha256=sha(receipt_raw),
        source_phase='cold_m128',source_tokens=[0,1],host_phases=list(PHASES),source_phases=list(SOURCE_PHASES),
        source_input_sha256={n:sha(v) for n,v in raw.items() if n.startswith('input/')},
        files={n:dict(bytes=len(v),sha256=sha(v)) for n,v in payload.items()},
        scope='M1_FULL_LAYER3_ATTENTION_BLOCK_RAW_HIDDEN_TO_FINAL_RESIDUAL',
        full_block_supported=False,full_block_source_prepared=True,model_m128_accepted=False,
        native_full_block_accepted=False,reset_restore_executed=False)
    output.mkdir(parents=True)
    for name,value in payload.items():
        p=output/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(value)
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return verify(output)


def verify(fixture):
    fixture=Path(fixture);m=json.loads(safe_file(fixture,'manifest.json').read_bytes())
    require(all(not p.is_symlink() for p in fixture.rglob('*')),'symlink fixture artifact')
    require(m.get('schema')==SCHEMA and m.get('status')=='FIXTURE_PREPARED_NOT_EXECUTED' and m.get('numerical_acceptance_eligible') is False,'fixture status')
    require(m['source_sha256']==source_identity(),'complete local source closure drift')
    receipt_raw=safe_file(fixture,'reference_receipt.json').read_bytes();receipt=json.loads(receipt_raw)
    raw=validate_reference_receipt(fixture,receipt);layout,wanted=derived_payload(raw,receipt);wanted['reference_receipt.json']=receipt_raw
    require(m['layout']==layout and sha(receipt_raw)==m['reference_receipt_sha256'],'layout/reference receipt drift')
    require(set(m['files'])==set(wanted),'fixture inventory drift')
    require(m['source_input_sha256']=={n:sha(v) for n,v in raw.items() if n.startswith('input/')},'source input hashes')
    for name,value in wanted.items():require(checked(fixture,name,m['files'][name])==value,'derived fixture drift: '+name)
    require({str(p.relative_to(fixture)) for p in fixture.rglob('*') if p.is_file()}==set(wanted)|{'manifest.json'},'extra fixture files')
    return dict(status='VERIFIED_FIXTURE_ONLY_NOT_NUMERICAL_PASS',manifest_sha256=file_sha(fixture/'manifest.json'),source_sha256=m['source_sha256'],layout=layout)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('fixture',type=Path);p.add_argument('--bundle',type=Path);a=p.parse_args()
    print(json.dumps(pack(a.bundle,a.fixture) if a.bundle else verify(a.fixture),indent=2))
