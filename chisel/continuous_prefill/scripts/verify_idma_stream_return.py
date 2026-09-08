#!/usr/bin/env python3
"""Check all same-timing real-iDMA A/B cases. Not whole-model performance."""
from pathlib import Path
import hashlib,json,re,sys

def require(ok,message):
    if not ok: raise ValueError(message)

def parse(root:Path,mode:int):
    d=root/f'mode{mode}'
    require((d/'simulation.exit').read_text().strip()=='0','simulator failure')
    log=(d/'run.log').read_text()
    require(not re.search(r'FAIL|%Error|Fatal|Assertion failed',log),'failed log')
    require('idma_backend_rw_axi_flat_wrap' in (d/'generated/IdmaStreamReturnProbe.sv').read_text(),'real iDMA binding missing')
    finals=[x for x in log.splitlines() if x.startswith('IDMA_STREAM_RETURN_PASS ')]
    require(len(finals)==1,'ambiguous completion')
    fields=dict(re.findall(r'(\w+)=(\d+)',finals[0]))
    for k,v in {'cut':mode,'cases':79,'numerical_mismatches':0,'late_errors':9,'protocol_rejections':5,'physical_idma':1}.items():
        require(fields.get(k)==str(v),'bad completion '+k)
    rows=[]
    for line in log.splitlines():
        if line.startswith('IDMA_STREAM_CASE '):
            r=dict(re.findall(r'(\w+)=(\S+)',line))
            require(r.get('cut')==str(mode),'wrong mode')
            require(all(re.fullmatch(r'[0-9]+',r[k]) for k in ['beats','first','cycles','position','invalid','hold','random']),'invalid counter')
            require(0<int(r['first'])<int(r['cycles']),'invalid latency')
            rows.append(r)
    require(len(rows)==79,'missing cases')
    require([int(x['beats']) for x in rows[:6]]==[1,2,3,8,15,16],'wrong benchmark')
    require(sum(x['fault']!='none' for x in rows)==9 and sum(x['invalid']=='1' for x in rows)==5,'fault coverage')
    require(int(fields['sequential_supply_cycles'])==sum(int(x['cycles']) for x in rows[:6]),'bad elapsed sum')
    return rows,hashlib.sha256(log.encode()).hexdigest()

def verify(root:Path):
    old,h0=parse(root,0);new,h1=parse(root,1)
    for a,b in zip(old,new):
        require(all(a[k]==b[k] for k in ['beats','fault','position','invalid','hold','random']),'different tests')
    oldc=sum(int(x['cycles']) for x in old[:6]);newc=sum(int(x['cycles']) for x in new[:6])
    require(newc<oldc,'no measured return-path improvement')
    require(all(int(b['first'])<int(a['first']) for a,b in zip(old[1:6],new[1:6])),'prefix latency not improved')
    return {'status':'PASS_REAL_IDMA_CUT_THROUGH_TRANSPORT','cases_per_mode':79,
            'replay_cycles':oldc,'cut_through_cycles':newc,'transport_speedup':oldc/newc,
            'log_sha256':{'replay':h0,'cut_through':h1},'same_axi_service_policy':True,'benchmark_no_artificial_stalls':True,
            'scope':'Transport-only A/B; successful LAST remains the commit fence. Not Matrix wall utilization or full real16.',
            'whole_request_50_percent_accepted':False}
if __name__=='__main__':
    try:print(json.dumps(verify(Path(sys.argv[1])),indent=2))
    except (ValueError,OSError,KeyError,IndexError) as e:raise SystemExit('IDMA_STREAM_AUDIT_REJECTED: '+str(e))
