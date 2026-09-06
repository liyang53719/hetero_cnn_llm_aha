#!/usr/bin/env python3
"""Verify external-arena ingestion without downloading checkpoint weights.

A separate invocation exports only synthetic weights, RoPE and initial hidden.
The numerical run restarts the DUT and reads that arena; it is not official
weight validation. All hardware comes from the supplied Chisel emitter output.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def run(argv: list[str], cwd: Path, logfile: Path, env: dict[str,str]) -> None:
    with logfile.open('x') as f:
        f.write('ARGV '+json.dumps(argv)+'\n');f.flush()
        result=subprocess.run(argv,cwd=cwd,env=env,stdout=f,stderr=subprocess.STDOUT)
    if result.returncode:raise RuntimeError(f'exit={result.returncode}; see {logfile}')


def sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for data in iter(lambda:f.read(1<<20),b''):h.update(data)
    return h.hexdigest()


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--generated',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--tokens',type=int,default=17)
    p.add_argument('--jobs',type=int,default=4)
    a=p.parse_args();generated=a.generated.resolve();out=a.out.resolve();project=Path(__file__).resolve().parents[1]
    if out.exists():raise ValueError('preserve prior evidence: output exists')
    if a.tokens<1 or a.jobs<1:raise ValueError('positive token/job counts required')
    rtl=generated/'Qwen2LayerStack.sv';header=generated/'block_layout.h'
    identity={'rtl_sha256':sha(rtl),'layout_sha256':sha(header)}
    text=header.read_text();shape={k:int(v) for k,v in re.findall(r'\b(H|F|MAX_TOKENS|STACK_LAYERS)\s*=\s*(\d+)',text)}
    if set(shape)!=set(('H','F','MAX_TOKENS','STACK_LAYERS')) or a.tokens>shape['MAX_TOKENS']:raise ValueError('invalid generated geometry')
    out.mkdir(parents=True);env=os.environ.copy();env['MAKEFLAGS']=env.get('MAKEFLAGS','')+' OPT_FAST=-O1 OPT_SLOW=-O1'
    source=out/'external_stack.cpp'
    run([sys.executable,str(project/'scripts/generate_external_stack_harness.py'),str(source)],project,out/'generate.log',env)
    cpp=source.read_text();needle='StackSim sim(n);'
    if cpp.count(needle)!=1:raise ValueError('unknown test main contract')
    branch=r'''StackSim sim(n);if(argc==4 && std::string(argv[2])=="--export-synthetic-input"){
      sim.load();std::ifstream old(argv[3],std::ios::binary);need(!old.good(),"refuse fixture overwrite");old.close();
      std::ofstream out(argv[3],std::ios::binary);out.write(reinterpret_cast<const char*>(sim.mem.data()),std::streamsize(sim.total));
      out.close();need(bool(out),"synthetic fixture write failed");return 0;}
'''
    # Test-only fixture mode, no edit to any Chisel or Verilog file.
    driver=out/'external_with_fixture.cpp';driver.write_text(cpp.replace(needle,branch,1))
    run(['verilator','--cc','--exe','--build','--assert','-Wno-fatal','--top-module','Qwen2LayerStack','-CFLAGS',f'-O2 -std=c++17 -ffp-contract=off -I{generated}','-j',str(a.jobs),'--Mdir',str(out/'obj'),str(rtl),str(driver)],project,out/'build.log',env)
    binary=out/'obj/VQwen2LayerStack';arena=out/'synthetic_input.bin';actual=out/'actual_hidden.f32'
    run([str(binary),str(a.tokens),'--export-synthetic-input',str(arena)],project,out/'fixture.log',env)
    before=sha(arena)
    run([str(binary),str(a.tokens),str(arena),str(actual)],project,out/'simulation.log',env)
    log=(out/'simulation.log').read_text();markers=re.findall(r'^CONTINUOUS_QWEN2_STACK_PASS (.*)$',log,re.M)
    if len(markers)!=1 or re.search(r'(^|\n)(FAIL|MISMATCH|%Error)',log):raise ValueError('numerical simulation did not pass')
    values=dict(re.findall(r'(\w+)=([^\s]+)',markers[0]));layers=shape['STACK_LAYERS']
    expected={'tokens':a.tokens,'hidden':shape['H'],'ffn':shape['F'],'layers':layers,'stages':layers*15,'bit_diffs':0,'host_intermediate_writes':0,'canonical_512_array':0}
    for key,value in expected.items():
        if values.get(key)!=str(value):raise ValueError('completion mismatch '+key)
    if values.get('synthetic_weights')!='false':raise ValueError('external path was not selected')
    if actual.stat().st_size!=a.tokens*shape['H']*4 or sha(arena)!=before:raise ValueError('output length or source mutation')
    if identity!={'rtl_sha256':sha(rtl),'layout_sha256':sha(header)}:raise ValueError('generated hardware changed')
    result={'status':'PASS_EXTERNAL_ARENA_PATH_WITH_SYNTHETIC_INPUTS','geometry':shape,'tokens':a.tokens,'counts':values,'synthetic_fixture':True,'official_weights':False,'source_arena_sha256':before,'actual_hidden_sha256':sha(actual),'hardware_identity':identity,'production_rtl_edited':False}
    (out/'RESULT.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':
    try:main()
    except Exception as error:
        print('FAIL '+str(error),file=sys.stderr);raise SystemExit(1)
