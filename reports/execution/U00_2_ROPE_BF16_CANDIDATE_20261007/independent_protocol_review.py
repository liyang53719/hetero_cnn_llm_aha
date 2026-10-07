#!/usr/bin/env python3
"""Replay the independent phase-reset/order/trace-stability review on real RTL.

Prerequisite: the official runner has emitted and verified pinned primitives.
This reviewer verifies that manifest again, uses a separate testbench, and never
claims fresh primitive emission itself or any synthesis/PPA result.
"""
from pathlib import Path
import hashlib
import json
import re
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[3]
REPORT=Path(__file__).resolve().parent
GENERATED=ROOT/'work/generated/rope_bf16_candidate'
OUTPUT=ROOT/'work/rope_bf16_independent_protocol_final'
VERILATOR=ROOT/'work/rope_hardware_oracle/bin/verilator'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    OUTPUT.mkdir(parents=True,exist_ok=True)
    manifest_command=[sys.executable,str(ROOT/'chisel/rope_hardware_oracle/manifest.py'),'verify',str(ROOT),str(GENERATED)]
    subprocess.run(manifest_command,check=True,timeout=60)
    sources=[GENERATED/'HeteroRoPEHardwarePrimitives.sv',
       ROOT/'rtl/sfu/fp32_to_bf16_rne_candidate.sv',
       ROOT/'rtl/sfu/fp32_rope_pair_bf16_candidate.sv',
       ROOT/'rtl/sfu/fp32_rope_pair_bf16_pipe_candidate.sv',
       REPORT/'tb_independent_protocol.sv']
    source_hashes={str(x.relative_to(ROOT)):digest(x) for x in sources}
    runs=[]
    for pipe in (0,1):
        obj=OUTPUT/f'obj{pipe}'
        command=[str(VERILATOR),'--binary','--timing','-Wno-fatal','-j','4',
           '--top-module','tb_independent_protocol',f'-GPIPE={pipe}',
           '--Mdir',str(obj),'-o','tb',*[str(x) for x in sources]]
        build_log=REPORT/f'independent_protocol_pipe{pipe}_build.log'
        with build_log.open('w') as log:
            subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True,cwd=ROOT,timeout=300)
        run_log=REPORT/f'independent_protocol_pipe{pipe}_run.log'
        with run_log.open('w') as log:
            subprocess.run([str(obj/'tb')],stdout=log,stderr=subprocess.STDOUT,check=True,cwd=ROOT,timeout=60)
        pattern=r'INDEPENDENT_PROTOCOL_PASS pipe=(\d+) reset_cases=(\d+) reset_phase_mask=([0-9a-f]+) transfers=(\d+) stall_checks=(\d+)'
        matches=re.findall(pattern,run_log.read_text())
        if len(matches)!=1:
            raise ValueError('missing or duplicate protocol PASS marker')
        p,resets,mask,transfers,stalls=matches[0]
        metrics={'pipe':int(p),'reset_cases':int(resets),'reset_phase_mask':int(mask,16),'ordered_transfers':int(transfers),'full_trace_stall_checks':int(stalls)}
        if metrics['pipe']!=pipe or metrics['reset_cases']!=(19 if pipe==0 else 18) or metrics['reset_phase_mask']!=(15 if pipe==0 else 63) or metrics['ordered_transfers']!=1024 or metrics['full_trace_stall_checks']<=0:
            raise ValueError('incomplete protocol coverage')
        runs.append({'metrics':metrics,'command':command,'build_log':build_log.name,'build_log_sha256':digest(build_log),'run_log':run_log.name,'run_log_sha256':digest(run_log)})
    if source_hashes!={str(x.relative_to(ROOT)):digest(x) for x in sources}:
        raise ValueError('review sources changed during run')
    subprocess.run(manifest_command,check=True,timeout=60)
    report={'status':'PASS_INDEPENDENT_RTL_PROTOCOL_REVIEW','source_sha256':source_hashes,
      'reviewer_script_sha256':digest(Path(__file__)),
      'primitive_manifest_sha256':digest(GENERATED/'manifest.json'),
      'reset_assertion':'Asynchronous, 2ns after falling edge; outputs/counters/all trace checked after 1ns; held over three rising clocks',
      'reset_coverage':'All four elastic occupancy states and all six registered-wrapper FSM states; drain after every reset',
      'traffic':'1024 distinct exact BF16 values per implementation, deterministic bubbles and stalls; one-to-one ordering and full trace checked from an independent handshake queue',
      'runs':runs,'PPA_measured':False,
      'limitation':'Simulation proves these directed scenarios only, not formal universal protocol correctness or physical reset recovery/removal timing.'}
    (REPORT/'independent_protocol_review.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__': main()
