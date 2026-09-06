#!/usr/bin/env python3
"""Independently compare every stored output word of the fixed real16 block gate.

The binary dumps are produced from DUT-written DDR, not used to serve any reads.
This verifier cannot turn a partial log, a tiny run, or synthetic weights into an
official-checkpoint result. No external correctness check relies on ``assert``.
"""
from __future__ import annotations
import argparse
import array
import csv
import gzip
import hashlib
import json
import math
import re
import sys
from pathlib import Path

SHAPE = dict(hidden=1536, ffn=8960, heads=12, kv_heads=2, head_dim=128, tokens=16)
STAGES = [('n0',1536),('qr',1536),('kr',256),('v',256),('q',1536),('k',256),
          ('att',1536),('o',1536),('r',1536),('n1',1536),('gate',8960),('up',8960),
          ('act',8960),('down',1536),('y',1536)]
EXPECTED_MACS = 749101056
EXPECTED_VALUES = 663552
EXPECTED_WRITE_BYTES = 2654208

def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def fields(line: str) -> dict[str, str]:
    pairs=re.findall(r'([a-zA-Z_][a-zA-Z_0-9]*)=([^\s]+)',line)
    require(len({k for k,_ in pairs})==len(pairs), 'duplicate log field')
    return dict(pairs)

def parse_log(text: str) -> tuple[list[dict[str,str]],list[dict[str,str]],dict[str,str]]:
    require(not re.search(r'BLOCK_FAIL|\bFatal\b|%Error|Assertion failed', text), 'simulation log contains failure')
    stages=[fields(x) for x in text.splitlines() if x.startswith('STAGE_CHECK ')]
    memory=[fields(x) for x in text.splitlines() if x.startswith('STAGE_MEMORY ')]
    final=[fields(x) for x in text.splitlines() if x.startswith('CONTINUOUS_QWEN2_BLOCK_PASS ')]
    require([int(x['phase']) for x in stages]==list(range(15)), 'missing, duplicate, or reordered stages')
    require([int(x['phase']) for x in memory]==list(range(15)), 'incomplete memory-ACK coverage')
    require(len(final)==1, 'exactly one full-block completion is required')
    f=final[0]
    for name,value in dict(tokens=16,hidden=1536,ffn=8960,heads=12,kv_heads=2,phases=15,
                           checked_fp32=EXPECTED_VALUES,bit_diffs=0,macs=EXPECTED_MACS,
                           executed_macs=EXPECTED_MACS,write_bytes=EXPECTED_WRITE_BYTES,
                           host_intermediate_writes=0,full_model=0,canonical_512_array=0).items():
        require(int(f[name])==value, f'wrong {name}: {f[name]} != {value}')
    require(float(f['max_abs'])==0.0, 'fixed recipe gate requires exact word parity')
    require(int(f['request_stalls'])>0 and int(f['response_delay_cycles'])>0,'random backpressure was not exercised')
    cycles=[int(x['cycle']) for x in stages]
    require(all(a<b for a,b in zip(cycles,cycles[1:])), 'nonmonotonic stage cycles')
    guards=[fields(x) for x in text.splitlines() if x.startswith('DDR_GUARD_PASS ')]
    require(len(guards)==1, 'missing or duplicate DDR guard check')
    require(int(guards[0]['visible_write_bytes'])==EXPECTED_WRITE_BYTES and int(guards[0]['host_intermediate_writes'])==0, 'bad DDR guards')
    require(sum(int(x['reads']) for x in memory)*64==int(f['read_bytes']), 'memory read count mismatch')
    for i,((name,width),s,m) in enumerate(zip(STAGES,stages,memory)):
        count=16*width
        require(s['name']==name and int(s['values'])==count, f'phase {i} shape mismatch')
        require(int(s['bit_diffs'])==0 and float(s['max_abs'])==0 and float(s['rel_l2'])==0, f'phase {i} parity failure')
        require(int(m['write_acks'])*64==count*4==int(m['visible_bytes']),f'phase {i} short/duplicate write ACKs')
    return stages,memory,f

def float_words(raw: bytes) -> array.array:
    values=array.array('f');values.frombytes(raw)
    if sys.byteorder!='little':values.byteswap()
    return values

def verify(out: Path) -> dict:
    log=out/'run.log'; tensors=out/'tensors'; layout=json.loads((out/'generated/layout.json').read_text())
    require((out/'simulation.exit').read_text().strip()=='0','simulator did not exit successfully')
    for key in ('hidden','ffn','heads','kv_heads','head_dim'):
        require(layout[key]==SHAPE[key],f'wrong elaborated geometry: {key}')
    require(layout['max_tokens']==1024 and layout['mac_lanes']==16 and not layout['retained_matrix'], 'wrong DUT backend')
    require(layout.get('dense_token_tile')==16 and layout.get('row_cache_bytes')==573440, 'wrong dense SRAM tiling')
    stages,memory,final=parse_log(log.read_text())
    expected_names={'input_x.f32le'}
    for i,(name,_) in enumerate(STAGES):
        expected_names|={f'phase_{i}_{name}_actual.f32le',f'phase_{i}_{name}_reference.f32le'}
    require({p.name for p in tensors.glob('*.f32le')}==expected_names, 'missing or unexpected tensor dump')
    require((tensors/'input_x.f32le').stat().st_size==16*1536*4,'input tensor size mismatch')
    source_manifest=out/'sources.sha256.json'
    require(source_manifest.is_file(), 'missing source identity')
    sources=json.loads(source_manifest.read_text())
    required=['chisel/continuous_prefill/src/main/scala/heteronpu/continuous/Qwen2Block.scala',
              'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/BlockWritebackFence.scala',
              'chisel/continuous_prefill/tests/qwen2_block_proof.cpp']
    require(all(k in sources for k in required), 'missing hardware/driver source hash')
    require(all(isinstance(x,str) and re.fullmatch('[0-9a-f]{64}',x) for x in sources.values()), 'invalid source hash')
    details=[]; csv_path=out/'all_elements.csv.gz'
    require(not csv_path.exists(),'refuse to overwrite previous full comparison')
    with gzip.open(csv_path,'wt',newline='') as fcsv:
        writer=csv.writer(fcsv);writer.writerow(['phase','tensor','index','actual_bits_hex','reference_bits_hex','absolute_error'])
        for i,(name,width) in enumerate(STAGES):
            a=tensors/f'phase_{i}_{name}_actual.f32le'; b=tensors/f'phase_{i}_{name}_reference.f32le'
            ar=a.read_bytes();br=b.read_bytes();count=16*width
            require(len(ar)==len(br)==count*4,f'{name}: byte length mismatch')
            af,bf=float_words(ar),float_words(br)
            require(all(math.isfinite(v) for v in af) and all(math.isfinite(v) for v in bf),f'{name}: NaN/Inf')
            require(ar==br,f'{name}: independently detected bit mismatch')
            for j in range(count):
                av=int.from_bytes(ar[4*j:4*j+4],'little');bv=int.from_bytes(br[4*j:4*j+4],'little')
                writer.writerow([i,name,j,f'{av:08x}',f'{bv:08x}',abs(af[j]-bf[j])])
            details.append({'phase':i,'name':name,'values':count,'bytes':len(ar),'bit_differences':0,
                            'actual_sha256':sha(a),'reference_sha256':sha(b),
                            'stage_cycle':int(stages[i]['cycle']),'read_beats':int(memory[i]['reads']),
                            'write_ack_beats':int(memory[i]['write_acks']),
                            'write_trace_fnv64':memory[i]['write_trace_fnv']})
    final_raw=(tensors/'phase_14_y_actual.f32le').read_bytes()
    output_hash=1469598103934665603
    for j in range(0,len(final_raw),4):
        output_hash=((output_hash^int.from_bytes(final_raw[j:j+4],'little'))*1099511628211)&((1<<64)-1)
    require(output_hash==int(final['hash'],16), 'final output hash mismatch')
    result={'schema':1,'status':'PASS_REAL_DIMENSION_16_TOKEN_CONTINUOUS_QWEN2_BLOCK',
            'shape':SHAPE,'backend':'functional_16_bf16_fma_lanes','weights':'deterministic_synthetic',
            'numerical_contract':'qwen2-functional-bf16-fp32-ordered-v1; not official checkpoint quality signoff',
            'checked_fp32_values':EXPECTED_VALUES,'bit_differences':0,'stage_count':15,
            'dut_cycles':int(final['cycles']),'useful_macs':EXPECTED_MACS,
            'successful_write_ack_bytes':EXPECTED_WRITE_BYTES,'ddr_read_bytes':int(final['read_bytes']),
            'request_stalls':int(final['request_stalls']),'response_delay_cycles':int(final['response_delay_cycles']),
            'output_fnv64':final['hash'],'log_sha256':sha(log),'source_manifest_sha256':sha(source_manifest),
            'full_comparison_csv_sha256':sha(csv_path),'stages':details,
            'scope':{'all_15_stages_continuous':True,'intermediate_reads_from_actual_DUT_writes':True,
                     'official_weights':False,'canonical_512_mac_integrated':False,
                     'command128_integrated':False,'pinned_idma_integrated':False,
                     'multi_layer':False,'q1024_prefill':False,'dc_timing_pass':False},
            'target_clock_hz':800000000,'timing_is_not_measured':True}
    return result

def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output_directory',type=Path)
    args=parser.parse_args();out=args.output_directory.resolve();target=out/'RESULT.json'
    require(not target.exists(),'refuse to overwrite earlier RESULT.json')
    result=verify(out);target.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,KeyError,OSError) as e:
        print(f'REAL16_GATE_FAIL: {e}',file=sys.stderr);raise SystemExit(1)
