#!/usr/bin/env python3
"""Actual Matrix4096/pinned-iDMA cold-repeat and fault recovery gate.

Reuse a frozen successful tiny16 L2 build; recompile the C++ AXI driver only.
No numerical callbacks, DUT register pokes, raw RTL modifications, or cleanup.
--verify-only reads existing outputs and never claims to rerun hardware.
"""
from __future__ import annotations
import argparse, hashlib, json, math, os, re, struct, subprocess
from pathlib import Path

CASES=[('descriptor-read-error',21),('read-error',22),('weight-mid-error',22),
       ('weight-last-error',37),('last-write-error',40),('last-write-error',41),('repeat',21)]

def require(ok, message):
    if not ok: raise ValueError(message)

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def manifest(base):
    require((base/'gate.exit').read_text().strip()=='0' and (base/'simulation.exit').read_text().strip()=='0','baseline did not pass')
    m=json.loads((base/'fixture/manifest.json').read_text())
    s=json.loads((base/'generated/SCOPE.json').read_text())
    require((m['tokens'],m['layers'],m['shape']['H'],m['shape']['F'],s['matrix_macs'],s['weight_read_burst_beats'])==(16,2,64,128,4096,16),'wrong fixed baseline')
    return m

def verify(base, out, complete_gate=True):
    if complete_gate: require((out/'gate.exit').read_text().strip()=='0','lifecycle gate did not finish')
    m=manifest(base);reports=[]
    for mode,pc in CASES:
        d=out/(mode+'_pc'+str(pc))
        require((d/'simulation.exit').read_text().strip()=='0','simulation failed')
        rawlog=(d/'run.log').read_bytes();log=rawlog.decode()
        require(not re.search('FAIL|%Error|Fatal',log),'failure in simulation log')
        prior=(pc//21)*21+10 if 10<=pc%21<=12 else pc
        expected=list(range(42))*2 if mode=='repeat' else list(range(prior))+list(range(42))
        require([int(x) for x in re.findall(r'^OWNER_COMPLETION pc=(\d+) ',log,re.M)]==expected,'completion order/coverage')
        marker=('WEIGHT_BURST_REPEAT_PASS requests=2 commands=84 checked_fp32=79872 bit_differences=0 same_dut=1 reset_between_requests=0 changed_weights=1 changed_input=1 mailbox_bytes=1024' if mode=='repeat' else
                f'WEIGHT_BURST_RECOVERY_PASS mode={mode} pc={pc} prior={prior} commands=42 checked_fp32=39936 bit_differences=0 same_dut=1 reset_after_error=1')
        require(log.splitlines().count(marker)==1,'missing lifecycle receipt')
        faults=re.findall(r'^FAULT_INJECT ',log,re.M)
        if mode=='repeat':require(not faults and 'EXPECTED_ERROR' not in log,'unexpected repeat error')
        else:
            require(len(faults)==1,'fault not injected once')
            require(re.findall(r'^EXPECTED_ERROR pc=(\d+) status=(\d+)',log,re.M)==[(str(pc),'3')],'wrong error status')
        count=0;hashes={}
        for request in (('first','second') if mode=='repeat' else ('recovered',)):
            q=d/'tensors'/request
            for op in m['schedule']:
                for name in op['outputs']:
                    a=q/(name+'_actual.f32le');b=q/(name+'_reference.f32le')
                    require(not a.is_symlink() and not b.is_symlink(),'symlink tensor')
                    raw=a.read_bytes()
                    require(len(raw)==m['tensors'][name]['words']*4 and raw==b.read_bytes(),'numerical mismatch '+name)
                    require(all(math.isfinite(x[0]) for x in struct.iter_unpack('<f',raw)),'nonfinite tensor')
                    if request in ('first','recovered'):
                        require(raw==(base/'tensors'/(name+'_actual.f32le')).read_bytes(),'frozen DUT output changed')
                    count+=len(raw)//4;hashes[request+'/'+name]=hashlib.sha256(raw).hexdigest()
        require(count==(79872 if mode=='repeat' else 39936),'incomplete output coverage')
        if mode=='repeat':
            for name in ('input_x.f32le','l1_y_actual.f32le'):
                require((d/'tensors/first'/name).read_bytes()!=(d/'tensors/second'/name).read_bytes(),'unchanged repeat '+name)
            ids=re.findall(r'^LAYER_WEIGHT_ID layer=(\d+) salt=(\d+) wq=(\d+) wg=(\d+) wd=(\d+)',log,re.M)
            require([(int(x[0]),int(x[1])) for x in ids]==[(0,0),(1,17),(0,11),(1,28)],'weight request identity')
            require(all(ids[i][j]!=ids[i+2][j] for i in range(2) for j in range(2,5)),'reused old weights')
        reports.append({'mode':mode,'pc':pc,'checked_fp32':count,'bit_differences':0,'actual_sha256':hashes,'log_sha256':hashlib.sha256(rawlog).hexdigest()})
    return {'status':'PASS_REAL_IDMA_BURST_TINY2_LIFECYCLE','cases':reports,'total_checked_fp32':sum(x['checked_fp32'] for x in reports),
            'scope':'Actual emitted Matrix4096 and original iDMA; T16 H64 F128 L2, not real-size performance, persistent KV or DC.'}

def run(repo,base,out):
    manifest(base);require(not out.exists() and not out.is_symlink(),'output must be new')
    p=repo/'chisel/continuous_prefill';vr=Path(os.environ.get('VERILATOR_ROOT',str(base/'verilator-runtime')))
    libs=[base/'obj/VHostBlockTop__ALL.a',base/'obj/Vqwen2_matrix_command_endpoint/libqwen2_matrix_command_endpoint.a',base/'obj/Vbf16_context_lane_cluster16_rev8b_b_candidate/libbf16_context_lane_cluster16_rev8b_b_candidate.a']
    runtime=[base/'obj'/x for x in ('verilated.o','verilated_dpi.o','verilated_threads.o')]
    identities=json.loads((base/'sources.sha256.json').read_text())
    hardware={n:h for n,h in identities.items() if n.endswith('.sv') or '/src/main/' in n}
    require(len(hardware)>100 and all(digest(repo/n)==h for n,h in hardware.items()),'DUT source drift')
    require(digest(p/'tests/host_block_commands.cpp')==identities['chisel/continuous_prefill/tests/host_block_commands.cpp'],'base harness drift')
    inputs=libs+runtime+[base/'generated/HostBlockTop.sv',base/'generated/owner_shape.h',base/'fixture/owner_fixture.h',p/'tests/weight_burst_lifecycle.cpp',p/'tests/host_block_commands.cpp',Path(__file__).resolve(),base/'fixture/manifest.json',base/'fixture/host_commands.bin',base/'fixture/host_descriptors.bin']
    before={str(x):digest(x) for x in inputs};out.mkdir(parents=True)
    (out/'INPUTS_SHA256.json').write_text(json.dumps(before,indent=2)+'\n')
    try:
        cmd=['g++','-O3','-std=c++17','-ffp-contract=off','-fno-fast-math']
        for inc in (base/'obj',vr/'include',vr/'include/vltstd',base/'generated',base/'fixture',p/'tests'):cmd+=['-I'+str(inc)]
        cmd+=[str(p/'tests/weight_burst_lifecycle.cpp')]+list(map(str,libs+runtime))+['-pthread','-latomic','-o',str(out/'VWeightBurstLifecycle')]
        with (out/'build.log').open('xb') as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True)
        for mode,pc in CASES:
            d=out/(mode+'_pc'+str(pc));d.mkdir()
            with (d/'run.log').open('xb') as f:
                r=subprocess.run([str(out/'VWeightBurstLifecycle'),str(base/'fixture'),str(d/'tensors'),mode,str(pc)],stdout=f,stderr=subprocess.STDOUT,timeout=900)
            (d/'simulation.exit').write_text(str(r.returncode)+'\n');require(r.returncode==0,'failed lifecycle simulator')
        result=verify(base,out,False);require(before=={n:digest(Path(n)) for n in before},'changed test inputs')
        result['inputs_sha256']=before;result['hardware_sources_verified']=len(hardware)
        (out/'RESULT.json').write_text(json.dumps(result,indent=2)+'\n');(out/'gate.exit').write_text('0\n');return result
    except Exception:
        (out/'gate.exit').write_text('1\n');raise

if __name__=='__main__':
    a=argparse.ArgumentParser(description=__doc__);a.add_argument('--repo',type=Path,required=True);a.add_argument('--base',type=Path,required=True);a.add_argument('--output',type=Path,required=True);a.add_argument('--verify-only',action='store_true');x=a.parse_args()
    try:
        report=verify(x.base.resolve(),x.output.resolve()) if x.verify_only else run(x.repo.resolve(),x.base.resolve(),x.output.resolve())
        print(json.dumps(report,indent=2))
    except (ValueError,OSError,KeyError,TypeError,subprocess.SubprocessError) as e:raise SystemExit('WEIGHT_BURST_LIFECYCLE_REJECTED: '+str(e))
