#!/usr/bin/env python3
"""Replay the existing FP32 RoPE RTL against an exact, separately named oracle.

A component PASS does not accept source-native BF16 semantics, a full Qwen3.5
block, coefficient generation, BF16 storage conversion or MAC utilization.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import random
import re
import subprocess
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from heteronpu.model_geometry import require, load_json
from heteronpu.weight_header_contract import sha256
from heteronpu.qwen35_bf16_reference import require_bf16, producer_compare
from heteronpu.rope_hardware_oracle import pair_rne, bf16_rne_word, native_bf16_pair

CONTRACT_PATH = 'config/upstream/qwen3_5_0p8b/rope_hardware_contract.json'
CONTRACT_SHA256 = '72236329a48a1e6ab9e9bb419c560c455cdcbcc61ab5cbb0060db4ef5f671132'


def file_record(path):
    return {'file':path.name,'bytes':path.stat().st_size,'sha256':sha256(path.read_bytes())}


def contract():
    require(sha256((ROOT/CONTRACT_PATH).read_bytes()) == CONTRACT_SHA256, 'RoPE contract drift')
    c = load_json(ROOT/CONTRACT_PATH)
    for name,digest in (c['rtl_source_sha256'] | c.get('emitter_source_sha256',{})).items():
        require(sha256((ROOT/name).read_bytes()) == digest,'RoPE arithmetic source drift: '+name)
    return c


def load_audit(directory, c, *, fresh_digest=None):
    require(sha256((directory/'result.json').read_bytes()) == (fresh_digest or c['saved_audit_report_sha256']), 'untrusted BF16 audit report')
    report = load_json(directory/'result.json')
    require(report['audit_collection_complete'] is True, 'incomplete BF16 audit')
    require(report['model_id'] == c['model_id'] and report['layer_id'] == 3, 'audit identity drift')
    require(report['arrays']['file'] == 'all_bf16_producers.npz', 'unexpected audit array path')
    path = directory / report['arrays']['file']
    require(file_record(path) == report['arrays'], 'audit arrays digest/size drift')
    arrays = np.load(path,allow_pickle=False)
    return report, arrays


def make_corpus(arrays):
    vectors, groups = [], []
    for case in ('cold_m128','carried_m128'):
        cos = require_bf16(arrays[f'{case}_native_cos'],'cos')
        sin = require_bf16(arrays[f'{case}_native_sin'],'sin')
        require(cos.shape == sin.shape == (1,128,64), 'coefficient shape drift')
        require(np.array_equal(cos[...,:32].view(np.uint32),cos[...,32:].view(np.uint32)), 'cos half mismatch')
        require(np.array_equal(sin[...,:32].view(np.uint32),sin[...,32:].view(np.uint32)), 'sin half mismatch')
        for label,index,heads,outindex in (('q',16,8,29),('k',25,2,32)):
            x = require_bf16(arrays[f'{case}_native_producer_{index:02d}'],label)
            require(x.shape == (1,128,heads,256),'Q/K producer shape drift')
            expected_native = require_bf16(arrays[f'{case}_native_producer_{outindex:02d}'],'source RoPE').transpose(0,2,1,3)
            require(expected_native.shape == (1,128,heads,64),'source RoPE shape drift')
            xb, cb, sb = x.view(np.uint32),cos.view(np.uint32),sin.view(np.uint32)
            start = len(vectors)
            native,projected = [],[]
            for token in range(128):
                for head in range(heads):
                    for channel in range(32):
                        inp = tuple(int(v) for v in (xb[0,token,head,channel],xb[0,token,head,channel+32],cb[0,token,channel],sb[0,token,channel]))
                        er,orr,flags = pair_rne(*inp)
                        source = native_bf16_pair(*inp)
                        observed = expected_native.view(np.uint32)[0,token,head,[channel,channel+32]]
                        require(tuple(int(v) for v in observed) == source,'source-native product-order mismatch')
                        vectors.append((*inp,er,orr,flags))
                        native.extend(source)
                        projected.extend((bf16_rne_word(er),bf16_rne_word(orr)))
            comparison = producer_compare(np.array(projected,dtype=np.uint32).view(np.float32),np.array(native,dtype=np.uint32).view(np.float32))
            groups.append({'case':case,'producer':label,'start':start,'pairs':len(vectors)-start,
                'hardware_FP32_then_software_BF16_vs_native_BF16':comparison,'native_product_semantics_replay_bitwise_pass':True})
    real_pairs = len(vectors)
    # Arithmetic/flags witnesses supplement the actual model inputs. They are
    # clearly counted separately and never represented as real model traffic.
    directed = [(0,0,0x3F800000,0),(0x80000000,0x80000000,0x3F800000,0),
        (0x3F800001,0x3F800000,0x3F7FFFFE,0x3F800000),
        (1,3,0x3F000000,0x3F000000),(0x00800000,0x00800000,0x3F7FFFFF,0),
        (0x3F800000,0x33800000,0x3F800000,0x3F800000),
        (0x3F800001,0x33800000,0x3F800000,0x3F800000)]
    rng=random.Random(0x524F5045)
    for _ in range(2048):
        directed.append(tuple(int(v) for v in np.array([rng.uniform(-16,16) for _ in range(4)],dtype=np.float32).view(np.uint32)))
    for inp in directed:
        vectors.append((*inp,*pair_rne(*inp)))
    result=np.asarray(vectors,dtype=np.uint32)
    require(result.shape == (real_pairs+len(directed),7) and real_pairs==81920,'incomplete real corpus')
    return result,groups,real_pairs


def write_vectors(path, vectors):
    path.write_text(''.join(f'{int(row[6]):02x}'+''.join(f'{int(v):08x}' for v in row[5::-1])+'\n' for row in vectors))


def verify_outputs(path, expected):
    lines=path.read_text().splitlines()
    require(len(lines)==len(expected),'missing/extra RTL output')
    require(all(re.fullmatch(r'[0-9a-f]{8} [0-9a-f]{8} [0-9a-f]{2}',line) for line in lines),'malformed RTL output')
    actual=np.array([[int(v,16) for v in line.split()] for line in lines],dtype=np.uint32)
    require(np.array_equal(actual,expected[:,4:]),'RTL bit/exception mismatch')
    return actual


def run_simulator(verilator, generated, output, vectors):
    sources=[generated/'HeteroRoPEHardwarePrimitives.sv',ROOT/'rtl/sfu/fp32_rope_pair.sv',ROOT/'rtl/sfu/fp32_rope_pair_pipe.sv',ROOT/'tb/tb_rope_hardware_oracle.sv']
    require(all(p.is_file() for p in sources),'missing actual emitted RTL')
    version=subprocess.check_output([str(verilator),'--version'],text=True).strip()
    runs=[]
    for pipe in (0,1):
        obj=output/f'obj{pipe}'
        command=[str(verilator),'--binary','--timing','-Wno-fatal','-j','4','--top-module','tb_rope_hardware_oracle',f'-GCOUNT={len(vectors)}',f'-GPIPE={pipe}','--Mdir',str(obj),'-o','tb',*[str(p) for p in sources]]
        with (output/f'build{pipe}.log').open('w') as log:
            subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=600)
        outputs=output/f'rtl_outputs{pipe}.txt'
        with (output/f'run{pipe}.log').open('w') as log:
            subprocess.run([str(obj/'tb'),f'+VECTORS={output / "vectors.memh"}',f'+OUTPUTS={outputs}'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=300)
        actual=verify_outputs(outputs,vectors)
        marker=re.findall(r'ROPE_HARDWARE_ORACLE_PASS pipe=(\d+) pairs=(\d+) cycles=(\d+) stalls=(\d+)',(output/f'run{pipe}.log').read_text())
        require(len(marker)==1 and tuple(map(int,marker[0][:2]))==(pipe,len(vectors)), 'missing simulation pass marker')
        require(int(marker[0][3])>0,'missing output backpressure')
        np.save(output/f'rtl_outputs{pipe}.npy',actual,allow_pickle=False)
        runs.append({'module':'fp32_rope_pair_pipe' if pipe else 'fp32_rope_pair','pairs':len(vectors),'output_words':actual.size,'bit_mismatches':0,'exception_mismatches':0,'cycles':int(marker[0][2]),'output_stall_cycles':int(marker[0][3]),'outputs':file_record(outputs),'compile_command':command})
    return version,runs,{str(p.relative_to(ROOT)):sha256(p.read_bytes()) for p in sources}


def emission_environment(generated, verilator):
    env=os.environ.copy()
    env.update({'OUT':str(generated),'PYTHON_BIN':sys.executable})
    if verilator is not None:
        env['VERILATOR_BIN']=str(verilator)
    else:
        # An inherited override must not select a different lint tool from the
        # simulator. Default uses the pinned locally extracted Verilator.
        env.pop('VERILATOR_BIN',None)
    return env, verilator or ROOT/'work/rope_hardware_oracle/bin/verilator'


def run(a):
    c=contract()
    require(not a.output.exists() or not any(a.output.iterdir()),'output must be fresh or empty')
    a.output.mkdir(parents=True,exist_ok=True)
    fresh_digest=None
    rebuilding=any(v is not None for v in (a.rebuild_layer0,a.rebuild_layer3,a.rebuild_extra,a.upstream))
    if rebuilding:
        require(all(v is not None for v in (a.rebuild_layer0,a.rebuild_layer3,a.rebuild_extra,a.upstream)),'all fresh rebuild inputs required')
        for name,digest in c['fresh_audit_source_sha256'].items():
            require(sha256((ROOT/name).read_bytes())==digest,'fresh audit source drift')
        spec=importlib.util.spec_from_file_location('pinned_bf16_audit',ROOT/'scripts/run_qwen35_bf16_audit.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        report=module.run(ROOT,a.rebuild_layer3,a.upstream,a.audit,rebuild_layer0=a.rebuild_layer0,rebuild_extra=a.rebuild_extra)
        require(load_json(a.audit/'result.json')==report,'fresh audit return/report mismatch')
        fresh_digest=sha256((a.audit/'result.json').read_bytes())
    audit,arrays=load_audit(a.audit,c,fresh_digest=fresh_digest)
    vectors,groups,real_pairs=make_corpus(arrays)
    arrays.close()
    write_vectors(a.output/'vectors.memh',vectors)
    np.save(a.output/'oracle_vectors.npy',vectors,allow_pickle=False)
    # Always emit in this invocation. A pre-existing manifest or SV supplied by
    # the caller can never authorize substituting a behavioral primitive.
    env,verilator=emission_environment(a.generated,a.verilator)
    with (a.output/'emission.log').open('w') as log:
        subprocess.run(['bash',str(ROOT/'scripts/generate_rope_hardware_primitives.sh')],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=900)
    verify_command=[sys.executable,str(ROOT/'chisel/rope_hardware_oracle/manifest.py'),'verify',str(ROOT),str(a.generated)]
    subprocess.run(verify_command,cwd=ROOT,env=env,check=True,timeout=60)
    version,runs,source_hashes=run_simulator(verilator,a.generated,a.output,vectors)
    subprocess.run(verify_command,cwd=ROOT,env=env,check=True,timeout=60)
    require(contract()==c,'arithmetic contract changed during execution')
    report={'schema_version':1,'status':'PASS_EXISTING_FP32_ROPE_RTL_PAIR_ONLY','rtl_component_bitwise_pass':True,
        'scope':c['scope'],'contract_sha256':CONTRACT_SHA256,'real_QK_pairs':real_pairs,'synthetic_arithmetic_pairs':len(vectors)-real_pairs,
        'native_audit_status':audit['status'],'native_audit_failed_producers':len(audit['failed_producers']),
        'native_audit_report_sha256':sha256((a.audit/'result.json').read_bytes()),'native_audit_arrays':audit['arrays'],
        'audit_admission':'fresh_pinned_producer' if rebuilding else 'immutable_saved_report_digest',
        'oracle':'integer_dyadic_per_operation_FP32_RNE_no_FMA','coefficient_generation_rtl_tested':False,
        'bf16_conversion_rtl_tested':False,'partial_RoPE_layout_rtl_tested':False,'native_intermediates_used_as_conditional_component_inputs':True,
        'source_native_BF16_equivalent':all(g['hardware_FP32_then_software_BF16_vs_native_BF16']['bit_different']==0 for g in groups),
        'source_native_BF16_within_existing_operator_limits':all(g['hardware_FP32_then_software_BF16_vs_native_BF16']['pass'] for g in groups),
        'groups':groups,'simulator':version,'rtl_runs':runs,'rtl_source_sha256':source_hashes,
        'runner_source_sha256':{name:sha256((ROOT/name).read_bytes()) for name in ('scripts/run_rope_hardware_oracle.py','src/heteronpu/rope_hardware_oracle.py','tb/tb_rope_hardware_oracle.sv')},
        'vectors':file_record(a.output/'oracle_vectors.npy'),'emission_manifest':load_json(a.generated/'manifest.json'),
        'full_block_hardware_oracle_complete':False,'U00_2_complete':False,'U01_complete':False,'mac_utilization_measured':False,
        'next_gates':c['missing_for_qwen35_block']}
    (a.output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--audit',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--generated',type=Path,default=ROOT/'work/generated/rope_hardware_oracle')
    p.add_argument('--verilator',type=Path,help='Explicit simulator override; default is the pinned local tool')
    for name in ('rebuild-layer0','rebuild-layer3','rebuild-extra','upstream'):p.add_argument('--'+name,type=Path)
    a=p.parse_args()
    for name,value in vars(a).items():
        if isinstance(value,Path):setattr(a,name,value.resolve())
    try:
        report=run(a)
    except (ValueError,KeyError,TypeError,OSError,subprocess.SubprocessError) as exc:
        print('ROPE_HARDWARE_ORACLE_REJECTED: '+str(exc),file=sys.stderr);raise SystemExit(3)
    print(json.dumps({k:report[k] for k in ('status','real_QK_pairs','synthetic_arithmetic_pairs','source_native_BF16_equivalent','source_native_BF16_within_existing_operator_limits','rtl_runs')},indent=2))
