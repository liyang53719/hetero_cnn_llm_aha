"""Post-cleanup stdlib-only comparison of one isolated head0/M64 output."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import time

HERE=Path(__file__).resolve().parent
PLAN_SHA = None
def need(ok,why):
    if not ok:raise ValueError(why)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def pin(path):
    raw=Path(path).read_bytes();return {'bytes':len(raw),'sha256':sha(raw)}
def verify(plan):
    for name,p in plan['inputs'].items():
        path=Path(name);before=path.stat();h=hashlib.sha256()
        with path.open('rb') as f:
            while data:=f.read(1024*1024):h.update(data)
        after=path.stat()
        need(path.resolve()==Path(p['resolved']) and before.st_size==p['bytes'] and h.hexdigest()==p['sha256'] and
          (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==
          (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns),'postcompare input drift: '+name)
def bf(w):
    e=(w>>7)&255;f=w&127;need(e!=255,'nonfinite BF16')
    x=math.ldexp(float(f if e==0 else 128+f),-133 if e==0 else e-134)
    return -x if w&0x8000 else x
def main():
    global PLAN_SHA
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True, type=Path)
    parser.add_argument('--reviewed-plan-sha256', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    PLAN_SHA = args.reviewed_plan_sha256
    start=time.monotonic();raw=args.plan.read_bytes();need(sha(raw)==PLAN_SHA,'plan changed');plan=json.loads(raw)
    run = Path(plan['run_directory'])
    launch=json.loads((run/'LAUNCH.json').read_text());actual=run/'actual'
    need(launch['isolated_component_complete_uncompared'] is True and launch['natural_exit'] is True and
      launch['cleanup_confirmed'] is True and launch['returncode']==0 and launch['failure'] is None and
      launch['all_frozen_actual_inputs_unchanged'] is True,'successful supervised component admission required')
    proof=launch['cleanup_proof'];need(proof['status']=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP' and
       proof['empty_complete_scans']==2 and proof['direct_leader_reaped'] is True and proof['direct_exit_code']==0,'cleanup proof fields')
    verify(plan)
    summary=json.loads((actual/'summary.json').read_text())
    a=(actual/'output.bf16le').read_bytes();r=Path(plan['reference_slice']).read_bytes()
    need(len(a)==len(r)==16384 and sha(a)==summary['output_sha256'],'output extent/hash')
    need(summary['output_reference_read'] is False and summary['state_oracle_available'] is False and
      summary['owner']['production_geometry'] is False and summary['terminal_count']==1,'component scope')
    av=[w[0] for w in struct.iter_unpack('<H',a)];rv=[w[0] for w in struct.iter_unpack('<H',r)]
    da=[bf(w) for w in av];dr=[bf(w) for w in rv];errors=[abs(x-y) for x,y in zip(da,dr)]
    worst=max(range(8192),key=errors.__getitem__)
    maximum=max(errors);mean=math.fsum(errors)/8192
    report={'status':'ISOLATED_HEAD0_M64_COMPARISON_COMPLETE','scope':'REAL_SAVED_PREP_HEAD0_TOKENS0_63_ONLY',
      'full_block_acceptance':False,'original_execution_status':'UNKNOWN','original_continuation':False,
      'state_numerical_validation':None,'state_oracle_available':False,'hardware_simulation':False,
      'elements':8192,'max_abs':maximum,'mean_abs':mean,'bit_mismatches':sum(x!=y for x,y in zip(av,rv)),
      'numerical_mismatches':sum(x!=y for x,y in zip(da,dr)),
      'thresholds':{'max_abs':0.03125,'mean_abs':0.005},'meets_existing_node_thresholds':maximum<=0.03125 and mean<=0.005,
      'actual_nonzero':sum(x!=0 for x in da),'reference_nonzero':sum(x!=0 for x in dr),
      'actual_max_magnitude':max(map(abs,da)),'reference_max_magnitude':max(map(abs,dr)),
      'worst_location':{'token':worst//128,'head':0,'value_column':worst%128},
      'policy':plan['policy'],'reference_mapping':'native0020 [1,128,16,128], concatenate token0..63/head0/128 values',
      'mean_reduction':'binary64 absolute deltas, stdlib math.fsum/count; no NumPy reduction-bit identity claim',
      'plan_sha256':PLAN_SHA,'output_pin':pin(actual/'output.bf16le'),'state_unvalidated_pin':pin(actual/'state.fp32le'),
      'reference_slice_pin':pin(plan['reference_slice']),'summary_pin':pin(actual/'summary.json'),
      'supervisor_pin':pin(run/'LAUNCH.json'),'cleanup_pin':pin(run/'CLEANUP.json'),
      'comparison_script_pin':pin(__file__),'source_pin_count':len(plan['inputs']),
      'candidate_elapsed_seconds':summary['elapsed_seconds'],'supervisor_elapsed_seconds':launch['elapsed_seconds'],
      'supervisor_peak_sampled_rss_bytes':launch['observed_peak_rss_bytes'],'owned_cleanup_confirmed':True}
    verify(plan);need(pin(actual/'output.bf16le')==report['output_pin'] and pin(plan['reference_slice'])==report['reference_slice_pin'],'comparison source changed')
    report['before_after_pins_match']=True;report['comparison_elapsed_seconds']=time.monotonic()-start
    with args.output.open('x') as f:json.dump(report,f,sort_keys=True,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps(report,sort_keys=True,allow_nan=False))
if __name__=='__main__':main()
