#!/usr/bin/env python3
"""Causal single-owner lookahead A/B, frozen Q8/K2 numerical source gate.

Default CLI materializes official sources and independent integer/C references.
A disk-bounded local option reuses only the previously published fixed receipt,
fully rechecked before and after; no user-selected saved-array digest is trusted.
Every full512-lane trace streams into the independent verifier and through EOF.
"""
from __future__ import annotations
from collections import Counter
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from heteronpu.model_geometry import require
from heteronpu.matrix_norm_rope_tile16_candidate import materialize,verify_materialized
import run_matrix_norm_rope_tile16_candidate as tile16
from run_matrix_norm_rope_tensor_candidate import sha256
from verify_matrix_read_lookahead_metrics import verify_metrics,verify_pair_metrics
CONTRACT='config/upstream/qwen3_5_0p8b/matrix_read_lookahead_contract.json'
EXTRA=('scripts/run_matrix_read_lookahead.py','scripts/verify_matrix_read_lookahead_stream.py',
       'scripts/verify_matrix_read_lookahead_metrics.py',CONTRACT,
       'reports/execution/U00_2_MATRIX_TOKEN_TILE16_20261008/result.json')

def source_hashes():
    return {**tile16.source_hashes(),**{p:sha256(ROOT/p) for p in EXTRA}}

def read_contract():
    c=json.loads((ROOT/CONTRACT).read_text())
    require(c['schema_version']==1 and c['default_enabled'] is False,'lookahead contract drift')
    require(c['fabrics']==['unstalled','replay'] and c['sources']==['baseline','avx2'] and c['lookahead_values']==[0,1],'A/B inventory drift')
    old=json.loads((ROOT/c['cached_fixture_source']).read_text())
    require(old['fixture_summary_sha256']==c['cached_fixture_receipt_sha256'],'published fixture pin mismatch')
    return c

def prepare_fixture(args,c):
    if args.cached_vectors:
        digest=c['cached_fixture_receipt_sha256']
        fixture=verify_materialized(args.cached_vectors,trusted_summary_sha256=digest)
        return args.cached_vectors,fixture,digest,'published_pinned_cache_revalidated'
    root=args.output/'vectors'
    fixture=materialize(ROOT,args.payload_layer0,args.payload_layer3,args.payload_extra,root)
    return root,fixture,fixture['summary_sha256'],'fresh_official_integer_and_C_materialization'

def build(args,lookahead):
    obj=args.output/('obj_'+str(lookahead));obj.mkdir()
    verilator=args.verilator or ROOT/'work/rope_hardware_oracle/bin/verilator'
    command=[str(verilator),'--binary','--timing','-Wno-fatal','-j',str(args.jobs),
             '--output-split','12000','--output-split-cfuncs','300',
             '--top-module','tb_qwen35_matrix_norm_rope_tile16','-GREAD_LOOKAHEAD='+str(lookahead),
             '--Mdir',str(obj),'-o','tb',str(args.generated/'HeteroMatrixNormRoPEHardwarePrimitives.sv'),
             *(str(ROOT/p) for p in tile16.RTL_SOURCES)]
    tile16.legacy.run_logged(command,args.output/('build_'+str(lookahead)+'.log'),timeout=3600)
    return obj/'tb',command

def run_stream(binary,vectors,output,*,source,fabric,lookahead,suite):
    key=f'{source}_{fabric}_{lookahead}_{suite}';prefix=output/key
    fifo=prefix.with_suffix('.fifo');require(not fifo.exists(),'stream FIFO already exists')
    os.mkfifo(fifo);worker=writer=None;started=time.monotonic()
    result_path=prefix.with_suffix('.verified.json');metrics=prefix.with_suffix('.metrics.jsonl')
    log=prefix.with_suffix('.log');verifier_log=prefix.with_suffix('.verifier.log')
    try:
        with verifier_log.open('w') as err,log.open('w') as out:
            worker=subprocess.Popen([sys.executable,str(ROOT/'scripts/verify_matrix_read_lookahead_stream.py'),
                '--fifo',str(fifo),'--vectors',str(vectors),'--suite',suite,'--output',str(result_path)],
                stdout=err,stderr=subprocess.STDOUT,cwd=ROOT)
            writer=subprocess.Popen([str(binary),'+vectors='+str(vectors),'+suite='+suite,'+fabric='+fabric,
                '+trace='+str(fifo),'+metrics='+str(metrics)],stdout=out,stderr=subprocess.STDOUT,cwd=ROOT)
            deadline=time.monotonic()+28800
            while writer.poll() is None:
                require(worker.poll() in (None,0),'independent stream verifier failed before simulator completion: '+str(verifier_log))
                require(time.monotonic()<deadline,'stream simulator timed out');time.sleep(1)
            require(writer.returncode==0,'actual RTL simulator failed: '+str(log))
            require(worker.wait(timeout=900)==0,'independent full-stream verification failed: '+str(verifier_log))
        result=json.loads(result_path.read_text());counts,cases=tile16.verify_log(log.read_text(),suite,require_stalls=fabric!='unstalled')
        checked=result['independent_trace'];successes=[r for r in checked['terminals'] if r['status']==0]
        require(len(cases)==len(successes),'log/trace successful inventory mismatch')
        for row,observed in zip(cases,successes):
            require(row['name']==observed['name'] and row['cycles']==observed['accepted_to_done_cycles'] and row['matrix_steps']==observed['matrix_packets'] and row['heads']==observed['completed_heads'] and row['tokens']==observed['completed_tokens'] and row['ddr_read_bytes']==observed['ddr_read_bytes'] and row['ddr_write_bytes']==observed['ddr_write_bytes'],'independent log/trace counters differ')
        require(checked['events']['matrix_input']==counts['actual_matrix_inputs'] and checked['events']['matrix']==counts['actual_matrix_outputs'],'actual input/output trace count mismatch')
        return {**result,'source':source,'fabric':fabric,'lookahead':lookahead,'suite':suite,'log_sha256':sha256(log),
                'metrics_sha256':sha256(metrics),'metrics_path':metrics.name,
                'command_metrics':verify_metrics(metrics,checked,fabric=fabric,lookahead=lookahead),
                'rtl_metrics':counts,'command_counters':cases,
                'simulation_and_stream_verification_tool_wall_seconds':time.monotonic()-started}
    finally:
        for process in (writer,worker):
            if process is not None and process.poll() is None:process.kill();process.wait(timeout=30)
        fifo.unlink(missing_ok=True)

def compare_runs(runs):
    inventory=Counter((source,fabric,flag,'main') for source in ('baseline','avx2') for fabric in ('unstalled','replay') for flag in (0,1))
    inventory[('baseline','random',1,'all')]=1
    require(Counter((r['source'],r['fabric'],r['lookahead'],r['suite']) for r in runs)==inventory,'incomplete A/B and randomstress run inventory')
    by={(r['source'],r['fabric'],r['lookahead']):r for r in runs if r['suite']=='main'}
    require(len(by)==8 and len(runs)==9,'incomplete A/B and randomstress run inventory')
    comparisons=[]
    for source in ('baseline','avx2'):
        for fabric in ('unstalled','replay'):
            a,b=by[source,fabric,0],by[source,fabric,1]
            verify_pair_metrics(a['command_metrics'],b['command_metrics'])
            require([{k:v for k,v in r.items() if k!='cycles'} for r in a['command_counters']]==[{k:v for k,v in r.items() if k!='cycles'} for r in b['command_counters']],'A/B byte/head/token workload mismatch')
            ac=sum(r['cycles'] for r in a['command_counters']);bc=sum(r['cycles'] for r in b['command_counters'])
            require(sum(r['matrix_steps'] for r in a['command_counters'])==sum(r['matrix_steps'] for r in b['command_counters'])==294912,'A/B workload drift')
            require(bc<=ac,'lookahead regressed paired command cycles')
            if fabric=='replay':require(bc<ac,'lookahead did not reduce deterministic-delay command cycles')
            comparisons.append({'source':source,'fabric':fabric,'default_cycles':ac,'lookahead_cycles':bc,
                'causal_injected_delay_schedule_equal':True,'cycles_saved':ac-bc,'speedup':ac/bc,'relative_cycle_reduction':(ac-bc)/ac,
                'useful_fma':150994944,'fixed_matrix_lanes':512,
                'default_candidate_useful_wall_fraction':150994944/(512*ac),
                'lookahead_candidate_useful_wall_fraction':150994944/(512*bc),'whole_block_metric':False})
    return comparisons

def run(args):
    require(1<=args.jobs<=2,'jobs must be1..2')
    require(not args.output.exists() or not any(args.output.iterdir()),'output must be new/empty')
    args.output.mkdir(parents=True,exist_ok=True)
    require(shutil.disk_usage(args.output).free>(600 if args.cached_vectors else 3000)*1024**2,'insufficient free space for bounded build and fixture')
    c=read_contract();hashes=source_hashes();started=time.monotonic()
    vectors,fixture,receipt,origin=prepare_fixture(args,c)
    require(hashes==source_hashes(),'source changed during fixture preparation')
    env=os.environ.copy();env.update(OUT=str(args.generated),PYTHON_BIN=sys.executable)
    if args.verilator:env['VERILATOR_BIN']=str(args.verilator)
    tile16.legacy.run_logged(['bash',ROOT/'scripts/generate_matrix_norm_rope_primitives.sh'],args.output/'emission.log',env=env)
    manifest=[sys.executable,str(ROOT/'chisel/matrix_norm_rope_hardware/manifest.py'),'verify',str(ROOT),str(args.generated)]
    subprocess.run(manifest,check=True,timeout=90,env=env)
    bins={};builds={}
    for flag in (0,1):bins[flag],builds[flag]=build(args,flag)
    runs=[]
    for fabric in ('unstalled','replay'):
        for source in ('baseline','avx2'):
            for flag in (0,1):
                r=run_stream(bins[flag],vectors/('avx2' if source=='avx2' else ''),args.output,source=source,fabric=fabric,lookahead=flag,suite='main')
                runs.append(r);(args.output/'partial_runs.json').write_text(json.dumps(runs,indent=2,sort_keys=True)+'\n')
                print(f'PASSED complete stream: {source}/{fabric}/lookahead={flag}',flush=True)
    runs.append(run_stream(bins[1],vectors,args.output,source='baseline',fabric='random',lookahead=1,suite='all'))
    verify_materialized(vectors,trusted_summary_sha256=receipt)
    subprocess.run(manifest,check=True,timeout=90,env=env)
    require(hashes==source_hashes(),'source changed during A/B gate')
    summary={'schema_version':1,'status':'PASS_SINGLE_OWNER_MATRIX_READ_LOOKAHEAD_AB','source_sha256':hashes,
        'fixture_summary_sha256':receipt,'fixture_origin':origin,'fixture_totals':fixture['totals'],
        'native_selected_gate_pass':fixture['native_gate_pass'],'native_failed_comparisons':fixture['native_failed_comparisons'],
        'native_failed_command_comparisons':fixture['native_failed_command_comparisons'],
        'native_full_block_gate_pass':fixture['native_full_block_gate_pass'],
        'hardware_manifest_sha256':sha256(args.generated/'manifest.json'),
        'generated_rtl_sha256':json.loads((args.generated/'manifest.json').read_text())['emitted_sha256'],
        'build_commands':builds,'runs':runs,'comparisons':compare_runs(runs),
        'full_M128_rtl_coverage':False,'whole_block_MAC90_measured':False,'PPA_measured':False,
        'production_default_changed':False,'raw_traces_retained':False,'replay_requires_regeneration':True,
        'total_tool_wall_seconds':time.monotonic()-started}
    require(summary['native_selected_gate_pass'],'source native threshold failed despite RTL match')
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n')
    return summary

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--cached-vectors',type=Path,help='Only the published fixed receipt is eligible; all provenance/files revalidated')
    p.add_argument('--generated',type=Path,default=ROOT/'work/generated/matrix_norm_rope_tile16_candidate')
    p.add_argument('--verilator',type=Path);p.add_argument('--jobs',type=int,default=2)
    for suffix in ('layer0','layer3','extra'):
        p.add_argument('--payload-'+suffix,type=Path,default=ROOT/('work/qwen35_'+('prefix' if suffix=='extra' else suffix)+'_payload'))
    a=p.parse_args()
    for k,v in vars(a).items():
        if isinstance(v,Path):setattr(a,k,v.resolve())
    try:r=run(a)
    except (ValueError,KeyError,TypeError,OSError,EOFError,subprocess.SubprocessError) as e:
        print('MATRIX_READ_LOOKAHEAD_REJECTED: '+str(e),file=sys.stderr);raise SystemExit(3)
    print(r['status'])
