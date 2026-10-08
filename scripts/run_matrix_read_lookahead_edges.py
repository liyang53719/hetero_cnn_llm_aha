#!/usr/bin/env python3
"""Reproducible supplemental actual-wrapper A2 error/reset proof, source-only.

Builds a transient instrumented copy; frozen production RTL, primary bench and
primary verifier remain unchanged. CLI accepts only the published pinned cache.
run_prepared is for a caller holding a fresh materializer receipt in-process.
"""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from heteronpu.model_geometry import require
from heteronpu.matrix_norm_rope_tile16_candidate import verify_materialized
import run_matrix_read_lookahead as primary
from verify_matrix_read_lookahead_edges import verify_trace
BENCH='tb/tb_qwen35_matrix_norm_rope_tile16.sv'
FRAGMENT='tb/qwen2_matrix_read_lookahead_edges.svh'
EXTRA=(FRAGMENT,'scripts/run_matrix_read_lookahead_edges.py','scripts/verify_matrix_read_lookahead_edges.py')

def replace_once(text,old,new):
    require(text.count(old)==1,'transient bench anchor drift: '+old[:90])
    return text.replace(old,new)

def make_bench():
    text=(ROOT/BENCH).read_text()
    text=replace_once(text,'  // Single in-flight read model and explicit, delayed write acknowledgments.',
                      (ROOT/FRAGMENT).read_text()+'\n  // Single in-flight read model and explicit, delayed write acknowledgments.')
    text=replace_once(text,'rperror<=!fault_injected&&fault_read_region==regid;',
        'rperror<=!fault_injected&&fault_read_region==regid&&(!edge_fault||addr==act_base+128);')
    text=replace_once(text,'if(!fault_injected&&fault_read_region==regid)fault_injected=1;',
        'if(!fault_injected&&fault_read_region==regid&&(!edge_fault||addr==act_base+128))fault_injected=1;')
    for event,hook in [('l2_read','edge_read_request(addr,regid);'),('l2_response','edge_read_response();')]:
        matches=[line for line in text.splitlines() if '$fdisplay(trace_fd,' in line and '\\"event\\":\\"'+event+'\\"' in line]
        require(len(matches)==1,'trace hook anchor drift: '+event)
        text=replace_once(text,matches[0],matches[0]+'\n        '+hook)
    text=replace_once(text,'      if(start&&ready)begin','      edge_tick();\n      if(start&&ready)begin')
    text=replace_once(text,'      if(done)begin\n        done_cycle=cycle;',
                      '      if(done)begin\n        edge_done();\n        done_cycle=cycle;')
    anchor='    if(suite=="main"||suite=="all")for(integer c=0;c<4;c++)good_case(c,0);'
    text=replace_once(text,anchor,
        '    if(suite=="lookahead_edges")begin\n'
        '      if(!READ_LOOKAHEAD||fabric_profile!=FAB_UNSTALLED||!metrics_fd)$fatal(1,"supplemental mode requires lookahead/unstalled/metrics");\n'
        '      edge_fault_case();good_case(1,0,1);edge_reset_case();good_case(1,0,1);\n'
        '      if(success_count!=2||fault_count!=1||reset_count!=1)$fatal(1,"supplemental command inventory");\n'
        '      $display("MATRIX_LOOKAHEAD_EDGES_PASS faults=1 resets=1 recoveries=2 recovery_steps=32768 original_scoreboard=1");\n'
        '    end\n'+anchor)
    return text

def source_hashes():
    return {**primary.source_hashes(),**{p:primary.sha256(ROOT/p) for p in EXTRA}}

def run_prepared(args,*,trusted_summary_sha256):
    """Use only an in-process fresh receipt or the fixed published CLI receipt."""
    require(not args.output.exists() or not any(args.output.iterdir()),'supplemental output must be new/empty')
    args.output.mkdir(parents=True,exist_ok=True)
    hashes=source_hashes()
    fixture=verify_materialized(args.vectors,trusted_summary_sha256=trusted_summary_sha256)
    require(fixture['native_gate_pass'],'selected native source gate failed')
    manifest=[sys.executable,str(ROOT/'chisel/matrix_norm_rope_hardware/manifest.py'),'verify',str(ROOT),str(args.generated)]
    subprocess.run(manifest,check=True,timeout=90)
    generated_hash=primary.sha256(args.generated/'HeteroMatrixNormRoPEHardwarePrimitives.sv')
    bench=args.output/'tb_supplemental.sv';bench.write_text(make_bench())
    bench_hash=primary.sha256(bench)
    command=[str(args.verilator or ROOT/'work/rope_hardware_oracle/bin/verilator'),'--binary','--timing','-Wno-fatal','-j','2',
             '--output-split','12000','--output-split-cfuncs','300','--top-module','tb_qwen35_matrix_norm_rope_tile16',
             '-GREAD_LOOKAHEAD=1','--Mdir',str(args.output/'obj'),'-o','tb',
             str(args.generated/'HeteroMatrixNormRoPEHardwarePrimitives.sv'),
             *(str(ROOT/p) for p in primary.tile16.RTL_SOURCES if not p.startswith('tb/')),str(bench)]
    primary.tile16.legacy.run_logged(command,args.output/'build.log',timeout=3600)
    fifo=args.output/'trace.fifo';os.mkfifo(fifo);writer=compressor=None
    trace=args.output/'trace.jsonl.gz';log=args.output/'run.log';metrics=args.output/'metrics.jsonl'
    try:
        with trace.open('wb') as zipped,log.open('w') as out:
            compressor=subprocess.Popen(['bash','-c','exec gzip -6 < "$1"','gzip-reader',str(fifo)],stdout=zipped,stderr=subprocess.PIPE)
            writer=subprocess.Popen([str(args.output/'obj/tb'),'+vectors='+str(args.vectors),'+suite=lookahead_edges',
                '+fabric=unstalled','+metrics='+str(metrics),'+trace='+str(fifo)],stdout=out,stderr=subprocess.STDOUT,cwd=ROOT)
            require(writer.wait(timeout=1800)==0,'supplemental actual RTL failed: '+str(log))
            _,error=compressor.communicate(timeout=120)
            require(compressor.returncode==0,'supplemental trace compressor failed: '+error.decode(errors='replace'))
    finally:
        for p in (writer,compressor):
            if p is not None and p.poll() is None:p.kill();p.wait(timeout=30)
        fifo.unlink(missing_ok=True)
    result=verify_trace(trace,args.vectors)
    text=log.read_text()
    require(text.count('MATRIX_LOOKAHEAD_EDGES_PASS faults=1 resets=1 recoveries=2 recovery_steps=32768 original_scoreboard=1')==1,'missing supplemental runtime proof')
    verify_materialized(args.vectors,trusted_summary_sha256=trusted_summary_sha256)
    subprocess.run(manifest,check=True,timeout=90)
    require(hashes==source_hashes(),'source changed during supplemental proof')
    require(primary.sha256(bench)==bench_hash and bench.read_text()==make_bench(),'derived harness changed during supplemental proof')
    require(generated_hash==primary.sha256(args.generated/'HeteroMatrixNormRoPEHardwarePrimitives.sv'),'generated arithmetic changed')
    result.update(source_sha256=hashes,fixture_summary_sha256=trusted_summary_sha256,
        transient_bench_sha256=bench_hash,generated_rtl_sha256=generated_hash,
        compressed_trace_sha256=primary.sha256(trace),metrics_sha256=primary.sha256(metrics),log_sha256=primary.sha256(log),
        build_command=command,source='baseline',lookahead=1,fabric='unstalled',new_weight_copies=0)
    (args.output/'summary.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    return result

def run(args):
    receipt=primary.read_contract()['cached_fixture_receipt_sha256']
    return run_prepared(args,trusted_summary_sha256=receipt)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cached-vectors',dest='vectors',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--generated',type=Path,default=ROOT/'work/generated/matrix_norm_rope_tile16_candidate')
    p.add_argument('--verilator',type=Path)
    a=p.parse_args()
    for k,v in vars(a).items():
        if isinstance(v,Path):setattr(a,k,v.resolve())
    try:r=run(a)
    except (ValueError,KeyError,TypeError,OSError,EOFError,subprocess.SubprocessError) as e:
        print('MATRIX_LOOKAHEAD_EDGES_REJECTED: '+str(e),file=sys.stderr);raise SystemExit(3)
    print(r['status'])
