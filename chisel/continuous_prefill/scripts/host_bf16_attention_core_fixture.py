#!/usr/bin/env python3
"""Pack audit-only independent bytes for two real Host attention-core launches.

This module performs no arithmetic, model capture, DUT build, or numerical
acceptance. It never copies an expected intermediate/cache/context into DDR.
The input reference receipt must describe cold_m128 token 0 then token 1;
carried1 is the second Host protocol launch, not a carried127 capture.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'src'))
from host_bf16_qkv_descriptor import HostQkvBinding
from host_bf16_qk_rope_descriptor import HostQkNormBinding, HostPartialRopeBinding
from host_bf16_attention_core_descriptor import build_host_attention_core_commands, validate_carried_attention_commands, HostAttentionCoreBinding

SCHEMA = 'HOST_ATTENTION_CORE_PAIR_V1'
NAMES = ('q','k','v','norm_q','gate','norm_k','rope_q','rope_k','cache_k','cache_v','context')
WIDTHS = (4096,512,512,2048,2048,512,2048,512,512,512,2048)
PCS = (0,1,2,3,3,4,5,6,7,7,10)
RECORDS = (21,21,21,15,12,12,12,11,13,9,13,12)
ENGINES = (2,2,2,3,3,3,3,4,2,3,2,3)
PHASES = ('cold0','carried1')
HEADER = 'base limit meta scratch cache capacity'.split()
LAUNCH = 'cb cl db dl rows first count position old_length old_generation epoch'.split()
COMMAND = 'name engine records signal input input_bytes constant constant_bytes'.split()
SPAN = 'name pc allocation allocation_bytes begin bytes'.split()
COMMAND_NAMES = ('q','k','v','norm_q','norm_k','rope_q','rope_k','append','qk','softmax','pv','fence')
INPUTS = {'activation.bf16le':128*2048, 'weight_q.bf16le':1024*4096*2,
          'weight_k.bf16le':1024*512*2,'weight_v.bf16le':1024*512*2,
          'q_gamma.bf16le':512,'k_gamma.bf16le':512,'trig.bf16le':256*128}

def require(ok, reason):
    if not ok: raise ValueError(reason)

def sha(raw): return hashlib.sha256(raw).hexdigest()
def file_sha(path):
    with Path(path).open('rb') as stream: return hashlib.file_digest(stream,'sha256').hexdigest()
def inside(a,n,b,size): return n>0 and b<=a and a+n<=b+size

def safe_file(root, name):
    root=Path(root);require(root.is_dir() and not root.is_symlink(),'missing/symlink root')
    rel=Path(name)
    require(not rel.is_absolute() and '..' not in rel.parts and bool(rel.parts), 'unsafe file path')
    path=Path(root)/rel
    require(all(not p.is_symlink() for p in [path,*list(path.parents)[:len(rel.parts)-1]]), 'symlink file path')
    require(path.is_file(), 'missing file: '+str(path))
    return path

def checked(root,name,record):
    path=safe_file(root,name)
    require(set(record)=={'bytes','sha256'} and type(record['bytes']) is int and record['bytes']>=0, 'file record')
    require(path.stat().st_size==record['bytes'] and file_sha(path)==record['sha256'], 'file byte/hash drift: '+name)
    return path.read_bytes()

def source_identity():
    """Current complete local Scala closure + all reference/descriptor sources.

    Upstream generated RTL, compiler/jar/HardFloat and binary identity belong
    to the later build receipt; this source-only fixture never claims them.
    """
    paths=set((ROOT/'chisel/continuous_prefill/src/main/scala').rglob('*.scala'))
    paths.update((ROOT/'src/heteronpu').glob('*.py'))
    paths.update((ROOT/'chisel/continuous_prefill/scripts').glob('*.py'))
    paths.add(ROOT/'chisel/continuous_prefill/tests/host_bf16_attention_core.cpp')
    paths.add(ROOT/'chisel/continuous_prefill/tests/host_physical_axi.h')
    require(all(p.is_file() and not p.is_symlink() for p in paths), 'source closure file/symlink')
    return {str(p.relative_to(ROOT)):file_sha(p) for p in sorted(paths)}

def build_layout():
    h={'base':0x120000000,'capacity':256}
    tables=[(h['base']+i*8192,h['base']+i*8192+4096) for i in range(2)]
    h['meta']=h['base']+16384
    cursor=h['meta']+4096
    def allocate(size):
        nonlocal cursor
        addr=cursor;cursor+=(size+63)//64*64+4096
        return addr
    addresses={name:allocate(size) for name,size in INPUTS.items()}
    h['scratch']=cursor
    h['cache']=allocate(256*2048)
    launches=[];pairs=[];preloads=[]
    for run,(cb,db) in enumerate(tables):
        l=dict(cb=cb,cl=cb+192,db=db,dl=db+2752,rows=128,first=run,count=1,
               position=run,old_length=run,old_generation=run,epoch=9+run)
        outputs=[allocate(128*w*2) for w in WIDTHS[:8]]
        scores,probability,context=allocate(64),allocate(64),allocate(128*4096)
        ps=[HostQkvBinding(i,128,run,1,addresses['activation.bf16le'],addresses['weight_'+r+'.bf16le'],outputs[i]) for i,r in enumerate('qkv')]
        ns=[HostQkNormBinding(i,128,run,1,outputs[i],addresses[('q' if i==0 else 'k')+'_gamma.bf16le'],outputs[3 if i==0 else 5],outputs[4] if i==0 else 0) for i in range(2)]
        rs=[HostPartialRopeBinding(i,128,run,1,outputs[3 if i==0 else 5],addresses['trig.bf16le'],outputs[6+i],256,run) for i in range(2)]
        core=HostAttentionCoreBinding(128,run,1,256,run,run,run,run==0,outputs[6],outputs[7],outputs[2],h['cache'],scores,probability,context)
        commands,records=build_host_attention_core_commands(ps,ns,rs,core);pairs.append((commands,records))
        specs=[]
        for pc in range(12):
            src=nb=const=nc=0
            if pc<3: src=addresses['activation.bf16le']+run*2048;nb=2048;const=ps[pc].weight_ddr;nc=1024*WIDTHS[pc]*2
            elif pc<5:
                b=ns[pc-3];src=b.job['input'];nb=b.input_columns*2;const=b.weight_ddr;nc=512
            elif pc<7:
                b=rs[pc-5];src=b.job['input'];nb=b.n*2;const=addresses['trig.bf16le']+run*128;nc=128
            elif pc==7: src=outputs[7]+run*1024;nb=1024;const=outputs[2]+run*1024;nc=1024
            elif pc==10: src=outputs[6]+run*4096;nb=4096;const=h['cache'];nc=256*2048
            specs.append(dict(zip(COMMAND,(COMMAND_NAMES[pc],ENGINES[pc],RECORDS[pc],pc+1,src,nb,const,nc))))
        spans=[]
        for name,pc,w,addr in zip(NAMES[:8],PCS[:8],WIDTHS[:8],outputs):
            spans.append(dict(zip(SPAN,(name,pc,addr,128*w*2,addr+run*w*2,w*2))))
        for name,addr in [('cache_k',h['cache']+run*1024),('cache_v',h['cache']+256*1024+run*1024)]:
            spans.append(dict(zip(SPAN,(name,7,h['cache'],256*2048,addr,1024))))
        spans.append(dict(zip(SPAN,('context',10,context,128*4096,context+run*4096,4096))))
        l.update(commands=specs,spans=spans,internal=[{'name':'scores','address':scores,'bytes':64},{'name':'probabilities','address':probability,'bytes':64}])
        launches.append(l)
        preloads += [{'file':PHASES[run]+'_commands.bin','address':cb,'bytes':192}, {'file':PHASES[run]+'_descriptors.bin','address':db,'bytes':2752}]
    validate_carried_attention_commands(*pairs[0],*pairs[1])
    preloads += [dict(file='input/'+name,address=addresses[name],bytes=size) for name,size in INPUTS.items()]
    h['limit']=cursor
    require(h['limit']-h['base']<=64*1024*1024 and sum(RECORDS)==172, 'layout bounds')
    return dict(header=h,preloads=preloads,launches=launches),pairs

def layout_text(layout):
    h=layout['header'];lines=[SCHEMA,' '.join(str(h[k]) for k in HEADER),str(len(layout['preloads']))]
    lines += [f"{p['file']} {p['address']} {p['bytes']}" for p in layout['preloads']]
    for l in layout['launches']:
        lines.append(' '.join(str(l[k]) for k in LAUNCH))
        lines.extend(' '.join(str(c[k]) for k in COMMAND) for c in l['commands'])
        lines.extend(' '.join(str(s[k]) for k in SPAN) for s in l['spans'])
    return ('\n'.join(lines)+'\n').encode()

def expected_inventory():
    return {**{'input/'+n:b for n,b in INPUTS.items()},
            **{'expected/'+phase+'/'+n+'.bf16le':w*2 for phase in PHASES for n,w in zip(NAMES,WIDTHS)}}

def reference_inventory(receipt):
    require(receipt.get('status')=='PREPARED_ADJACENT_ATTENTION_CORE_EXPECTED_ONLY','reference receipt status')
    require(receipt.get('expected_only') is True and receipt.get('actual_cache_execution') is False and
            receipt.get('intermediate_preload_allowed') is False and receipt.get('input_injection') is False,
            'expected-only reference provenance')
    digest=receipt.get('official_manifest_sha256','')
    require(isinstance(digest,str) and len(digest)==64 and all(c in '0123456789abcdef' for c in digest),'official capture manifest hash')
    require(set(receipt.get('cases',{}))==set(PHASES),'reference case inventory')
    for token,phase in enumerate(PHASES):
        c=receipt['cases'][phase]
        require((c.get('source_phase'),c.get('source_token'),c.get('absolute_position'),c.get('host_cold'),
                 c.get('host_expected_length'),c.get('host_expected_generation'))==('cold',token,token,token==0,token,token),
                'source cold0/cold1 versus Host cold/carried contract')
        witness=c.get('matrix_reference',{})
        require(witness.get('status')=='PASS_INTEGER_C_EVERY_QK_PV_FMA' and witness.get('fmas')==4096*(token+1)
                and witness.get('bit_mismatches')==0 and witness.get('flag_mismatches')==0,'independent matrix witness')
        require(c.get('numerical_rtl_executed') is False and c.get('projection_reference') and c.get('norm_rope_reference'),
                'reference authority proofs absent or actual-output dependent')
    require('original_operator_gate_pass' in receipt and 'original_operator_criteria' in receipt and
            'native_full_block_failures' in receipt,'original acceptance limitations missing')
    require(set(receipt.get('expected',{}))==set(PHASES),'expected phase inventory')
    return {**{'input/'+name:rec for name,rec in receipt.get('inputs',{}).items()},
            **{'expected/'+phase+'/'+name:rec for phase,files in receipt['expected'].items() for name,rec in files.items()}}

def validate_reference_receipt(bundle, receipt):
    records=reference_inventory(receipt)
    sources=receipt.get('source_sha256');require(type(sources) is dict and sources,'reference source hashes required')
    for name,digest in sources.items():
        require(file_sha(safe_file(ROOT,name))==digest, 'reference source drift: '+name)
    require(set(records)==set(expected_inventory()), 'reference file inventory')
    raw={name:checked(bundle,name,records[name]) for name in expected_inventory()}
    for name,size in expected_inventory().items():require(len(raw[name])==size,'reference byte geometry: '+name)
    for phase in PHASES:
        for left,right in [('cache_k','rope_k'),('cache_v','v')]:
            require(raw[f'expected/{phase}/{left}.bf16le']==raw[f'expected/{phase}/{right}.bf16le'], 'cache append reference is not the independent predecessor')
    return raw

def write_reference_bundle(inputs, expected, receipt, output):
    """Serialize the live reference factory's return unchanged; no math here.

    A saved receipt is provenance, not a replacement for the originating live
    capture authority. The eventual numerical runner must retain that authority.
    """
    output=Path(output);require(not output.exists(),'fresh reference bundle required')
    records=reference_inventory(receipt)
    raw={**{'input/'+name:value for name,value in inputs.items()},
         **{'expected/'+phase+'/'+name:value for phase,files in expected.items() for name,value in files.items()}}
    require(set(raw)==set(records)==set(expected_inventory()),'returned reference inventory')
    for name,value in raw.items():
        require(type(value) is bytes and len(value)==expected_inventory()[name] and
                records[name]==dict(bytes=len(value),sha256=sha(value)),'returned reference hash: '+name)
    output.mkdir(parents=True)
    for name,value in raw.items():
        path=output/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(value)
    (output/'reference_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    validate_reference_receipt(output,receipt)
    return output

def pack(bundle,output):
    bundle,output=Path(bundle),Path(output)
    require(not output.exists(),'fresh fixture output required')
    receipt_raw=safe_file(bundle,'reference_receipt.json').read_bytes();receipt=json.loads(receipt_raw)
    payload=validate_reference_receipt(bundle,receipt);layout,pairs=build_layout()
    payload['launch.txt']=layout_text(layout);payload['reference_receipt.json']=receipt_raw
    for phase,(commands,records) in zip(PHASES,pairs):
        payload[phase+'_commands.bin']=b''.join(c.pack().to_bytes(16,'little') for c in commands)
        payload[phase+'_descriptors.bin']=b''.join(records[i].pack().to_bytes(16,'little') for i in range(172))
    manifest=dict(schema=SCHEMA,status='FIXTURE_PREPARED_NOT_EXECUTED',numerical_acceptance_eligible=False,
                  layout=layout,source_sha256=source_identity(),reference_receipt_sha256=sha(receipt_raw),
                  source_phase='cold_m128',source_tokens=[0,1],source_input_sha256={n:sha(raw) for n,raw in payload.items() if n.startswith('input/')},
                  files={n:dict(bytes=len(raw),sha256=sha(raw)) for n,raw in payload.items()},
                  scope='QKV_NORM_ROPE_APPEND_CAUSAL_GQA_CORE',full_block_supported=False,model_m128_accepted=False)
    output.mkdir(parents=True)
    for name,raw in payload.items():
        p=output/name;p.parent.mkdir(exist_ok=True,parents=True);p.write_bytes(raw)
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return verify(output)

def verify(fixture):
    fixture=Path(fixture);m=json.loads(safe_file(fixture,'manifest.json').read_bytes())
    require(all(not p.is_symlink() for p in fixture.rglob('*')),'symlink fixture artifact')
    require(m.get('schema')==SCHEMA and m.get('status')=='FIXTURE_PREPARED_NOT_EXECUTED' and m.get('numerical_acceptance_eligible') is False,'fixture status')
    layout,pairs=build_layout();require(m['layout']==layout,'serialized physical layout drift')
    require(m['source_sha256']==source_identity(),'complete local source closure drift')
    expected=set(expected_inventory())|{'launch.txt','reference_receipt.json',*(p+'_'+k+'.bin' for p in PHASES for k in ('commands','descriptors'))}
    require(set(m['files'])==expected, 'fixture inventory drift')
    raw={name:checked(fixture,name,rec) for name,rec in m['files'].items()}
    require(raw['launch.txt']==layout_text(layout),'driver layout drift')
    require(sha(raw['reference_receipt.json'])==m['reference_receipt_sha256'],'reference receipt drift')
    validate_reference_receipt(fixture,json.loads(raw['reference_receipt.json']))
    require(m['source_input_sha256']=={n:sha(raw[n]) for n in raw if n.startswith('input/')},'source input hash inventory')
    for phase,(commands,records) in zip(PHASES,pairs):
        require(raw[phase+'_commands.bin']==b''.join(c.pack().to_bytes(16,'little') for c in commands),'raw command drift')
        require(raw[phase+'_descriptors.bin']==b''.join(records[i].pack().to_bytes(16,'little') for i in range(172)),'raw descriptor drift')
    actual={str(p.relative_to(fixture)) for p in fixture.rglob('*') if p.is_file()}
    require(actual==expected|{'manifest.json'},'extra fixture files')
    return dict(status='VERIFIED_FIXTURE_ONLY_NOT_NUMERICAL_PASS',manifest_sha256=file_sha(fixture/'manifest.json'),source_sha256=m['source_sha256'],layout=layout)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('fixture',type=Path);p.add_argument('--bundle',type=Path);a=p.parse_args()
    print(json.dumps(pack(a.bundle,a.fixture) if a.bundle else verify(a.fixture),indent=2))
