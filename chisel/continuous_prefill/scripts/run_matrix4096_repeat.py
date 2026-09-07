#!/usr/bin/env python3
"""Two cold requests through frozen 4096-MAC/iDMA DUT; no reset between them.

Each request is a two-layer synthetic tiny16 Host graph. This does not test
persistent KV sessions, official weights, or real-dimensional performance.
"""
from __future__ import annotations
import argparse,hashlib,json,math,os,re,struct,subprocess
from pathlib import Path
from run_matrix4096_recovery import require,digest

def verify(base:Path,out:Path)->dict:
    require((out/'simulation.exit').read_text().strip()=='0','failed simulator')
    m=json.loads((base/'fixture/manifest.json').read_text())
    require((m['tokens'],m['layers'],m['shape']['H'],m['shape']['F'])==(16,2,64,128),'wrong fixture')
    text=(out/'run.log').read_text()
    require(not re.search(r'HOST_BLOCK_FAIL|MATRIX4096_REPEAT_FAIL|%Error|Fatal',text),'failed log')
    marker='MATRIX4096_REPEAT_PASS requests=2 tokens=16 layers_per_request=2 commands=84 checked_fp32=79872 bit_differences=0 same_dut=1 reset_between_requests=0 changed_input=1 changed_weights=1 legacy_block_launch=0 '
    finals=[x for x in text.splitlines() if x.startswith('MATRIX4096_REPEAT_PASS ')]
    require(len(finals)==1 and finals[0].startswith(marker),'wrong completion')
    require([int(x) for x in re.findall(r'^OWNER_COMPLETION pc=(\d+) ',text,re.M)]==list(range(42))*2,'incomplete command execution')
    identities=re.findall(r'^LAYER_WEIGHT_ID layer=(\d+) salt=(\d+) wq=(\d+) wg=(\d+) wd=(\d+)',text,re.M)
    require([(int(x[0]),int(x[1])) for x in identities]==[(0,0),(1,17),(0,11),(1,28)],'wrong distinct weight requests')
    require(all(identities[i][j]!=identities[i+2][j] for i in range(2) for j in range(2,5)),'unchanged repeated weights')
    count=0;hashes={}
    for request in ('first','second'):
        root=out/'tensors'/request
        for op in m['schedule']:
            for name in op['outputs']:
                a=root/(name+'_actual.f32le');b=root/(name+'_reference.f32le');raw=a.read_bytes()
                require(len(raw)==len(b.read_bytes())==m['tensors'][name]['words']*4 and raw==b.read_bytes(),'wrong numerical output')
                require(all(math.isfinite(x[0]) for x in struct.iter_unpack('<f',raw)),'nonfinite output')
                if request=='first':require(raw==(base/'tensors'/(name+'_actual.f32le')).read_bytes(),'first request differs from frozen DUT')
                count+=len(raw)//4;hashes[str(a.relative_to(out))]=hashlib.sha256(raw).hexdigest()
    require(count==79872,'incomplete output coverage')
    for name in ('input_x.f32le','l1_y_actual.f32le'):
        require((out/'tensors/first'/name).read_bytes()!=(out/'tensors/second'/name).read_bytes(),'repeated input/output')
    return {'status':'PASS_MATRIX4096_TWO_LAYER_COLD_REPEAT','requests':2,'commands':84,
            'checked_fp32':count,'bit_differences':0,'same_dut':True,'reset_between_requests':False,
            'changed_input':True,'changed_weights':True,'actual_sha256':hashes,'log_sha256':digest(out/'run.log'),
            'scope':'Synthetic tiny H64/F128 T16 L2 per cold request; not persistent KV, real-size or DC.'}

def run(repo:Path,base:Path,out:Path)->dict:
    require(not out.exists() and not out.is_symlink(),'new output required')
    require((base/'gate.exit').read_text().strip()=='0' and (base/'simulation.exit').read_text().strip()=='0','baseline failed')
    scope=json.loads((base/'generated/SCOPE.json').read_text());require(scope['matrix_macs']==4096,'not 4096 MAC')
    p=repo/'chisel/continuous_prefill';vr=Path(os.environ['VERILATOR_ROOT']).resolve()
    libs=[base/'obj/VHostBlockTop__ALL.a',base/'obj/Vqwen2_matrix_command_endpoint/libqwen2_matrix_command_endpoint.a',base/'obj/Vbf16_context_lane_cluster16_rev8b_b_candidate/libbf16_context_lane_cluster16_rev8b_b_candidate.a']
    runtime=[base/'obj'/n for n in ('verilated.o','verilated_dpi.o','verilated_threads.o')]
    inputs=libs+runtime+[base/'generated/HostBlockTop.sv',base/'generated/owner_shape.h',base/'fixture/owner_fixture.h',base/'fixture/host_commands.bin',base/'fixture/host_descriptors.bin',p/'tests/host_block_commands.cpp',p/'tests/matrix4096_repeat.cpp']
    before={str(x):digest(x) for x in inputs}
    recorded=json.loads((base/'sources.sha256.json').read_text())
    frozen={n:v for n,v in recorded.items() if n.endswith('.sv') or ('/src/main/' in n and n.endswith('.scala'))}
    require(len(frozen)>100 and all(digest(repo/n)==v for n,v in frozen.items()),'DUT source changed')
    require(digest(p/'tests/host_block_commands.cpp')==recorded['chisel/continuous_prefill/tests/host_block_commands.cpp'],'base harness changed')
    out.mkdir(parents=True);(out/'INPUTS_SHA256.json').write_text(json.dumps(before,indent=2)+'\n')
    command=['g++','-O3','-std=c++17','-ffp-contract=off','-fno-fast-math']
    for inc in (base/'obj',vr/'include',vr/'include/vltstd',base/'generated',base/'fixture',p/'tests'):command+=['-I'+str(inc)]
    command+=[str(p/'tests/matrix4096_repeat.cpp')]+list(map(str,libs+runtime))+['-pthread','-latomic','-o',str(out/'VMatrix4096Repeat')]
    with (out/'build.log').open('xb') as f:subprocess.run(command,stdout=f,stderr=subprocess.STDOUT,check=True)
    with (out/'run.log').open('xb') as f:
        done=subprocess.run([str(out/'VMatrix4096Repeat'),str(base/'fixture'),str(out/'tensors')],stdout=f,stderr=subprocess.STDOUT,timeout=900)
    (out/'simulation.exit').write_text(str(done.returncode)+'\n')
    report=verify(base,out)
    require(before=={n:digest(Path(n)) for n in before},'test inputs changed')
    report['inputs_sha256']=before
    (out/'RESULT.json').write_text(json.dumps(report,indent=2)+'\n');(out/'gate.exit').write_text('0\n')
    return report
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repo',type=Path,required=True);p.add_argument('--base',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    try:print(json.dumps(run(a.repo.resolve(),a.base.resolve(),a.output.resolve()),indent=2))
    except (ValueError,OSError,KeyError,TypeError,subprocess.SubprocessError) as e:raise SystemExit('MATRIX4096_REPEAT_REJECTED: '+str(e))
