#!/usr/bin/env python3
"""Reproduce C06.1/C08.1/Q21.1 software gates and keep actual logs/artifacts.

Uses a NEW output directory, never runs plan commands or changes the checklist.
Requires numpy, pytest, PyYAML. The --design-sha argument is attribution, not a
replacement for the captured source byte hashes or a verified Git checkout.
"""
from __future__ import annotations
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from heteronpu.weight_packing import PackContract,pack_file,verify_package
from heteronpu.block_receipt import verify
from block_contract_tools import control_case
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
TESTS=['tests/test_command_window_contract.py','tests/test_block_receipt.py','tests/test_weight_packing.py','tests/test_block_contract_cli.py','tests/test_control_transport_types.py']
REGRESSION=['tests/test_model_geometry.py','tests/test_qwen_family_contracts.py','tests/test_block_performance.py',
            'tests/test_block_checklist.py','tests/test_typical_block_plan.py']
SOURCES=['src/heteronpu/command_window_contract.py','src/heteronpu/block_receipt.py','src/heteronpu/weight_packing.py',
         'scripts/block_contract_tools.py','scripts/run_independent_block_tasks.py',*TESTS,
         'chisel/continuous_prefill/scripts/pack_owner_bf16_weights.py']


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path,doc):
    with path.open('x',encoding='utf-8') as f: json.dump(doc,f,indent=2,ensure_ascii=False);f.write('\n')


def run(out: Path, design_sha: str) -> dict:
    if out.exists() or out.is_symlink(): raise ValueError('output must be NEW')
    if re.fullmatch('[0-9a-f]{40}',design_sha) is None: raise ValueError('fixed design SHA required')
    out.mkdir(parents=True)
    identity={name:sha(ROOT/name) for name in SOURCES}
    runs=[]
    for tag,options in [('normal',[]),('optimized',['-O'])]:
        cmd=[sys.executable,*options,'-m','pytest','-q',*TESTS,*REGRESSION]
        began=datetime.now(timezone.utc).isoformat()
        with (out/(tag+'.log')).open('x') as f:
            result=subprocess.run(cmd,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
        record=dict(command=cmd,exit=result.returncode,started=began,finished=datetime.now(timezone.utc).isoformat(),log=tag+'.log')
        runs.append(record)
        save(out/(tag+'.execution.json'),record)
        if result.returncode: raise ValueError('test failed, raw log preserved: '+tag)
    controls=[control_case(n,seed) for n in (63,64,65,255,256,588) for seed in range(20)]
    save(out/'C06_cases.json',controls)
    control=dict(task='C06.1',status='PASS_CONTROL_ORACLE',cases=len(controls),
                 commands_tested=[63,64,65,255,256,588],seeds_per_count=20,
                 total_commands=sum(x['completed'] for x in controls),peak_live=2,
                 cases_sha256=sha(out/'C06_cases.json'),design_sha=design_sha,
                 rtl_execution=False,production_frontend_modified=False)
    save(out/'C06_1.json',control)
    packs=[]
    for n,k,kind in [(1536,32,'f32le'),(33,17,'f32le'),(256,640,'bf16le')]:
        name=f'n{n}_k{k}_{kind}';path=out/(name+'.raw')
        values=(np.arange(n*k,dtype=np.float32).reshape(n,k)%127-63)/32
        if kind=='bf16le':
            raw=(values.astype('<f4').view('<u4')>>16).astype('<u2').tobytes()
        else: raw=values.astype('<f4').tobytes()
        path.write_bytes(raw)
        contract=PackContract(n,k,True,input_dtype=kind,chunk_rows=7,tile_columns=31)
        save(out/(name+'.contract.json'),asdict(contract))
        pack_file(path,out/name,contract)
        packs.append(verify_package(path,out/name,contract))
    save(out/'Q21_1.json',dict(task='Q21.1',status='PASS_SYNTHETIC_WEIGHT_PACK',design_sha=design_sha,
         results=packs,official_weights_verified=False,descriptor_modified=False,rtl_execution=False))
    # Frozen synthetic expected exports: same fixture, independent actual copies.
    fixture=out/'export_fixture';fixture.mkdir()
    tensors=[];exports=[]
    for pc,(name,role,dtype,raw) in enumerate([
        ('hidden','tensor','f32le',values[:2,:16].astype('<f4').tobytes()),
        ('state','state','u32le',np.arange(32,dtype='<u4').tobytes())]):
        for prefix in ('reference','actual'): (fixture/(prefix+'_'+name)).write_bytes(raw)
        h=hashlib.sha256(raw).hexdigest();gen=2 if role=='state' else None
        tensors.append(dict(id=name,role=role,dtype=dtype,shape=[2,16],reference='reference_'+name,
                            reference_sha256=h,comparison='bit_exact',generation=gen,producer_pc=pc))
        exports.append(dict(id=name,file='actual_'+name,sha256=h,dtype=dtype,shape=[2,16],generation=gen,producer_pc=pc))
    run_id=dict(design_sha=design_sha,reference_sha=design_sha,model_revision='0'*40,
                input_sha256=sha(out/'n33_k17_f32le.raw'),run_id='synthetic_schema_fixture_not_model')
    spec=dict(version=1,identity=run_id,tensors=tensors,commands=[dict(pc=i,write_ack_bytes=128) for i in range(2)])
    save(fixture/'manifest.json',spec)
    save(fixture/'receipt.json',dict(version=1,identity=run_id,manifest_sha256=sha(fixture/'manifest.json'),exports=exports,
        completions=[dict(pc=i,status=0,write_ack_bytes=128) for i in range(2)],
        attestation=dict(cpu_fallback=0,host_intermediate_writes=0,unresolved_owners=0)))
    receipt=verify(fixture/'manifest.json',fixture/'receipt.json',fixture)
    save(out/'C08_1.json',dict(task='C08.1',design_sha=design_sha,**receipt))
    if identity!={name:sha(ROOT/name) for name in SOURCES}: raise ValueError('source modified during gate')
    report=dict(status='PASS_THREE_INDEPENDENT_SOFTWARE_SUBTASKS',design_sha=design_sha,python=platform.python_version(),
        numpy=np.__version__,tests=runs,source_sha256=identity,rtl_execution=False,official_weights_verified=False,
        parent_tasks_complete=False,scope='C06 control oracle; C08 exact export framework; Q21 synthetic byte pack. No C02 approximate formula, production frontend or official-block execution.')
    save(out/'RESULT.json',report)
    (out/'gate.exit').write_text('0\n')
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);p.add_argument('--design-sha',required=True)
    a=p.parse_args()
    try:
        print(json.dumps(run(a.output.resolve(),a.design_sha),ensure_ascii=False,indent=2));return 0
    except (ValueError,KeyError,TypeError,OSError) as exc:
        print('INDEPENDENT_TASKS_FAILED: '+str(exc),file=sys.stderr);return 2


if __name__=='__main__': raise SystemExit(main())
