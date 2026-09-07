#!/usr/bin/env python3
"""Inject middle/last read-beat faults in all seven second-layer Dense owners.

Reuse the frozen lifecycle executable. Each case runs the real Matrix4096 and
pinned iDMA, fails without a success event, resets that same DUT and completes
both layers. This is a tiny16 hardware regression, not real-size performance.
"""
from __future__ import annotations
import argparse, concurrent.futures, hashlib, json, math, re, struct, subprocess
from pathlib import Path

DENSE_PCS = (22,25,28,34,37,38,40)
CASES = tuple((mode,pc) for pc in DENSE_PCS for mode in ('weight-mid-error','weight-last-error'))


def require(ok, message):
    if not ok: raise ValueError(message)


def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()


def audit(base: Path, out: Path) -> dict:
    m=json.loads((base/'fixture/manifest.json').read_text())
    require((m['tokens'],m['layers'],m['shape']['H'],m['shape']['F'])==(16,2,64,128),'wrong scope')
    reports=[]
    for mode,pc in CASES:
        root=out/(mode+'_pc'+str(pc));log=(root/'run.log').read_text()
        require((root/'simulation.exit').read_text().strip()=='0' and not re.search('FAIL|%Error|Fatal',log),'simulator failed')
        require([int(x) for x in re.findall(r'^OWNER_COMPLETION pc=(\d+) ',log,re.M)]==list(range(pc))+list(range(42)), 'wrong completion prefix/recovery')
        require(re.findall(r'^EXPECTED_ERROR pc=(\d+) status=(\d+)',log,re.M)==[(str(pc),'3')], 'wrong failure owner')
        require(len(re.findall(r'^FAULT_INJECT ',log,re.M))==1, 'fault not injected exactly once')
        marker=f'WEIGHT_BURST_RECOVERY_PASS mode={mode} pc={pc} prior={pc} commands=42 checked_fp32=39936 bit_differences=0 same_dut=1 reset_after_error=1'
        require(log.splitlines().count(marker)==1, 'missing full recovery')
        final=[x for x in log.splitlines() if x.startswith('HOST_BLOCK_ALL_OWNERS_PASS ')]
        require(len(final)==1,'duplicate or missing successful request')
        c=dict(re.findall(r'(\w+)=(\w+)',final[0]))
        for name,n in {'host_commands':42,'completed':42,'owner_jobs':38,'checked_fp32':39936,'bit_differences':0,'matrix_macs':4096,'weight_read_burst_beats':16,'original_idma_instances':1,'legacy_block_launch':0,'host_intermediate_writes':0}.items():
            require(int(c[name])==n,'wrong recovered counter: '+name)
        checked=0;hashes={}
        for op in m['schedule']:
            for name in op['outputs']:
                a=root/'tensors/recovered'/(name+'_actual.f32le')
                b=root/'tensors/recovered'/(name+'_reference.f32le')
                require(not a.is_symlink() and not b.is_symlink(),'symlink output')
                raw=a.read_bytes()
                require(len(raw)==m['tensors'][name]['words']*4 and raw==b.read_bytes()==(base/'tensors'/(name+'_actual.f32le')).read_bytes(),'actual output mismatch: '+name)
                require(all(math.isfinite(x[0]) for x in struct.iter_unpack('<f',raw)),'nonfinite output')
                if op['pc']>=pc:
                    require(not (root/'tensors/first'/(name+'_actual.f32le')).exists(),'failed producer or consumer published output')
                checked+=len(raw)//4;hashes[name]=hashlib.sha256(raw).hexdigest()
        require(checked==39936,'missing output coverage')
        reports.append(dict(mode=mode,pc=pc,checked_fp32=checked,bit_differences=0,
                            log_sha256=digest(root/'run.log'),actual_sha256=hashes))
    return dict(schema=1,status='PASS_ALL_SECOND_LAYER_DENSE_BURST_FAILURES',cases=reports,
                checked_fp32=14*39936,bit_differences=0,
                scope='T16 H64 F128 two distinct layers, same DUT reset recovery per case; not official weights or real-size performance.')


def run(repo: Path, base: Path, lifecycle: Path, out: Path, jobs: int) -> dict:
    require(1<=jobs<=4,'bounded parallelism')
    require(not out.exists() and not out.is_symlink(),'preserve prior output')
    require((base/'gate.exit').read_text().strip()=='0','base unfinished')
    # Reuse only a previously verified lifecycle build with unchanged inputs.
    require((lifecycle/'gate.exit').read_text().strip()=='0','lifecycle baseline unfinished')
    recorded=json.loads((lifecycle/'INPUTS_SHA256.json').read_text())
    require(all(digest(Path(p))==h for p,h in recorded.items()),'lifecycle build inputs changed')
    source=json.loads((base/'sources.sha256.json').read_text())
    hardware={n:h for n,h in source.items() if n.endswith('.sv') or '/src/main/' in n}
    require(len(hardware)>100 and all(digest(repo/p)==h for p,h in hardware.items()),'hardware source changed')
    binary=lifecycle/'VWeightBurstLifecycle'
    binary_hash=digest(binary);out.mkdir(parents=True)
    (out/'INPUTS_SHA256.json').write_text(json.dumps(dict(executable={str(binary):binary_hash},lifecycle_inputs=recorded),indent=2)+'\n')
    def one(case):
        mode,pc=case;root=out/(mode+'_pc'+str(pc));root.mkdir()
        with (root/'run.log').open('xb') as log:
            p=subprocess.run([str(binary),str(base/'fixture'),str(root/'tensors'),mode,str(pc)],stdout=log,stderr=subprocess.STDOUT,timeout=1200)
        (root/'simulation.exit').write_text(str(p.returncode)+'\n')
        require(p.returncode==0,'fault case failed: '+mode+' '+str(pc))
        print(mode,pc,'SIMULATION_COMPLETED',flush=True)
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
            list(pool.map(one,CASES))
        r=audit(base,out)
        require(digest(binary)==binary_hash and all(digest(Path(p))==h for p,h in recorded.items()),'test inputs changed')
        r.update(executable_sha256=binary_hash,hardware_sources_verified=len(hardware),rtl_rerun=True)
        (out/'RESULT.json').write_text(json.dumps(r,indent=2)+'\n');(out/'gate.exit').write_text('0\n');return r
    except Exception:
        (out/'gate.exit').write_text('1\n');raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo',type=Path,required=True);p.add_argument('--base',type=Path,required=True)
    p.add_argument('--lifecycle',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--jobs',type=int,default=3);p.add_argument('--verify-only',action='store_true');a=p.parse_args()
    try:
        if a.verify_only:
            require((a.output/'gate.exit').read_text().strip()=='0','gate incomplete')
            report=audit(a.base,a.output);report['rtl_rerun']=False
        else:report=run(a.repo.resolve(),a.base.resolve(),a.lifecycle.resolve(),a.output.resolve(),a.jobs)
        print(json.dumps(report,indent=2))
    except (ValueError,OSError,KeyError,TypeError,subprocess.SubprocessError) as e:raise SystemExit('DENSE_BURST_RECOVERY_REJECTED: '+str(e))
