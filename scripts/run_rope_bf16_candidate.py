#!/usr/bin/env python3
"""Actual, separately named experimental BF16 RoPE RTL. No production switch.

Always regenerate pinned HardFloat. Compare every arithmetic/conversion node,
flags and actual 16-bit terminal outputs to integer and independent C references.
Frozen native expectations are read without executing a model on this CPU.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from heteronpu.model_geometry import require
from heteronpu.weight_header_contract import sha256
from heteronpu.rope_bf16_candidate import COLUMNS, pair_trace, bf16_convert, synthetic_pairs, converter_inputs


def load_script(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/f'{name}.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod

frozen=load_script('run_rope_rounding_ablation')
old=load_script('run_rope_hardware_oracle')
CONTRACT_PATH='config/upstream/qwen3_5_0p8b/rope_bf16_candidate_contract.json'
CONTRACT_SHA256='5ad1dce1dd31b38ef995d69b932998ece1560d344998ec330a6eddd8727fb766'
SOURCES=(CONTRACT_PATH,'scripts/run_rope_bf16_candidate.py','scripts/rope_bf16_candidate_reference.c',
 'src/heteronpu/rope_bf16_candidate.py','rtl/sfu/fp32_to_bf16_rne_candidate.sv',
 'rtl/sfu/fp32_rope_pair_bf16_candidate.sv','rtl/sfu/fp32_rope_pair_bf16_pipe_candidate.sv',
 'tb/tb_rope_bf16_candidate.sv','tb/tb_fp32_to_bf16_candidate.sv')


def record(path):
    return {'file':path.name,'bytes':path.stat().st_size,'sha256':sha256(path.read_bytes())}


def contract():
    require(record(ROOT/CONTRACT_PATH)['sha256']==CONTRACT_SHA256,'candidate contract drift')
    old.contract()  # Protect original arithmetic/emitters; never relax their gate.
    return json.loads((ROOT/CONTRACT_PATH).read_text())


def parse_trace(text, rows, cols):
    lines=text.splitlines()
    require(len(lines)==rows,'missing/extra output rows')
    require(all(re.fullmatch(r'[0-9a-f]{8}( [0-9a-f]{8}){'+str(cols-1)+'}',s) for s in lines),'malformed trace words')
    return np.array([[int(x,16) for x in s.split()] for s in lines],dtype=np.uint32)


def write_vectors(path, rows):
    require(rows.dtype==np.uint32 and rows.ndim==2,'bad vector shape/dtype')
    path.write_text(''.join(''.join(f'{int(x):08x}' for x in row[::-1])+'\n' for row in rows))


def flag_aggregate(trace):
    return np.bitwise_or.reduce(trace[:,[4,5,6,7,12,13,14,15,18,19,22,23]],axis=1)


def compare_c(actual, expected):
    """Only the separately documented min-normal FP32 UF convention may differ."""
    require(actual.shape==expected.shape and actual.shape[1]==25,'C trace shape')
    require(np.array_equal(actual[:,24],flag_aggregate(actual)),'C aggregate not its node flags')
    require(np.array_equal(expected[:,24],flag_aggregate(expected)),'oracle aggregate not its node flags')
    corrected=actual.copy();differences=[]
    for row,col in np.argwhere(actual[:,:24]!=expected[:,:24]):
        require(col in (4,5,6,7,18,19),'C arithmetic/conversion value/flag mismatch')
        value_col=int(col)-4 if col<8 else int(col)-2
        a,b=int(actual[row,col]),int(expected[row,col])
        require(a^b==2 and a&1 and b&1,'C mismatch beyond FP32 underflow convention')
        require(int(actual[row,value_col])==int(expected[row,value_col]) and
                int(expected[row,value_col])&0x7fffffff==0x00800000,'C UF waiver outside min-normal result')
        differences.append({'pair':int(row),'column':COLUMNS[col],'host_flags':a,'HardFloat_flags':b})
        corrected[row,col]=expected[row,col]
    corrected[:,24]=flag_aggregate(corrected)
    require(np.array_equal(corrected,expected),'unexplained C trace mismatch')
    return differences


def compile_reference(output, compiler):
    source=ROOT/'scripts/rope_bf16_candidate_reference.c';executable=output/'c_reference'
    command=[compiler,'-std=c11','-O2','-frounding-math','-ffp-contract=off','-fno-fast-math',str(source),'-lm','-o',str(executable)]
    with (output/'c_build.log').open('w') as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=60)
    process=subprocess.run([str(executable),'--self-test'],capture_output=True,text=True,check=True,timeout=60)
    (output/'c_self_test.log').write_text(process.stdout+process.stderr)
    return executable,{'source':record(source),'command':command,'compiler':subprocess.check_output([compiler,'--version'],text=True).splitlines()[0],'self_test':process.stdout+process.stderr}


def run_reference(executable, inputs, expected, output, label, converter=False):
    text=''.join(' '.join(f'{int(x):08x}' for x in row)+'\n' for row in inputs)
    process=subprocess.run([str(executable)]+(['--converter'] if converter else []),input=text,capture_output=True,text=True,check=True,timeout=120)
    (output/(label+'_c.log')).write_text(process.stderr)
    actual=parse_trace(process.stdout,len(inputs),expected.shape[1])
    np.save(output/(label+'_independent_c.npy'),actual,allow_pickle=False)
    if converter:
        require(np.array_equal(actual,expected),'independent C BF16 conversion value/flag mismatch');diff=[]
    else:diff=compare_c(actual,expected)
    return {'rows':len(inputs),'value_mismatches':0,'unexplained_flag_mismatches':0,
            'FP32_min_normal_tininess_differences':diff,'trace':record(output/(label+'_independent_c.npy'))}


def sim_build(verilator, sources, top, obj, parameters, output):
    cmd=[str(verilator),'--binary','--timing','-Wno-fatal','-j','4','--top-module',top,
         *[f'-G{k}={v}' for k,v in parameters.items()],'--Mdir',str(obj),'-o','tb',*[str(p) for p in sources]]
    with output.open('w') as log:subprocess.run(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=600)
    return cmd


def run_pair_sim(verilator, generated, output, inputs, expected, *, pipe, stall, label):
    vectors=output/(label+'_vectors.memh');write_vectors(vectors,np.concatenate((inputs,expected),axis=1))
    sources=[generated/'HeteroRoPEHardwarePrimitives.sv',ROOT/'rtl/sfu/fp32_to_bf16_rne_candidate.sv',
             ROOT/'rtl/sfu/fp32_rope_pair_bf16_candidate.sv',ROOT/'rtl/sfu/fp32_rope_pair_bf16_pipe_candidate.sv',ROOT/'tb/tb_rope_bf16_candidate.sv']
    obj=output/('obj_'+label)
    command=sim_build(verilator,sources,'tb_rope_bf16_candidate',obj,{'COUNT':len(inputs),'PIPE':pipe,'STALL':stall},output/(label+'_build.log'))
    actualfile=output/(label+'_rtl.txt');logpath=output/(label+'_run.log')
    with logpath.open('w') as log:subprocess.run([str(obj/'tb'),f'+VECTORS={vectors}',f'+OUTPUTS={actualfile}'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=300)
    actual=parse_trace(actualfile.read_text(),len(inputs),25)
    require(np.array_equal(actual,expected),'RTL intermediate/output/exception mismatch: '+label)
    marker=re.findall(r'ROPE_BF16_CANDIDATE_PASS ([^\n]+)',logpath.read_text())
    require(len(marker)==1,'missing RTL pass marker')
    metrics={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',marker[0])}
    require(metrics.get('pairs')==len(inputs) and metrics.get('pipe')==pipe,'wrong RTL scope')
    require(metrics.get('reset_checks')==2 and metrics.get('reset_inflight')==1 and metrics.get('reset_blocked')==1,'reset coverage missing')
    require(metrics.get('accepted')==len(inputs) and metrics.get('completed')==len(inputs),'transaction counter mismatch')
    if stall:require(metrics.get('stalls',0)>0,'output backpressure not exercised')
    else:require(metrics.get('stalls')==0,'unexpected performance-run output stalls')
    np.save(output/(label+'_rtl.npy'),actual,allow_pickle=False)
    return {'label':label,'module':'fp32_rope_pair_bf16_pipe_candidate' if pipe else 'fp32_rope_pair_bf16_candidate',
            'metrics':metrics,'trace_columns':25,'bit_and_flag_mismatches':0,'outputs':record(actualfile),
            'output_npy':record(output/(label+'_rtl.npy')),'vectors':record(vectors),'command':command,
            'traffic':'continuously offered input; always-ready output' if not stall else 'deterministic input bubbles and output stalls',
            'clock_period_is_testbench_only':True},actual


def run_converter_sim(verilator, output, vectors):
    path=output/'converter_vectors.memh';write_vectors(path,vectors)
    sources=[ROOT/'rtl/sfu/fp32_to_bf16_rne_candidate.sv',ROOT/'tb/tb_fp32_to_bf16_candidate.sv']
    obj=output/'obj_converter'
    command=sim_build(verilator,sources,'tb_fp32_to_bf16_candidate',obj,{'COUNT':len(vectors)},output/'converter_build.log')
    actualfile=output/'converter_rtl.txt'
    with (output/'converter_run.log').open('w') as log:subprocess.run([str(obj/'tb'),f'+VECTORS={path}',f'+OUTPUTS={actualfile}'],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=300)
    actual=parse_trace(actualfile.read_text(),len(vectors),2)
    require(np.array_equal(actual,vectors[:,1:]),'standalone converter mismatch')
    require('BF16_CONVERTER_PASS' in (output/'converter_run.log').read_text(),'converter pass marker missing')
    np.save(output/'converter_rtl.npy',actual,allow_pickle=False)
    return {'rows':len(vectors),'value_and_flag_mismatches':0,'outputs':record(actualfile),'command':command,'independent_of_RoPE_terminal_path':True}


def run(a):
    require(not a.output.exists() or not any(a.output.iterdir()),'output must be fresh or empty')
    c=contract();frozen.verify_fixtures()
    source_hashes={p:record(ROOT/p)['sha256'] for p in SOURCES}
    a.output.mkdir(parents=True,exist_ok=True)
    executable,cinfo=compile_reference(a.output,a.compiler)
    inputs=[];expected=[];corpora={};offset=0
    for name in ('local','remote'):
        data,provenance=frozen.load_corpus(name)
        trace=np.array([pair_trace(*(int(x) for x in row)) for row in data['inputs']],dtype=np.uint32)
        require(trace.shape==(81920,25),'real corpus trace shape')
        require(np.array_equal(trace[:,8:12],data['native_products']),'candidate native product mismatch')
        require(np.array_equal(trace[:,20:22],data['native_outputs']),'candidate native terminal mismatch')
        corpora[name]={'pairs':81920,'start':offset,'provenance':provenance,'native_product_bit_mismatches':0,
                        'native_terminal_bit_mismatches':0,'independent_C':run_reference(executable,data['inputs'],trace,a.output,name)}
        inputs.append(data['inputs']);expected.append(trace);offset+=len(trace)
        print(name+': frozen native products and actual BF16 output oracle bit exact',flush=True)
    synth=np.asarray(synthetic_pairs(),dtype=np.uint32)
    st=np.array([pair_trace(*(int(x) for x in row)) for row in synth],dtype=np.uint32)
    sinfo=run_reference(executable,synth,st,a.output,'synthetic')
    inputs.append(synth);expected.append(st)
    inputs=np.concatenate(inputs);expected=np.concatenate(expected)
    np.save(a.output/'inputs.npy',inputs,allow_pickle=False);np.save(a.output/'oracle_traces.npy',expected,allow_pickle=False)
    cin=np.asarray(converter_inputs(),dtype=np.uint32).reshape(-1,1)
    cout=np.asarray([bf16_convert(int(x)) for x in cin[:,0]],dtype=np.uint32)
    cref=run_reference(executable,cin,cout,a.output,'converter',True)
    np.save(a.output/'converter_inputs.npy',cin,allow_pickle=False);np.save(a.output/'converter_oracle.npy',cout,allow_pickle=False)
    env,verilator=old.emission_environment(a.generated,a.verilator)
    with (a.output/'emission.log').open('w') as log:subprocess.run(['bash',str(ROOT/'scripts/generate_rope_hardware_primitives.sh')],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=900)
    verify=[sys.executable,str(ROOT/'chisel/rope_hardware_oracle/manifest.py'),'verify',str(ROOT),str(a.generated)]
    subprocess.run(verify,check=True,timeout=60)
    conv=run_converter_sim(verilator,a.output,np.concatenate((cin,cout),axis=1));conv['independent_C']=cref
    runs=[]
    for pipe in (0,1):
        result,actual=run_pair_sim(verilator,a.generated,a.output,inputs,expected,pipe=pipe,stall=1,label=f'pipe{pipe}_stalled')
        # Verify native values against ACTUAL DUT records too, not just oracle.
        for name in ('local','remote'):
            data,_=frozen.load_corpus(name);start=corpora[name]['start'];sl=slice(start,start+81920)
            require(np.array_equal(actual[sl,8:12],data['native_products']),'RTL native product mismatch')
            require(np.array_equal(actual[sl,20:22],data['native_outputs']),'RTL native terminal mismatch')
        runs.append(result)
        result,_=run_pair_sim(verilator,a.generated,a.output,synth[:512],st[:512],pipe=pipe,stall=0,label=f'pipe{pipe}_continuous')
        runs.append(result)
    subprocess.run(verify,check=True,timeout=60)
    require(contract()==c,'contract changed during execution');frozen.verify_fixtures()
    require(source_hashes=={p:record(ROOT/p)['sha256'] for p in SOURCES},'candidate source changed during execution')
    report={'schema_version':1,'status':'PASS_EXPERIMENTAL_BF16_ROPE_RTL_COMPONENT_ONLY','production_policy_changed':False,
            'contract':c,'contract_sha256':CONTRACT_SHA256,'trace_columns':COLUMNS,'real_pairs_per_stalled_DUT':163840,
            'synthetic_pairs_per_stalled_DUT':len(synth),'native_products_per_DUT':655360,'native_outputs_per_DUT':327680,
            'synthetic_aggregate_flag_counts':{str(int(f)):int(np.count_nonzero(st[:,24]==f)) for f in np.unique(st[:,24])},
            'converter_flag_counts':{str(int(f)):int(np.count_nonzero(cout[:,1]==f)) for f in np.unique(cout[:,1])},
            'native_model_expectations_regenerated':False,'corpora':corpora,'synthetic_independent_C':sinfo,
            'converter':conv,'independent_C_build':cinfo,'rtl_runs':runs,'source_sha256':source_hashes,
            'fixture_sha256':frozen.FIXTURE_PINS,'emission_manifest':json.loads((a.generated/'manifest.json').read_text()),
            'runtime':{'python':sys.version,'numpy':np.__version__,'platform':platform.platform(),'verilator':subprocess.check_output([str(verilator),'--version'],text=True).strip()},
            'structural_operations_per_pair':{'FP32_mul':4,'FP32_add':2,'product_BF16_conversion':4,'terminal_BF16_conversion':2},
            'structural_not_synthesis_count':True,'PPA_measured':False,'memory_packing_or_store_tested':False,
            'full_block_hardware_oracle_complete':False,'U00_2_complete':False,'U01_complete':False,'mac_utilization_measured':False}
    report['artifacts']={p.name:record(p) for p in sorted(a.output.iterdir()) if p.is_file() and p.name!='c_reference'}
    (a.output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--generated',type=Path,default=ROOT/'work/generated/rope_bf16_candidate');p.add_argument('--verilator',type=Path);p.add_argument('--compiler',default='gcc')
    a=p.parse_args()
    for key,value in vars(a).items():
        if isinstance(value,Path):setattr(a,key,value.resolve())
    try:r=run(a)
    except (ValueError,KeyError,TypeError,OSError,subprocess.SubprocessError) as exc:
        print('ROPE_BF16_CANDIDATE_REJECTED: '+str(exc),file=sys.stderr);raise SystemExit(3)
    print(r['status'])
