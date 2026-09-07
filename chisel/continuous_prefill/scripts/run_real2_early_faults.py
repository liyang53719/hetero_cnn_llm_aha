#!/usr/bin/env python3
"""Seven early real-dimensional faults on an existing original Matrix/iDMA DUT.

Reuses the immutable executable and fixture. No RTL, memory service or source
is edited. This negative gate does NOT establish full numerical or recovery
completion. Every run receives a new process/reset, and tests reset lockout.
"""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess

CASES=[('bad-first-op',0,0),('descriptor-shape',0,0),('wrong-dependency',1,1),
       ('descriptor-read-error',1,1),('read-error',1,1),('write-error',1,1),('last-write-error',1,1)]

def require(ok,message):
    if not ok:raise ValueError(message)

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def run(build,out):
    require(not out.exists(),'refuse to overwrite any previous result')
    exe=build/'obj/VHostBlockTop';fixture=build/'fixture'
    require(exe.is_file() and os.access(exe,os.X_OK),'missing compiled DUT')
    m=json.loads((fixture/'manifest.json').read_text())
    require((m['tokens'],m.get('layers'),m['commands'],m['shape']['H'],m['shape']['F'])==(16,2,42,1536,8960),'fixed real16 two-layer DUT/fixture required')
    paths=[exe,fixture/'manifest.json',fixture/'host_commands.bin',fixture/'host_descriptors.bin',build/'generated/HostBlockTop.sv',build/'sources.sha256.json']
    before={str(p.relative_to(build)):sha(p) for p in paths};out.mkdir(parents=True);results=[]
    for mode,pc,prior in CASES:
        d=out/mode;d.mkdir()
        with (d/'run.log').open('xb') as stream:
            completed=subprocess.run([str(exe),str(fixture),str(d/'tensors'),mode],stdout=stream,stderr=subprocess.STDOUT,timeout=600)
        (d/'simulation.exit').write_text(str(completed.returncode)+'\n');text=(d/'run.log').read_text()
        require(completed.returncode==0,'simulator failed: '+mode)
        require(not re.search(r'HOST_BLOCK_FAIL|HOST_BLOCK_ALL_OWNERS_PASS|%Error|\bFatal\b',text),'unexpected success or fatal: '+mode)
        receipt=f'HOST_BLOCK_FAULT_PASS mode={mode} pc={pc} prior_completions={prior} next_owner_not_started=1'
        require(text.splitlines().count(receipt)==1,'missing or duplicate fault receipt: '+mode)
        errors=re.findall(r'^EXPECTED_ERROR pc=(\d+) status=(\d+)$',text,re.M)
        require(len(errors)==1 and int(errors[0][0])==pc and int(errors[0][1])!=0,'failure identity: '+mode)
        pcs=[int(x) for x in re.findall(r'^OWNER_COMPLETION pc=(\d+) ',text,re.M)]
        require(pcs==list(range(prior)),'consumer completed after failure: '+mode)
        if mode.endswith('error'):
            injection=re.findall(r'^FAULT_INJECT pc=1 mode='+mode+r' address=(\d+) prior_write_bytes=(\d+)$',text,re.M)
            require(len(injection)==1,'AXI fault not actually injected')
            if mode=='last-write-error':require(int(injection[0][1])==16*1536*4-64,'last-write fault missed the partial output boundary')
            elif mode=='write-error':require(int(injection[0][1])==0,'first-write fault was not first')
        results.append({'mode':mode,'error_pc':pc,'status':int(errors[0][1]),'completed_prefix':pcs,'log_sha256':sha(d/'run.log')})
    require(before=={str(p.relative_to(build)):sha(p) for p in paths},'DUT or fixture changed')
    result={'schema':1,'status':'PASS_REAL16_TWO_LAYER_EARLY_FAULTS','tokens':16,'layers':2,
            'commands_in_fixture':42,'hidden':1536,'ffn':8960,'cases':results,'inputs_sha256':before,
            'actual_dut':True,'reset_recovery_tested':False,'full_numerical_pass':False,
            'scope':'First-layer early rejection/lockout on real16 two-layer hardware; not a positive request or reset recovery test.'}
    with (out/'RESULT.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    (out/'gate.exit').write_text('0\n');print(json.dumps(result,indent=2));return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    try:run(a.build.resolve(),a.output.resolve())
    except (ValueError,OSError,KeyError,TypeError,subprocess.TimeoutExpired) as e:
        raise SystemExit('REAL2_EARLY_FAULTS_REJECTED: '+str(e))
