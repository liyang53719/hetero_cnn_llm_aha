"""Post-cleanup stdlib-only comparison of one bounded isolated head0 or all16 output."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import struct
import time

# -I omits the script directory; admit only this pinned helper directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from chunk_case import case, plan_case, validate_carry, validate_first_states

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
def state_metrics(actual, reference, heads=1):
    selected=case(128, heads);elements=selected['state_bytes']//4
    need(len(actual)==len(reference)==selected['state_bytes'],'after128 state extent')
    values=[x[0] for x in struct.iter_unpack('<f',actual)]
    refs=[x[0] for x in struct.iter_unpack('<f',reference)]
    need(all(math.isfinite(x) for x in values+refs),'nonfinite after128 state')
    errors=[abs(x-y) for x,y in zip(values,refs)]
    tolerances=[1e-4+1e-4*abs(y) for y in refs]
    worst=max(range(elements),key=lambda i:errors[i]/tolerances[i])
    return {'elements':elements,'max_abs':max(errors),'mean_abs':math.fsum(errors)/elements,
      'bit_mismatches':sum(x!=y for x,y in zip(struct.iter_unpack('<I',actual),struct.iter_unpack('<I',reference))),
      'violations':sum(e>t for e,t in zip(errors,tolerances)),'atol':1e-4,'rtol':1e-4,
      'meets_existing_state_threshold':all(e<=t for e,t in zip(errors,tolerances)),
      'max_error_over_tolerance':errors[worst]/tolerances[worst],
      'worst_normalized_location':{'head':worst//16384,'key_row':(worst//128)%128,'value_column':worst%128},
      'actual_nonzero':sum(x!=0 for x in values),'reference_nonzero':sum(x!=0 for x in refs)}


def main():
    global PLAN_SHA
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True, type=Path)
    parser.add_argument('--reviewed-plan-sha256', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    PLAN_SHA = args.reviewed_plan_sha256
    start=time.monotonic();raw=args.plan.read_bytes();need(sha(raw)==PLAN_SHA,'plan changed');plan=json.loads(raw)
    selected=plan_case(plan);tokens=selected['tokens'];heads=selected['heads'];elements=selected['elements'];label=selected['label'].upper()
    run = Path(plan['run_directory'])
    launch=json.loads((run/'LAUNCH.json').read_text());actual=run/'actual'
    need(launch['isolated_component_complete_uncompared'] is True and launch['natural_exit'] is True and
      launch['cleanup_confirmed'] is True and launch['returncode']==0 and launch['failure'] is None and
      launch['all_frozen_actual_inputs_unchanged'] is True,'successful supervised component admission required')
    need(launch['plan_sha256']==PLAN_SHA,'supervisor plan identity')
    proof=launch['cleanup_proof'];need(proof['status']=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP' and
       proof['empty_complete_scans']==2 and proof['direct_leader_reaped'] is True and proof['direct_exit_code']==0,'cleanup proof fields')
    verify(plan)
    summary=json.loads((actual/'summary.json').read_text())
    a=(actual/'output.bf16le').read_bytes();r=Path(plan['reference_slice']).read_bytes()
    need(len(a)==len(r)==elements*2 and sha(a)==summary['output_sha256'],'output extent/hash')
    need(summary['output_reference_read'] is False and summary['state_oracle_available'] is selected['state_oracle'] and
      summary['owner']['production_geometry'] is (heads==16) and summary['terminal_count']==1,'component scope')
    av=[w[0] for w in struct.iter_unpack('<H',a)];rv=[w[0] for w in struct.iter_unpack('<H',r)]
    da=[bf(w) for w in av];dr=[bf(w) for w in rv];errors=[abs(x-y) for x,y in zip(da,dr)]
    worst=max(range(elements),key=errors.__getitem__)
    maximum=max(errors);mean=math.fsum(errors)/elements
    report={'status':f'ISOLATED_{label}_M{tokens}_COMPARISON_COMPLETE','scope':f'REAL_SAVED_PREP_{label}_TOKENS0_{tokens-1}_ONLY',
      'full_block_acceptance':False,'original_execution_status':'UNKNOWN','original_continuation':False,
      'state_numerical_validation':None,'state_oracle_available':selected['state_oracle'],'hardware_simulation':False,
      'elements':elements,'max_abs':maximum,'mean_abs':mean,'bit_mismatches':sum(x!=y for x,y in zip(av,rv)),
      'numerical_mismatches':sum(x!=y for x,y in zip(da,dr)),
      'thresholds':{'max_abs':0.03125,'mean_abs':0.005},'meets_existing_node_thresholds':maximum<=0.03125 and mean<=0.005,
      'actual_nonzero':sum(x!=0 for x in da),'reference_nonzero':sum(x!=0 for x in dr),
      'actual_max_magnitude':max(map(abs,da)),'reference_max_magnitude':max(map(abs,dr)),
      'worst_location':{'token':worst//(heads*128),'head':(worst//128)%heads,'value_column':worst%128},
      'policy':plan['policy'],'reference_mapping':('native0020 [1,128,16,128], exact full contiguous tensor' if heads==16 else
          f'native0020 [1,128,16,128], concatenate token0..{tokens-1}/head0/128 values'),
      'mean_reduction':'binary64 absolute deltas, stdlib math.fsum/count; no NumPy reduction-bit identity claim',
      'plan_sha256':PLAN_SHA,'output_pin':pin(actual/'output.bf16le'),'state_unvalidated_pin':pin(actual/'state.fp32le'),
      'reference_slice_pin':pin(plan['reference_slice']),'summary_pin':pin(actual/'summary.json'),
      'supervisor_pin':pin(run/'LAUNCH.json'),'cleanup_pin':pin(run/'CLEANUP.json'),
      'comparison_script_pin':pin(__file__),'source_pin_count':len(plan['inputs']),
      'candidate_elapsed_seconds':summary['elapsed_seconds'],'supervisor_elapsed_seconds':launch['elapsed_seconds'],
      'supervisor_peak_sampled_rss_bytes':launch['observed_peak_rss_bytes'],'owned_cleanup_confirmed':True}
    if selected['state_oracle']:
        state=(actual/'state.fp32le').read_bytes();reference_state=Path(plan['reference_state_slice']).read_bytes()
        need(sha(state)==summary['state_sha256'],'after128 state hash')
        validate_carry(summary['actual_chunks_completed'],summary['observed_second_chunk_prior_state_read_beats'],heads)
        validate_first_states(summary['first_chunk_state_sha256'],heads)
        report.update(state_numerical_validation=state_metrics(state,reference_state,heads),
            state_pin=report.pop('state_unvalidated_pin'),reference_state_pin=pin(plan['reference_state_slice']),
            state_reference_mapping=('native0021 [1,16,128,128] FP32 after128, full contiguous state, identical official final cache0043' if heads==16 else
                'native0021 [1,16,128,128] FP32 after128, head0 first65536 bytes, identical official final cache0043'),
            actual_chunks_completed=summary['actual_chunks_completed'],
            observed_second_chunk_prior_state_read_beats=summary['observed_second_chunk_prior_state_read_beats'],
            first_chunk_actual_state_sha256=summary['first_chunk_state_sha256'],after64_state_oracle_available=False)
    verify(plan)
    if selected['state_oracle']:
        need(pin(actual/'state.fp32le')==report['state_pin'] and
             pin(plan['reference_state_slice'])==report['reference_state_pin'],'state comparison source changed')
    need(pin(actual/'output.bf16le')==report['output_pin'] and pin(plan['reference_slice'])==report['reference_slice_pin'],'comparison source changed')
    report['before_after_pins_match']=True;report['comparison_elapsed_seconds']=time.monotonic()-start
    with args.output.open('x') as f:json.dump(report,f,sort_keys=True,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps(report,sort_keys=True,allow_nan=False))
if __name__=='__main__':main()
