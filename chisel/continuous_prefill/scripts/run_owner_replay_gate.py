#!/usr/bin/env python3
"""Replay relocated, tail-token or multi-layer public commands on frozen RTL.

Only the C++ memory/test harness is linked for a new allocation header; no
Chisel or SV is edited, and no generated DUT or prior output is overwritten.
"""
from __future__ import annotations
import argparse,hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
from pack_owner_block_fixture import pack
from pack_owner_multilayer_fixture import pack_layers
from swap_owner_fixture import swap
from verify_host_block_gate import verify
from audit_owner_block_abi import audit


def require(ok,message):
    if not ok:raise ValueError(message)


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def run(repo,base,out,tokens,relocate,layers,swapped,seed):
    require(not out.exists(),'new output directory required')
    require((base/'gate.exit').read_text().strip()=='0' and (base/'simulation.exit').read_text().strip()=='0','baseline must have passed')
    p=repo/'chisel/continuous_prefill';vr=Path(os.environ['VERILATOR_ROOT']).resolve()
    require((vr/'include/verilated.h').is_file(),'missing Verilator runtime')
    original=json.loads((base/'sources.sha256.json').read_text());frozen={}
    for path,digest in original.items():
        if path.endswith('.sv') or ('/src/main/' in path and path.endswith('.scala')):
            require(sha(repo/path)==digest,'DUT source differs from frozen build: '+path);frozen[path]=digest
    require(len(frozen)>20,'incomplete baseline hardware identity')
    shape=json.loads((base/'fixture/manifest.json').read_text())['shape']
    require(1<=layers<=3 and (not swapped or layers==1),'unsupported layer/swap combination')
    require(0<seed<2**32,'invalid random seed')
    out.mkdir(parents=True)
    target=out/('fixture_initial' if swapped else 'fixture')
    if layers>1:pack_layers(shape,tokens,layers,target,relocate)
    else:pack(shape,tokens,target,relocate)
    if swapped:swap(target,out/'fixture')
    shutil.copytree(base/'generated',out/'generated')
    for name in ['sources.sha256.json','hardfloat.sha256.json','idma_identity.json','source_base_commit.txt']:shutil.copyfile(base/name,out/name)
    libs=[base/'obj/VHostBlockTop__ALL.a',base/'obj/Vbf16_context_lane_cluster16_rev8b_b_candidate/libbf16_context_lane_cluster16_rev8b_b_candidate.a']
    runtime=[base/'obj'/n for n in ['verilated.o','verilated_dpi.o','verilated_threads.o']]
    inputs=libs+runtime+[base/'generated/HostBlockTop.sv',p/'tests/host_block_commands.cpp',out/'fixture/owner_fixture.h',out/'fixture/host_commands.bin',out/'fixture/host_descriptors.bin']
    before={str(x):sha(x) for x in inputs}
    shutil.copyfile(out/'sources.sha256.json',out/'BASE_BUILD_SOURCES_SHA256.json')
    actual=dict(original)
    actual['chisel/continuous_prefill/tests/host_block_commands.cpp']=sha(p/'tests/host_block_commands.cpp')
    (out/'sources.sha256.json').write_text(json.dumps(actual,indent=2)+'\n')
    proof={'frozen_build':str(base),'same_emitted_dut':True,'frozen_dut_sources':frozen,'inputs_sha256':before,
           'tokens':tokens,'layers':layers,'relocate':relocate,'individual_swaps':swapped,'seed':seed,
           'test_harness_updated':True,'test_harness_sha256':sha(p/'tests/host_block_commands.cpp')}
    (out/'REPLAY_PROVENANCE.json').write_text(json.dumps(proof,indent=2)+'\n')
    cmd=['g++','-O3','-std=c++17','-ffp-contract=off','-fno-fast-math']
    for inc in [base/'obj',vr/'include',vr/'include/vltstd',out/'generated',out/'fixture']:cmd+=['-I'+str(inc)]
    cmd+=[str(p/'tests/host_block_commands.cpp')]+list(map(str,libs+runtime))+['-pthread','-latomic','-o',str(out/'VHostOwnerReplay')]
    with (out/'link.log').open('xb') as log:subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
    env=dict(os.environ,OWNER_RANDOM_SEED=str(seed))
    with (out/'run.log').open('xb') as log:
        done=subprocess.run([str(out/'VHostOwnerReplay'),str(out/'fixture'),str(out/'tensors')],env=env,stdout=log,stderr=subprocess.STDOUT)
    (out/'simulation.exit').write_text(str(done.returncode)+'\n')
    require(done.returncode==0,'DUT simulation failed; inspect run.log')
    require(before=={str(x):sha(x) for x in inputs},'frozen replay inputs changed')
    report=verify(out,True);abi=audit(out)
    (out/'PUBLIC_ABI.json').write_text(json.dumps(abi,indent=2)+'\n');(out/'verification.log').write_text(json.dumps(report,indent=2)+'\n')
    (out/'gate.exit').write_text('0\n');return report


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--repo',type=Path,required=True);ap.add_argument('--build',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--tokens',type=int,default=17);ap.add_argument('--layers',type=int,default=1);ap.add_argument('--relocate',type=int,default=9467985920);ap.add_argument('--swap',action='store_true');ap.add_argument('--seed',type=int,default=20260907);a=ap.parse_args()
    try:print(json.dumps(run(a.repo.resolve(),a.build.resolve(),a.output.resolve(),a.tokens,a.relocate,a.layers,a.swap,a.seed),indent=2))
    except (ValueError,OSError,KeyError,TypeError,subprocess.CalledProcessError) as e:
        # Existing evidence is never changed on rejection; caller records exit status.
        raise SystemExit('OWNER_REPLAY_FAILED: '+str(e))
