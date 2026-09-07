#!/usr/bin/env python3
"""Six actual cross-layer faults and full same-DUT reset recovery, tiny33 L=3.
Links a new test harness against unchanged original Matrix/iDMA DUT libraries.
"""
from pathlib import Path
import argparse,csv,gzip,hashlib,json,math,os,re,struct,subprocess

CASES=[('descriptor-read-error',21),('descriptor-read-error',32),('read-error',33),
       ('last-write-error',41),('read-error',42),('last-write-error',62)]

def req(ok,message):
    if not ok:raise ValueError(message)

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def library_inputs(build):
    files=[build/'obj/VHostBlockTop__ALL.a',
        build/'obj/Vbf16_context_lane_cluster16_rev8b_b_candidate/libbf16_context_lane_cluster16_rev8b_b_candidate.a',
        build/'generated/HostBlockTop.sv',build/'generated/owner_shape.h']
    files += [build/'obj'/n for n in ['verilated.o','verilated_dpi.o','verilated_threads.o']]
    return {str(p.resolve()):sha(p) for p in files}

def frozen_hardware(repo,build):
    recorded=json.loads((build/'sources.sha256.json').read_text());result={}
    for relative,digest in recorded.items():
        if relative.endswith('.sv') or ('/src/main/' in relative and relative.endswith('.scala')):
            req(sha(repo/relative)==digest,'DUT differs from frozen build: '+relative);result[relative]=digest
    req(len(result)>20,'incomplete DUT identity');return result

def verify(directory,manifest,mode,pc):
    req((directory/'simulation.exit').read_text().strip()=='0','simulator failed')
    text=(directory/'run.log').read_text();local=pc%21;prior=pc-local+10 if 10<=local<=12 else pc
    req(not re.search(r'HOST_STACK_RECOVERY_FAIL|HOST_BLOCK_FAIL|%Error|\bFatal\b',text),'DUT failure')
    expected=f'HOST_STACK_RECOVERY_PASS mode={mode} global_pc={pc} prior_completed={prior} layers=3 tokens=33 recovered_commands=63 recovered_jobs=57 recovered_values=123552 reset_between_requests=1 same_dut=1 host_intermediate_writes=0'
    req([l for l in text.splitlines() if l.startswith('HOST_STACK_RECOVERY_PASS')]==[expected],'bad recovery receipt')
    req(len(re.findall(r'^HOST_BLOCK_ALL_OWNERS_PASS ',text,re.M))==1,'missing complete numerical recovery')
    req([int(x) for x in re.findall(r'^OWNER_COMPLETION pc=(\d+) ',text,re.M)]==list(range(prior))+list(range(63)),'wrong completion prefixes')
    errors=re.findall(r'^EXPECTED_ERROR pc=(\d+) status=(\d+)$',text,re.M)
    req(len(errors)==1 and int(errors[0][0])==pc and int(errors[0][1])>0,'missing nonzero error')
    values=0;hashes={};csv_path=directory/'all_recovery_elements.csv.gz'
    req(not csv_path.exists(),'refuse to overwrite CSV')
    with gzip.open(csv_path,'wt',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(['request','pc','tensor','index','actual_hex','reference_hex'])
        for request,count in [('failed',prior),('recovered',63)]:
            for op in manifest['schedule']:
                for name in op['outputs']:
                    a=directory/request/(name+'_actual.f32le');b=directory/request/(name+'_reference.f32le')
                    if op['pc']>=count:
                        req(not a.exists() and not b.exists(),'consumer output after failure');continue
                    raw=a.read_bytes();ref=b.read_bytes();words=manifest['tensors'][name]['words']
                    req(len(raw)==words*4 and raw==ref,'numerical mismatch')
                    req(all(math.isfinite(v[0]) for v in struct.iter_unpack('<f',raw)),'nonfinite output')
                    for i,((x,),(y,)) in enumerate(zip(struct.iter_unpack('<I',raw),struct.iter_unpack('<I',ref))):
                        writer.writerow([request,op['pc'],name,i,f'{x:08x}',f'{y:08x}'])
                    values+=words;hashes[str(a.relative_to(directory))]=sha(a)
    result={'status':'PASS_SAME_DUT_CROSS_LAYER_FAULT_RECOVERY','mode':mode,'global_pc':pc,'prior_completed':prior,
            'layers':3,'tokens':33,'hidden':64,'ffn':128,'recovered_commands':63,'recovered_owner_jobs':57,
            'recovered_fp32':123552,'total_checked_fp32':values,'bit_differences':0,'same_dut':True,
            'reset_between_requests':True,'host_intermediate_writes':0,'actual_sha256':hashes,
            'full_csv_sha256':sha(csv_path),'run_log_sha256':sha(directory/'run.log')}
    with (directory/'RESULT.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    return result

def run(repo,build,fixture,out,ownership=None):
    req(not out.exists(),'new output directory required');req((build/'gate.exit').read_text().strip()=='0','baseline failed')
    manifest=json.loads((fixture/'manifest.json').read_text())
    req((manifest['shape']['H'],manifest['shape']['F'],manifest['tokens'],manifest.get('layers'),manifest['commands'])==(64,128,33,3,63),'wrong fixed geometry')
    p=repo/'chisel/continuous_prefill';vr=Path(os.environ['VERILATOR_ROOT']);out.mkdir(parents=True)
    if ownership is not None:ownership.append(out)
    inputs=library_inputs(build);sources=frozen_hardware(repo,build)
    for f in [p/'tests/host_owner_stack_recovery.cpp',p/'tests/host_block_commands.cpp',p/'scripts/run_owner_stack_recovery.py',*sorted(fixture.iterdir())]:
        if f.is_file():inputs[str(f.resolve())]=sha(f)
    (out/'INPUTS_SHA256.json').write_text(json.dumps(inputs,indent=2)+'\n')
    (out/'HARDWARE_SHA256.json').write_text(json.dumps(sources,indent=2)+'\n')
    cmd=['g++','-O3','-std=c++17','-ffp-contract=off','-fno-fast-math',*[f'-I{x}' for x in [build/'obj',vr/'include',vr/'include/vltstd',build/'generated',fixture,p/'tests']],
         str(p/'tests/host_owner_stack_recovery.cpp'),str(build/'obj/VHostBlockTop__ALL.a'),str(build/'obj/Vbf16_context_lane_cluster16_rev8b_b_candidate/libbf16_context_lane_cluster16_rev8b_b_candidate.a'),
         *[str(build/'obj'/x) for x in ['verilated.o','verilated_dpi.o','verilated_threads.o']],'-pthread','-latomic','-o',str(out/'VHostStackRecovery')]
    with (out/'build.log').open('xb') as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True)
    cases=[]
    for i,(mode,pc) in enumerate(CASES):
        d=out/f'{i:02d}_{mode}_{pc}';d.mkdir()
        with (d/'run.log').open('xb') as f:r=subprocess.run([str(out/'VHostStackRecovery'),str(fixture),str(d/'outputs'),mode,str(pc),str(20260907+i)],stdout=f,stderr=subprocess.STDOUT,timeout=900)
        (d/'simulation.exit').write_text(str(r.returncode)+'\n')
        # Keep a single directory layout without changing any numerical byte.
        # The verifier is pointed at outputs via an explicit subdirectory below.
        req(r.returncode==0,'stack simulator failed: '+str(d))
        outputs=d/'outputs'
        for name in ['failed','recovered']:
            (outputs/name).rename(d/name)
        cases.append(verify(d,manifest,mode,pc));print('PASS',mode,pc,flush=True)
    req(inputs=={k:sha(Path(k)) for k in inputs},'immutable library/fixture/source changed')
    req(sources==frozen_hardware(repo,build),'hardware changed')
    result={'status':'PASS_SIX_CROSS_LAYER_FAULT_RECOVERIES','cases':cases,'source_sha256':sources,
            'scope':'Tiny three-layer 33-token original Host command graph; not real-size multilayer, cache persistence, official weights or q1024.'}
    with (out/'RESULT.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    (out/'gate.exit').write_text('0\n');return result

if __name__=='__main__':
    a=argparse.ArgumentParser(description=__doc__)
    for n in ['repo','build','fixture','output']:a.add_argument('--'+n,type=Path,required=True)
    args=a.parse_args();owned=[]
    try:print(json.dumps(run(args.repo.resolve(),args.build.resolve(),args.fixture.resolve(),args.output.resolve(),owned),indent=2))
    except (ValueError,OSError,KeyError,TypeError,subprocess.CalledProcessError,subprocess.TimeoutExpired) as e:
        if owned:(owned[0]/'gate.exit').write_text('1\n')
        raise SystemExit('STACK_RECOVERY_REJECTED: '+str(e))
