#!/usr/bin/env python3
"""Strict evidence for retained Matrix + pinned iDMA block integration.

This does not certify the host Command128 frontend, official checkpoints,
q1024 full-network inference, or physical timing. No external check uses assert.
"""
from __future__ import annotations
import argparse
import array
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import sys

PROFILES = {'tiny': (64,128,2,1,32), 'tail': (64,80,2,1,32), 'real': (1536,8960,12,2,128)}
NAMES = 'n0 qr kr v q k att o r n1 gate up act down y'.split()

def require(ok: bool, message: str) -> None:
    if not ok: raise ValueError(message)

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def fields(line: str) -> dict[str,str]:
    pairs = re.findall(r'([A-Za-z_][A-Za-z_0-9]*)=([^\s]+)', line)
    require(len(pairs)==len({k for k,_ in pairs}), 'duplicate receipt key')
    return dict(pairs)

def counts(profile: str, tokens: int) -> tuple[list[int],int,int]:
    require(profile in PROFILES,'unsupported geometry')
    require(type(tokens) is int and 0 < tokens <= 1024,'invalid runtime token count')
    h,f,heads,kvheads,hd = PROFILES[profile];kv=kvheads*hd
    widths=[h,h,kv,kv,h,kv,h,h,h,h,f,f,f,h,h]
    useful=tokens*(2*h*h+2*h*kv+3*h*f)+tokens*(tokens+1)*h
    dense_steps=((tokens+15)//16)*(2*h*((h+31)//32)+2*h*((kv+31)//32)+2*h*((f+31)//32)+f*((h+31)//32))
    physical=(dense_steps+tokens*(tokens+1)*h//16)*512
    return [x*tokens for x in widths],useful,physical

def parse_log(text: str, profile: str, tokens: int) -> dict:
    expected,useful,physical=counts(profile,tokens)
    h,f,heads,kvheads,_=PROFILES[profile]
    require(not re.search(r'BLOCK_FAIL|TRANSPORT_FAIL|%Error|\bFatal\b|Assertion failed',text),'run contains a failure')
    records={tag:[fields(x) for x in text.splitlines() if x.startswith(tag+' ')] for tag in
             ['STAGE_CHECK','STAGE_MEMORY','PINNED_IDMA_BLOCK','DDR_GUARD_PASS','CONTINUOUS_QWEN2_BLOCK_PASS']}
    stages,mem=records['STAGE_CHECK'],records['STAGE_MEMORY']
    for items in (stages,mem):
        require([int(x['phase']) for x in items]==list(range(15)),'incomplete/duplicate/reordered phase coverage')
    for tag in ['PINNED_IDMA_BLOCK','DDR_GUARD_PASS','CONTINUOUS_QWEN2_BLOCK_PASS']:
        require(len(records[tag])==1,'missing or duplicate '+tag)
    end=records['CONTINUOUS_QWEN2_BLOCK_PASS'][0];dma=records['PINNED_IDMA_BLOCK'][0];guard=records['DDR_GUARD_PASS'][0]
    for key,value in dict(tokens=tokens,hidden=h,ffn=f,heads=heads,kv_heads=kvheads,phases=15,
                          checked_fp32=sum(expected),bit_diffs=0,macs=useful,executed_macs=physical,
                          write_bytes=sum(expected)*4,host_intermediate_writes=0,full_model=0,canonical_512_array=1).items():
        require(int(end[key])==value,'wrong '+key)
    require(float(end['max_abs'])==0.0,'ordered recipe is not bit-exact')
    require(int(end['request_stalls'])>0 and int(end['response_delay_cycles'])>0,'backpressure was not exercised')
    prev=0
    for i,(st,m,n) in enumerate(zip(stages,mem,expected)):
        require(st['name']==NAMES[i] and int(st['values'])==n,'wrong stage shape/name')
        require(int(st['bit_diffs'])==0 and float(st['max_abs'])==0 and float(st['rel_l2'])==0,'stage mismatch')
        require(int(st['cycle'])>prev,'nonmonotonic stage time');prev=int(st['cycle'])
        require(int(m['write_acks'])*64==int(m['visible_bytes'])==n*4,'short/duplicate write acknowledgement')
    rb=sum(int(x['reads']) for x in mem); wb=sum(int(x['write_acks']) for x in mem)
    require(rb*64==int(end['read_bytes']),'read byte counter mismatch')
    require(int(dma['full_backend'])==1 and int(dma['transfers'])==rb+wb,'not all transfers passed pinned backend')
    require(int(dma['external_read_beats'])==rb and int(dma['external_write_beats'])==wb,'DMA vs bus count mismatch')
    require(int(guard['visible_write_bytes'])==sum(expected)*4 and int(guard['host_intermediate_writes'])==0,'invalid DDR guards')
    require(int(end['cycles'])>0 and 0<=prev-int(end['cycles'])<=64,'invalid cycle counter/trace origin')
    require(physical<=int(end['cycles'])*512,'physical work exceeds array capacity')
    return {'stages':stages,'memory':mem,'final':end,'dma':dma,'counts':expected}

def verify(out: Path,profile: str,tokens: int) -> dict:
    require((out/'simulation.exit').read_text().strip()=='0','simulator did not exit successfully')
    result=parse_log((out/'run.log').read_text(),profile,tokens)
    scope=json.loads((out/'generated/production_scope.json').read_text())
    h,f,*_=PROFILES[profile]
    for k,v in {'hidden':h,'ffn':f,'max_tokens':1024,'physical_lanes':512,'dense_rows':16,'dense_columns':32,
                'transport':'pinned_idma_mailbox','host_command128_frontend':False,'original_graph_descriptor_fetch':False,'timing_signed_off':False}.items():
        require(type(scope[k]) is type(v) and scope[k]==v,'wrong emitted scope '+k)
    for name in ['compile.exit','emit.exit','build.exit']:
        require((out/name).read_text().strip()=='0',name+' is not success')
    source_manifest=json.loads((out/'sources.sha256.json').read_text())
    required=['chisel/continuous_prefill/src/main/scala/heteronpu/continuous/RetainedIdma.scala',
              'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/RetainedMatrix.scala',
              'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/Qwen2Block.scala',
              'rtl/integration/idma_backend_rw_axi_flat_wrap.sv','rtl/integration/qwen2_matrix_command_endpoint.sv']
    require(all(p in source_manifest for p in required),'missing source identity')
    require(all(isinstance(v,str) and re.fullmatch('[0-9a-f]{64}',v) for v in source_manifest.values()),'bad SHA256')
    idma=json.loads((out/'idma_identity.json').read_text())
    require(idma['commits']['idma']=='2e0b0fe53b6f8823319e2428e2e9abc2db149b7d' and idma['files_verified']>0,'unverified iDMA source')
    text=(out/'generated/Qwen2IdmaBlockTop.sv').read_text()
    for mod in ['idma_backend_rw_axi_flat_wrap','qwen2_matrix_command_endpoint']:
        require(len(re.findall(r'^\s+'+mod+r'\s+[A-Za-z_][A-Za-z_0-9]*\s*\(',text,re.M))==1,'wrong '+mod+' instance count')
    expected={'input_x.f32le'}
    for i,n in enumerate(NAMES): expected|={f'phase_{i}_{n}_actual.f32le',f'phase_{i}_{n}_reference.f32le'}
    td=out/'tensors'
    require({p.name for p in td.glob('*.f32le')}==expected,'incomplete tensor dumps')
    require((td/'input_x.f32le').stat().st_size==tokens*h*4,'wrong input size')
    csv_path=out/'all_elements.csv.gz';require(not csv_path.exists(),'refuse to overwrite comparison')
    hashes={};count=0
    with gzip.open(csv_path,'wt',newline='',compresslevel=6) as cf:
        writer=csv.writer(cf);writer.writerow(['phase','tensor','index','actual_hex','reference_hex'])
        for i,(name,n) in enumerate(zip(NAMES,result['counts'])):
            ap=td/f'phase_{i}_{name}_actual.f32le';bp=td/f'phase_{i}_{name}_reference.f32le'
            a,b=ap.read_bytes(),bp.read_bytes();require(len(a)==len(b)==n*4,'short tensor '+name)
            floats=array.array('f');floats.frombytes(a)
            if sys.byteorder!='little':floats.byteswap()
            require(all(math.isfinite(x) for x in floats),'nonfinite '+name)
            require(a==b,'bit mismatch '+name)
            for j in range(n):
                x=int.from_bytes(a[4*j:4*j+4],'little');writer.writerow([i,name,j,f'{x:08x}',f'{x:08x}'])
            count+=n;hashes[ap.name]=sha(ap);hashes[bp.name]=sha(bp)
    raw=(td/'phase_14_y_actual.f32le').read_bytes();hv=1469598103934665603
    for j in range(0,len(raw),4):hv=((hv^int.from_bytes(raw[j:j+4],'little'))*1099511628211)&((1<<64)-1)
    require(hv==int(result['final']['hash'],16),'wrong final output hash')
    report={'schema':1,'status':'PASS_CONTINUOUS_BLOCK_RETAINED_MATRIX_PINNED_IDMA',
            'profile':profile,'tokens':tokens,'hidden':h,'ffn':f,'checked_fp32':count,
            'weights':'deterministic_synthetic','backend':'original_512_lane_matrix_and_pinned_idma',
            'receipt':result['final'],'phase_memory':result['memory'],
            'files':{'run.log':sha(out/'run.log'),'all_elements.csv.gz':sha(csv_path),
                     'sources.sha256.json':sha(out/'sources.sha256.json'),
                     'generated/Qwen2IdmaBlockTop.sv':sha(out/'generated/Qwen2IdmaBlockTop.sv')},
            'tensor_sha256':hashes,'scope':{'continuous_ddr':True,'dense_full_16x32':True,
             'shared_dense_qk_pv_array':True,'host_command128_frontend':False,'original_graph_descriptor_fetch':False,
             'official_weights':False,'full_network_q1024':False,'timing_800mhz_signed_off':False}}
    (out/'RESULT.json').write_text(json.dumps(report,indent=2)+'\n');return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);p.add_argument('profile',choices=PROFILES);p.add_argument('--tokens',type=int,default=16);a=p.parse_args()
    try: print(json.dumps(verify(a.output,a.profile,a.tokens),indent=2))
    except (ValueError,KeyError,OSError,TypeError) as e: raise SystemExit('PRODUCTION_EVIDENCE_FAILED: '+str(e))
