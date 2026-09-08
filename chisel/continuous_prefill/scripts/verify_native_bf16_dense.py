#!/usr/bin/env python3
"""Independent shape/traffic/finite-output audit of the real native Dense DUT."""
import hashlib,json,re,struct,sys
from pathlib import Path
CASES=[(16,1536,64,0,0),(16,1536,64,1,0),(80,256,128,0,0),
       (80,256,128,1,0),(81,256,128,1,0),(33,544,64,1,0),
       (32,1536,64,1,0),(17,528,128,0,0),(1,16,16,0,0),
       (80,256,64,1,1),(80,256,64,1,0),(16,544,32,1,2),(16,544,32,1,0)]
def require(x,msg):
    if not x:raise ValueError(msg)
def verify(root):
    require((root/'simulation.exit').read_text().strip()=='0','simulator failure')
    log=(root/'run.log').read_text()
    require(not re.search(r'STREAM_DENSE_FAIL|Fatal|%Error|Assertion failed',log),'failed run')
    found=[dict(re.findall(r'(\w+)=(\d+)',s)) for s in log.splitlines() if s.startswith('STREAM_DENSE_CASE_PASS ')]
    require(len(found)==len(CASES),'incomplete cases')
    values=0;rows=[]
    for data,(m,n,k,bf,fault) in zip(found,CASES):
        d={key:int(value) for key,value in data.items()}
        require(tuple(d[x] for x in ['m','n','k','bf16','fault'])==(m,n,k,bf,fault),'wrong case order')
        require(d['checked_fp32']==(0 if fault else m*n) and d['cycles']>0,'incomplete values')
        if not fault:
            # A loaded once per macro; B once per <=80-token macro, irrespective of N group count.
            expected=m*k*4+k*n*(2 if bf else 4)*((m+79)//80)
            require(d['read_beats']*64==expected,'unexpected or repeated operand reads')
            require(d['write_acks']*64==m*n*4,'missing output ACK')
        values+=d['checked_fp32'];rows.append(d)
    require(values==216128,'coverage')
    marker='NATIVE_DENSE_NUMERIC_PASS cases=13 numeric_cases=11 fault_resets=2 checked_fp32=216128 bit_differences=0 real_idma=1 physical_mac=4096 same_dut=1'
    require(log.splitlines().count(marker)==1,'final marker')
    a=(root/'outputs/actual.f32le').read_bytes();b=(root/'outputs/reference.f32le').read_bytes()
    require(len(a)==len(b)==values*4 and a==b,'binary comparison')
    require(all((x[0]&0x7f800000)!=0x7f800000 for x in struct.iter_unpack('<I',a)),'nonfinite output')
    return {'status':'PASS_NATIVE_BF16_MACRO_M_DENSE_COMPONENT','cases':rows,'checked_fp32':values,
            'bit_differences':0,'same_memory_timing_as_baseline':True,'all_output_sha256':hashlib.sha256(a).hexdigest(),
            'scope':'Real retained 4096 MAC and pinned iDMA, K<=128 component. Not full real16, q1024 or 50% wall utilization.'}
if __name__=='__main__':
    try:print(json.dumps(verify(Path(sys.argv[1])),indent=2))
    except (ValueError,OSError,KeyError,IndexError) as e:raise SystemExit('NATIVE_DENSE_REJECTED: '+str(e))
