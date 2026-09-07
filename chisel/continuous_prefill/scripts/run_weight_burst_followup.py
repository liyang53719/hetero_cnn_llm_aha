#!/usr/bin/env python3
"""Execution-only follow-ups on a frozen burst-enabled real or tiny T16 L2 DUT.

'profile' observes existing public counters without changing the schedule.
'align' rebinds only DDR addresses to test 1KiB weight alignment. Neither mode
changes Chisel/RTL or substitutes any reference tensor for actual computation.
Requires the base gate's compiled objects, not just an archived JSON receipt.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,os,shutil,subprocess
from pathlib import Path
from align_owner_weight_fixture import transform
from verify_host_block_gate import verify,tagged
from audit_owner_block_abi import audit


def require(ok,message):
    if not ok:raise ValueError(message)


def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def run(repo:Path,base:Path,out:Path,mode:str)->dict:
    require(mode in ('profile','align'),'unsupported follow-up')
    require(not out.exists() and not out.is_symlink(),'new output required')
    require((base/'gate.exit').read_text().strip()=='0' and (base/'simulation.exit').read_text().strip()=='0','base gate unfinished')
    manifest=json.loads((base/'fixture/manifest.json').read_text())
    scope=json.loads((base/'generated/SCOPE.json').read_text())
    require((manifest['tokens'],manifest['layers'],scope['matrix_macs'],scope['weight_read_burst_beats'])==(16,2,4096,16),'frozen burst T16 L2 required')
    old=verify(base,False);identities=json.loads((base/'sources.sha256.json').read_text())
    hw={p:h for p,h in identities.items() if p.endswith('.sv') or '/src/main/' in p}
    require(len(hw)>100 and all(digest(repo/p)==h for p,h in hw.items()),'hardware source drift')
    project=repo/'chisel/continuous_prefill';harness=project/'tests/host_block_commands.cpp'
    require(digest(harness)==identities['chisel/continuous_prefill/tests/host_block_commands.cpp'],'original harness drift')
    vr=Path(os.environ.get('VERILATOR_ROOT',str(base/'verilator-runtime')))
    libraries=[base/'obj/VHostBlockTop__ALL.a',base/'obj/Vqwen2_matrix_command_endpoint/libqwen2_matrix_command_endpoint.a',base/'obj/Vbf16_context_lane_cluster16_rev8b_b_candidate/libbf16_context_lane_cluster16_rev8b_b_candidate.a']
    libraries += [base/'obj'/n for n in ('verilated.o','verilated_dpi.o','verilated_threads.o')]
    driver=project/'tests/weight_burst_owner_profile.cpp' if mode=='profile' else harness
    inputs=libraries+[driver,harness,base/'generated/HostBlockTop.sv',Path(__file__).resolve(),project/'scripts/align_owner_weight_fixture.py']
    before={str(p):digest(p) for p in inputs}
    out.mkdir(parents=True);numeric=out/'numerical';numeric.mkdir()
    (out/'INPUTS_SHA256.json').write_text(json.dumps(before,indent=2)+'\n')
    try:
        if mode=='align':transform(base/'fixture',numeric/'fixture')
        else:shutil.copytree(base/'fixture',numeric/'fixture')
        shutil.copytree(base/'generated',numeric/'generated')
        for name in ('sources.sha256.json','hardfloat.sha256.json','source_base_commit.txt','idma_identity.json'):
            shutil.copyfile(base/name,numeric/name)
        command=['g++','-O3','-std=c++17','-ffp-contract=off','-fno-fast-math']
        for p in (base/'obj',vr/'include',vr/'include/vltstd',numeric/'generated',numeric/'fixture',project/'tests'):
            command+=['-I'+str(p)]
        command+=[str(driver)]+list(map(str,libraries))+['-pthread','-latomic','-o',str(out/'VFollowup')]
        (out/'BUILD_COMMAND.json').write_text(json.dumps(command,indent=2)+'\n')
        with (out/'build.log').open('xb') as f:subprocess.run(command,stdout=f,stderr=subprocess.STDOUT,check=True)
        payload=out/'payload';destination=payload if mode=='profile' else payload/'tensors'
        with (numeric/'run.log').open('xb') as f:
            process=subprocess.run([str(out/'VFollowup'),str(numeric/'fixture'),str(destination)],stdout=f,stderr=subprocess.STDOUT,timeout=18000)
        (numeric/'simulation.exit').write_text(str(process.returncode)+'\n')
        require(process.returncode==0,'simulation failed')
        shutil.copytree(payload/'tensors',numeric/'tensors')
        current=verify(numeric,True);abi=audit(numeric)
        (numeric/'PUBLIC_ABI.json').write_text(json.dumps(abi,indent=2)+'\n')
        checked=0
        for op in manifest['schedule']:
            for name in op['outputs']:
                a=numeric/'tensors'/(name+'_actual.f32le');b=base/'tensors'/(name+'_actual.f32le')
                require(a.read_bytes()==b.read_bytes(),'frozen actual output mismatch: '+name);checked+=len(a.read_bytes())//4
        require(checked==old['checked_fp32']==current['checked_fp32'],'coverage mismatch')
        for key in ('useful_macs','executed_macs','read_bytes','write_ack_bytes'):
            require(current['counters'][key]==old['counters'][key],'changed work or physical bytes')
        if mode=='profile':
            require(current['counters']==old['counters'],'passive profiling altered execution')
            rows=list(csv.DictReader((payload/'owner_counters.csv').open()));require(len(rows)==42,'incomplete profile')
            ends=tagged((numeric/'run.log').read_text(),'OWNER_COMPLETION');prior={}
            for i,row in enumerate(rows):
                now={k:int(v) for k,v in row.items()}
                require(now['pc']==i and now['cycle']==int(ends[i]['cycle']),'profile ordering')
                require(all(v>=prior.get(k,0) for k,v in now.items()),'nonmonotonic profile')
                prior=now
            for name,key in [('idma_transfers','idma_transfers'),('read_bursts','read_bursts'),('cache_hits','weight_cache_hits'),('useful_macs','useful_macs'),('executed_macs','executed_macs'),('write_ack_bytes','write_ack_bytes')]:
                require(prior[name]==int(current['counters'][key]),'profile counter mismatch')
            require(prior['read_beats']*64==int(current['counters']['read_bytes']),'profile read bytes')
            shutil.copyfile(payload/'owner_counters.csv',out/'OWNER_COUNTERS.csv')
        require(before=={p:digest(Path(p)) for p in before},'frozen inputs changed')
        result=dict(status='PASS_WEIGHT_BURST_FROZEN_DUT_FOLLOWUP',mode=mode,
                    tokens=16,layers=2,hidden=manifest['shape']['H'],ffn=manifest['shape']['F'],
                    checked_fp32=checked,bit_differences=0,baseline_counters=old['counters'],
                    current_counters=current['counters'],hardware_changed=False,host_intermediate_copy=False,
                    official_weights=False,dc_timing=False,inputs_sha256=before)
        (out/'RESULT.json').write_text(json.dumps(result,indent=2)+'\n')
        (numeric/'gate.exit').write_text('0\n');(out/'gate.exit').write_text('0\n');return result
    except Exception:
        (out/'gate.exit').write_text('1\n');raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repo',type=Path,required=True);p.add_argument('--base',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--mode',choices=('profile','align'),required=True);a=p.parse_args()
    try:print(json.dumps(run(a.repo.resolve(),a.base.resolve(),a.output.resolve(),a.mode),indent=2))
    except (ValueError,OSError,KeyError,TypeError,subprocess.SubprocessError) as e:raise SystemExit('WEIGHT_BURST_FOLLOWUP_REJECTED: '+str(e))
