#!/usr/bin/env python3
"""Execute lifecycle/fault tests against unchanged, already-generated HostBlockTop.

Rebuild only the C++ AXI test harness. Immutable Chisel-emitted RTL and both DUT
libraries are hashed before/after. The second request uses the SAME DUT object;
reset is applied only in fault recovery, never between successful cold requests.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import struct
import subprocess


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for b in iter(lambda:stream.read(1<<20),b''):h.update(b)
    return h.hexdigest()


def fields(line):
    pairs=re.findall(r'(\w+)=([^\s]+)',line)
    require(len(pairs)==len(dict(pairs)),'duplicate receipt field')
    return dict(pairs)


def verify(out, fixture, mode, pc):
    require((out/'simulation.exit').read_text().strip()=='0','nonzero simulator exit')
    text=(out/'run.log').read_text()
    require(not re.search(r'HOST_(?:BLOCK|OWNER_LIFECYCLE)_FAIL|%Error|\bFatal\b',text),'fatal log')
    finals=[fields(x) for x in text.splitlines() if x.startswith('HOST_OWNER_LIFECYCLE_PASS ')]
    require(len(finals)==1,'missing/duplicate lifecycle receipt');f=finals[0]
    shape=fixture['shape'];tokens=fixture['tokens'];repeat=mode=='repeat'
    expected={'mode':mode,'tokens':str(tokens),'hidden':str(shape['H']),'ffn':str(shape['F']),
        'requests':'2','second_commands':'21','second_owner_jobs':'19','bit_differences':'0',
        'reset_between_requests':str(int(not repeat)),'changed_input':str(int(repeat)),
        'changed_weights':str(int(repeat)),'recovered':'1','legacy_block_launch':'0'}
    require(all(f.get(k)==v for k,v in expected.items()),'receipt scope/count mismatch')
    prior=21 if repeat else (10 if 10<=pc<=12 else pc)
    completed=[int(x) for x in re.findall(r'^OWNER_COMPLETION pc=(\d+) ',text,re.M)]
    require(completed==list(range(prior))+list(range(21)),'missing/out-of-order completion')
    errors=re.findall(r'^EXPECTED_ERROR pc=(\d+) status=(\d+)',text,re.M)
    require((not errors) if repeat else (len(errors)==1 and int(errors[0][0])==pc and int(errors[0][1])!=0),'fault status mismatch')
    if not repeat:
        injections=[fields(x) for x in text.splitlines() if x.startswith('FAULT_INJECT ')]
        require(len(injections)==1 and injections[0].get('pc')==str(pc) and injections[0].get('mode')==mode,'fault not injected')
    total=0;hashes={};counts=[]
    for request,count in [('first',prior),('second',21)]:
        checked=0
        for op in fixture['schedule']:
            for name in op['outputs']:
                p=out/'tensors'/request/(name+'_actual.f32le');q=p.with_name(name+'_reference.f32le')
                if op['pc']>=count:
                    require(not p.exists() and not q.exists(),'unpublished consumer output file');continue
                a,b=p.read_bytes(),q.read_bytes();words=fixture['tensors'][name]['words']
                require(len(a)==len(b)==words*4 and a==b,'binary output mismatch '+name)
                require(all(math.isfinite(v[0]) for v in struct.iter_unpack('<f',a)),'nonfinite output')
                checked+=words;hashes[str(p.relative_to(out))]=digest(p)
        counts.append(checked);total+=checked
    require(f['first_checked_fp32']==str(counts[0]) and f['second_checked_fp32']==str(counts[1]),'binary/receipt count mismatch')
    if repeat:
        for name in ['input_x.f32le','y_actual.f32le']:
            require((out/'tensors/first'/name).read_bytes()!=(out/'tensors/second'/name).read_bytes(),'unchanged repeated stimulus/output')
    return {'status':'PASS_ACTUAL_HOST_OWNER_LIFECYCLE','mode':mode,'fault_pc':None if repeat else pc,
        'tokens':tokens,'shape':shape,'checked_fp32':total,'bit_differences':0,
        'same_dut':True,'reset_between_requests':not repeat,'completed_pcs':completed,
        'actual_sha256':hashes,'scope':'Synthetic weights, one block per request; not a layer chain or q1024 model.'}


def run(repo,build,out,cases,seed):
    require(not out.exists(),'new output directory required')
    require((build/'gate.exit').read_text().strip()=='0','baseline gate not successful')
    require((build/'simulation.exit').read_text().strip()=='0','baseline simulator not successful')
    p=repo/'chisel/continuous_prefill';vr=Path(os.environ['VERILATOR_ROOT']).resolve()
    require((vr/'include/verilated.h').is_file(),'Verilator runtime missing')
    manifest=json.loads((build/'fixture/manifest.json').read_text())
    require(manifest.get('layers',1)==1 and manifest['commands']==21,'lifecycle gate is one block per cold request')
    libs=[build/'obj/VHostBlockTop__ALL.a',build/'obj/Vbf16_context_lane_cluster16_rev8b_b_candidate/libbf16_context_lane_cluster16_rev8b_b_candidate.a']
    runtime=[build/'obj'/n for n in ['verilated.o','verilated_dpi.o','verilated_threads.o']]
    inputs=libs+runtime+[build/'generated/HostBlockTop.sv',build/'generated/owner_shape.h',
        build/'fixture/owner_fixture.h',build/'fixture/host_commands.bin',build/'fixture/host_descriptors.bin',
        p/'tests/host_block_commands.cpp',p/'tests/host_owner_lifecycle.cpp']
    original=json.loads((build/'sources.sha256.json').read_text());frozen={}
    for path,checksum in original.items():
        if path.endswith('.sv') or ('/src/main/' in path and path.endswith('.scala')):
            require(digest(repo/path)==checksum,'DUT source differs from frozen build: '+path);frozen[path]=checksum
    require(len(frozen)>20,'incomplete baseline DUT identity')
    before={str(x):digest(x) for x in inputs};out.mkdir(parents=True)
    (out/'FROZEN_DUT_SOURCES.json').write_text(json.dumps(frozen,indent=2)+'\n')
    (out/'INPUTS_SHA256.json').write_text(json.dumps(before,indent=2)+'\n')
    cmd=['g++','-O3','-std=c++17','-ffp-contract=off','-fno-fast-math']
    for inc in [build/'obj',vr/'include',vr/'include/vltstd',build/'generated',build/'fixture',p/'tests']:cmd+=['-I'+str(inc)]
    cmd+=[str(p/'tests/host_owner_lifecycle.cpp')]+list(map(str,libs+runtime))+['-pthread','-latomic','-o',str(out/'VHostOwnerLifecycle')]
    with (out/'build.log').open('xb') as log:subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
    results=[]
    for i,(mode,pc) in enumerate(cases):
        d=out/f'{i:03}_{mode}_pc{pc}';d.mkdir()
        with (d/'run.log').open('xb') as log:
            result=subprocess.run([str(out/'VHostOwnerLifecycle'),str(build/'fixture'),str(d/'tensors'),mode,str(pc),str(seed+i)],stdout=log,stderr=subprocess.STDOUT)
        (d/'simulation.exit').write_text(str(result.returncode)+'\n')
        result=verify(d,manifest,mode,pc);(d/'RESULT.json').write_text(json.dumps(result,indent=2)+'\n');results.append(result)
        print(json.dumps({k:result[k] for k in ['status','mode','fault_pc','checked_fp32']}),flush=True)
    require(before=={str(x):digest(x) for x in inputs},'input/DUT changed during execution')
    require(all(digest(repo/path)==checksum for path,checksum in frozen.items()),'hardware source changed during lifecycle')
    result={'status':'PASS_HOST_OWNER_LIFECYCLE_SUITE','cases':results,'seed':seed,'immutable_inputs':before,'frozen_dut_sources':frozen}
    (out/'RESULT.json').write_text(json.dumps(result,indent=2)+'\n');(out/'gate.exit').write_text('0\n');return result


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--repo',type=Path,required=True);ap.add_argument('--build',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--case',action='append',help='repeat:0 or fault-mode:PC');ap.add_argument('--seed',type=int,default=20260907);a=ap.parse_args()
    try:
        require(0<a.seed<2**32-1000,'bad seed')
        allowed={'repeat','command-read-error','descriptor-read-error','read-error','write-error','last-write-error'}
        raw=a.case or ['repeat:0','command-read-error:0','descriptor-read-error:15','read-error:12','write-error:9','last-write-error:20']
        require(all(re.fullmatch(r'[a-z-]+:[0-9]+',x) for x in raw),'invalid mode:PC syntax')
        cases=[(x.split(':')[0],int(x.split(':')[1])) for x in raw]
        require(len(cases)<=1000 and len(cases)==len(set(cases)),'too many or duplicate cases')
        require(all(m in allowed and 0<=p<21 for m,p in cases),'bad fault case')
        require(all(p==0 if m=='repeat' else (p not in (10,11) if m in ('read-error','write-error','last-write-error') else True) for m,p in cases),'logical fused tensor has no independent payload transaction')
        run(a.repo.resolve(),a.build.resolve(),a.output.resolve(),cases,a.seed)
    except (ValueError,OSError,KeyError,TypeError,subprocess.CalledProcessError) as e:
        if a.output.exists():(a.output/'gate.exit').write_text('1\n')
        raise SystemExit('LIFECYCLE_GATE_REJECTED: '+str(e))
