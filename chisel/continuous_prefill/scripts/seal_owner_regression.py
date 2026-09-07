#!/usr/bin/env python3
"""Read-only full-regression checks before writing one new summary.

The fixed profiles have different scopes. The tiny suite must include all 99
physical fault sites, same-DUT recovery, no-reset repeat and 2/3-layer graphs.
The real-cross profile proves ONLY the real-dimension relocated 17-token block.
A checksum is provenance, not independent proof that a simulation took place.
"""
from __future__ import annotations
import argparse,csv,gzip,hashlib,json,re,struct,sys
from pathlib import Path
from audit_owner_block_abi import audit
from verify_host_block_gate import verify,fields
from run_owner_lifecycle_gate import verify as verify_lifecycle


def require(ok,message):
    if not ok:raise ValueError(message)


def sha(path):
    h=hashlib.sha256sum() if False else hashlib.sha256()
    with path.open('rb') as f:
        for data in iter(lambda:f.read(1<<20),b''):h.update(data)
    return h.hexdigest()


def compare_csv(out):
    m=json.loads((out/'fixture/manifest.json').read_text());count=0
    with gzip.open(out/'all_owner_elements.csv.gz','rt',newline='') as stream:
        rows=csv.reader(stream)
        require(next(rows,None)==['pc','tensor','index','actual_hex','reference_hex'],'CSV header')
        for op in m['schedule']:
            for name in op['outputs']:
                a=(out/f'tensors/{name}_actual.f32le').read_bytes();b=(out/f'tensors/{name}_reference.f32le').read_bytes()
                require(len(a)==len(b)==4*m['tensors'][name]['words'],'CSV source length')
                for i,((x,),(y,)) in enumerate(zip(struct.iter_unpack('<I',a),struct.iter_unpack('<I',b))):
                    require(next(rows,None)==[str(op['pc']),name,str(i),f'{x:08x}',f'{y:08x}'],'CSV row identity/order')
                    require(x==y,'CSV actual/reference mismatch');count+=1
        require(next(rows,None) is None,'extra CSV row')
    return count


def source_check(repo,out):
    manifest=json.loads((out/'sources.sha256.json').read_text());hardware={}
    for path,digest in manifest.items():
        if path.endswith('.sv') or ('/src/main/' in path and path.endswith('.scala')):
            p=Path(path);require(not p.is_absolute() and '..' not in p.parts,'unsafe hardware path')
            require(sha(repo/p)==digest,'changed hardware source: '+path);hardware[path]=digest
    require(len(hardware)>20,'incomplete hardware identity')
    harness='chisel/continuous_prefill/tests/host_block_commands.cpp'
    require(manifest.get(harness)==sha(repo/harness),'actual test harness not bound to current checkout')
    if (out/'REPLAY_PROVENANCE.json').exists():
        p=json.loads((out/'REPLAY_PROVENANCE.json').read_text())
        require(p['same_emitted_dut'] is True and p['frozen_dut_sources']==hardware,'replay hardware identity')
        require(p['test_harness_sha256']==sha(repo/harness),'replay harness identity')
        for path,digest in p['inputs_sha256'].items():require(sha(Path(path))==digest,'changed frozen replay input')
    return len(hardware)


def numerical(repo,out,tokens,layers,hidden,ffn):
    require((out/'gate.exit').read_text().strip()=='0','numerical gate did not pass')
    r=verify(out,False);a=audit(out);count=compare_csv(out)
    require((r['tokens'],r.get('layers',1),r['shape']['H'],r['shape']['F'])==(tokens,layers,hidden,ffn),'wrong requested geometry')
    require(r['checked_fp32']==a['checked_fp32']==count,'binary/CSV count disagreement')
    return {'status':r['status'],'tokens':tokens,'layers':layers,'hidden':hidden,'ffn':ffn,
            'checked_fp32':count,'commands':21*layers,'owner_jobs':19*layers,'counters':r['counters'],
            'hardware_sources_verified':source_check(repo,out),'generated_rtl_sha256':sha(out/'generated/HostBlockTop.sv'),
            'csv_sha256':sha(out/'all_owner_elements.csv.gz'),'log_sha256':sha(out/'run.log')}


def lifecycle(repo,path,manifest,allowed):
    require((path/'gate.exit').read_text().strip()=='0','lifecycle gate did not pass')
    r=json.loads((path/'RESULT.json').read_text());require(r['status']=='PASS_HOST_OWNER_LIFECYCLE_SUITE','lifecycle status')
    for name,digest in r['immutable_inputs'].items():require(sha(Path(name))==digest,'lifecycle library/harness/input changed')
    frozen=r['frozen_dut_sources']
    require(len(frozen)>20 and all(sha(repo/name)==digest for name,digest in frozen.items()),'lifecycle hardware changed')
    results=[];observed=set();dirs=sorted(p for p in path.iterdir() if p.is_dir())
    require(len(dirs)==len(r['cases']),'lifecycle case count')
    for d,saved in zip(dirs,r['cases']):
        mode=saved['mode'];pc=saved['fault_pc'];key=(mode,0 if pc is None else pc)
        require(key in allowed and key not in observed,'unexpected/duplicate fault site');observed.add(key)
        checked=verify_lifecycle(d,manifest,mode,key[1]);require(checked==saved,'lifecycle receipt not reproducible')
        require(json.loads((d/'RESULT.json').read_text())==checked,'per-case receipt disagrees')
        results.append({'mode':mode,'fault_pc':pc,'checked_fp32':checked['checked_fp32'],'same_dut':True,
                        'reset_between_requests':checked['reset_between_requests'],'log_sha256':sha(d/'run.log')})
    require(observed==allowed,'missing required fault sites')
    return results


def seal(repo,root,profile):
    require(profile in ('tiny','real-cross'),'unknown fixed profile')
    target=root/'REGRESSION_RESULT.json';require(not target.exists(),'preserve existing regression summary')
    commit=(root/'source_commit.txt').read_text().strip();require(re.fullmatch('[0-9a-f]{40}',commit) is not None,'invalid source identity')
    if profile=='real-cross':
        cases={'real17':numerical(repo,root/'real17',17,1,1536,8960)}
        m=json.loads((root/'real17/fixture/manifest.json').read_text())
        require(m['base']==0x100000000+9467985920,'real request was not relocated')
        faults=[];repeat=[]
    else:
        plans=[('base17',17,1),('relocated32',32,1),('relocated33',33,1),('high48_33',33,1),('layers2_17',17,2),('layers3_33',33,3)]
        cases={n:numerical(repo,root/n,t,l,64,128) for n,t,l in plans}
        for name in ('relocated32','relocated33'):
            m=json.loads((root/name/'fixture/manifest.json').read_text())
            require(m['base']==0x100000000+9467985920,'missing relocated request')
            p=json.loads((root/name/'REPLAY_PROVENANCE.json').read_text());require(p['individual_swaps'] is True,'individual address swaps absent')
        high=json.loads((root/'high48_33/fixture/manifest.json').read_text());require(high['base']==0x100000000+(1<<48),'upper address bits not tested')
        base=json.loads((root/'base17/fixture/manifest.json').read_text())
        repeat=lifecycle(repo,root/'repeat',base,{('repeat',0)})
        metadata={(mode,pc) for mode in ('command-read-error','descriptor-read-error') for pc in range(21)}
        payload={(mode,pc) for mode in ('read-error','write-error','last-write-error') for pc in range(21) if pc not in (10,11)}
        faults=lifecycle(repo,root/'fault_metadata',base,metadata)+lifecycle(repo,root/'fault_payload',base,payload)
        require(len(faults)==99,'not full scoped fault matrix')
        require((root/'unit/gate.exit').read_text().strip()=='0','Chisel unit gate failed')
        text=(root/'unit/chisel_tests.log').read_text();plain=re.sub(r'\x1b\[[0-9;]*m','',text)
        require('All tests passed.' in plain and 'FAILED' not in plain,'Chisel test result')
        require('clear previous-request producer visibility' in plain,'missing stale-producer test')
        for name in ('python_tests.log','python_optimized_tests.log'):
            t=(root/name).read_text();require(re.search(r'Ran 15 tests\b',t) is not None and '\nOK\n' in t and 'skipped=' not in t,'negative tests incomplete')
    report={'schema':1,'status':'PASS_FIXED_HOST_OWNER_REGRESSION','profile':profile,'source_commit':commit,'cases':cases,
            'fault_recoveries':faults,'no_reset_repeats':repeat,
            'scope':{'synthetic_weights':True,'retained_matrix':True,'pinned_idma':True,'block_launch':False,
                     'real17_cross_tile':profile=='real-cross','tiny_multilayer':profile=='tiny','real_multilayer':False,
                     'official_weights':False,'q1024_full_network':False,'dc':False}}
    # Successful verification precedes the only write. Preserve complete raw artifacts.
    with target.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
    print(json.dumps(report,indent=2));return report


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--repo',type=Path,required=True);ap.add_argument('--root',type=Path,required=True);ap.add_argument('--profile',choices=('tiny','real-cross'),required=True);a=ap.parse_args()
    try:seal(a.repo.resolve(),a.root.resolve(),a.profile)
    except (ValueError,OSError,KeyError,TypeError) as e:raise SystemExit('OWNER_REGRESSION_REJECTED: '+str(e))
