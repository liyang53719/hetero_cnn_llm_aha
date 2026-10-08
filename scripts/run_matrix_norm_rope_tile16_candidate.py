#!/usr/bin/env python3
"""Fresh default-off Matrix16x32 token batching, full512-lane RTL and event gate.

The CLI always rebuilds pinned official sources and independent integer/C oracles.
Large traces are losslessly compressed while the simulator writes an ordinary
FIFO; summary publication never includes source payload or full trace files.
"""
from __future__ import annotations
import argparse
import gzip
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from heteronpu.model_geometry import require
import run_matrix_norm_rope_candidate as legacy
from run_matrix_norm_rope_tensor_candidate import sha256
from verify_matrix_norm_rope_tile16_trace import verify_trace
CONTRACT='config/upstream/qwen3_5_0p8b/matrix_norm_rope_tile16_contract.json'
RTL_SOURCES=tuple(p for p in legacy.RTL_SOURCES if not p.startswith('tb/'))+('tb/tb_qwen35_matrix_norm_rope_tile16.sv',)
EXTRA_SOURCES=legacy.EXTRA_SOURCES+(CONTRACT,'scripts/run_matrix_norm_rope_tile16_candidate.py',
    'scripts/verify_matrix_norm_rope_tensor_trace.py','scripts/verify_matrix_norm_rope_tile16_trace.py',
    'scripts/run_matrix_norm_rope_tensor_candidate.py','scripts/materialize_matrix_norm_rope_tile16_vectors.py',
    'src/heteronpu/matrix_norm_rope_tile16_candidate.py')


def _fields(text,strings=()):
    result={}
    for token in text.split():
        pair=token.split('=')
        require(len(pair)==2 and pair[0] not in result,'malformed/duplicate log field')
        key,value=pair
        require(re.fullmatch(r'[a-zA-Z_][a-zA-Z_0-9]*',key) is not None,'malformed log key')
        if key not in strings:
            require(re.fullmatch(r'0|[1-9][0-9]*',value) is not None,'malformed numeric log value')
            value=int(value)
        result[key]=value
    return result


def verify_log(text,suite):
    markers=re.findall(r'QWEN35_MATRIX_NORM_ROPE_TILE16_PASS ([^\n]+)',text)
    require(len(markers)==1,'missing/duplicate tile16 PASS marker')
    metrics=_fields(markers[0],('suite',))
    require(metrics.pop('suite',None)==suite,'tile16 suite mismatch')
    expected={'main':(4,0,0,0),'all':(10,35,2,2)}
    require(suite in expected and tuple(metrics.get(k) for k in ('successes','rejects','faults','resets'))==expected[suite],'tile16 transaction inventory mismatch')
    required={'successes','rejects','faults','resets','capacity_bytes','source_injection','matrix_lanes_per_output',
              'actual_matrix_inputs','actual_matrix_outputs','explicit_write_acks','read_stall_cycles',
              'write_stall_cycles','dma_stall_cycles','delayed_ACK_cycles','same_cycle_ACKs'}
    require(set(metrics)==required,'aggregate log field inventory drift')
    require(metrics['capacity_bytes']==1572864 and metrics['source_injection']==0 and metrics['matrix_lanes_per_output']==512,'tile16 resource/source claim drift')
    for key in ('actual_matrix_inputs','actual_matrix_outputs','explicit_write_acks','read_stall_cycles','write_stall_cycles','dma_stall_cycles','delayed_ACK_cycles','same_cycle_ACKs'):
        require(metrics[key]>0,'missing real tile16 handshake/stall: '+key)
    require(metrics['actual_matrix_inputs']==metrics['actual_matrix_outputs'],'Matrix accepted/output count mismatch')
    require(metrics['actual_matrix_inputs']==(294912 if suite=='main' else 450560),'Matrix packet coverage drift')
    require(metrics['explicit_write_acks']==(9728 if suite=='main' else 12800),'producer ACK coverage drift')
    inventory=[('cold_Q',0,16),('cold_K',1,16),('carried_Q',2,16),('carried_K',3,16)]
    if suite=='all':inventory += [('recovery_after_fault_or_reset',1,1)]*2+[('legal_exact_1p5MiB_end',1,1)]+[('tail_'+str(n),1,n) for n in (1,3,17)]
    rows=re.findall(r'QWEN35_MATRIX_NORM_ROPE_TILE16_CASE_PASS ([^\n]+)',text)
    require(len(rows)==len(inventory),'case counter inventory missing')
    cases=[]
    for line,(name,command,n) in zip(rows,inventory):
        values=_fields(line,('test',))
        require(set(values)=={'command','test','heads','tokens','matrix_steps','dma_requests','cycles','ddr_read_bytes','ddr_write_bytes'},'case log field inventory drift')
        require(values['test']==name and values['command']==command,'case name/order/command drift')
        h,t=(8,16) if command%2==0 else (2,8);b=(n+15)//16
        require(values['heads']==n*h and values['tokens']==n and values['matrix_steps']==b*h*t*1024,'case geometry/Matrix count drift')
        require(values['dma_requests']==n+2*b*h*t+2*n*h,'case DMA count drift')
        require(values['ddr_read_bytes']==n*2048+b*h*t*65536 and values['ddr_write_bytes']==n*h*(64*t+1024),'case DDR ACK byte drift')
        require(values['cycles']>=5*values['matrix_steps'],'impossible case payload cycle count')
        values['name']=values.pop('test');cases.append(values)
    return metrics,cases


def build(verilator,generated,output,jobs):
    obj=output/'obj_tile16'
    command=[verilator,'--binary','--timing','-Wno-fatal','-j',str(jobs),'--output-split','12000',
             '--output-split-cfuncs','300','--top-module','tb_qwen35_matrix_norm_rope_tile16',
             '--Mdir',obj,'-o','tb',generated/'HeteroMatrixNormRoPEHardwarePrimitives.sv']
    command.extend(ROOT/p for p in RTL_SOURCES)
    legacy.run_logged(command,output/'build.log',timeout=3600)
    return obj/'tb',[str(x) for x in command]


def run_compressed(binary,root,suite,log,trace,timeout=28800):
    """Drain a real FIFO concurrently; propagate simulator AND compressor errors."""
    fifo=trace.with_suffix('.fifo');require(not fifo.exists(),'trace FIFO already exists')
    os.mkfifo(fifo)
    writer=None;compressor=None
    try:
        # Shell opens the FIFO before launching gzip; it blocks until simulator
        # opens the write end. No unbounded in-memory trace capture is used.
        with trace.open('wb') as compressed,log.open('w') as output:
            compressor=subprocess.Popen(['bash','-c','exec gzip -6 < "$1"','gzip-reader',str(fifo)],stdout=compressed,stderr=subprocess.PIPE)
            writer=subprocess.Popen([str(binary),'+vectors='+str(root),'+suite='+suite,'+trace='+str(fifo)],stdout=output,stderr=subprocess.STDOUT,cwd=ROOT)
            code=writer.wait(timeout=timeout)
            require(code==0,'actual tile16 simulator failed: '+str(code))
            _,error=compressor.communicate(timeout=120)
            require(compressor.returncode==0,'lossless trace compression failed: '+error.decode(errors='replace'))
        # Reading the last byte through gzip validates its CRC and final trailer.
        with gzip.open(trace,'rb') as stream:
            while stream.read(1024*1024):pass
    finally:
        for p in (writer,compressor):
            if p is not None and p.poll() is None:p.kill();p.wait(timeout=30)
        fifo.unlink(missing_ok=True)


def source_hashes():
    from heteronpu.matrix_norm_rope_tile16_candidate import MATERIALIZER_SOURCES
    names=sorted(set(RTL_SOURCES+legacy.EMISSION_SOURCES+EXTRA_SOURCES+tuple(MATERIALIZER_SOURCES)))
    return {p:sha256(ROOT/p) for p in names}


def run_prepared(args,fixture,*,trusted_summary_sha256):
    """Internal recovery entry: caller must hold the fresh materializer receipt.

    Not exposed as a saved-array/digest CLI bypass. Public run() obtains its
    fixture in process, and this boundary always revalidates every source/file.
    """
    from heteronpu.matrix_norm_rope_tile16_candidate import verify_materialized
    fixture_dir=args.output/'vectors';hashes=source_hashes();started=time.monotonic()
    checked=verify_materialized(fixture_dir,trusted_summary_sha256=trusted_summary_sha256)
    require({k:v for k,v in fixture.items() if k!='summary_sha256'}==checked,'prepared fixture object/receipt drift')
    env=os.environ.copy();env.update(OUT=str(args.generated),PYTHON_BIN=sys.executable)
    if args.verilator:env['VERILATOR_BIN']=str(args.verilator)
    else:env.pop('VERILATOR_BIN',None)
    verilator=args.verilator or ROOT/'work/rope_hardware_oracle/bin/verilator'
    legacy.run_logged(['bash',ROOT/'scripts/generate_matrix_norm_rope_primitives.sh'],args.output/'emission.log',env=env)
    manifest=[sys.executable,ROOT/'chisel/matrix_norm_rope_hardware/manifest.py','verify',ROOT,args.generated]
    subprocess.run([str(x) for x in manifest],check=True,timeout=90,env=env)
    binary,command=build(verilator,args.generated,args.output,args.jobs)
    print('Actual Matrix16x32 and bounded Norm/RoPE tile16 owner built',flush=True)
    suites=[]
    trace_directory=getattr(args,'trace_directory',None) or args.output
    trace_directory.mkdir(parents=True,exist_ok=True)
    for source,suite,root in [('baseline','all',fixture_dir),('avx2','main',fixture_dir/'avx2')]:
        prefix=source+'_'+suite;log=args.output/(prefix+'.log');trace=trace_directory/(prefix+'.jsonl.gz')
        t=time.monotonic();run_compressed(binary,root,suite,log,trace)
        elapsed=time.monotonic()-t;metrics,counters=verify_log(log.read_text(),suite)
        check=verify_trace(trace,root,suite=suite)
        successes=[v for v in check['terminals'] if v['status']==0]
        require(len(counters)==len(successes),'log/trace successful inventory drift')
        for row,v in zip(counters,successes):
            require(row['name']==v['name'] and row['cycles']==v['accepted_to_done_cycles'] and row['matrix_steps']==v['matrix_packets'] and row['ddr_read_bytes']==v['ddr_read_bytes'] and row['ddr_write_bytes']==v['ddr_write_bytes'] and row['heads']==v['completed_heads'] and row['tokens']==v['completed_tokens'],'independent ordered command cycle/byte counter mismatch')
        require(metrics['actual_matrix_outputs']==check['events'].get('matrix',0) and metrics['actual_matrix_inputs']==metrics['actual_matrix_outputs'] and metrics['explicit_write_acks']==check['events'].get('l2_ack',0),'aggregate log/event counter drift')
        suites.append({'source':source,'suite':suite,'metrics':metrics,'command_counters':counters,
            'simulation_tool_wall_seconds':elapsed,'trace_sha256':sha256(trace),'log_sha256':sha256(log),
            'independent_trace':check})
        print(source+'/'+suite+' actual RTL and independent events passed',flush=True)
    verify_materialized(fixture_dir,trusted_summary_sha256=trusted_summary_sha256)
    subprocess.run([str(x) for x in manifest],check=True,timeout=90,env=env)
    require(hashes==source_hashes(),'source changed during tile16 verification')
    hardware=json.loads((args.generated/'manifest.json').read_text());native=fixture['native_gate_pass']
    summary={'schema_version':1,'status':'PASS_Q8_K2_TOKEN_TILE16_RTL' if native else 'REJECTED_NATIVE_SOURCE_THRESHOLD_TILE16_RTL_MATCHED',
        'hardware_manifest_sha256':sha256(args.generated/'manifest.json'),'generated_rtl_sha256':hardware['emitted_sha256'],
        'tool_versions':hardware['tool_versions'],'build_command':command,'source_sha256':hashes,
        'fixture_summary_sha256':trusted_summary_sha256,'fixture_summary':fixture,'rtl_suites':suites,
        'native_selected_tile16_gate_pass':native,'native_full_block_gate_pass':fixture['native_full_block_gate_pass'],
        'total_tool_wall_seconds':time.monotonic()-started,'actual_Matrix16x32_rows_verified':True,
        'primary_tokens_per_source':32,'primary_heads_per_source':320,'all_M128_tokens_rtl_verified':False,
        'production_policy_changed':False,'matrix_producer_injected':False,'generic_Command128_complete':False,
        'full_block_numerical_complete':False,'PPA_measured':False,'whole_block_MAC90_measured':False,'U00_2_complete':False,'U01_complete':False}
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n')
    return summary


def run(args):
    from heteronpu.matrix_norm_rope_tile16_candidate import materialize
    require(not args.output.exists() or not any(args.output.iterdir()),'output must be new/empty')
    args.output.mkdir(parents=True,exist_ok=True);hashes=source_hashes()
    fixture=materialize(ROOT,args.payload_layer0,args.payload_layer3,args.payload_extra,args.output/'vectors')
    require(hashes==source_hashes(),'source changed during fresh materialization')
    return run_prepared(args,fixture,trusted_summary_sha256=fixture['summary_sha256'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--generated',type=Path,default=ROOT/'work/generated/matrix_norm_rope_tile16_candidate')
    p.add_argument('--verilator',type=Path);p.add_argument('--jobs',type=int,default=2)
    p.add_argument('--trace-directory',type=Path,help='Optional transient trace filesystem; default is output')
    for suffix in ('layer0','layer3','extra'):
        p.add_argument('--payload-'+suffix,type=Path,default=ROOT/('work/qwen35_'+('prefix' if suffix=='extra' else suffix)+'_payload'))
    a=p.parse_args()
    for k,v in vars(a).items():
        if isinstance(v,Path):setattr(a,k,v.resolve())
    try:
        require(1<=a.jobs<=2,'jobs must be1..2 to cap build memory')
        result=run(a)
    except (ValueError,KeyError,TypeError,OSError,EOFError,subprocess.SubprocessError) as e:
        print('MATRIX_NORM_ROPE_TILE16_REJECTED: '+str(e),file=sys.stderr);raise SystemExit(3)
    print(result['status']);raise SystemExit(0 if result['native_selected_tile16_gate_pass'] else 3)
