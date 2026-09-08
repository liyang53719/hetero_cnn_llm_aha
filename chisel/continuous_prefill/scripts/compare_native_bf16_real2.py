#!/usr/bin/env python3
"""Same-request native-weight comparison. Never promote partial/active-only MAC rates."""
import argparse, hashlib, json, math, struct
from pathlib import Path
from verify_host_block_gate import verify
from verify_real_two_layer import fixed_contract,compare_all
from audit_owner_block_abi import audit
from compare_matrix4096_real2 import metrics

def require(ok,msg):
    if not ok:raise ValueError(msg)

def compare(current,baseline):
    outputs=[];reports=[];manifests=[]
    for d in (baseline,current):
        require((d/'gate.exit').read_text().strip()=='0','unfinished numerical execution')
        m=json.loads((d/'fixture/manifest.json').read_text());fixed_contract(m)
        r=verify(d,False);audit(d);require(compare_all(d,m)==1409024,'incomplete output comparison')
        reports.append(r);manifests.append(m)
    old,new=manifests
    require(old.get('weight_storage','fp32')=='fp32' and new.get('weight_storage')=='bf16','storage comparison order')
    require(old['schedule']==new['schedule'] and old['allocations']==new['allocations'],'different command graph')
    weights={o['b'] for o in old['schedule'] if o['opcode']=='MATRIX_GEMM'}
    for name,t in old['tensors'].items():
        actual=dict(new['tensors'][name]);actual.pop('storage_dtype',None);actual.pop('storage_bytes',None)
        require(actual==t,'tensor shape/address change')
    for name in ['input_x.f32le','host_commands.bin']+[n+'_actual.f32le' for o in old['schedule'] for n in o['outputs']]:
        a=(baseline/'tensors'/name).read_bytes();b=(current/'tensors'/name).read_bytes()
        require(a==b,'actual output changed: '+name)
        outputs.append({'file':name,'bytes':len(a),'sha256':hashlib.sha256(b).hexdigest()})
    m=[metrics(r['counters'],4096) for r in reports]
    expected_saved=sum(t['words']*2 for n,t in old['tensors'].items() if n in weights)
    require(expected_saved==187170816,'wrong two-layer weight work')
    require(m[0]['ddr_read_bytes']-m[1]['ddr_read_bytes']==expected_saved,'native weights did not halve actual weight traffic')
    require(m[0]['useful_macs']==m[1]['useful_macs']==1498202112,'useful work changed')
    require(m[0]['ddr_write_ack_bytes']==m[1]['ddr_write_ack_bytes']==5636096,'output coverage changed')
    return {'status':'PASS_NATIVE_BF16_REAL16_TWO_LAYER_NUMERICAL','tokens':16,'layers':2,'checked_fp32':1409024,
        'bit_differences':0,'baseline':m[0],'optimized':m[1],'speedup':m[0]['cycles']/m[1]['cycles'],
        'actual_weight_bytes_saved':expected_saved,'whole_request_target':0.5,
        'performance_accepted':m[1]['useful_wall_mac_utilization']>=0.5,'compared_files':outputs,
        'scope':{'whole_request_cycles':True,'synthetic_weights':True,'host_commands':42,'original_idma':True,
                 'preloaded_weights_excluded_from_timing':False,'official_weights':False,'dc':False}}

if __name__=='__main__':
    a=argparse.ArgumentParser(description=__doc__);a.add_argument('--current',type=Path,required=True);a.add_argument('--baseline',type=Path,required=True);a.add_argument('--output',type=Path,required=True);x=a.parse_args()
    try:
        require(not x.output.exists(),'preserve report');r=compare(x.current,x.baseline)
        with x.output.open('x') as f:json.dump(r,f,indent=2,allow_nan=False);f.write('\n')
        print(json.dumps(r,indent=2,allow_nan=False))
        # Numerical acceptance and the user's 50% performance acceptance are
        # separate. A functional PASS never silently lowers the target.
        if not r['performance_accepted']:raise SystemExit(3)
    except (ValueError,KeyError,TypeError,OSError) as e:raise SystemExit('NATIVE_REAL2_REJECTED: '+str(e))
