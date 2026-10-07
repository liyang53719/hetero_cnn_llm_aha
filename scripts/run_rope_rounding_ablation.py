#!/usr/bin/env python3
"""Four experimental software ablations on two immutable historical real corpora.

Never regenerates model inputs/native expectations on the executing CPU. The
independent compiled C reference checks every retained arithmetic intermediate.
Historical actual RTL is an unchanged baseline, not an execution of a candidate.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import platform
import random
import subprocess
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from heteronpu.model_geometry import require
from heteronpu.rope_rounding_ablation import VARIANTS,COLUMNS,trace_pair,compare_words

FIXTURE_PINS={'local.npz':'36a68fd9573d5b9757283668cd635cce5bb2f9ed9a12ceb254ebde7e35140e32',
 'remote.npz':'e9526ac7b8084fadb200ab5c6d5b7bc909ec8f34408a4b63daa7af664c66ca6c',
 'provenance.json':'3573898549e7bae16d2c191b99c14e492dd94f38c9097513485747c26d4e6b4a',
 'historical_arithmetic.npy':'39a0b80418759549d02691d879db80b6fa53d29855349eb0119d7790fc0c4f8b'}
FIXTURES=ROOT/'tests/fixtures/rope_rounding'


def record(path):
    return {'file':path.name,'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def verify_fixtures(directory=FIXTURES):
    for name,pin in FIXTURE_PINS.items():
        require((directory/name).is_file(), 'missing frozen corpus: '+name+'; run python scripts/materialize_rope_rounding_corpora.py')
        require(record(directory/name)['sha256']==pin,'frozen corpus digest drift: '+name)
    return json.loads((directory/'provenance.json').read_text())


def load_corpus(name, directory=FIXTURES):
    require(name in ('local','remote'),'unknown frozen corpus')
    provenance=verify_fixtures(directory)[name]
    with np.load(directory/(name+'.npz'),allow_pickle=False) as a:
        require(set(a.files)=={'inputs','native_products','native_outputs','hardware_comb','hardware_pipe'},'frozen array inventory drift')
        data={key:a[key] for key in a.files}
    shapes={'inputs':4,'native_products':4,'native_outputs':2,'hardware_comb':3,'hardware_pipe':3}
    for key,width in shapes.items():
        require(data[key].dtype==np.uint32 and data[key].shape==(81920,width),'frozen array shape/dtype drift')
    require(np.array_equal(data['hardware_comb'],data['hardware_pipe']),'historical DUT divergence')
    for key in ('inputs','native_products','native_outputs'):
        require(not np.any(data[key]&0xFFFF),'non-BF16 corpus')
        require(np.isfinite(data[key].view(np.float32)).all(),'nonfinite corpus')
    require(sum(g['pairs'] for g in provenance['groups'])==81920,'group size drift')
    return data,provenance


def calculate(inputs):
    return np.asarray([[trace_pair(*(int(x) for x in row),v) for v in VARIANTS] for row in inputs],dtype=np.uint32)


def compile_reference(output, compiler):
    source=ROOT/'scripts/rope_rounding_fenv_reference.c'
    executable=output/'fenv_reference'
    command=[compiler,'-std=c11','-O2','-frounding-math','-ffp-contract=off','-fno-fast-math',str(source),'-lm','-o',str(executable)]
    with (output/'c_build.txt').open('w') as log:
        subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
    selftest=subprocess.run([str(executable),'--self-test'],capture_output=True,text=True,check=True)
    (output/'c_self_test.txt').write_text(selftest.stdout+selftest.stderr)
    return executable,{'compiler':subprocess.check_output([compiler,'--version'],text=True).splitlines()[0],
                       'command':command,'source':record(source),'self_test':selftest.stdout+selftest.stderr}


def independent_check(executable, inputs, traces, output, label, *, allow_tininess_difference=False):
    text=''.join(' '.join(f'{int(x):08x}' for x in row)+'\n' for row in inputs)
    process=subprocess.run([str(executable)],input=text,capture_output=True,text=True,check=True)
    (output/(label+'_c_stderr.txt')).write_text(process.stderr)
    parsed=process.stdout.split()
    # Parsing count and each uint32 token are checked, never truncate trailing output.
    require(len(parsed)==inputs.shape[0]*len(VARIANTS)*len(COLUMNS),'independent C trace length')
    c=np.asarray([int(s,16) for s in parsed],dtype=np.uint32).reshape(traces.shape)
    np.save(output/(label+'_independent_c.npy'),c,allow_pickle=False)
    value_columns=[0,1,2,3,8,9,10,11,12,13,16,17]
    require(np.array_equal(c[:,:,value_columns],traces[:,:,value_columns]),'independent C intermediate/value mismatch')
    flags=np.argwhere(c!=traces)
    differences=[]
    for pair,variant,column in flags:
        require(allow_tininess_difference and column in (4,5,6,7,14,15),'independent C flag mismatch')
        require(int(c[pair,variant,column]^traces[pair,variant,column])==2,'difference beyond tininess underflow flag')
        require(int(c[pair,variant,column]) & 1 and int(traces[pair,variant,column]) & 1,
                'underflow waiver requires inexact on both references')
        # HardFloat precision-p unbounded-exponent tininess can flag min-normal
        # even when host IEEE fenv considers the encoded result non-tiny.
        value_col=int(column)-4 if column<8 else int(column)-2
        require((int(traces[pair,variant,value_col])&0x7FFFFFFF)==0x00800000,'unexpected tininess exception')
        differences.append({'pair':int(pair),'variant':VARIANTS[variant],'column':COLUMNS[column],
                            'integer_hardfloat_flags':int(traces[pair,variant,column]),'host_fenv_flags':int(c[pair,variant,column])})
    return {'pairs':len(inputs),'intermediate_value_mismatches':0,'unexplained_flag_mismatches':0,
            'host_vs_HardFloat_min_normal_tininess_differences':differences,'reference':record(output/(label+'_independent_c.npy'))}


def group_metrics(traces, data, output, name, groups):
    result={}
    mismatch_arrays={}
    baseline=traces[:,0,16:18]
    for vi,variant in enumerate(VARIANTS):
        t=traces[:,vi]
        comparisons={'terminal_BF16_vs_frozen_native':(t[:,16:18],data['native_outputs'],True),
                     'terminal_BF16_vs_hardware_projection':(t[:,16:18],baseline,True),
                     'sum_FP32_vs_frozen_actual_hardware':(t[:,12:14],data['hardware_comb'][:,:2],False),
                     'selected_products_vs_frozen_native':(t[:,8:12],data['native_products'],False)}
        rows=[]
        for group in [dict(case='all',producer='q_and_k',start=0,pairs=len(t)),*groups]:
            sl=slice(group['start'],group['start']+group['pairs'])
            row={**group,**{key:compare_words(a[sl],b[sl],bf16=bf) for key,(a,b,bf) in comparisons.items()}}
            sums=t[sl,12:14]; projected=t[sl,16:18]; native=data['native_outputs'][sl]
            midpoint=(sums & 0xFFFF)==0x8000
            row['rounding_diagnostics']={'sum_at_terminal_BF16_midpoint':int(np.count_nonzero(midpoint)),
                'native_mismatches_at_candidate_midpoint':int(np.count_nonzero(midpoint & (projected!=native))),
                'native_zero_candidate_nonzero':int(np.count_nonzero(((native & 0x7FFFFFFF)==0) & ((projected & 0x7FFFFFFF)!=0))),
                'selected_products_changed_from_FP32':int(np.count_nonzero(t[sl,8:12]!=t[sl,0:4]))}
            # Coordinates use corpus pair order plus lane 0=i / lane 1=i+32.
            error=np.abs(projected.view(np.float32).astype(np.float64)-native.view(np.float32).astype(np.float64))
            pos=np.unravel_index(error.argmax(),error.shape)
            pair=group['start']+int(pos[0]);lane=int(pos[1])
            owner=next(g for g in groups if g['start']<=pair<g['start']+g['pairs'])
            offset=pair-owner['start']
            row['max_abs_witness']={'flat_pair_index':pair,'lane':lane,'case':owner['case'],'producer':owner['producer'],
                'token':offset//(owner['heads']*32),'head':offset//32%owner['heads'],'channel':offset%32+lane*32,
                'inputs_hex':[f'{x:08x}' for x in data['inputs'][pair]],'candidate_hex':f'{t[pair,16+lane]:08x}',
                'frozen_native_hex':f'{data["native_outputs"][pair,lane]:08x}','abs_error':float(error[pos])}
            rows.append(row)
        result[variant]=rows
        for key,(a,b,_) in comparisons.items():
            mismatch_arrays[variant+'__'+key]=np.argwhere(a!=b).astype(np.uint32)
    np.savez_compressed(output/(name+'_mismatch_indices.npz'),**mismatch_arrays)
    return result


def synthetic_inputs():
    verify_fixtures()
    historical=np.load(FIXTURES/'historical_arithmetic.npy',allow_pickle=False)
    rng=random.Random(0x524E4246)
    random_bf16=np.array([[(rng.randrange(2)<<31)|(rng.randrange(60,191)<<23)|(rng.randrange(128)<<16) for _ in range(4)] for _ in range(4096)],dtype=np.uint32)
    zeros=np.array([(e,o,c,s) for e in (0,0x80000000) for o in (0,0x80000000) for c in (0x3F800000,0xBF800000) for s in (0,0x80000000,0x3F800000,0xBF800000)],dtype=np.uint32)
    tiny=np.array([(rng.randrange(0x00800000)|(rng.randrange(2)<<31),rng.randrange(0x00800000)|(rng.randrange(2)<<31),0x3F000000,0x3F800000) for _ in range(1024)],dtype=np.uint32)
    return np.concatenate((historical,random_bf16,zeros,tiny))


def rejected_cases(executable):
    inputs=[(w,0,0x3F800000,0) for w in (0x7F800000,0xFF800000,0x7FC00000,0x7F800001)]
    inputs += [(0x7F7FFFFF,0,0x40000000,0),(0x7F7FFFFF,0,0x3F800000,0),
               (0x7F7F0000,0x7F7F0000,0x3F800000,0xBF800000)]
    result=[]
    for row in inputs:
        reasons={}
        for variant in VARIANTS:
            try:trace_pair(*row,variant)
            except ValueError as exc:reasons[variant]=str(exc)
        require(len(reasons)==4,'unsupported case unexpectedly accepted')
        p=subprocess.run([str(executable)],input=' '.join(f'{x:08x}' for x in row)+'\n',capture_output=True,text=True)
        require(p.returncode!=0 and not p.stdout.strip(),'independent C failed to reject unsupported row')
        result.append({'inputs':[f'{x:08x}' for x in row],'rejections':reasons,'independent_C_exit':p.returncode})
    return result


def run(output, compiler='gcc'):
    require(not output.exists() or not any(output.iterdir()),'output must be fresh or empty')
    verify_fixtures()
    sources=['scripts/run_rope_rounding_ablation.py','scripts/freeze_rope_rounding_corpora.py','scripts/rope_rounding_fenv_reference.c','src/heteronpu/rope_rounding_ablation.py','src/heteronpu/rope_hardware_oracle.py','src/heteronpu/qwen35_bf16_reference.py']
    source_hashes={p:record(ROOT/p)['sha256'] for p in sources}
    output.mkdir(parents=True,exist_ok=True)
    executable,cinfo=compile_reference(output,compiler)
    report={'schema_version':1,'status':'PASS_FROZEN_CORPUS_SOFTWARE_ABLATION_ONLY',
            'production_policy_changed':False,'candidate_RTL_executed':False,'historical_hardware_baseline_only':True,
            'model_native_expectations_regenerated':False,'U00_2_complete':False,'U01_complete':False,'mac_utilization_measured':False,
            'scope':'conditional_same_input_RoPE_pair_software_only_not_full_block_or_storage',
            'trace_columns':COLUMNS,'variants':VARIANTS,'fixture_sha256':FIXTURE_PINS,'independent_reference':cinfo,
            'BF16_conversion_flags_policy':'not_defined_software_value_ablation_only',
            'runtime':{'python':sys.version,'numpy':np.__version__,'platform':platform.platform()},'corpora':{}}
    for name in ('local','remote'):
        data,provenance=load_corpus(name)
        traces=calculate(data['inputs'])
        require(np.array_equal(traces[:,0,12:14],data['hardware_comb'][:,:2]),'baseline historical hardware values drift')
        aggregate=np.bitwise_or.reduce(traces[:,0,[4,5,6,7,14,15]],axis=1)
        require(np.array_equal(aggregate,data['hardware_comb'][:,2]),'baseline historical hardware flags drift')
        require(np.array_equal(traces[:,3,8:12],data['native_products']),'both-BF16 frozen native product mismatch')
        require(np.array_equal(traces[:,3,16:18],data['native_outputs']),'both-BF16 frozen native output mismatch')
        np.save(output/(name+'_traces.npy'),traces,allow_pickle=False)
        independent=independent_check(executable,data['inputs'],traces,output,name)
        metrics=group_metrics(traces,data,output,name,provenance['groups'])
        report['corpora'][name]={'provenance':provenance,'metrics':metrics,'independent':independent,
                                'historical_actual_RTL_outputs_and_flags_replayed':True,'native_products_and_outputs_bitwise_replayed':True}
        if name=='remote':
            idx=69266
            require(tuple(map(int,data['inputs'][idx]))==(0xBF920000,0xC1100000,0x3F800000,0x3CE10000),'permanent witness moved')
            report['permanent_witness']={'flat_pair_index':idx,'case':'carried_m128','producer':'q','token':110,'head':4,'even_channel':18,'odd_channel':50,
                'inputs':[f'{x:08x}' for x in data['inputs'][idx]],'frozen_native':[f'{x:08x}' for x in data['native_outputs'][idx]],
                'traces':{v:{col:f'{x:08x}' for col,x in zip(COLUMNS,traces[idx,i])} for i,v in enumerate(VARIANTS)}}
        print(name+': all saved native products/outputs and actual hardware baseline verified',flush=True)
    synthetic=synthetic_inputs();st=calculate(synthetic)
    np.save(output/'synthetic_inputs.npy',synthetic,allow_pickle=False)
    np.save(output/'synthetic_traces.npy',st,allow_pickle=False)
    report['synthetic']={'historical_FP32_directed_random':2055,'new_random_BF16':4096,'signed_zero':32,'raw_FP32_subnormal':1024,
                         'independent':independent_check(executable,synthetic,st,output,'synthetic',allow_tininess_difference=True),
                         'unsupported_cases':rejected_cases(executable)}
    require(report['corpora']['remote']['metrics']['fp32_all'][0]['terminal_BF16_vs_frozen_native']['mismatches_over_max']==1,'lost real source rejection')
    require(source_hashes=={p:record(ROOT/p)['sha256'] for p in sources},'ablation source changed during run')
    verify_fixtures()
    report['source_sha256']=source_hashes
    report['artifacts']={p.name:record(p) for p in sorted(output.iterdir()) if p.is_file() and p.name!='result.json' and p.name!='fenv_reference'}
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--compiler',default='gcc')
    args=p.parse_args()
    try:r=run(args.output.resolve(),args.compiler)
    except (ValueError,KeyError,TypeError,OSError,subprocess.SubprocessError) as exc:
        print('ROPE_ABLATION_REJECTED: '+str(exc),file=sys.stderr);raise SystemExit(3)
    print(r['status'])
