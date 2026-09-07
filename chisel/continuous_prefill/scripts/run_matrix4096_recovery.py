#!/usr/bin/env python3
"""Execute three real-DUT error/reset/recovery cases on frozen 4096-MAC tiny L2.

The single DUT is reset, not recreated, after each injected second-layer fault.
Rebuild only the C++ AXI service/test driver. Every recovered output must equal
the frozen successful run. This is NOT real-size or timing signoff.
"""
from __future__ import annotations
import argparse,hashlib,json,math,os,re,struct,subprocess
from pathlib import Path

CASES=[('descriptor-read-error',21),('read-error',33),('last-write-error',41)]

def require(ok,msg):
    if not ok:raise ValueError(msg)

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def run(repo,base,out):
    require(not out.exists(),'output must be new')
    require((base/'gate.exit').read_text().strip()=='0' and (base/'simulation.exit').read_text().strip()=='0','baseline unfinished')
    m=json.loads((base/'fixture/manifest.json').read_text());scope=json.loads((base/'generated/SCOPE.json').read_text())
    require((m['tokens'],m['layers'],m['shape']['H'],m['shape']['F'],scope['matrix_macs'])==(16,2,64,128,4096),'fixed scope')
    p=repo/'chisel/continuous_prefill';vr=Path(os.environ['VERILATOR_ROOT']).resolve()
    libs=[base/'obj/VHostBlockTop__ALL.a',base/'obj/Vqwen2_matrix_command_endpoint/libqwen2_matrix_command_endpoint.a',base/'obj/Vbf16_context_lane_cluster16_rev8b_b_candidate/libbf16_context_lane_cluster16_rev8b_b_candidate.a']
    runtime=[base/'obj'/n for n in ('verilated.o','verilated_dpi.o','verilated_threads.o')]
    inputs=libs+runtime+[base/'generated/HostBlockTop.sv',base/'generated/owner_shape.h',base/'fixture/owner_fixture.h',base/'fixture/host_commands.bin',base/'fixture/host_descriptors.bin',p/'tests/host_block_commands.cpp',p/'tests/matrix4096_recovery.cpp']
    before={str(x):digest(x) for x in inputs}
    identities=json.loads((base/'sources.sha256.json').read_text())
    frozen={name:value for name,value in identities.items() if name.endswith('.sv') or ('/src/main/' in name and name.endswith('.scala'))}
    require(len(frozen)>100 and all(digest(repo/n)==v for n,v in frozen.items()),'DUT source drift')
    require(digest(p/'tests/host_block_commands.cpp')==identities['chisel/continuous_prefill/tests/host_block_commands.cpp'],'base harness drift')
    out.mkdir(parents=True)
    (out/'INPUTS_SHA256.json').write_text(json.dumps(before,indent=2)+'\n')
    cmd=['g++','-O3','-std=c++17','-ffp-contract=off','-fno-fast-math']
    for inc in (base/'obj',vr/'include',vr/'include/vltstd',base/'generated',base/'fixture',p/'tests'):cmd+=['-I'+str(inc)]
    cmd+=[str(p/'tests/matrix4096_recovery.cpp')]+list(map(str,libs+runtime))+['-pthread','-latomic','-o',str(out/'VMatrix4096Recovery')]
    with (out/'build.log').open('xb') as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True)
    cases=[]
    for mode,pc in CASES:
        d=out/(mode+'_pc'+str(pc));d.mkdir()
        with (d/'run.log').open('xb') as f:
            proc=subprocess.run([str(out/'VMatrix4096Recovery'),str(base/'fixture'),str(d/'tensors'),mode,str(pc),'20260907'],stdout=f,stderr=subprocess.STDOUT,timeout=900)
        (d/'simulation.exit').write_text(str(proc.returncode)+'\n')
        require(proc.returncode==0,'simulator failure')
        log=(d/'run.log').read_text();require(not re.search('HOST_BLOCK_FAIL|MATRIX4096_RECOVERY_FAIL|%Error|Fatal',log),'failed log')
        prior=31 if pc in (31,32,33) else pc
        marker=f'MATRIX4096_RECOVERY_PASS mode={mode} pc={pc} prior={prior} matrix_macs=4096 tokens=16 layers=2 commands=42 owner_jobs=38 checked_fp32=39936 bit_differences=0 same_dut=1 reset_after_error=1 legacy_block_launch=0'
        require(log.splitlines().count(marker)==1,'bad recovery marker')
        require([int(x) for x in re.findall(r'^OWNER_COMPLETION pc=(\d+) ',log,re.M)]==list(range(prior))+list(range(42)),'completion order')
        require(len(re.findall(r'^FAULT_INJECT ',log,re.M))==1,'fault not injected exactly once')
        require(re.findall(r'^EXPECTED_ERROR pc=(\d+) status=(\d+)',log,re.M)==[(str(pc),'3')],'wrong error status')
        count=0;sha256={}
        for op in m['schedule']:
            for name in op['outputs']:
                q=d/'tensors/recovered';a=(q/(name+'_actual.f32le')).read_bytes();b=(q/(name+'_reference.f32le')).read_bytes()
                require(len(a)==m['tensors'][name]['words']*4 and a==b==(base/'tensors'/(name+'_actual.f32le')).read_bytes(),'recovered output mismatch')
                require(all(math.isfinite(v[0]) for v in struct.iter_unpack('<f',a)),'nonfinite output')
                count+=len(a)//4;sha256[name]=hashlib.sha256(a).hexdigest()
                if op['pc']>=prior:require(not (d/'tensors/failed'/(name+'_actual.f32le')).exists(),'unpublished output dumped')
        require(count==39936,'missing numerical coverage')
        cases.append({'mode':mode,'pc':pc,'prior_completions':prior,'recovered_checked_fp32':count,'bit_differences':0,'log_sha256':digest(d/'run.log'),'actual_sha256':sha256})
        print(mode,pc,'PASS',flush=True)
    require(before=={str(x):digest(Path(x)) for x in before},'inputs changed')
    report={'status':'PASS_MATRIX4096_TINY_TWO_LAYER_FAULT_RESET_RECOVERY','cases':cases,'same_dut_per_case':True,'hardware_sources_unchanged':True,'immutable_inputs':before,'scope':'Actual 4096-MAC original arithmetic and pinned iDMA; tiny H64/F128 T16 L2; not real-size/DC.'}
    (out/'RESULT.json').write_text(json.dumps(report,indent=2)+'\n');(out/'gate.exit').write_text('0\n');return report

if __name__=='__main__':
    a=argparse.ArgumentParser(description=__doc__);a.add_argument('--repo',type=Path,required=True);a.add_argument('--base',type=Path,required=True);a.add_argument('--output',type=Path,required=True);x=a.parse_args()
    try:print(json.dumps(run(x.repo.resolve(),x.base.resolve(),x.output.resolve()),indent=2))
    except (ValueError,KeyError,TypeError,OSError,subprocess.SubprocessError) as e:raise SystemExit('MATRIX4096_RECOVERY_REJECTED: '+str(e))
