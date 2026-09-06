#!/usr/bin/env python3
"""Build and execute the Chisel stack using a supplied Qwen2 checkpoint.

The driver compares against the hardware's explicit numerical recipe. A pass
here is not an official framework-forward equivalence or a 512-MAC/iDMA claim.
No host reference intermediate is loaded into simulated memory.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path


def digest(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(4<<20),b''):
            h.update(b)
    return h.hexdigest()


def run(argv: list[str], cwd: Path, log: Path, env: dict[str,str]) -> None:
    with log.open('x') as f:
        f.write('ARGV '+json.dumps(argv)+'\n');f.flush()
        result=subprocess.run(argv,cwd=cwd,env=env,stdout=f,stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f'{argv[0]} failed with {result.returncode}; see {log}')


def verify_marker(text: str, tokens: int, layers: int) -> dict[str,str]:
    lines=re.findall(r'^CONTINUOUS_QWEN2_STACK_PASS (.*)$',text,re.M)
    if len(lines)!=1 or re.search(r'(^|\n)(FAIL|MISMATCH|%Error)',text):
        raise ValueError('simulation lacks one unambiguous success marker')
    fields=dict(re.findall(r'(\w+)=([^\s]+)',lines[0]))
    required={'tokens':tokens,'layers':layers,'hidden':1536,'ffn':8960,'stages':15*layers,
              'checked_fp32':41472*tokens*layers,'bit_diffs':0,'host_intermediate_writes':0,'canonical_512_array':0}
    for key,value in required.items():
        if fields.get(key)!=str(value):raise ValueError('invalid completion counter '+key)
    if fields.get('synthetic_weights')!='false':raise ValueError('synthetic inputs cannot validate a checkpoint run')
    if int(fields.get('cycles','0'))<=0 or (layers>1 and int(fields.get('previous_layer_read_bytes','0'))<=0):
        raise ValueError('missing numerical execution or previous-layer consumption')
    return fields


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--checkpoint',type=Path,required=True)
    p.add_argument('--token-ids',type=Path,required=True)
    p.add_argument('--revision',required=True)
    p.add_argument('--layers',type=int,default=2)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--jobs',type=int,default=4)
    a=p.parse_args()
    if not 1<=a.layers<=28 or not 1<=a.jobs<=64:raise ValueError('invalid layer/job count')
    if re.fullmatch(r'[0-9a-f]{40}',a.revision) is None:raise ValueError('full checkpoint revision required')
    tokens=json.loads(a.token_ids.read_text())
    if not isinstance(tokens,list) or not 1<=len(tokens)<=1024:raise ValueError('token IDs must contain 1..1024 elements')
    if any(type(t) is not int or not 0<=t<151936 for t in tokens):raise ValueError('invalid Qwen2 token ID')
    project=Path(__file__).resolve().parents[1];repo=project.parents[1]
    out=a.out.resolve()
    if out.exists():raise ValueError('output already exists; preserve earlier evidence')
    missing=[tool for tool in ('git','java','sbt','verilator','g++') if shutil.which(tool) is None]
    if missing:
        print('BLOCKED_MISSING_TOOLS '+','.join(missing),file=sys.stderr);return 77
    out.mkdir(parents=True)
    env=os.environ.copy()
    env.setdefault('JVM_OPTS','-Xmx5G -Xss4M -XX:ActiveProcessorCount=4')
    env['MAKEFLAGS']=env.get('MAKEFLAGS','')+' OPT_FAST=-O1 OPT_SLOW=-O1'
    env.setdefault('HARDFLOAT_SOURCE',str(repo/'work/upstream/hardfloat_continuous'))
    source_paths=subprocess.check_output(['git','ls-files','-z','chisel/continuous_prefill','chisel/p0_safety/src/main/scala','integration/gemmini'],cwd=repo).decode().split('\0')
    sources={name:digest(repo/name) for name in source_paths if name}
    source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
    worktree=subprocess.check_output(['git','status','--porcelain'],cwd=repo,text=True)
    identity={'source_commit':source_commit,'worktree_status':worktree,'sources_sha256':sources,'requested_checkpoint_revision':a.revision,'layers':a.layers,'tokens':len(tokens),'started_unix':time.time()}
    (out/'IDENTITY.json').write_text(json.dumps(identity,indent=2)+'\n')
    receipt={'status':'FAILED_OR_INCOMPLETE','source_commit':source_commit,'official_framework_parity':False,'pinned_idma':False,'canonical_512_array':False,'dc':False}
    try:
        run(['bash',str(project/'scripts/prepare_hardfloat.sh')],repo,out/'prepare.log',env)
        run(['sbt','-batch','compile','Test/compile',f'runMain heteronpu.continuous.EmitQwenStack {out}/generated --layers={a.layers}'],project,out/'compile_emit.log',env)
        run([sys.executable,str(project/'scripts/pack_qwen2_stack.py'),'--checkpoint',str(a.checkpoint.resolve()),'--layout',str(out/'generated/block_layout.h'),'--token-ids',str(a.token_ids.resolve()),'--revision',a.revision,'--out',str(out/'packed')],repo,out/'pack.log',env)
        run([sys.executable,str(project/'scripts/generate_external_stack_harness.py'),str(out/'external_stack.cpp')],repo,out/'harness.log',env)
        run(['verilator','--cc','--exe','--build','--assert','-Wno-fatal','--top-module','Qwen2LayerStack','-CFLAGS',f'-O2 -std=c++17 -ffp-contract=off -I{out}/generated','-j',str(a.jobs),'--Mdir',str(out/'obj'),str(out/'generated/Qwen2LayerStack.sv'),str(out/'external_stack.cpp')],project,out/'verilator_build.log',env)
        packed_manifest=json.loads((out/'packed/manifest.json').read_text())
        if packed_manifest['arena']['sha256']!=digest(out/'packed/arena.bin'):raise ValueError('packed arena changed before launch')
        run([str(out/'obj/VQwen2LayerStack'),str(len(tokens)),str(out/'packed/arena.bin'),str(out/'actual_hidden.f32')],project,out/'simulation.log',env)
        counts=verify_marker((out/'simulation.log').read_text(),len(tokens),a.layers)
        if (out/'actual_hidden.f32').stat().st_size!=len(tokens)*1536*4:raise ValueError('short actual hidden output')
        if packed_manifest['arena']['sha256']!=digest(out/'packed/arena.bin'):raise ValueError('input arena mutated during execution')
        for name,h in sources.items():
            if digest(repo/name)!=h:raise ValueError('source changed during execution: '+name)
        receipt.update(status='PASS_PACKED_CHECKPOINT_HARDWARE_RECIPE',counts=counts,checkpoint_manifest_sha256=digest(out/'packed/manifest.json'),actual_hidden_sha256=digest(out/'actual_hidden.f32'),official_repository_revision_verified=False,host_intermediate_injection=False)
        return_code=0
    except Exception as exc:
        receipt.update(error_type=type(exc).__name__,error=str(exc));return_code=1
    receipt['completed_unix']=time.time()
    receipt['artifacts_sha256']={str(f.relative_to(out)):digest(f) for f in out.iterdir() if f.is_file() and f.name!='RESULT.json'}
    (out/'RESULT.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))
    return return_code


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except (ValueError,OSError,json.JSONDecodeError) as error:
        print('ERROR '+str(error),file=sys.stderr);raise SystemExit(2)
