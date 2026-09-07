#!/usr/bin/env python3
"""Recheck arithmetic service intervals, not Host/model performance.

Closed-form dyadic sums independently check all values. Zero explicit testbench
stall does not mean an II=1 engine: reported periods include the adapter's own
request/reply protocol and retained arithmetic. No target period is assumed.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,re,struct
from pathlib import Path


def require(ok,message):
    if not ok:raise ValueError(message)


def fields(line):
    pairs=re.findall(r'(\w+)=([^\s]+)',line)
    require(len(pairs)==len(dict(pairs)),'duplicate counter field')
    return dict(pairs)


def check(root):
    require((root/'simulation.exit').read_text().strip()=='0','unsuccessful simulation')
    log=(root/'run.log').read_text()
    require(not re.search(r'MATRIX_SERVICE_FAIL|%Error|\bFatal\b',log),'error in log')
    cases=[fields(s) for s in log.splitlines() if s.startswith('MATRIX_SERVICE_CASE ')]
    final=[fields(s) for s in log.splitlines() if s.startswith('MATRIX_SERVICE_PASS ')]
    require(len(cases)==2 and len(final)==1,'incomplete diagnostic receipt')
    require(final[0]==dict(checked_fp32='1048576',bit_differences='0',actual_slice_steps='1152',physical_slices='8',host_idma='0',full_model='0'),'wrong diagnostic scope')
    results=[]
    for mask,case in zip((255,1),cases):
        for k,v in dict(mask=mask,depth=128,checked_fp32=524288,steady_samples=126,active_macs_per_step=mask.bit_count()*512,explicit_result_hold_cycles=0,explicit_inter_request_delay=0).items():
            require(case.get(k)==str(v),'counter mismatch '+k)
        for k in ('cycles','steady_period_min','steady_period_max'):
            require(re.fullmatch('[0-9]+',case.get(k,'')) is not None and int(case[k])>0,'invalid cycles')
        period=int(case['steady_period_min'])
        require(period==int(case['steady_period_max']) and int(case['cycles'])>=126*period,'inconsistent service timing')
        results.append({'slice_mask':mask,'active_macs_per_step':mask.bit_count()*512,
            'steady_service_period_cycles':period,'steady_samples':126,'dot_cycles':int(case['cycles']),
            'steady_executed_macs_per_cycle':mask.bit_count()*512/period,
            'steady_fraction_of_installed_4096_capacity':mask.bit_count()*512/(period*4096)})
    raw=(root/'outputs/actual.f32le').read_bytes();ref=(root/'outputs/reference.f32le').read_bytes()
    require(len(raw)==len(ref)==1048576*4 and raw==ref,'binary output incomplete or mismatched')
    count=0
    with (root/'outputs/all_elements.csv').open(newline='') as stream:
        rows=csv.reader(stream)
        require(next(rows,None)==['request','mask','row','column','actual_hex','reference_hex'],'CSV header')
        for request in range(256):
            mask=255 if request<128 else 1;k=request%128
            for r in range(16):
                for c in range(256):
                    numerator=(c-128)*((k+1)*(r+1)+k*(k+1)//2)
                    expected=struct.unpack('<I',struct.pack('<f',numerator/4096.0 if mask&(1<<(c//32)) else 0.0))[0]
                    actual=struct.unpack_from('<I',raw,count*4)[0]
                    require(actual==expected,'independent dyadic sum mismatch')
                    require(next(rows,None)==[str(request),str(mask),str(r),str(c),f'{actual:08x}',f'{expected:08x}'],'CSV identity/value mismatch')
                    count+=1
        require(next(rows,None) is None,'extra CSV row')
    require(count==1048576,'incomplete output count')
    return {'status':'PASS_ACTUAL_MATRIX4096_SERVICE_DIAGNOSTIC','checked_fp32':count,'bit_differences':0,
        'physical_slices':8,'cases':results,'clock_target_hz':800000000,
        'scope':{'actual_eight_slice_arithmetic':True,'explicit_testbench_backpressure':False,
                 'host_idma_included':False,'model_inference':False,'physical_timing_signoff':False},
        'sha256':{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [root/'run.log',root/'outputs/actual.f32le',root/'outputs/reference.f32le',root/'outputs/all_elements.csv']}}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    try:
        require(not a.output.exists() and not a.output.is_symlink(),'preserve existing evidence')
        result=check(a.root.resolve());text=json.dumps(result,indent=2,allow_nan=False)+'\n'
        with a.output.open('x') as f:f.write(text)
        print(text,end='')
    except (ValueError,OSError,KeyError,TypeError) as error:raise SystemExit('MATRIX_SERVICE_REJECTED: '+str(error))
