#!/usr/bin/env python3
"""Admit a scoped Host SFU_VECTOR/shared-iDMA result, never a full graph claim."""
from __future__ import annotations
import argparse
import array
import gzip
import csv
import hashlib
import json
import math
import re
import struct
from pathlib import Path
from verify_production_chain import parse_log as parse_block, counts, NAMES, PROFILES, fields, require, sha

LENGTHS = [1,15,16,17,31,32,33,1023,1024,1025,24576]

def records(text: str, tag: str) -> list[dict[str,str]]:
    return [fields(line) for line in text.splitlines() if line.startswith(tag+' ')]

def host_checks(text: str, count: int, dtype: int) -> dict:
    rows=records(text,'HOST_COMMAND_CHECK')
    require([int(x['pc']) for x in rows]==[0,1,2], 'incomplete or duplicate Host command sequence')
    for row in rows:
        require(int(row['values'])==count and int(row['bit_diffs'])==0 and
                int(row['write_ack_bytes'])==count*(2 if dtype==5 else 4), 'bad Host data/ACK count')
    ends=records(text,'HOST_COMMAND_CHAIN_PASS');require(len(ends)==1,'one Host chain completion required')
    end=ends[0];packed=32 if dtype==5 else 16
    expected_dma=33+9*((count+packed-1)//packed)
    for k,v in {'commands':3,'values':3*count,'dtype':dtype,'bit_diffs':0,'metadata_reads':33,
                'payload_reads':6*((count+packed-1)//packed),'write_ack_bytes':3*count*(2 if dtype==5 else 4),
                'idma_transfers':expected_dma,'host_intermediate_writes':0}.items():
        require(int(end[k])==v,'Host chain counter mismatch '+k)
    require(int(end['request_stalls'])>0 and int(end['response_delay_cycles'])>0,'Host stalls not exercised')
    return end

def parse_commands(text: str) -> dict:
    chunks=text.split('HOST_COMMAND_CHAIN_PASS ')
    require(len(chunks)==23,'expected 22 legal numeric chains')
    # Each chain includes exactly three per-command checks, ordered inside its
    # own scope; reject a full-log check count that merely happens to add up.
    sequences=records(text,'HOST_COMMAND_CHAIN_PASS')
    checks=records(text,'HOST_COMMAND_CHECK')
    require(len(checks)==66,'wrong legal command check count')
    for i,(dtype,n) in enumerate((d,n) for d in (5,7) for n in LENGTHS):
        fragment='\n'.join('HOST_COMMAND_CHECK '+' '.join(f'{k}={v}' for k,v in row.items()) for row in checks[3*i:3*i+3])
        fragment+='\nHOST_COMMAND_CHAIN_PASS '+' '.join(f'{k}={v}' for k,v in sequences[i].items())
        host_checks(fragment,n,dtype)
    errors=records(text,'HOST_COMMAND_CHAIN_ERROR_REJECT_PASS');require(len(errors)==8,'missing bus/envelope failure probes')
    for row in errors:
        require(int(row['commands'])==0 and int(row['values'])==0 and int(row['write_ack_bytes'])==0,'error published output')
    suite=records(text,'HOST_COMMAND_IDMA_SUITE_PASS');require(len(suite)==1,'missing suite result')
    for k,v in {'cases':30,'original_idma':1,'command128':1,'actual_sfu':1,'arithmetic_stub':0}.items():
        require(int(suite[0][k])==v,'wrong suite field '+k)
    return {'legal_cases':22,'error_cases':8,'commands_executed':66,'fp_values_checked':sum(LENGTHS)*6}

def exact_words(path: Path, reference: Path, n: int) -> tuple[bytes,bytes]:
    a,b=path.read_bytes(),reference.read_bytes();require(len(a)==len(b)==n*4,'short tensor '+path.name)
    require(a==b,'tensor bit mismatch '+path.name)
    require(all(math.isfinite(x[0]) for x in struct.iter_unpack('<f',a)),'nonfinite '+path.name)
    return a,b

def verify(out: Path, profile: str, tokens: int) -> dict:
    require((out/'simulation.exit').read_text().strip()=='0','nonzero simulator exit')
    text=(out/'run.log').read_text()
    require(not re.search(r'HOST_COMMAND_FAIL|SHARED_PRODUCTION_FAIL|BLOCK_FAIL|%Error|\bFatal\b|Assertion failed',text),'simulation failure')
    scope=json.loads((out/'generated/SCOPE.json').read_text())
    require(scope['profile']==profile and scope['host_opcode_enabled']==[48] and scope['single_idma'] is True,'wrong emitted scope')
    require(scope['original_full_graph'] is False and scope['official_weights'] is False and scope['dc_pass'] is False,'scope inflation')
    sources=json.loads((out/'sources.sha256.json').read_text())
    for name in ['SharedMemoryArbiter','TypedTensorReader','HostResidualCommands','SharedProductionTop']:
        require('chisel/continuous_prefill/src/main/scala/heteronpu/continuous/'+name+'.scala' in sources,'missing source '+name)
    require('chisel/continuous_prefill/tests/host_command_axi_service.h' in sources,'untracked memory service')
    require(all(isinstance(x,str) and re.fullmatch('[0-9a-f]{64}',x) for x in sources.values()),'invalid SHA')
    idma=json.loads((out/'idma_identity.json').read_text())
    require(idma['commits']['idma']=='2e0b0fe53b6f8823319e2428e2e9abc2db149b7d' and idma['files_verified']>0,'unverified original iDMA')
    top='HostResidualIdmaTop' if profile=='commands' else 'Qwen2SharedProductionTop'
    sv=(out/f'generated/{top}.sv').read_text()
    require(len(re.findall(r'^\s+idma_backend_rw_axi_flat_wrap\s+\w+\s*\(',sv,re.M))==1,'not exactly one original DMA')
    tensors={};block=None;host=None
    if profile=='commands': details=parse_commands(text)
    else:
        require(profile in PROFILES and 0<tokens<=1024,'bad profile/tokens')
        block=parse_block(text,profile,tokens);h,f,*_=PROFILES[profile];n=tokens*h
        host=host_checks(text,n,7)
        end=records(text,'SHARED_PRODUCTION_COMMAND_PASS');require(len(end)==1,'missing combined completion')
        for k,v in {'tokens':tokens,'hidden':h,'ffn':f,'block_stages':15,'host_commands':3,
                    'block_checked_fp32':sum(block['counts']),'host_checked_fp32':3*n,'bit_diffs':0,
                    'original_matrix_instances':1,'original_idma_instances':1,'host_intermediate_writes':0,
                    'reset_between_block_and_commands':0,'full_21_command_graph':0,'official_weights':0}.items():
            require(int(end[0][k])==v,'combined counter mismatch '+k)
        require(int(end[0]['total_idma_transfers'])==int(block['dma']['transfers'])+int(host['idma_transfers']),'shared backend count not conserved')
        require(len(re.findall(r'^\s+qwen2_matrix_command_endpoint\s+\w+\s*\(',sv,re.M))==1,'not exactly one original Matrix')
        require('module HeteroBF16FmaLane' not in sv,'unexpected replacement Matrix')
        td=out/'tensors';expected={'input_x.f32le','host_commands.bin','host_descriptors.bin'}
        for i,name in enumerate(NAMES):expected|={f'phase_{i}_{name}_actual.f32le',f'phase_{i}_{name}_reference.f32le'}
        for i in range(3):expected|={f'host_{i}_actual.f32le',f'host_{i}_reference.f32le'}
        require({p.name for p in td.iterdir() if p.is_file()}==expected,'missing/extra tensor dump')
        require((td/'input_x.f32le').stat().st_size==n*4,'input size')
        csvpath=out/'all_shared_elements.csv.gz';require(not csvpath.exists(),'refuse overwrite comparison')
        with gzip.open(csvpath,'wt',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(['phase','tensor','index','actual_hex','reference_hex'])
            for i,(name,num) in enumerate(zip(NAMES,block['counts'])):
                ap=td/f'phase_{i}_{name}_actual.f32le';bp=td/f'phase_{i}_{name}_reference.f32le';a,_=exact_words(ap,bp,num)
                for j,(u,) in enumerate(struct.iter_unpack('<I',a)):writer.writerow([i,name,j,f'{u:08x}',f'{u:08x}'])
            predecessor=(td/'phase_14_y_actual.f32le').read_bytes();input_x=(td/'input_x.f32le').read_bytes()
            for i in range(3):
                ap=td/f'host_{i}_actual.f32le';bp=td/f'host_{i}_reference.f32le';a,_=exact_words(ap,bp,n)
                # Independently re-evaluate each residual against the actual
                # predecessor dump, not just a C++ reference hash.
                for j,((x,),(b,),(actual,)) in enumerate(zip(struct.iter_unpack('<f',predecessor),struct.iter_unpack('<f',input_x),struct.iter_unpack('<I',a))):
                    expected_bits=struct.unpack('<I',struct.pack('<f',x+b))[0]
                    require(actual==expected_bits,'actual predecessor ADD mismatch')
                    writer.writerow([15+i,f'host_{i}',j,f'{actual:08x}',f'{expected_bits:08x}'])
                predecessor=a
        header=(out/'generated/block_layout.h').read_text()
        off_y=int(re.search(r'OFF_Y=(\d+)ULL',header).group(1))
        require(int(end[0]['block_to_command_address'],16)==0x100000000+off_y,'wrong predecessor address')
        commands=(td/'host_commands.bin').read_bytes();descs=(td/'host_descriptors.bin').read_bytes()
        require(len(commands)==64 and len(descs)==512,'wrong table lengths')
        for i in range(3):
            cmd=int.from_bytes(commands[16*i:16*i+16],'little')
            require((cmd&0xffffff)==0x330 and (cmd>>24)&65535==i and (cmd>>40)&65535==i+1,'wrong frozen command envelope')
            root=(cmd>>56)&0xffffff;require(root==10*i,'wrong descriptor root')
        tensors={p.name:sha(p) for p in sorted(td.iterdir()) if p.is_file()}
        details={'block_values':sum(block['counts']),'host_values':3*n,'total_values':sum(block['counts'])+3*n,
                 'command_backend_transfers':int(host['idma_transfers']),'block_backend_transfers':int(block['dma']['transfers']),
                 'comparison_sha256':sha(csvpath)}
    report={'schema':1,'status':'PASS_SHARED_COMMAND_IDMA_SUITE' if profile=='commands' else 'PASS_BLOCK_TO_HOST_COMMAND_SHARED_IDMA',
            'profile':profile,'tokens':tokens if profile!='commands' else None,'details':details,'block_receipt':block['final'] if block else None,
            'host_receipt':host,'tensor_sha256':tensors,'files':{'run.log':sha(out/'run.log'),'sources.sha256.json':sha(out/'sources.sha256.json'),
            f'generated/{top}.sv':sha(out/f'generated/{top}.sv')},
            'scope':{'host_sfu_vector_add':True,'typed_tensor_decode':True,'single_original_idma':True,
                     'original_21_command_graph':False,'official_weights':False,'full_network_q1024':False,'timing_800mhz_signed_off':False}}
    (out/'RESULT.json').write_text(json.dumps(report,indent=2)+'\n');return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);p.add_argument('profile',choices=['commands',*PROFILES]);p.add_argument('--tokens',type=int,default=16);a=p.parse_args()
    try: print(json.dumps(verify(a.output,a.profile,a.tokens),indent=2))
    except (ValueError,KeyError,OSError,TypeError,AttributeError) as e:raise SystemExit('SHARED_COMMAND_EVIDENCE_FAILED: '+str(e))
