import argparse, hashlib, json, math, re
from pathlib import Path
EXPECTED='17646e6a6b6ec2f50fe550830c3f2184a4261df662ecaa35b92c68d521c541a6'
STAGES=['prepare_programs_inputs_only','P0_provider','P0_transport','P1_provider','P2_provider','P3_provider','P4_provider']
RSS='INCOMPLETE_SINGLE_OR_EARLY_SAMPLES_NOT_PEAK_COVERAGE'
def need(v):
    if not v: raise ValueError('invalid measurement')
def sha(v):
    need(isinstance(v,str) and re.fullmatch('[0-9a-f]{64}',v)); return v
def num(v, maximum=10**12):
    need(type(v) in (int,float) and math.isfinite(v) and 0<=v<=maximum); return v
def extract(raw):
    need(len(raw)<=65536 and hashlib.sha256(raw).hexdigest()==EXPECTED)
    x=json.loads(raw); need(x['overall_native_exit']==0)
    need([s['stage'] for s in x['stages']]==STAGES)
    stages=[]
    for s in x['stages']:
        need(s['native_exit']==0 and s['errors']==[] and s['cleanup_complete'] is True)
        need(s['process_sample_count']==1 and s['process_sample_max_gap_seconds'] is None and s['rss_qualification']==RSS)
        stages.append(dict(stage=s['stage'],receipt_sha256=sha(s['receipt_sha256']),native_exit=0,cleanup_complete=True,
            elapsed_seconds=num(s['elapsed_seconds']),process_sample_count=1,rss_qualification=RSS,
            observed_rss_sample_bytes=num(s['observed_peak_rss']),disk_census_max_seconds=num(s['disk_census_max_seconds'])))
    need([p['profile'] for p in x['profiles']]==list(range(5)))
    profiles=[]
    for p in x['profiles']:
        need(p['tokens']==128 and p['hardware_executed'] is False)
        profiles.append(dict(profile=p['profile'],tokens=128,receipt_sha256=sha(p['receipt_sha256']),
            written_regular_bytes=num(p['written_regular_bytes']),files=num(p['files']),hardware_executed=False))
    return dict(schema='PROVIDER_ONLY_OBSERVED_MEASUREMENT_V1',source_summary_sha256=EXPECTED,
        proposal_sha256=sha(x['proposal_sha256']),source_proposal_sha256=sha(x['source_proposal_sha256']),owner_sha256=sha(x['owner_sha256']),
        scope='FIVE_FULL128_INPUT_PROVIDER_MAPPING_ONLY',whole_orchestration_wall_seconds=num(x['whole_orchestration_wall_seconds']),
        summed_stage_wall_seconds=num(x['summed_supervisor_stage_wall_seconds']),stages=stages,profiles=profiles,
        global_tree_observed_max_bytes=num(x['global_tree_observed_max_bytes']),
        resource_admission='INCOMPLETE_RSS_AND_TRANSIENT_PEAK_NOT_OBSERVED',
        existing_references='REVERIFIED_EXISTING_IDENTITIES_NOT_NEW_REFERENCE_EXECUTION',
        new_reference_execution=False,dut_execution=False,full_block_numeric_pass_count=0,
        observed_bytes_not_upper_bound=True,public_payload_included=False)
def main():
    a=argparse.ArgumentParser(); a.add_argument('--input',type=Path,required=True); a.add_argument('--output',type=Path,required=True); o=a.parse_args()
    with o.input.open('rb') as f: raw=f.read(65537)
    out=json.dumps(extract(raw),indent=2,sort_keys=True)+'\n'
    need(len(out.encode())<=16384)
    with o.output.open('x') as f: f.write(out)
if __name__=='__main__': main()
